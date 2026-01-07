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
        # 1. Read existing config to preserve app_config
        existing_data = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    existing_data = json.load(f)
            except:
                pass # corrupted or empty, start fresh-ish
        
        # Fetch all groups with their nodes
        groups = db.query(GroupDB).all()
        
        config_data = {
            "app_config": existing_data.get("app_config", {}), # Preserve existing app_config
            "groups": []
        }
        
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

def save_app_config(app_config: dict):
    """
    Updates the app_config section in config.json without modifying groups.
    """
    try:
        if not os.path.exists(CONFIG_PATH):
            logger.error("config.json not found")
            return

        # Validate Pushover Config
        if "pushover" in app_config:
            p_config = app_config["pushover"]
            if "priority" in p_config:
                 try:
                     p = int(p_config["priority"])
                     if not (-2 <= p <= 2):
                         raise ValueError("Priority must be between -2 and 2")
                 except ValueError:
                     logger.warning("Invalid priority in pushover config, defaulting to 0")
                     p_config["priority"] = 0
            
            # Validate Throttling
            if "alert_threshold" in p_config:
                try:
                    t = int(p_config["alert_threshold"])
                    if t < 1: raise ValueError
                except:
                    logger.warning("Invalid alert_threshold, defaulting to 5")
                    p_config["alert_threshold"] = 5
            
            if "alert_window" in p_config:
                try:
                    w = int(p_config["alert_window"])
                    if w < 1: raise ValueError
                except:
                    logger.warning("Invalid alert_window, defaulting to 60")
                    p_config["alert_window"] = 60

        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            
        data["app_config"] = app_config
        
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
            
        logger.info(f"App configuration saved to {CONFIG_PATH}")
        
    except Exception as e:
        logger.error(f"Failed to save app configuration: {e}")
        raise
