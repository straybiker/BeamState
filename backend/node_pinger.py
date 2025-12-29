import asyncio
import logging
import time
from typing import Dict
from ping3 import ping
from database import SessionLocal
from models import NodeDB, GroupDB
from storage import storage

logger = logging.getLogger("NetSentry.Pinger")

class Pinger:
    def __init__(self):
        self.running = False
        self.last_ping_time: Dict[int, float] = {} # node_id -> timestamp
        self.latest_results: Dict[int, dict] = {} # node_id -> {status, latency, packet_loss, timestamp}
        self.node_states: Dict[int, dict] = {} # node_id -> {status, failure_count, first_failure_time}


    async def ping_ip(self, ip: str, count: int = 1, timeout: int = 2):
        """
        Returns (avg_latency_ms, packet_loss_percent)
        Uses ping3 which works without admin privileges on Windows.
        """
        success_count = 0
        total_latency = 0.0
        
        for _ in range(count):
            try:
                # ping3.ping returns latency in seconds, or None on failure
                latency_sec = ping(ip, timeout=timeout)
                if latency_sec is not None:
                    total_latency += latency_sec * 1000  # to ms
                    success_count += 1
            except Exception as e:
                logger.debug(f"Ping error for {ip}: {e}")
            
            # Small delay between packets if count > 1
            if count > 1:
                await asyncio.sleep(0.5)

        if success_count == 0:
            return None, 100.0  # No response, 100% loss
        
        avg_latency = total_latency / success_count
        packet_loss = ((count - success_count) / count) * 100.0
        
        return avg_latency, packet_loss

    def remove_node(self, node_id: int):
        if node_id in self.latest_results:
            del self.latest_results[node_id]
        if node_id in self.last_ping_time:
            del self.last_ping_time[node_id]
        # Clear failure tracking
        self.node_states.pop(node_id, None)
        logger.info(f"Removed node {node_id} from pinger cache")

    def get_node_state(self, node_id: int) -> dict:
        if node_id not in self.node_states:
            self.node_states[node_id] = {
                "status": "UP",
                "failure_count": 0,
                "first_failure_time": 0
            }
        return self.node_states[node_id]

    async def process_node(self, node: NodeDB):
        # Determine config (override or group default)
        if node.group is None:
            logger.warning(f"Node {node.name} ({node.id}) is an orphan (no group). Skipping.")
            return

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
        now = time.time()
        last = self.last_ping_time.get(node.id, 0)
        
        if now - last >= effective_interval:
            logger.debug(f"Node {node.id} ({current_status}): Time delta {now - last:.2f}s >= Interval {effective_interval:.2f}s. Pinging.")
            self.last_ping_time[node.id] = now
            
            # Perform Ping
            logger.debug(f"Pinging {node.name} ({node.ip})...")
            latency, packet_loss = await self.ping_ip(node.ip, count=packet_count)
            
            is_up = packet_loss < 100
            new_status = current_status
            
            if is_up:
                # Success - Reset everything
                if current_status != "UP":
                    logger.info(f"Node {node.name} recovered from {current_status}")
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
                    logger.warning(f"Node {node.name} ping failed. Entering PENDING state (Retry 1/{max_retries})")
                elif current_status == "PENDING":
                    state["failure_count"] += 1
                    logger.warning(f"Node {node.name} retry failed ({state['failure_count']}/{max_retries})")
                    if state["failure_count"] > max_retries:
                        # Transition to DOWN
                        new_status = "DOWN"
                        logger.error(f"Node {node.name} exceeded max retries. Marking DOWN.")
                elif current_status == "DOWN":
                    # Stay DOWN
                    new_status = "DOWN"
            
            # Update state status
            state["status"] = new_status
            
            logger.info(f"Result for {node.name}: {new_status}, Latency: {latency}ms, Loss: {packet_loss}%")

            # Update In-Memory Cache for API
            self.latest_results[node.id] = {
                "node_id": node.id,
                "node_name": node.name,
                "ip": node.ip,
                "group_id": node.group_id,
                "group_name": node.group.name,
                "status": new_status,
                "latency": latency,
                "packet_loss": packet_loss,
                "timestamp": now,
                "retry_count": state["failure_count"] if new_status == "PENDING" else 0
            }
            
            # Write to Storage
            storage.write_ping_result(
                node_name=node.name,
                ip=node.ip,
                group_name=node.group.name,
                latency=latency,
                packet_loss=packet_loss,
                status=new_status
            )

    async def run_loop(self):
        self.running = True
        logger.info("Pinger Loop Started")
        
        while self.running:
            db = SessionLocal()
            try:
                nodes = db.query(NodeDB).filter(NodeDB.enabled == True).all()
                # Process concurrently or sequentially?
                # Sequentially safer for simple loop, async allows some concurrency.
                # Let's create tasks for each node to parallelize a bit within this cycle
                tasks = [self.process_node(n) for n in nodes]
                if tasks:
                    await asyncio.gather(*tasks)
                
                # Pruning is now handled by remove_node() call from API
            except Exception as e:
                logger.error(f"Error in Pinger Loop: {e}")
            finally:
                db.close()
            
            # Sleep a bit to prevent busy loop, but short enough to check intervals
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
        logger.info("Stopping Pinger Loop...")

    def get_status(self):
        return {
            "running": self.running,
            "monitored_devices": len(self.last_ping_time),
            "latest_results": list(self.latest_results.values())
        }

