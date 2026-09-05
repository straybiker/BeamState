"""
Topology persistence: the database is the source of truth.

config.json is an export of the database (groups, nodes, dependencies and
metric configuration). It is rewritten after every change through the API and
at startup, so the file on disk always mirrors the database and doubles as a
backup you can copy to another host.

Importing from the file happens only when should_import_config() says so. An
import upserts: it adds and updates, it never deletes anything from the
database.
"""
import json
import os
import uuid
import logging
from sqlalchemy.orm import Session
from models import NodeDB, GroupDB, NodeMetricDB, MetricDefinitionDB
from utils import save_config

logger = logging.getLogger("BeamState.Cleanup")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config_file() -> dict | None:
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        return None


def should_import_config(db: Session, config_data: dict) -> bool:
    """
    Decide whether the topology in config.json must be imported into the
    database at startup.

    The database is authoritative, so this should be the exception, not the
    rule. Typical cases where an import is wanted:
    - first start with an empty database (bootstrap from the file)
    - a file restored from a backup or edited by hand on the host

    Return True to import (upsert, no deletes), False to leave the database as it is.
    Available inputs: `db` (SQLAlchemy session), `config_data` (parsed config.json).
    Hint: `config_data.get("groups", [])`, `db.query(GroupDB).count()`, and the file's
    mtime via `os.path.getmtime(CONFIG_PATH)` compared to the timestamp the export
    writes into `config_data.get("exported_at")`.
    """
    # 1. Explicit request: {"import": true} in the file (the export never writes this key)
    if config_data.get("import") is True:
        logger.info("Import policy: explicit 'import' flag found in config.json")
        return True

    # 2. Bootstrap: empty database, seed it from the file
    if db.query(GroupDB).count() == 0 and config_data.get("groups"):
        logger.info("Import policy: database is empty, bootstrapping from config.json")
        return True

    # 3. File changed after BeamState last exported it (hand edit or restored backup).
    #    A file without exported_at predates the export format and is imported once.
    try:
        modified = os.path.getmtime(CONFIG_PATH)
    except OSError:
        return False
    exported_at = float(config_data.get("exported_at") or 0)
    if modified > exported_at + 5:
        logger.info("Import policy: config.json modified after last export, importing")
        return True

    return False


def import_config(db: Session, config_data: dict, replace_metrics: bool = True) -> dict:
    """
    Upsert groups, nodes, dependencies and metric configuration from a config
    dict. Nothing is deleted. Returns counts of what was created or updated.
    """
    counts = {"groups_created": 0, "groups_updated": 0, "nodes_created": 0, "nodes_updated": 0, "metrics": 0, "skipped_metrics": 0}
    node_ids_in_file = []

    for g_data in config_data.get("groups", []):
        group_id = g_data.get("id") or str(uuid.uuid4())
        g_data["id"] = group_id

        group = db.query(GroupDB).filter(GroupDB.id == group_id).first()
        if not group:
            group = GroupDB(id=group_id, name=g_data["name"])
            db.add(group)
            counts["groups_created"] += 1
            logger.info(f"Import: creating group {g_data['name']} ({group_id})")
        else:
            counts["groups_updated"] += 1

        group.name = g_data["name"]
        group.interval = g_data.get("interval", 60)
        group.packet_count = g_data.get("packet_count", 1)
        group.max_retries = g_data.get("max_retries", 4)
        group.enabled = g_data.get("enabled", True)
        group.monitor_ping = g_data.get("monitor_ping", True)
        group.monitor_snmp = g_data.get("monitor_snmp", False)
        group.snmp_community = g_data.get("snmp_community", "public")
        group.snmp_port = g_data.get("snmp_port", 161)
        group.is_default = g_data.get("is_default", False)
        db.flush()

        for n_data in g_data.get("nodes", []):
            node_id = n_data.get("id") or str(uuid.uuid4())
            n_data["id"] = node_id
            node_ids_in_file.append(node_id)

            node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
            if not node:
                node = NodeDB(id=node_id, name=n_data["name"], group_id=group.id)
                db.add(node)
                counts["nodes_created"] += 1
                logger.info(f"Import: creating node {n_data['name']} ({node_id}) in {group.name}")
            else:
                counts["nodes_updated"] += 1

            node.name = n_data["name"]
            node.group_id = group.id
            node.ip = n_data["ip"]
            node.interval = n_data.get("interval")
            node.packet_count = n_data.get("packet_count")
            node.max_retries = n_data.get("max_retries")
            node.notification_priority = n_data.get("notification_priority")
            node.enabled = n_data.get("enabled", True)
            node.monitor_ping = n_data.get("monitor_ping")
            node.monitor_snmp = n_data.get("monitor_snmp")
            node.snmp_community = n_data.get("snmp_community")
            node.snmp_port = n_data.get("snmp_port")

    db.commit()

    # Parents: resolved after every node exists so forward references work
    for g_data in config_data.get("groups", []):
        for n_data in g_data.get("nodes", []):
            node = db.query(NodeDB).filter(NodeDB.id == n_data["id"]).first()
            if node is None:
                continue
            parent_id = n_data.get("parent_id")
            if parent_id and parent_id != node.id and db.query(NodeDB).filter(NodeDB.id == parent_id).first():
                node.parent_id = parent_id
            else:
                if parent_id:
                    logger.warning(f"Import: node {node.name}: parent {parent_id} not found, clearing dependency")
                node.parent_id = None
    db.commit()

    # Metric configuration, matched to definitions by name
    if replace_metrics:
        definitions = {d.name: d for d in db.query(MetricDefinitionDB).all()}
        for g_data in config_data.get("groups", []):
            for n_data in g_data.get("nodes", []):
                if "metrics" not in n_data:
                    continue
                node_id = n_data["id"]
                db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node_id).delete()
                for m in n_data["metrics"]:
                    definition = definitions.get(m.get("definition"))
                    if not definition:
                        counts["skipped_metrics"] += 1
                        logger.warning(f"Import: unknown metric definition '{m.get('definition')}' for node {n_data['name']}, skipped")
                        continue
                    db.add(NodeMetricDB(
                        node_id=node_id,
                        metric_definition_id=definition.id,
                        interface_index=m.get("interface_index"),
                        interface_name=m.get("interface_name"),
                        collection_interval=m.get("collection_interval", 60),
                        warning_threshold=m.get("warning_threshold"),
                        critical_threshold=m.get("critical_threshold"),
                        alert_condition=m.get("alert_condition", "gt"),
                        alert_min_samples=m.get("alert_min_samples", 1),
                        alert_enabled=True,
                        enabled=m.get("enabled", True),
                    ))
                    counts["metrics"] += 1
        db.commit()

    logger.info(f"Import complete: {counts}")
    return counts


def sync_with_config(db: Session):
    """
    Startup reconciliation. Imports from config.json only when the policy says
    so, then exports the database so the file mirrors it.
    """
    config_data = load_config_file()
    if config_data is None:
        logger.warning(f"Config file not found at {CONFIG_PATH}. Exporting database to create it.")
        save_config(db)
        return

    try:
        do_import = should_import_config(db, config_data)
    except NotImplementedError as e:
        logger.warning(f"Import policy missing ({e}). Database left unchanged.")
        do_import = False

    if do_import:
        logger.info("Importing topology from config.json...")
        import_config(db, config_data)

    save_config(db)
