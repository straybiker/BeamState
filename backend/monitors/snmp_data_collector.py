import asyncio
import time
import logging
from typing import Dict, List
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, get_cmd,
)
from models import NodeDB, NodeMetricDB, MetricDefinitionDB
from database import SessionLocal

logger = logging.getLogger("BeamState.SNMPCollector")

TICK_SECONDS = 5  # Scheduler resolution


class SNMPDataCollector:
    """
    Collects configured SNMP metrics.

    Each metric is polled on its own collection_interval. Nodes are polled
    concurrently, metrics within one node sequentially against one UDP target.
    """

    def __init__(self):
        self.running = False
        # Current metric values: {node_metric_id: {'value': val, 'rate': rate, 'timestamp': ts}}
        self.current_values = {}
        # Last collection time per metric for interval scheduling
        self.last_collected: Dict[str, float] = {}
        self.metric_processor = None
        self.snmp_engine = SnmpEngine()
        self.semaphore = asyncio.Semaphore(8)
        self._task = None

    def set_processor(self, processor):
        self.metric_processor = processor

    async def start(self):
        """Start the collector service"""
        self.running = True
        logger.info("SNMP Data Collector started")
        self._task = asyncio.create_task(self.main_loop())

    def stop(self):
        """Stop the collector service"""
        self.running = False
        logger.info("SNMP Data Collector stopping...")

    @staticmethod
    def _snmp_active(node: NodeDB) -> bool:
        """True when SNMP collection applies to this node (node override, else group default)."""
        group = node.group
        if group is None or not group.enabled:
            return False
        if node.monitor_snmp is not None:
            return bool(node.monitor_snmp)
        return bool(group.monitor_snmp)

    def _due_metric_ids(self, node_metrics: List[NodeMetricDB], now: float) -> List[str]:
        due = []
        for nm in node_metrics:
            interval = max(TICK_SECONDS, int(nm.collection_interval or 60))
            if now - self.last_collected.get(nm.id, 0) >= interval:
                due.append(nm.id)
        return due

    async def main_loop(self):
        """Scheduler: every tick, collect the metrics that are due."""
        while self.running:
            started = time.time()
            try:
                db = SessionLocal()
                try:
                    nodes = [
                        n for n in db.query(NodeDB).filter(NodeDB.enabled == True).all()
                        if self._snmp_active(n)
                    ]
                    work = []
                    for node in nodes:
                        enabled_metrics = [nm for nm in node.node_metrics
                                           if nm.enabled and nm.metric_definition
                                           and (nm.metric_definition.metric_source or "snmp") == "snmp"]
                        due_ids = self._due_metric_ids(enabled_metrics, started)
                        if due_ids:
                            for mid in due_ids:
                                self.last_collected[mid] = started
                            work.append(self._collect_with_limit(node.id, due_ids))
                    if work:
                        await asyncio.gather(*work)
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Error in main collection loop: {e}")

            elapsed = time.time() - started
            await asyncio.sleep(max(1.0, TICK_SECONDS - elapsed))

    async def _collect_with_limit(self, node_id: str, metric_ids: List[str]):
        async with self.semaphore:
            await self.collect_node_metrics(node_id, metric_ids)

    async def collect_node_metrics(self, node_id: str, metric_ids: List[str] = None):
        """Collect metrics for a specific node (all enabled metrics when metric_ids is None)"""
        db = SessionLocal()
        try:
            node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
            if not node:
                return

            query = db.query(NodeMetricDB).join(MetricDefinitionDB).filter(
                NodeMetricDB.node_id == node_id,
                NodeMetricDB.enabled == True
            )
            if metric_ids is not None:
                query = query.filter(NodeMetricDB.id.in_(metric_ids))
            node_metrics = query.all()

            if not node_metrics:
                return

            community = node.snmp_community or (node.group.snmp_community if node.group else "public")
            port = node.snmp_port or (node.group.snmp_port if node.group else 161)
            target = await UdpTransportTarget.create((node.ip, port), timeout=2.0, retries=1)

            logger.debug(f"Collecting {len(node_metrics)} metrics for {node.name}")

            for node_metric in node_metrics:
                val = await self.collect_single_metric(node, node_metric, community, target)
                if val is not None:
                    await self.store_metric_value(node, node_metric, val)

        except Exception as e:
            logger.error(f"Error collecting metrics for node {node_id}: {e}")
        finally:
            db.close()

    async def collect_single_metric(self, node: NodeDB, node_metric: NodeMetricDB, community: str, target):
        """Collect a single metric via SNMP GET"""
        try:
            metric_def = node_metric.metric_definition

            if metric_def.requires_index:
                if node_metric.interface_index is None:
                    return None
                oid = metric_def.oid_template.replace("{index}", str(node_metric.interface_index))
            else:
                oid = metric_def.oid_template

            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                self.snmp_engine,
                CommunityData(community, mpModel=1),  # SNMPv2c
                target,
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
                return str(varBind[1])

        except Exception as e:
            logger.error(f"Metric collection exception: {e}")
            return None

    async def store_metric_value(self, node: NodeDB, node_metric: NodeMetricDB, value: str):
        """Store the latest metric value using MetricProcessor"""
        if not self.metric_processor:
            return
        try:
            result = await self.metric_processor.process_metric(node, node_metric, value)
            if result:
                self.current_values[node_metric.id] = result
        except Exception as e:
            logger.error(f"Error storing metric {node_metric.id}: {e}")

    def get_current_values(self, node_id: str = None) -> Dict:
        """Get current values (node filtering happens in the UI)"""
        return self.current_values
