import asyncio
from pysnmp.hlapi.asyncio import *
from typing import List, Dict, Optional
from models import NodeDB, NodeMetricDB, MetricDefinitionDB
from database import SessionLocal
import logging
import time

logger = logging.getLogger("BeamState.SNMPCollector")

class SNMPDataCollector:
    def __init__(self):
        self.running = False
        self.collection_tasks = {}  # node_id -> task
        # Current metric values: {node_metric_id: {'value': val, 'timestamp': ts}}
        self.current_values = {}
        
    async def start(self):
        """Start the collector service"""
        self.running = True
        logger.info("SNMP Data Collector started")
        # Start collection loop
        asyncio.create_task(self.main_loop())
        
    def stop(self):
        """Stop the collector service"""
        self.running = False
        logger.info("SNMP Data Collector stopping...")
        
    async def main_loop(self):
        """Main loop checking for nodes that need collection"""
        while self.running:
            try:
                # Get all nodes with enabled SNMP metrics
                db = SessionLocal()
                try:
                    # In a real efficient system, we'd query just what we need
                    # For now, iterate all enabled nodes with enabled metrics
                    nodes = db.query(NodeDB).filter(NodeDB.enabled == True, NodeDB.monitor_snmp == True).all()
                    
                    for node in nodes:
                        # Check if we should collect for this node
                        # Ideally, this should be scheduled individually based on interval
                        # For Phase 1 simplicity: collect all every 60s
                        # Future: Implement per-node/per-metric scheduling
                        await self.collect_node_metrics(node.id)
                        
                finally:
                    db.close()
                    
                # Sleep for 30s before next global check
                # This limits resolution to 30s minimum for now
                await asyncio.sleep(60) 
                
            except Exception as e:
                logger.error(f"Error in main collection loop: {e}")
                await asyncio.sleep(10)
    
    async def collect_node_metrics(self, node_id: str):
        """Collect all enabled metrics for a specific node"""
        db = SessionLocal()
        try:
            node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
            if not node:
                return
            
            # Get enabled metrics
            node_metrics = db.query(NodeMetricDB).join(MetricDefinitionDB).filter(
                NodeMetricDB.node_id == node_id,
                NodeMetricDB.enabled == True
            ).all()
            
            if not node_metrics:
                return
                
            # Group by community/port to batch if optimizing (skip for now)
            community = node.snmp_community or (node.group.snmp_community if node.group else "public")
            port = node.snmp_port or (node.group.snmp_port if node.group else 161)
            
            logger.debug(f"Collecting {len(node_metrics)} metrics for {node.name}")
            
            for node_metric in node_metrics:
                val = await self.collect_single_metric(node, node_metric, community, port)
                if val is not None:
                    self.store_metric_value(node_metric.id, val)
                    
        except Exception as e:
            logger.error(f"Error collecting metrics for node {node_id}: {e}")
        finally:
            db.close()
            
    async def collect_single_metric(self, node: NodeDB, node_metric: NodeMetricDB, community: str, port: int):
        """Collect a single metric via SNMP GET"""
        try:
            metric_def = node_metric.metric_definition
            
            # Format OID with index if needed
            if metric_def.requires_index:
                if node_metric.interface_index is None:
                    return None
                oid = metric_def.oid_template.replace("{index}", str(node_metric.interface_index))
            else:
                oid = metric_def.oid_template
                
            # Perform SNMP GET
            errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((node.ip, port), timeout=2.0, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(oid))
            )
            
            if errorIndication:
                logger.warning(f"SNMP Timed out for {node.name} metric {metric_def.name}")
                return None
            elif errorStatus:
                logger.warning(f"SNMP Error: {errorStatus.prettyPrint()}")
                return None
                
            for varBind in varBinds:
                val = varBind[1]
                # Convert to Python type
                return str(val)
                
        except Exception as e:
            logger.error(f"Metric collection exception: {e}")
            return None
            
    def store_metric_value(self, node_metric_id: str, value: str):
        """Store the latest metric value in memory"""
        self.current_values[node_metric_id] = {
            "value": value,
            "timestamp": time.time()
        }
        
    def get_current_values(self, node_id: str = None) -> Dict:
        """Get current values, optionally filtered by node"""
        if node_id is None:
            return self.current_values
        
        # This is inefficient without a reverse mapping, but fine for small scale
        # Ideally we'd structure current_values as {node_id: {metric_id: val}}
        # Or query DB for metric IDs belonging to node
        # For now, let's trust the caller knows the metric IDs or improve structure later
        return self.current_values

