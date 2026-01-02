import os
import json
import logging
import asyncio
import aiofiles
import pathlib
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import ASYNCHRONOUS

logger = logging.getLogger("BeamState.Storage")

CONFIG_FILE = pathlib.Path(__file__).parent / "config.json"

class Storage:
    def __init__(self):
        self._file_lock = asyncio.Lock()
        self.reload_config()

    def reload_config(self):
        """Load configuration from config.json"""
        self.config = {
            "influxdb": {
                "enabled": False,
                "url": "",
                "token": "",
                "org": "beamstate",
                "bucket": "monitoring"
            },
            "logging": {
                "file_enabled": True,
                "file_path": "data/logs.json",
                "retention_lines": 200,
                "log_level": "INFO"
            }
        }
        
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    if "app_config" in data:
                        # Deep merge or just update keys
                        app_config = data["app_config"]
                        if "influxdb" in app_config:
                            self.config["influxdb"].update(app_config["influxdb"])
                        if "logging" in app_config:
                            self.config["logging"].update(app_config["logging"])
                            
            # Setup InfluxDB
            influx_conf = self.config["influxdb"]
            if influx_conf["enabled"] and influx_conf["url"] and influx_conf["token"]:
                self.client = InfluxDBClient(
                    url=influx_conf["url"], 
                    token=influx_conf["token"], 
                    org=influx_conf["org"]
                )
                self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)
                self.use_influx = True
                logger.info(f"Storage: InfluxDB ENABLED ({influx_conf['url']})")
            else:
                self.client = None
                self.write_api = None
                self.use_influx = False
                logger.info("Storage: InfluxDB DISABLED")
                
        except Exception as e:
            logger.error(f"Storage: Failed to load config: {e}")
            self.use_influx = False

    async def write_snmp_metric(
        self,
        node_name: str,
        ip: str,
        group_name: str,
        metric_name: str,
        value: float,
        unit: str = None,
        interface: str = None,
        metric_type: str = "gauge"
    ):
        """Write specific SNMP metric to storage"""
        if not self.use_influx:
            return

        try:
            point = (
                Point("snmp_metrics")
                .tag("node", node_name)
                .tag("ip", ip)
                .tag("group", group_name)
                .tag("metric", metric_name)
                .field("value", float(value))
            )
            
            if unit:
                point.tag("unit", unit)
            if interface:
                point.tag("interface", interface)
            if metric_type:
                point.tag("type", metric_type)
            
            # Write asynchronously
            self.write_api.write(bucket=self.config["influxdb"]["bucket"], org=self.config["influxdb"]["org"], record=point)
            
        except Exception as e:
            logger.error(f"Error writing SNMP metric: {e}")

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
        """
        # Explicit format to ensure local time is clear
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
        
        # 1. Write to InfluxDB if enabled
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
                
                influx_conf = self.config["influxdb"]
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
                )
                self.write_api.write(bucket=influx_conf["bucket"], org=influx_conf["org"], record=point)
            except Exception as e:
                logger.error(f"Error writing to InfluxDB: {e}")
        
        # 2. Write to Log File if enabled
        log_conf = self.config["logging"]
        if log_conf["file_enabled"]:
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
            
            # Use configurable path
            # If path is relative, make it relative to backend/ directory
            log_path = pathlib.Path(log_conf["file_path"])
            if not log_path.is_absolute():
                log_path = pathlib.Path(__file__).parent / log_path
                
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with self._file_lock:
                try:
                    # Write new entry
                    async with aiofiles.open(log_path, mode='a') as f:
                        await f.write(json.dumps(entry) + "\n")
                except Exception as e:
                    logger.error(f"Error writing to log file: {e}")
                    return
                
                # Log rotation
                max_lines = log_conf.get("retention_lines", 200)
                try:
                    async with aiofiles.open(log_path, mode='r') as f:
                        lines = await f.readlines()
                    if len(lines) > max_lines:
                        async with aiofiles.open(log_path, mode='w') as f:
                            await f.writelines(lines[-max_lines:])
                            # logger.debug(f"Rotated log file: {len(lines)} -> {max_lines} lines")
                except Exception as e:
                    logger.debug(f"Log rotation skipped: {e}")

# Global storage instance
storage = Storage()
