from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from database import get_db
from models import MetricDefinition, MetricDefinitionDB, NodeMetric, NodeMetricCreate, NodeMetricDB, NodeDB, NodeInterface, NodeInterfaceDB, NodeInterfaceBase
# Note: pysnmp imports are done inside _sync_discover_interfaces to avoid async/sync conflicts
import uuid
import logging
import asyncio

logger = logging.getLogger("BeamState.Metrics")

router = APIRouter(prefix="/metrics", tags=["metrics"])

print("LOADING METRICS MODULE V100 - CONFIRMED")

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

@router.get("/nodes/{node_id}", response_model=List[NodeMetric])
def read_node_metrics(node_id: str, db: Session = Depends(get_db)):
    """Get all metrics configured for a node"""
    return db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node_id).all()

@router.post("/nodes/{node_id}", response_model=List[NodeMetric])
def set_node_metrics(node_id: str, metrics: List[NodeMetricCreate], db: Session = Depends(get_db)):
    """Set configured metrics for a node (replaces existing configuration)"""
    # Verify node exists
    node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
        
    # Delete existing metrics
    db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node_id).delete()
    
    new_metrics = []
    for m in metrics:
        metric_db = NodeMetricDB(**m.model_dump())
        # Ensure ID is new
        metric_db.id = str(uuid.uuid4())
        metric_db.node_id = node_id  # Ensure node_id is set
        db.add(metric_db)
        new_metrics.append(metric_db)
        
    db.commit()
    for m in new_metrics:
        db.refresh(m)
        
    return new_metrics

# --- INTERFACE DISCOVERY ---

def _sync_discover_interfaces(ip: str, port: int, community: str) -> list:
    """Synchronous SNMP interface discovery - runs in thread pool"""
    from pysnmp.hlapi import (
        SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
        ObjectType, ObjectIdentity, nextCmd
    )
    
    interfaces = {}
    
    # helper to fetch a column
    def fetch_column(oid_base, key_name):
        for errorIndication, errorStatus, errorIndex, varBinds in nextCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),  # v2c
            UdpTransportTarget((ip, port), timeout=2.0, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid_base)),
            lexicographicMode=False
        ):
            if errorIndication or errorStatus:
                continue # Skip errors for secondary columns to be safe
            
            for varBind in varBinds:
                oid = varBind[0]
                val = varBind[1]
                try:
                    idx = int(oid[-1])
                    if idx not in interfaces:
                        interfaces[idx] = {"index": idx}
                    interfaces[idx][key_name] = val.prettyPrint()
                except:
                    pass

    # 1. Fetch ifDescr (Base)
    fetch_column('1.3.6.1.2.1.2.2.1.2', 'name')
    
    # 2. Fetch ifType
    fetch_column('1.3.6.1.2.1.2.2.1.3', 'type')
    
    # 3. Fetch ifPhysAddress
    fetch_column('1.3.6.1.2.1.2.2.1.6', 'mac_address')
    
    # 4. Fetch ifAdminStatus
    fetch_column('1.3.6.1.2.1.2.2.1.7', 'admin_status')
    
    # 5. Fetch ifOperStatus
    fetch_column('1.3.6.1.2.1.2.2.1.8', 'oper_status')
    
    # Convert dict to list
    result_list = sorted(interfaces.values(), key=lambda x: x["index"])
    return result_list


@router.get("/discover-interfaces/{node_id}", response_model=List[NodeInterface])
async def discover_interfaces(node_id: str, db: Session = Depends(get_db)):
    """Perform SNMP walk to discover interfaces on a node"""
    print(f"=== DISCOVERY ENDPOINT HIT: {node_id} ===")
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
        print(f"=== CALLING SYNC DISCOVERY: {node.ip}:{port} ===")

        # Run synchronous SNMP in thread pool to avoid asyncio issues
        loop = asyncio.get_event_loop()
        interfaces = await loop.run_in_executor(
            None,  # Default executor
            _sync_discover_interfaces,
            node.ip, port, community
        )
        print(f"=== DISCOVERY SUCCESS: {len(interfaces)} interfaces ===")
        
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
        print(f"=== DISCOVERY EXCEPTION: {e} ===")
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
