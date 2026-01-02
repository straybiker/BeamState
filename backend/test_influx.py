
import json
import logging
import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Setup basic logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("TestInflux")

try:
    with open("config.json", "r") as f:
        config = json.load(f)
        influx_conf = config.get("app_config", {}).get("influxdb", {})
        
    print(f"Testing connection to: {influx_conf.get('url')}")
    print(f"Org: {influx_conf.get('org')}")
    print(f"Bucket: {influx_conf.get('bucket')}")
    print(f"Token: {influx_conf.get('token')[:10]}...")
    
    client = InfluxDBClient(
        url=influx_conf["url"], 
        token=influx_conf["token"], 
        org=influx_conf["org"]
    )
    
    # Use Synchronous write to get immediate feedback
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    point = (
        Point("test_measurement")
        .tag("host", "test_script")
        .field("value", 1.0)
    )
    
    print("Attempting to write test point...")
    write_api.write(bucket=influx_conf["bucket"], org=influx_conf["org"], record=point)
    print("Successfully wrote test point!")
    
    client.close()

except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
