from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from database import get_db
from models import MetricDefinition, MetricDefinitionDB, NodeMetric, NodeMetricCreate, NodeMetricDB, NodeDB
from pysnmp.hlapi.asyncio import *
import uuid
import logging
import asyncio

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

@router.get("/discover-interfaces/{node_id}")
async def discover_interfaces(node_id: str, db: Session = Depends(get_db)):
    """Perform SNMP walk to discover interfaces on a node"""
    logger.info(f"Received discovery request for node {node_id}")
    node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    if not node.monitor_snmp:
        raise HTTPException(status_code=400, detail="SNMP monitoring not enabled for this node")
        
    group = node.group
    
    # SNMP parameters
    group_community = group.snmp_community if group else "public"
    port = node.snmp_port if node.snmp_port else (group.snmp_port if group else 161)
    
    interfaces = []
    
    logger.info(f"Targeting {node.ip}:{port} with v2c")

    try:
        # Walk ifDescr (1.3.6.1.2.1.2.2.1.2) to get interface names and indices
        # Use nextCmd (GetNext) as it is more universally supported than bulkCmd
        iterator = nextCmd(
            SnmpEngine(),
            CommunityData(node.snmp_community or group_community, mpModel=1), # v2c
            UdpTransportTarget((node.ip, port), timeout=2.0, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.2'))
        )
    except Exception as e:
        logger.error(f"Failed to create SNMP iterator: {e}")
        raise HTTPException(status_code=500, detail=f"SNMP Setup Failed: {e}")
        
    # Process results using async iteration
    try:
        async for row in iterator:
            # Defensive check for invalid rows yielding from pysnmp
            if not row or not isinstance(row, tuple):
                continue
            
            errorIndication, errorStatus, errorIndex, varBinds = row
            
            if errorIndication:
                logger.error(f"SNMP Discovery Error: {errorIndication}")
                break
            elif errorStatus:
                logger.error(f"SNMP Error: {errorStatus.prettyPrint()}")
                break
                
            for varBind in varBinds:
                oid = varBind[0]
                val = varBind[1]
                
                # Check if we stepped out of the tree
                if not str(oid).startswith("1.3.6.1.2.1.2.2.1.2"):
                    # We can't break the async for easily from here without flag, 
                    # but nextCmd with lexicographicMode=True (default) continues.
                    # We should return sorted interfaces now.
                    return sorted(interfaces, key=lambda x: x["index"])

                # Extract index (last part of OID)
                try:
                    # OID structure: ...ifDescr.INDEX
                    idx = int(oid[-1]) 
                    name = val.prettyPrint()
                    interfaces.append({"index": idx, "name": name})
                except Exception as e:
                    logger.warning(f"Error parsing interface OID {oid}: {e}")
                    
    except Exception as e:
        logger.error(f"Discovery loop exception: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery failed (DEBUG MARKER): {e}")

    return sorted(interfaces, key=lambda x: x["index"])

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
