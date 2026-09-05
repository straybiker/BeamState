import asyncio
import logging
import time
from typing import Dict, List, Optional
import httpx
from database import SessionLocal
from models import NodeDB, GroupDB
from storage import storage
from monitors import PingMonitor, SNMPMonitor, MonitorResult
from monitors.snmp_data_collector import SNMPDataCollector
from notifications import Notifier
from metrics_processor import MetricProcessor
from broadcast import status_stream
from models import MetricDefinitionDB, NodeMetricDB
from trace_manager import trace_manager, TraceEvent

logger = logging.getLogger("BeamState.MonitorManager")

# Node status vocabulary
#   UP        reachable, no metric alert
#   DEGRADED  reachable, at least one metric in WARNING or CRITICAL
#   PENDING   a reachability check failed, retrying
#   DOWN      retries exhausted
#   PAUSED    monitoring disabled for node or group


def _format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class MonitorManager:
    def __init__(self):
        self.running = False
        self.last_ping_time: Dict[str, float] = {} # node_id -> timestamp
        self.latest_results: Dict[str, dict] = {} # node_id -> {status, latency, packet_loss, timestamp}
        self.node_states: Dict[str, dict] = {} # node_id -> {status, failure_count, first_failure_time, ...}

        # Concurrency limit for Windows (SelectorEventLoop 64 FD limit)
        self.semaphore = asyncio.Semaphore(32)

        # Initialize monitors
        self.ping_monitor = PingMonitor()
        self.snmp_monitor = SNMPMonitor()
        self.snmp_collector = SNMPDataCollector()

        # Notifications: one facade for every channel
        self.notifier = Notifier(storage)
        self.metric_processor = MetricProcessor(self.notifier)

        # Inject processor into collector
        self.snmp_collector.set_processor(self.metric_processor)

        # Throttling state
        self.alert_history: List[float] = [] # timestamps of recent alerts
        self.last_storm_alert_time = 0

        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None

    def remove_node(self, node_id: str):
        self.latest_results.pop(node_id, None)
        self.last_ping_time.pop(node_id, None)
        self.node_states.pop(node_id, None)
        logger.info(f"Removed node {node_id} from monitor cache")

    def get_node_state(self, node_id: str) -> dict:
        if node_id not in self.node_states:
            self.node_states[node_id] = {
                "status": "UP",
                "failure_count": 0,
                "first_failure_time": 0,
                "down_since": 0,
                "down_alert_sent": False,
            }
        return self.node_states[node_id]

    def trigger_immediate_check(self, node_id: str):
        """Trigger an immediate check for a specific node (e.g., when unpausing)"""
        # Reset the last ping time to 0 to force immediate check on next loop iteration
        self.last_ping_time[node_id] = 0
        logger.info(f"Triggered immediate check for node {node_id}")

    def set_paused(self, node: NodeDB):
        """Immediately force a node's status to PAUSED in the cache"""
        now = time.time()
        self.latest_results[node.id] = {
            "node_id": node.id,
            "node_name": node.name,
            "ip": node.ip,
            "group_name": node.group.name if node.group else "Unknown",
            "status": "PAUSED",
            "latency": None,
            "packet_loss": 0,
            "timestamp": now,
            "monitor_ping": False,
            "monitor_snmp": False,
            "failure_count": 0,
            "max_retries": None,
        }
        # Also clear any failure state so it doesn't resume as PENDING/DOWN later
        state = self.get_node_state(node.id)
        state["status"] = "PAUSED"
        state["failure_count"] = 0
        state["down_alert_sent"] = False
        try:
            self.metric_processor.clear_node(node)
        except Exception as e:
            logger.debug(f"Could not clear metric alerts for paused node {node.name}: {e}")

        logger.info(f"Node {node.name} status forced to PAUSED")

    # ------------------------------------------------------------------ #
    # Dependency helpers
    # ------------------------------------------------------------------ #

    def _down_ancestor(self, node: NodeDB) -> Optional[NodeDB]:
        """Return the nearest ancestor currently DOWN, or None."""
        seen = set()
        parent = node.parent
        while parent is not None and parent.id not in seen:
            seen.add(parent.id)
            if self.node_states.get(parent.id, {}).get("status") == "DOWN":
                return parent
            parent = parent.parent
        return None

    # ------------------------------------------------------------------ #
    # Processing
    # ------------------------------------------------------------------ #

    async def process_node_with_limit(self, node: NodeDB):
        """Process a node with semaphore to limit concurrent sockets"""
        async with self.semaphore:
            await self.process_node(node)

    def _emit(self, node: NodeDB, old: str, new: str, reason: str):
        asyncio.create_task(trace_manager.emit(TraceEvent(
            timestamp=time.time(),
            node_id=node.id,
            node_name=node.name,
            ip=node.ip,
            group_name=node.group.name if node.group else "Unknown",
            old_status=old,
            new_status=new,
            reason=reason
        )))

    def _metric_reason(self, node: NodeDB, level: str, offending_metric_id: Optional[str]) -> str:
        reason = f"Metric alert: {level}"
        if not offending_metric_id:
            return reason
        metric = next((m for m in node.node_metrics if m.id == offending_metric_id), None)
        if not metric:
            return reason
        current_data = self.snmp_collector.current_values.get(offending_metric_id)
        if not current_data:
            return f"{metric.metric_definition.name}: {level}"
        val = current_data.get("processed_value")
        val_str = f"{val:.2f}" if isinstance(val, (int, float)) else str(val)
        unit = metric.metric_definition.unit or ""
        threshold = metric.critical_threshold if level == "CRITICAL" else metric.warning_threshold
        cond = getattr(metric, 'alert_condition', 'gt') or 'gt'
        symbol = ">" if cond == 'gt' else "<"
        return f"{metric.metric_definition.name}: {val_str}{unit} ({symbol} {threshold}, {level})"

    async def process_node(self, node: NodeDB):
        """Process a single node with configured monitoring protocols"""
        now = time.time()
        last = self.last_ping_time.get(node.id, 0)

        if node.group is None:
            logger.warning(f"Node {node.name} ({node.id}) is an orphan (no group). Skipping.")
            return

        # Effective settings (node override, else group default)
        interval = node.interval if node.interval is not None else node.group.interval
        packet_count = node.packet_count if node.packet_count is not None else node.group.packet_count
        max_retries = node.max_retries if node.max_retries is not None else node.group.max_retries

        state = self.get_node_state(node.id)
        current_status = state["status"]

        # Retry faster while PENDING
        effective_interval = interval / 3 if current_status == "PENDING" else interval

        if now - last < effective_interval:
            return

        self.last_ping_time[node.id] = now

        # Paused node or group: publish PAUSED and clear stale alerts in storage
        if not node.enabled or not node.group.enabled:
            self.latest_results[node.id] = {
                "node_id": node.id,
                "node_name": node.name,
                "ip": node.ip,
                "group_name": node.group.name,
                "status": "PAUSED",
                "latency": None,
                "packet_loss": 0,
                "timestamp": now,
                "monitor_ping": False,
                "monitor_snmp": False,
                "failure_count": 0,
                "max_retries": max_retries,
            }
            if current_status != "PAUSED":
                state["status"] = "PAUSED"
                state["failure_count"] = 0
                state["down_alert_sent"] = False
                status_stream.publish({"type": "node", "data": self.latest_results[node.id]})
            await storage.write_monitor_result(
                node_name=node.name,
                ip=node.ip,
                group_name=node.group.name,
                protocol="icmp", # Use icmp so it shows up in main status query
                latency=0.0,
                status="PAUSED",
                success=True,
                raw_data={}
            )
            return

        use_ping = node.monitor_ping if node.monitor_ping is not None else node.group.monitor_ping
        use_snmp = node.monitor_snmp if node.monitor_snmp is not None else node.group.monitor_snmp

        # Run configured monitors
        monitor_results: List[MonitorResult] = []

        if use_ping:
            logger.debug(f"Running PING monitor for {node.name} ({node.ip})")
            ping_result = await self.ping_monitor.check(node.ip, count=packet_count, timeout=5)
            monitor_results.append(ping_result)

        if use_snmp:
            logger.debug(f"Running SNMP monitor for {node.name} ({node.ip})")
            community = node.snmp_community or node.group.snmp_community
            port = node.snmp_port or node.group.snmp_port
            snmp_result = await self.snmp_monitor.check(node.ip, community=community, port=port, timeout=5)
            monitor_results.append(snmp_result)

        # Node is reachable only if ALL configured monitors succeed
        overall_success = all(r.success for r in monitor_results) if monitor_results else False

        successful_latencies = [r.latency_ms for r in monitor_results if r.protocol == "icmp" and r.success and r.latency_ms is not None]
        avg_latency = sum(successful_latencies) / len(successful_latencies) if successful_latencies else None

        packet_loss = 0.0
        for result in monitor_results:
            if result.protocol == "icmp":
                packet_loss = result.raw_data.get("packet_loss", 0.0)
                break

        # Process ICMP-derived metrics first so metric alert state is current
        # when the node status is derived below.
        for result in monitor_results:
            if result.protocol == "icmp" and result.success:
                await self._process_icmp_metrics(node, result)
            elif result.protocol == "snmp" and result.success:
                self._check_reboot(node, state, result.raw_data.get("uptime_ticks"), now)

        new_status = current_status

        if overall_success:
            # Reachable. Metric alerts make it DEGRADED, never DOWN.
            metric_level, offending_metric_id = self.metric_processor.get_node_alert_status(node)
            new_status = "DEGRADED" if metric_level else "UP"

            if current_status != new_status:
                if metric_level:
                    reason = self._metric_reason(node, metric_level, offending_metric_id)
                elif current_status == "DOWN":
                    reason = f"Reachability restored after {_format_duration(now - state['down_since'])}"
                elif current_status == "DEGRADED":
                    reason = "Metrics back within thresholds"
                else:
                    reason = "Reachability OK"
                logger.info(f"Node {node.name} status changed: {current_status} -> {new_status} ({reason})")
                self._emit(node, current_status, new_status, reason)

                if current_status == "DOWN":
                    # Capture before the flag is reset below; the task runs later
                    asyncio.create_task(self._send_recovery_alert(
                        node, now - state["down_since"], alert_was_sent=state.get("down_alert_sent", False)))

            state["failure_count"] = 0
            state["first_failure_time"] = 0
            state["down_since"] = 0
            state["down_alert_sent"] = False
        else:
            # Reachability failure
            if current_status in ("UP", "DEGRADED", "PAUSED"):
                new_status = "PENDING"
                state["failure_count"] = 1
                state["first_failure_time"] = now
                self._emit(node, current_status, new_status, "Check failed, entering retry state")
                logger.warning(f"Node {node.name} check failed. Entering PENDING state (retry 1/{max_retries} scheduled)")
            elif current_status == "PENDING":
                state["failure_count"] += 1
                retry_no = state["failure_count"] - 1
                logger.warning(f"Node {node.name} retry {retry_no}/{max_retries} failed")
                if state["failure_count"] > max_retries:
                    new_status = "DOWN"
                    state["down_since"] = state["first_failure_time"] or now
                    logger.error(f"Node {node.name} exceeded max retries. Marking DOWN.")
                    self._emit(node, "PENDING", "DOWN", f"Exceeded max retries ({max_retries})")
                    asyncio.create_task(self._send_down_alert(node))
            elif current_status == "DOWN":
                new_status = "DOWN"

        state["status"] = new_status

        lat_str = f"{avg_latency:.2f}ms" if avg_latency is not None else "N/A"
        protocols = [r.protocol.upper() for r in monitor_results]
        logger.debug(f"Result for {node.name} ({'/'.join(protocols)}): {new_status}, Latency: {lat_str}, Loss: {packet_loss}%")

        self.latest_results[node.id] = {
            "node_id": node.id,
            "node_name": node.name,
            "ip": node.ip,
            "group_name": node.group.name,
            "status": new_status,
            "latency": avg_latency,
            "packet_loss": packet_loss,
            "timestamp": now,
            "monitor_ping": use_ping,
            "monitor_snmp": use_snmp,
            "failure_count": state["failure_count"],
            "max_retries": max_retries,
            "parent_id": node.parent_id,
            "uptime_seconds": state.get("uptime_ticks") // 100 if state.get("uptime_ticks") is not None else None,
        }
        status_stream.publish({"type": "node", "data": self.latest_results[node.id]})

        # Write to Storage (log each monitor result separately)
        for result in monitor_results:
            if new_status == "PENDING":
                record_status = "PENDING"
            elif result.success:
                record_status = new_status if new_status in ("UP", "DEGRADED") else "UP"
            else:
                record_status = "DOWN"

            await storage.write_monitor_result(
                node_name=node.name,
                ip=node.ip,
                group_name=node.group.name,
                protocol=result.protocol,
                latency=result.latency_ms,
                status=record_status,
                success=result.success,
                raw_data=result.raw_data
            )

    def _check_reboot(self, node: NodeDB, state: dict, uptime_ticks, now: float):
        """
        sysUpTime counts hundredths of a second since the SNMP agent started.
        A value lower than the previous reading means the device restarted.
        """
        if uptime_ticks is None:
            return
        try:
            ticks = int(uptime_ticks)
        except (TypeError, ValueError):
            return

        prev = state.get("uptime_ticks")
        state["uptime_ticks"] = ticks
        if prev is None or ticks >= prev:
            return

        # Counter wrap (2^32 ticks, about 497 days) is not a reboot
        if prev > 2**32 - 24 * 360000:
            return

        previous_uptime = _format_duration(prev / 100)
        booted_ago = _format_duration(ticks / 100)
        reason = f"Device rebooted (uptime was {previous_uptime}, now {booted_ago})"
        logger.warning(f"Node {node.name}: {reason}")
        self._emit(node, state["status"], state["status"], reason)

        if self.notifier.storage.config.get("alerting", {}).get("notify_reboot", True):
            title = f"BeamState Reboot: {node.name}"
            message = f"{node.name} ({node.ip}) rebooted. Previous uptime {previous_uptime}, up again for {booted_ago}."
            asyncio.create_task(self.notifier.send(
                title, message, 0, event="node_reboot",
                previous_uptime_seconds=prev // 100, **self._node_context(node, state["status"])))

    async def _process_icmp_metrics(self, node: NodeDB, result: MonitorResult):
        """Feed ICMP latency and packet loss into the generic metric pipeline."""
        for nm in node.node_metrics:
            if not nm.enabled:
                continue
            definition = nm.metric_definition
            if not definition or definition.metric_source != "icmp":
                continue

            val = None
            if definition.name == "ICMP Latency" and result.latency_ms is not None:
                val = result.latency_ms
            elif definition.name == "ICMP Packet Loss":
                val = result.raw_data.get("packet_loss", 0.0)

            if val is None:
                continue
            try:
                processed = await self.metric_processor.process_metric(node, nm, val)
                if processed:
                    self.snmp_collector.current_values[nm.id] = processed
            except Exception as ex:
                logger.error(f"Error processing ICMP metric {definition.name}: {ex}")

    # ------------------------------------------------------------------ #
    # Loops
    # ------------------------------------------------------------------ #

    async def run_loop(self):
        self.running = True
        logger.info("Monitor Loop Started")

        await self.snmp_collector.start()
        self._heartbeat_task = asyncio.create_task(self.heartbeat_loop())

        while self.running:
            db = SessionLocal()
            try:
                nodes = db.query(NodeDB).all()
                tasks = [self.process_node_with_limit(n) for n in nodes]
                if tasks:
                    await asyncio.gather(*tasks)
            except Exception as e:
                logger.error(f"Error in Monitor Loop: {e}")
            finally:
                db.close()

            await asyncio.sleep(1)

    async def heartbeat_loop(self):
        """
        Deadman switch: GET a URL on a fixed interval while the monitor runs.
        Point it at Healthchecks.io, Uptime Kuma push or a Home Assistant webhook.
        """
        while self.running:
            conf = storage.config.get("heartbeat", {})
            interval = max(10, int(conf.get("interval", 60) or 60))
            if conf.get("enabled") and conf.get("url"):
                try:
                    async with httpx.AsyncClient() as client:
                        r = await client.get(conf["url"], timeout=10.0)
                        if r.status_code >= 300:
                            logger.warning(f"Heartbeat returned status {r.status_code}")
                        else:
                            logger.debug("Heartbeat sent")
                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        self.running = False
        self.snmp_collector.stop()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        logger.info("Stopping Monitor Loop...")

    def get_status(self):
        return {
            "running": self.running,
            "monitored_devices": len(self.last_ping_time),
            "latest_results": list(self.latest_results.values())
        }

    # ------------------------------------------------------------------ #
    # Notifications
    # ------------------------------------------------------------------ #

    def _node_context(self, node: NodeDB, status: str) -> dict:
        return {
            "node": node.name,
            "ip": node.ip,
            "group": node.group.name if node.group else None,
            "status": status,
        }

    async def _send_down_alert(self, node: NodeDB):
        """Send notification for DOWN node"""
        state = self.get_node_state(node.id)
        try:
            if not self.notifier.any_channel_enabled():
                logger.debug("No notification channel enabled. Skipping alert.")
                return

            # Dependency: an upstream device is already DOWN, this alert is noise
            ancestor = self._down_ancestor(node)
            if ancestor is not None:
                logger.info(f"Suppressing DOWN alert for {node.name}: parent {ancestor.name} is DOWN")
                self._emit(node, "DOWN", "DOWN", f"Alert suppressed: parent {ancestor.name} is DOWN")
                return

            pushover_config = storage.config.get("pushover", {})

            # --- Throttling Logic ---
            if pushover_config.get("throttling_enabled", False):
                threshold = int(pushover_config.get("alert_threshold", 5))
                window = int(pushover_config.get("alert_window", 60))
                now = time.time()

                self.alert_history = [t for t in self.alert_history if now - t < window]
                logger.info(f"Throttling Check: History={len(self.alert_history)}, Threshold={threshold}, Window={window}")

                if len(self.alert_history) >= threshold:
                    logger.warning(f"Alert storm detected ({len(self.alert_history)} alerts in last {window}s). Suppressing individual alert for {node.name}.")
                    if now - self.last_storm_alert_time > window:
                        self.last_storm_alert_time = now
                        title = "⚠️ Global Alert: High failure rate detected"
                        message = f"Alert Storm: {len(self.alert_history)} nodes down within {window}s. Suppressing individual alerts to prevent spam."
                        await self.notifier.send(title, message, 1, event="alert_storm", count=len(self.alert_history), window=window)
                    return

                self.alert_history.append(now)

            global_priority = int(pushover_config.get("priority", 0))
            priority = node.notification_priority if node.notification_priority is not None else global_priority
            template = pushover_config.get("message_template", "Node {name} ({ip}) is DOWN")

            message = template.format(name=node.name, ip=node.ip)
            title = f"BeamState Alert: {node.name}"

            sent = await self.notifier.send(title, message, priority, event="node_down", **self._node_context(node, "DOWN"))
            state["down_alert_sent"] = bool(sent)

        except Exception as e:
            logger.error(f"Failed to trigger alert for {node.name}: {e}")

    async def _send_recovery_alert(self, node: NodeDB, downtime: float, alert_was_sent: bool):
        """Send notification when a node returns from DOWN to reachable."""
        try:
            if not self.notifier.notify_recovery():
                return
            if not alert_was_sent:
                # The DOWN alert was suppressed (parent down, storm, maintenance): stay quiet
                logger.debug(f"Skipping recovery alert for {node.name}: no DOWN alert was sent")
                return

            title = f"BeamState Recovered: {node.name}"
            message = f"Node {node.name} ({node.ip}) is back UP after {_format_duration(downtime)}"
            await self.notifier.send(title, message, 0, event="node_up", downtime_seconds=int(downtime), **self._node_context(node, "UP"))
        except Exception as e:
            logger.error(f"Failed to send recovery alert for {node.name}: {e}")
