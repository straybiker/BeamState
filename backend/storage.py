import os
import aiofiles
import logging
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import ASYNCHRONOUS

logger = logging.getLogger("BeamState.Storage")

class Storage:
    def __init__(self):
        # InfluxDB Configuration
        influx_url = os.getenv("INFLUX_URL")
        influx_token = os.getenv("INFLUX_TOKEN")
        self.org = os.getenv("INFLUX_ORG", "beamstate")
        self.bucket = os.getenv("INFLUX_BUCKET", "monitoring")
        
        self.use_influx = bool(influx_url and influx_token)
        
        if self.use_influx:
            self.client = InfluxDBClient(url=influx_url, token=influx_token, org=self.org)
            self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)
            logger.info(f"InfluxDB configured: {influx_url}")
        else:
            self.client = None
            self.write_api = None
            logger.info("InfluxDB not configured. Using file logging.")
        
        # Lock for file operations to prevent race conditions
        import asyncio
        self._file_lock = asyncio.Lock()

    async def write_monitor_result(
        self, 
        node_name: str, 
        ip: str, 
        group_name: str, 
        protocol: str,  # "icmp" or "snmp"
        latency: float, 
        status: str,
        success: bool,
        raw_data: dict
    ):
        """
        Write monitoring result to storage.
        
        Args:
            node_name: Name of the monitored node
            ip: IP address
            group_name: Group name
            protocol: Monitoring protocol ("icmp" or "snmp")
            latency: Latency in milliseconds (or None)
            status: Node status (UP/DOWN/PENDING/PAUSED)
            success: Whether this specific monitor succeeded
            raw_data: Protocol-specific data (packet_loss, responses, uptime_ticks, etc.)
        """
        # Explicit format to ensure local time is clear
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
        
        if self.use_influx:
            try:
                # Format raw responses for InfluxDB
                response_str = ""
                if protocol == "icmp" and "responses" in raw_data:
                    formatted = []
                    for resp in raw_data["responses"]:
                        if isinstance(resp, float):
                            formatted.append(f"{round(resp * 1000, 2)}ms")
                        elif resp is None:
                            formatted.append("timeout")
                        elif resp is False:
                            formatted.append("error")
                        else:
                            formatted.append(str(resp))
                    response_str = ",".join(formatted)
                
                point = (
                    Point("monitoring")
                    .tag("node", node_name)
                    .tag("ip", ip)
                    .tag("group", group_name)
                    .tag("status", status)
                    .tag("protocol", protocol)
                    .field("latency", float(latency) if latency is not None else 0.0)
                    .field("packet_loss", float(raw_data.get("packet_loss", 0.0)))
                    .field("status_code", 1 if status == "UP" else 0)
                    .field("success", 1 if success else 0)
                    .field("responses", response_str if response_str else "none")
                    .time(timestamp)
                )
                self.write_api.write(bucket=self.bucket, org=self.org, record=point)
                return
            except Exception as e:
                logger.error(f"Error writing to InfluxDB: {e}")
        
        # Fallback or Default to File (async)
        # Format raw responses for JSON serialization
        formatted_responses = []
        if protocol == "icmp" and "responses" in raw_data:
            for resp in raw_data["responses"]:
                if isinstance(resp, float):
                    formatted_responses.append(round(resp * 1000, 2))  # Convert to ms
                elif resp is None:
                    formatted_responses.append("timeout")
                elif resp is False:
                    formatted_responses.append("error")
                else:
                    formatted_responses.append(str(resp))
        
        entry = {
            "timestamp": timestamp_str,
            "node": node_name,
            "ip": ip,
            "group": group_name,
            "protocol": protocol,
            "latency": round(latency, 2) if latency is not None else None,
            "packet_loss": raw_data.get("packet_loss", 0.0),
            "status": status,
            "success": success,
            "ping_responses": formatted_responses if formatted_responses else None
        }
        
        # File logging with lock to prevent race conditions
        # Use absolute path to avoid issues with working directory
        import pathlib
        log_file = pathlib.Path(__file__).parent / "data" / "ping_logs.json"
        log_file.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        
        async with self._file_lock:
            try:
                # Write new entry
                async with aiofiles.open(log_file, mode='a') as f:
                    import json
                    await f.write(json.dumps(entry) + "\n")
            except Exception as e:
                logger.error(f"Error writing to log file: {e}")
                return
            
            # Log rotation (keep last 200 lines)
            try:
                async with aiofiles.open(log_file, mode='r') as f:
                    lines = await f.readlines()
                if len(lines) > 200:
                    async with aiofiles.open(log_file, mode='w') as f:
                        await f.writelines(lines[-200:])
                        logger.debug(f"Rotated log file: {len(lines)} -> 200 lines")
            except Exception as e:
                logger.debug(f"Log rotation skipped: {e}")

# Global storage instance
storage = Storage()
