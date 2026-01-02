import asyncio
from pysnmp.hlapi.asyncio import *
from typing import List, Dict, Optional
from models import NodeDB, NodeMetricDB, MetricDefinitionDB
from database import SessionLocal
from storage import storage
import logging
import time

logger = logging.getLogger("BeamState.SNMPCollector")

class SNMPDataCollector:
    def __init__(self):
        self.running = False
        self.collection_tasks = {}  # node_id -> task
        # Current metric values: {node_metric_id: {'value': val, 'rate': rate, 'timestamp': ts}}
        self.current_values = {}
        # Previous raw values for delta calc: {node_metric_id: {'value': val, 'timestamp': ts}}
        self.previous_values = {} 
        self.snmp_engine = SnmpEngine()        
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
                    
                # Sleep for 10s (reduced for testing responsiveness)
                await asyncio.sleep(10) 
                
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
                    # Pass the definition's metric type and unit to store_metric_value
                    await self.store_metric_value(
                        node,
                        node_metric,
                        val
                    )
                    
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
                self.snmp_engine,
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
            
    async def store_metric_value(self, node: NodeDB, node_metric: NodeMetricDB, value: str):
        """Store the latest metric value in memory, calculate rate, and persist to storage"""
        now = time.time()
        metric_def = node_metric.metric_definition
        node_metric_id = node_metric.id
        metric_type = metric_def.metric_type
        unit = metric_def.unit
        
        entry = {
            "value": value,
            "timestamp": now,
            "rate": None
        }
        
        # Value to store in InfluxDB 
        # (for counters, we prefer rate if available, otherwise raw delta or simply allow flexible query)
        # Actually, standard practice for InfluxDB: store the raw COUNTER value, let InfluxQL/Flux calculate derivative.
        # BUT, because counters reset/wrap, and we want easy querying, storing the calculated rate is often friendlier 
        # for simple dashboards. Let's store BOTH if possible, or just the useful one.
        #
        # Decision: Store the calculated RATE for counters (bps), and raw VALUE for gauges (cpu %).
        persist_value = None
        
        try:
             float_val = float(value)
             persist_value = float_val
        except:
             pass

        # Rate Calculation Logic
        if metric_type == 'counter':
            prev = self.previous_values.get(node_metric_id)
            if prev:
                try:
                    cur_val = float(value)
                    prev_val = float(prev['value'])
                    time_delta = now - prev['timestamp']
                    
                    if time_delta > 0:
                        val_delta = cur_val - prev_val
                        # Handle Wrap-around (simple 32/64 bit detection or just ignore negative)
                        if val_delta >= 0:
                            # Formula for Bytes -> Bits/sec
                            if unit == 'bytes':
                                rate = (val_delta * 8) / time_delta
                            else:
                                rate = val_delta / time_delta
                            
                            entry['rate'] = rate
                            persist_value = rate # For counters, we often care about the rate
                            
                except (ValueError, TypeError):
                    pass
            
            # Update previous value store
            self.previous_values[node_metric_id] = {
                "value": value,
                "timestamp": now
            }
            
        self.current_values[node_metric_id] = entry
        
        # Persist to InfluxDB
        if persist_value is not None:
             # Add interface name to metric name if applicable for clarity? 
             # Or keep generic metric name and use tag? Tag is better.
             # e.g. metric="Traffic In", interface="eth0"
             
             await storage.write_snmp_metric(
                 node_name=node.name,
                 ip=node.ip,
                 group_name=node.group.name if node.group else "global",
                 metric_name=metric_def.name,
                 value=persist_value,
                 unit=unit if metric_type != 'counter' or unit != 'bytes' else 'bps', # Change unit to bps if rate
                 interface=node_metric.interface_name,
                 metric_type=metric_type
             )
        
    def get_current_values(self, node_id: str = None) -> Dict:
        """Get current values, optionally filtered by node"""
        if node_id is None:
            return self.current_values
        return self.current_values

