import json
import os
import logging
from sqlalchemy.orm import Session
from models import GroupDB, NodeDB

logger = logging.getLogger("BeamState.Utils")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def save_config(db: Session):
    """
    Exports the current state of the database to config.json.
    This ensures persistence across restarts.
    """
    try:
        # Fetch all groups with their nodes
        groups = db.query(GroupDB).all()
        
        config_data = {"groups": []}
        
        for group in groups:
            group_data = {
                "id": group.id,
                "name": group.name,
                "interval": group.interval,
                "packet_count": group.packet_count,
                "max_retries": group.max_retries,
                "enabled": group.enabled,
                "nodes": []
            }
            
            for node in group.nodes:
                node_data = {
                    "id": node.id,
                    "name": node.name,
                    "ip": node.ip,
                    "interval": node.interval,
                    "packet_count": node.packet_count,
                    "max_retries": node.max_retries,
                    "enabled": node.enabled,
                    "monitor_ping": node.monitor_ping,
                    "monitor_snmp": node.monitor_snmp,
                    "snmp_community": node.snmp_community,
                    "snmp_port": node.snmp_port
                }
                group_data["nodes"].append(node_data)
            
            config_data["groups"].append(group_data)
            
        # Write to file
        with open(CONFIG_PATH, "w") as f:
            json.dump(config_data, f, indent=4)
            
        logger.info(f"Configuration saved to {CONFIG_PATH}")
        
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
