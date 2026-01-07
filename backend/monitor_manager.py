import asyncio
import logging
import time
from typing import Dict, List
from database import SessionLocal
from models import NodeDB, GroupDB
from storage import storage
from monitors import PingMonitor, SNMPMonitor, MonitorResult
from monitors.snmp_data_collector import SNMPDataCollector
from notifications import PushoverClient

logger = logging.getLogger("BeamState.MonitorManager")

class MonitorManager:
    def __init__(self):
        self.running = False
        self.last_ping_time: Dict[int, float] = {} # node_id -> timestamp
        self.latest_results: Dict[int, dict] = {} # node_id -> {status, latency, packet_loss, timestamp}
        self.node_states: Dict[int, dict] = {} # node_id -> {status, failure_count, first_failure_time}
        
        # Concurrency limit for Windows (SelectorEventLoop 64 FD limit)
        self.semaphore = asyncio.Semaphore(32)
        
        # Initialize monitors
        self.ping_monitor = PingMonitor()
        self.snmp_monitor = SNMPMonitor()
        self.snmp_collector = SNMPDataCollector()
        self.snmp_collector = SNMPDataCollector()
        self.pushover = PushoverClient()
        
        # Throttling state
        self.alert_history: List[float] = [] # timestamps of recent alerts
        self.last_storm_alert_time = 0


    def remove_node(self, node_id: int):
        if node_id in self.latest_results:
            del self.latest_results[node_id]
        if node_id in self.last_ping_time:
            del self.last_ping_time[node_id]
        # Clear failure tracking
        self.node_states.pop(node_id, None)
        logger.info(f"Removed node {node_id} from monitor cache")

    def get_node_state(self, node_id: int) -> dict:
        if node_id not in self.node_states:
            self.node_states[node_id] = {
                "status": "UP",
                "failure_count": 0,
                "first_failure_time": 0
            }
        return self.node_states[node_id]
    
    def trigger_immediate_check(self, node_id: str):
        """Trigger an immediate check for a specific node (e.g., when unpausing)"""
        if node_id in self.last_ping_time:
            # Reset the last ping time to 0 to force immediate check on next loop iteration
            self.last_ping_time[node_id] = 0
            logger.info(f"Triggered immediate check for node {node_id}")

    async def process_node_with_limit(self, node: NodeDB):
        """Process a node with semaphore to limit concurrent sockets"""
        async with self.semaphore:
            await self.process_node(node)

    async def process_node(self, node: NodeDB):
        """Process a single node with configured monitoring protocols"""
        now = time.time()
        last = self.last_ping_time.get(node.id, 0)
        
        # Check if node has a group
        if node.group is None:
            logger.warning(f"Node {node.name} ({node.id}) is an orphan (no group). Skipping.")
            return
        
        # Get node settings
        interval = node.interval if node.interval is not None else node.group.interval
        packet_count = node.packet_count if node.packet_count is not None else node.group.packet_count
        max_retries = node.max_retries if node.max_retries is not None else node.group.max_retries
        
        # Get current state
        state = self.get_node_state(node.id)
        current_status = state["status"]
        
        # Determine effective interval based on status
        effective_interval = interval
        if current_status == "PENDING":
             # Retry interval is 1/3 of heartbeat
             effective_interval = interval / 3

        # Determine if due
        if now - last < effective_interval:
            return
        
        self.last_ping_time[node.id] = now

        # Skip monitoring if node or group is disabled (PAUSED)
        # BUT write a PAUSED record to storage to ensure alerts clear (status_code=1)
        if not node.enabled or not node.group.enabled:
            # Update cache
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
                "monitor_snmp": False
            }
            # Write 'PAUSED' to storage to clear any stale DOWN alerts
            # We use a dummy protocol 'system' or just 'icmp' to ensure it appears in the same query
            await storage.write_monitor_result(
                node_name=node.name,
                ip=node.ip,
                group_name=node.group.name,
                protocol="icmp", # Use icmp so it shows up in main status query
                latency=0.0,
                status="PAUSED",
                success=True, # Treated as success to be safe
                raw_data={}
            )
            return
        
        # Determine monitoring configuration
        use_ping = node.monitor_ping if node.monitor_ping is not None else node.group.monitor_ping
        use_snmp = node.monitor_snmp if node.monitor_snmp is not None else node.group.monitor_snmp
        
        # Get node settings (re-fetch to be safe/clear, though we fetched earlier)
        # interval/packet_count are already fetched at top of function but we can reuse or just use what we have.
        # Actually, looking at code above, I already fetched 'interval', 'packet_count', 'max_retries' at lines 68-71.
        # So I only need to define use_ping and use_snmp.
        
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
        
        # Aggregate results: node is UP only if ALL configured monitors succeed
        overall_success = all(r.success for r in monitor_results) if monitor_results else False
        
        # Calculate average latency from successful monitors
        successful_latencies = [r.latency_ms for r in monitor_results if r.success and r.latency_ms is not None]
        avg_latency = sum(successful_latencies) / len(successful_latencies) if successful_latencies else None
        
        # Determine packet loss (only relevant for PING)
        packet_loss = 0.0
        for result in monitor_results:
            if result.protocol == "icmp":
                packet_loss = result.raw_data.get("packet_loss", 0.0)
                break
        
        # Update state based on aggregated result
        new_status = current_status
        
        if overall_success:
            # Success
            if current_status in ["PENDING", "DOWN"]:
                logger.info(f"Node {node.name} recovered. Marking UP.")
            new_status = "UP"
            state["failure_count"] = 0
            state["first_failure_time"] = 0
        else:
            # Failure
            if current_status == "UP":
                # Transition to PENDING
                new_status = "PENDING"
                state["failure_count"] = 1
                state["first_failure_time"] = now
                logger.warning(f"Node {node.name} check failed. Entering PENDING state (Retry 1/{max_retries})")
            elif current_status == "PENDING":
                state["failure_count"] += 1
                logger.warning(f"Node {node.name} retry failed ({state['failure_count']}/{max_retries})")
                if state["failure_count"] > max_retries:
                    # Transition to DOWN
                    new_status = "DOWN"
                    logger.error(f"Node {node.name} exceeded max retries. Marking DOWN.")
                    
                    # Trigger Notification
                    asyncio.create_task(self._send_down_alert(node))
            elif current_status == "DOWN":
                # Stay DOWN
                new_status = "DOWN"
        
        # Update state
        state["status"] = new_status
        
        # Log result at DEBUG level (use INFO for warnings/errors)
        lat_str = f"{avg_latency:.2f}ms" if avg_latency is not None else "N/A"
        protocols = [r.protocol.upper() for r in monitor_results]
        logger.debug(f"Result for {node.name} ({'/'.join(protocols)}): {new_status}, Latency: {lat_str}, Loss: {packet_loss}%")
        
        # Store latest result
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
            "monitor_snmp": use_snmp
        }
        
        # Write to Storage (log each monitor result separately)
        for result in monitor_results:
            # Determine status for this specific protocol check
            # Use Node status if it's PENDING (to show retry state), otherwise purely based on success
            if new_status == "PENDING":
                record_status = "PENDING"
            else:
                record_status = "UP" if result.success else "DOWN"

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

    async def run_loop(self):
        self.running = True
        logger.info("Monitor Loop Started")
        
        # Start SNMP Collector
        await self.snmp_collector.start()
        
        while self.running:
            db = SessionLocal()
            try:
                nodes = db.query(NodeDB).all()
                # Process nodes concurrently
                tasks = [self.process_node_with_limit(n) for n in nodes]
                if tasks:
                    await asyncio.gather(*tasks)
            except Exception as e:
                logger.error(f"Error in Monitor Loop: {e}")
            finally:
                db.close()
            
            # Sleep to prevent busy loop
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
        self.snmp_collector.stop()
        logger.info("Stopping Monitor Loop...")

    def get_status(self):
        return {
            "running": self.running,
            "monitored_devices": len(self.last_ping_time),
            "latest_results": list(self.latest_results.values())
        }

    async def _send_down_alert(self, node: NodeDB):
        """Send notification for DOWN node"""
        try:
            pushover_config = storage.config.get("pushover", {})
            if not pushover_config.get("enabled", False):
                logger.debug("Pushover disabled in config. Skipping alert.")
                return

            # --- Throttling Logic ---
            throttling_enabled = pushover_config.get("throttling_enabled", False)
            if throttling_enabled:
                threshold = int(pushover_config.get("alert_threshold", 5))
                window = int(pushover_config.get("alert_window", 60))
                now = time.time()
                
                # Prune history
                self.alert_history = [t for t in self.alert_history if now - t < window]
                
                logger.info(f"Throttling Check: History={len(self.alert_history)}, Threshold={threshold}, Window={window}")

                # Check storm condition
                if len(self.alert_history) >= threshold:
                    logger.warning(f"Alert storm detected ({len(self.alert_history)} alerts in last {window}s). Suppressing individual alert for {node.name}.")
                    
                    # Send General "Outage detected" alert if not sent recently (limit to once per window)
                    if now - self.last_storm_alert_time > window:
                        self.last_storm_alert_time = now
                        title = "⚠️ Global Alert: High failure rate detected"
                        message = f"Alert Storm: {len(self.alert_history)} nodes down within {window}s. Suppressing individual alerts to prevent spam."
                        priority = 1 # High priority
                        
                        # Use keys (already fetched below, so we need to move fetching up or re-fetch)
                        token = pushover_config.get("token")
                        user_key = pushover_config.get("user_key")
                        if token and user_key:
                            self.pushover.configure(token, user_key)
                            await self.pushover.send_notification(title, message, priority)
                    return
                
                # Add current to history
                self.alert_history.append(now)

            token = pushover_config.get("token")
            user_key = pushover_config.get("user_key")
            
            if not token or not user_key:
                logger.warning("Pushover enabled but credentials missing. Skipping alert.")
                return

            # Configure client
            self.pushover.configure(token, user_key)
            
            # Format message
            priority = int(pushover_config.get("priority", 0))
            template = pushover_config.get("message_template", "Node {name} ({ip}) is DOWN")
            
            message = template.format(name=node.name, ip=node.ip)
            title = f"BeamState Alert: {node.name}"
            
            await self.pushover.send_notification(title, message, priority)
            
        except Exception as e:
            logger.error(f"Failed to trigger alert for {node.name}: {e}")
