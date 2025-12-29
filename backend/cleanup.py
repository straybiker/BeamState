import json
import os
from sqlalchemy.orm import Session
from models import NodeDB, GroupDB
import logging

logger = logging.getLogger("BeamState.Cleanup")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def sync_with_config(db: Session):
    """
    Syncs the database with the config.json file.
    - Adds missing groups/nodes.
    - Updates existing groups/nodes.
    - REMOVES groups/nodes not present in config.json.
    """
    if not os.path.exists(CONFIG_PATH):
        logger.warning(f"Config file not found at {CONFIG_PATH}. Skipping sync.")
        return

    try:
        with open(CONFIG_PATH, 'r') as f:
            config_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        return

    logger.info("Syncing database with config.json...")
    
    # Track valid IDs to determine what to delete later
    valid_group_ids = []
    valid_node_ids = []

    # 1. Sync Groups and Nodes
    for g_data in config_data.get("groups", []):
        group_id = g_data.get("id")
        if group_id is None:
            # If no ID in config, we can't sync it properly blindly.
            # But the requirement was unique IDs not followup numbers.
            # Assuming config.json is SSOT, it MUST have IDs.
            # If not, create one?
            import uuid
            group_id = str(uuid.uuid4())
            g_data["id"] = group_id
            logger.warning(f"Group {g_data.get('name')} missing ID. Generated: {group_id}")

        group = db.query(GroupDB).filter(GroupDB.id == group_id).first()
        if not group:
            logger.info(f"Creating group: {g_data['name']} (ID: {group_id})")
            group = GroupDB(id=group_id, name=g_data["name"], max_retries=g_data.get("max_retries", 3))
            db.add(group)
        else:
            group.name = g_data["name"]
        
        # Update Group fields
        group.interval = g_data.get("interval", 60)
        group.packet_count = g_data.get("packet_count", 1)
        group.max_retries = g_data.get("max_retries", 4)
        group.enabled = g_data.get("enabled", True)
        valid_group_ids.append(group_id)
        db.flush() # Ensure group exists for FKs

        # Sync Nodes for this Group
        for n_data in g_data.get("nodes", []):
            node_id = n_data.get("id")
            if node_id is None:
                import uuid
                node_id = str(uuid.uuid4())
                n_data["id"] = node_id
                logger.warning(f"Node {n_data.get('name')} missing ID. Generated: {node_id}")

            node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
            if not node:
                logger.info(f"Creating node: {n_data['name']} (ID: {node_id}) in {group.name}")
                node = NodeDB(id=node_id, name=n_data["name"], group_id=group.id)
                db.add(node)
            else:
                node.name = n_data["name"]
                node.group_id = group.id # Allow moving nodes between groups
            
            # Update Node fields
            node.ip = n_data["ip"]
            node.interval = n_data.get("interval")
            node.packet_count = n_data.get("packet_count")
            node.enabled = n_data.get("enabled", True)
            valid_node_ids.append(node_id)

    db.commit()

    # 2. Cleanup Orphans (Nodes first, then Groups)
    
    # Delete invalid nodes
    all_nodes = db.query(NodeDB).all()
    for n in all_nodes:
        if n.id not in valid_node_ids:
            logger.info(f"Deleting stale node: {n.name} (ID: {n.id})")
            db.delete(n)
    
    db.commit() # Commit node deletions first to satisfy foreign keys if any? (Cascade usually handles but safer)

    # Delete invalid groups
    all_groups = db.query(GroupDB).all()
    for g in all_groups:
        if g.id not in valid_group_ids:
            logger.info(f"Deleting stale group: {g.name} (ID: {g.id})")
            db.delete(g)
    
    db.commit()
    logger.info("Database sync complete.")
