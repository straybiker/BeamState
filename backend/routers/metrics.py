from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from database import get_db
from models import MetricDefinition, MetricDefinitionDB, NodeMetric, NodeMetricCreate, NodeMetricDB, NodeDB, NodeInterface, NodeInterfaceDB, NodeInterfaceBase
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, walk_cmd,
)
import uuid
import logging

logger = logging.getLogger("BeamState.Metrics")

router = APIRouter(prefix="/metrics", tags=["metrics"])


# --- METRIC DEFINITIONS ---

@router.get("/definitions", response_model=List[MetricDefinition])
def read_metric_definitions(
    device_type: Optional[str] = None, 
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(MetricDefinitionDB)
    
    if device_type:
        query = query.filter(MetricDefinitionDB.device_type == device_type)
        
    if search:
        query = query.filter(MetricDefinitionDB.name.contains(search))
        
    return query.all()

# --- NODE METRICS Configuration ---

@router.get("/nodes", response_model=List[NodeMetric])
def read_all_node_metrics(db: Session = Depends(get_db)):
    """Get configured metrics for every node in one call (dashboard bootstrap)"""
    return db.query(NodeMetricDB).all()

@router.get("/nodes/{node_id}", response_model=List[NodeMetric])
def read_node_metrics(node_id: str, db: Session = Depends(get_db)):
    """Get all metrics configured for a node"""
    return db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node_id).all()

UPDATABLE_METRIC_FIELDS = (
    "interface_name", "collection_interval", "warning_threshold", "critical_threshold",
    "alert_enabled", "alert_condition", "alert_min_samples", "enabled",
)


def _metric_key(definition_id: str, interface_index) -> tuple:
    return (definition_id, interface_index)


@router.post("/nodes/{node_id}", response_model=List[NodeMetric])
def set_node_metrics(node_id: str, metrics: List[NodeMetricCreate], request: Request, db: Session = Depends(get_db)):
    """
    Set the configured metrics for a node.

    Rows are matched on (metric definition, interface index) and updated in
    place, so their IDs stay stable and history, rates and alert state survive
    edits to other metrics. Rows missing from the payload are removed.
    """
    node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    existing = {
        _metric_key(m.metric_definition_id, m.interface_index): m
        for m in db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node_id).all()
    }

    kept = []
    seen = set()
    for m in metrics:
        key = _metric_key(m.metric_definition_id, m.interface_index)
        if key in seen:
            continue  # duplicate in payload, first one wins
        seen.add(key)

        row = existing.get(key)
        if row is None:
            row = NodeMetricDB(**m.model_dump())
            row.id = str(uuid.uuid4())
            row.node_id = node_id
            db.add(row)
        else:
            for field in UPDATABLE_METRIC_FIELDS:
                setattr(row, field, getattr(m, field))
        kept.append(row)

    removed = [row for key, row in existing.items() if key not in seen]
    for row in removed:
        db.delete(row)

    db.commit()
    for row in kept:
        db.refresh(row)

    # Drop runtime state of removed metrics so a stale alert cannot keep the node DEGRADED
    pinger = getattr(request.app.state, "pinger", None)
    if pinger and removed:
        for row in removed:
            pinger.metric_processor.alert_states.pop(row.id, None)
            pinger.metric_processor.breach_counts.pop(row.id, None)
            pinger.snmp_collector.current_values.pop(row.id, None)
        pinger.metric_processor._save_alert_states()

    return kept

# --- INTERFACE DISCOVERY ---

async def _discover_interfaces(ip: str, port: int, community: str) -> list:
    """Walk the ifTable columns over SNMP v2c and merge them per ifIndex."""
    interfaces = {}
    engine = SnmpEngine()
    target = await UdpTransportTarget.create((ip, port), timeout=2.0, retries=1)

    async def fetch_column(oid_base, key_name):
        async for errorIndication, errorStatus, errorIndex, varBinds in walk_cmd(
            engine,
            CommunityData(community, mpModel=1),  # v2c
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid_base)),
            lexicographicMode=False  # Stop at the end of this column
        ):
            if errorIndication or errorStatus:
                # Unreachable host or unsupported column: stop this walk, keep what we have
                logger.debug(f"Walk of {oid_base} on {ip} stopped: {errorIndication or errorStatus.prettyPrint()}")
                break

            for varBind in varBinds:
                oid = varBind[0]
                val = varBind[1]
                try:
                    idx = int(oid[-1])
                    if idx not in interfaces:
                        interfaces[idx] = {"index": idx}
                    interfaces[idx][key_name] = val.prettyPrint()
                except Exception:
                    pass

    try:
        await fetch_column('1.3.6.1.2.1.2.2.1.2', 'name')          # ifDescr
        await fetch_column('1.3.6.1.2.1.2.2.1.3', 'type')          # ifType
        await fetch_column('1.3.6.1.2.1.2.2.1.6', 'mac_address')   # ifPhysAddress
        await fetch_column('1.3.6.1.2.1.2.2.1.7', 'admin_status')  # ifAdminStatus
        await fetch_column('1.3.6.1.2.1.2.2.1.8', 'oper_status')   # ifOperStatus
    finally:
        engine.close_dispatcher()

    return sorted(interfaces.values(), key=lambda x: x["index"])


@router.get("/discover-interfaces/{node_id}", response_model=List[NodeInterface])
async def discover_interfaces(node_id: str, db: Session = Depends(get_db)):
    """Perform SNMP walk to discover interfaces on a node"""
    logger.info(f"Received discovery request for node {node_id}")
    
    try:
        node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        
        if not node.monitor_snmp:
            raise HTTPException(status_code=400, detail="SNMP monitoring not enabled for this node")
            
        group = node.group
        
        # SNMP parameters
        group_community = group.snmp_community if group else "public"
        community = node.snmp_community or group_community
        port = node.snmp_port if node.snmp_port else (group.snmp_port if group else 161)
        
        logger.info(f"Targeting {node.ip}:{port} with v2c, community={community}")

        interfaces = await _discover_interfaces(node.ip, port, community)
        
        # Persist interfaces to DB
        # 1. Get existing interfaces
        existing_interfaces = db.query(NodeInterfaceDB).filter(NodeInterfaceDB.node_id == node_id).all()
        existing_map = {i.index: i for i in existing_interfaces}
        
        saved_interfaces = []
        
        for iface_data in interfaces:
            idx = iface_data["index"]
            name = iface_data.get("name")
            if_type = iface_data.get("type")
            mac = iface_data.get("mac_address")
            admin_status = iface_data.get("admin_status")
            oper_status = iface_data.get("oper_status")


            if idx in existing_map:
                # Update existing
                db_iface = existing_map[idx]
                db_iface.name = name
                db_iface.type = if_type
                db_iface.mac_address = mac
                db_iface.admin_status = admin_status
                db_iface.oper_status = oper_status
                saved_interfaces.append(db_iface)
            else:
                # Create new
                new_iface = NodeInterfaceDB(
                    node_id=node_id,
                    index=idx,
                    name=name,
                    type=if_type,
                    mac_address=mac,
                    admin_status=admin_status,
                    oper_status=oper_status,
                    enabled=False # User must manually enable
                )
                db.add(new_iface)
                saved_interfaces.append(new_iface)
        
        db.commit()
        
        return saved_interfaces
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery failed: {e}")

@router.get("/interfaces/{node_id}", response_model=List[NodeInterface])
def read_node_interfaces(node_id: str, db: Session = Depends(get_db)):
    """Get stored interfaces for a node"""
    return db.query(NodeInterfaceDB).filter(NodeInterfaceDB.node_id == node_id).order_by(NodeInterfaceDB.index).all()

@router.post("/interfaces/{node_id}/config")
def update_interface_config(node_id: str, config: List[NodeInterfaceBase], db: Session = Depends(get_db)):
    """Update interface configuration (enable/disable monitoring)"""
    
    # Verify node exists
    node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
        
    logger.info(f"Processing interface config update for {node_id}")
    
    for cfg in config:
        # Find interface
        iface = db.query(NodeInterfaceDB).filter(
            NodeInterfaceDB.node_id == node_id,
            NodeInterfaceDB.index == cfg.index
        ).first()
        
        if iface:
            # Update Interface State
            iface.enabled = cfg.enabled
            iface.alias = cfg.alias
            

    try:
        db.commit()
        logger.info("Interface config committed successfully")
    except Exception as e:
        logger.error(f"Failed to commit interface config: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return db.query(NodeInterfaceDB).filter(NodeInterfaceDB.node_id == node_id).order_by(NodeInterfaceDB.index).all()

# --- DATA RETRIEVAL ---

@router.get("/history")
def get_metric_history(
    hours: float = Query(6, gt=0, le=24 * 30),
    points: int = Query(48, ge=2, le=1000),
    node_metric_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Downsampled metric history from SQLite: {node_metric_id: [[timestamp, avg_value], ...]}.
    Each series is bucketed into 'points' equal intervals over the window.
    """
    from sqlalchemy import func, cast, Integer
    from models import MetricSampleDB
    import time

    now = time.time()
    start = now - hours * 3600
    bucket = max(1.0, (hours * 3600) / points)

    bucket_expr = cast(MetricSampleDB.timestamp / bucket, Integer)
    q = (db.query(MetricSampleDB.node_metric_id, bucket_expr.label("b"), func.avg(MetricSampleDB.value))
           .filter(MetricSampleDB.timestamp >= start))
    if node_metric_id:
        q = q.filter(MetricSampleDB.node_metric_id == node_metric_id)
    rows = q.group_by(MetricSampleDB.node_metric_id, "b").order_by("b").all()

    series = {}
    for mid, b, avg in rows:
        series.setdefault(mid, []).append([round(b * bucket, 0), round(avg, 3)])
    return {"hours": hours, "bucket_seconds": bucket, "series": series}

@router.get("/current")
async def get_all_current_metrics(request: Request):
    """Get all current in-memory metric values"""
    if hasattr(request.app.state, "pinger") and hasattr(request.app.state.pinger, "snmp_collector"):
        return request.app.state.pinger.snmp_collector.get_current_values()
    return {}

@router.get("/current/{node_id}")
async def get_current_metrics(node_id: str, request: Request):
    """Get current in-memory metric values for a node"""
    if hasattr(request.app.state, "pinger") and hasattr(request.app.state.pinger, "snmp_collector"):
        collector = request.app.state.pinger.snmp_collector
        
        # Filter values for this node
        all_values = collector.get_current_values()
        
        # We need to filter by node_id.
        # Ideally, the collector would return {metric_id: value}
        # But we need to know which metrics belong to this node.
        # For simplicity, we'll return all values for now, but in future, filter.
        # OR, better: The UI knows the metric IDs for the node, so it can just pick what it needs.
        # But let's try to filter if possible.
        
        # Actually, let's just return the raw values map and let UI handle mapping
        # since we don't have easy DB access here without dependency injection to query node_metrics again
        # which would be slow for a high-frequency polling endpoint.
        
        return all_values
        
    return {}
