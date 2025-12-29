import os
import json
import logging
import time
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger("NetSentry.Storage")

class Storage:
    def __init__(self):
        self.use_influx = False
        self.influx_client = None
        self.write_api = None
        self.log_file = os.getenv("LOG_FILE", "backend/data/ping_logs.json")
        
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

    def write_ping_result(self, node_name: str, ip: str, group_name: str, latency: float, packet_loss: float, status: str):
        """
        latency: ms
        packet_loss: 0-100%
        status: UP / DOWN
        """
        timestamp = datetime.utcnow()
        
        if self.use_influx:
            try:
                point = (
                    Point("ping")
                    .tag("node", node_name)
                    .tag("ip", ip)
                    .tag("group", group_name)
                    .field("latency", float(latency) if latency is not None else 0.0)
                    .field("packet_loss", float(packet_loss))
                    .field("status_code", 1 if status == "UP" else 0)
                    .field("status", status)
                    .time(timestamp)
                )
                self.write_api.write(bucket=self.bucket, org=self.org, record=point)
                return
            except Exception as e:
                logger.error(f"Error writing to InfluxDB: {e}")
        
        # Fallback or Default to File
        entry = {
            "timestamp": timestamp.isoformat(),
            "node": node_name,
            "ip": ip,
            "group": group_name,
            "latency": latency,
            "packet_loss": packet_loss,
            "status": status
        }
        
        try:
            # Simple append to file with rotation
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            
            # Log rotation: keep only last 200 lines
            self._rotate_log()
        except Exception as e:
            logger.error(f"Error writing to log file: {e}")
    
    def _rotate_log(self, max_lines: int = 200):
        """Keep only the last max_lines entries in the log file."""
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
            
            if len(lines) > max_lines:
                # Keep only the last max_lines
                with open(self.log_file, "w") as f:
                    f.writelines(lines[-max_lines:])
        except Exception as e:
            logger.debug(f"Log rotation skipped: {e}")

storage = Storage()
