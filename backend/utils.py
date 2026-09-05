import json
import os
import time
import logging
from sqlalchemy.orm import Session
from models import GroupDB, NodeDB, NodeMetricDB

logger = logging.getLogger("BeamState.Utils")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def _read_existing() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass  # corrupted or empty, start fresh
    return {}


def build_export(db: Session, app_config: dict | None = None) -> dict:
    """
    Serialise the database topology: groups, nodes, dependencies and metric
    configuration. app_config is carried over unchanged when given.
    """
    export = {
        "exported_at": time.time(),
        "app_config": app_config if app_config is not None else _read_existing().get("app_config", {}),
        "groups": []
    }

    for group in db.query(GroupDB).order_by(GroupDB.name).all():
        group_data = {
            "id": group.id,
            "name": group.name,
            "interval": group.interval,
            "packet_count": group.packet_count,
            "max_retries": group.max_retries,
            "enabled": group.enabled,
            "monitor_ping": group.monitor_ping,
            "monitor_snmp": group.monitor_snmp,
            "snmp_community": group.snmp_community,
            "snmp_port": group.snmp_port,
            "is_default": group.is_default,
            "nodes": []
        }

        for node in sorted(group.nodes, key=lambda n: n.name or ""):
            metrics = []
            for nm in db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node.id).all():
                if not nm.metric_definition:
                    continue
                metrics.append({
                    "definition": nm.metric_definition.name,
                    "interface_index": nm.interface_index,
                    "interface_name": nm.interface_name,
                    "collection_interval": nm.collection_interval,
                    "warning_threshold": nm.warning_threshold,
                    "critical_threshold": nm.critical_threshold,
                    "alert_condition": nm.alert_condition,
                    "alert_min_samples": nm.alert_min_samples,
                    "enabled": nm.enabled,
                })

            group_data["nodes"].append({
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
                "snmp_port": node.snmp_port,
                "notification_priority": node.notification_priority,
                "parent_id": node.parent_id,
                "metrics": metrics,
            })

        export["groups"].append(group_data)

    return export


def save_config(db: Session):
    """Export the database to config.json (the file mirrors the database)."""
    try:
        data = build_export(db)
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
        logger.info(f"Configuration exported to {CONFIG_PATH}")
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
                except (ValueError, TypeError):
                    logger.warning("Invalid alert_threshold, defaulting to 5")
                    p_config["alert_threshold"] = 5

            if "alert_window" in p_config:
                try:
                    w = int(p_config["alert_window"])
                    if w < 1: raise ValueError
                except (ValueError, TypeError):
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
