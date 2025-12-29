import os
import json
import logging
import asyncio
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import aiofiles

logger = logging.getLogger("BeamState.Storage")

class Storage:
    def __init__(self):
        self.use_influx = False
        self.influx_client = None
        self.write_api = None
        self.log_file = os.getenv("LOG_FILE", "backend/data/ping_logs.json")
        self._write_lock = asyncio.Lock()
        
        # Influx Config
        self.url = os.getenv("INFLUXDB_URL")
        self.token = os.getenv("INFLUXDB_TOKEN")
        self.org = os.getenv("INFLUXDB_ORG")
        self.bucket = os.getenv("INFLUXDB_BUCKET")

        if self.url and self.token and self.org and self.bucket:
            try:
                self.influx_client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
                self.write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
                self.use_influx = True
                logger.info(f"Connected to InfluxDB at {self.url}")
            except Exception as e:
                logger.error(f"Failed to connect to InfluxDB: {e}. Falling back to file logging.")
        else:
            logger.info("InfluxDB not configured. Using file logging.")

    async def write_ping_result(self, node_name: str, ip: str, group_name: str, latency: float, packet_loss: float, status: str, raw_responses: list = None):
        """
        latency: ms
        packet_loss: 0-100%
        status: UP / DOWN / PENDING / PAUSED
        raw_responses: list of raw ping3 return values
        """
        # Explicit format to ensure local time is clear
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
        
        if self.use_influx:
            try:
                # Format raw responses for InfluxDB
                response_str = ""
                if raw_responses:
                    formatted = []
                    for resp in raw_responses:
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
                    Point("ping")
                    .tag("node", node_name)
                    .tag("ip", ip)
                    .tag("group", group_name)
                    .tag("status", status)
                    .field("latency", float(latency) if latency is not None else 0.0)
                    .field("packet_loss", float(packet_loss))
                    .field("status_code", 1 if status == "UP" else 0)
                    .field("ping_responses", response_str if response_str else "none")
                    .time(timestamp)
                )
                self.write_api.write(bucket=self.bucket, org=self.org, record=point)
                return
            except Exception as e:
                logger.error(f"Error writing to InfluxDB: {e}")
        
        # Fallback or Default to File (async)
        # Format raw responses for JSON serialization
        formatted_responses = []
        if raw_responses:
            for resp in raw_responses:
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
            "latency": round(latency, 2) if latency is not None else None,
            "packet_loss": packet_loss,
            "status": status,
            "ping_responses": formatted_responses if formatted_responses else None
        }
        
        try:
            async with self._write_lock:
                # Async append to file
                async with aiofiles.open(self.log_file, "a") as f:
                    await f.write(json.dumps(entry) + "\n")
                
                # Log rotation: keep only last 200 lines
                await self._rotate_log()
        except Exception as e:
            logger.error(f"Error writing to log file: {e}")
    
    async def _rotate_log(self, max_lines: int = 200):
        """Keep only the last max_lines entries in the log file."""
        try:
            async with aiofiles.open(self.log_file, "r") as f:
                content = await f.read()
                lines = content.splitlines(keepends=True)
            
            if len(lines) > max_lines:
                # Keep only the last max_lines
                async with aiofiles.open(self.log_file, "w") as f:
                    await f.writelines(lines[-max_lines:])
        except Exception as e:
            logger.debug(f"Log rotation skipped: {e}")

storage = Storage()
