from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from models import Group, GroupCreate, GroupDB, Node, NodeCreate, NodeDB
from utils import save_config
from broadcast import status_stream
import uuid


def _config_changed():
    """Tell dashboard clients to refetch groups, nodes and app settings."""
    status_stream.publish({"type": "config"})

import logging
logger = logging.getLogger("BeamState.Config")

router = APIRouter(prefix="/config", tags=["configuration"])

# --- GROUPS ---

@router.get("/groups", response_model=List[Group])
def read_groups(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    try:
        groups = db.query(GroupDB).offset(skip).limit(limit).all()
        logger.debug(f"Fetched {len(groups)} groups")
        return groups
    except Exception as e:
        logger.error(f"Failed to fetch groups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load groups: {str(e)}")

@router.post("/groups", response_model=Group)
def create_group(group: GroupCreate, db: Session = Depends(get_db)):
    try:
        db_group = db.query(GroupDB).filter(GroupDB.name == group.name).first()
        if db_group:
            raise HTTPException(status_code=400, detail="Group already exists")
        
        new_group = GroupDB(**group.model_dump())
        db.add(new_group)
        db.commit()
        db.refresh(new_group)
        
        # Sync to config.json
        save_config(db)
        _config_changed()
        logger.info(f"Created group: {new_group.name} (ID: {new_group.id})")
        
        return new_group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create group '{group.name}': {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create group: {str(e)}")

@router.put("/groups/{group_id}", response_model=Group)
def update_group(group_id: str, group: GroupCreate, request: Request, db: Session = Depends(get_db)):
    db_group = db.query(GroupDB).filter(GroupDB.id == group_id).first()
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if group is being unpaused (enabled: false -> true)
    was_paused = db_group.enabled == False
    will_be_enabled = group.enabled == True
    
    # Update fields
    for key, value in group.model_dump().items():
        setattr(db_group, key, value)
    
    # If this group is being set as default, clear is_default from all other groups
    if group.is_default:
        db.query(GroupDB).filter(GroupDB.id != group_id).update({GroupDB.is_default: False})
        
    db.commit()
    db.refresh(db_group)
    
    # Sync to config.json
    save_config(db)
    _config_changed()
    
    # Trigger immediate check for all nodes in group if it was just unpaused
    # Trigger immediate check (unpause) or set status (pause)
    if hasattr(request.app.state, "pinger"):
        if was_paused and will_be_enabled:
            # Unpausing: Trigger immediate checks
            nodes = db.query(NodeDB).filter(NodeDB.group_id == group_id).all()
            for node in nodes:
                if node.enabled:  # Only trigger for enabled nodes
                    request.app.state.pinger.trigger_immediate_check(str(node.id))
            logger.info(f"Group {db_group.name} unpaused - triggering immediate checks for {len(nodes)} nodes")
        
        elif not will_be_enabled and (not was_paused): # Just paused
             # Pausing: Set status immediately
             nodes = db.query(NodeDB).filter(NodeDB.group_id == group_id).all()
             for node in nodes:
                 # We must ensure the node object has the group loaded/associated for the helper to work
                 node.group = db_group 
                 request.app.state.pinger.set_paused(node)
    
    return db_group

@router.delete("/groups/{group_id}")
def delete_group(group_id: str, request: Request, db: Session = Depends(get_db)):
    group = db.query(GroupDB).filter(GroupDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Explicitly delete nodes first to ensure clean removal
    nodes = db.query(NodeDB).filter(NodeDB.group_id == group_id).all()
    for node in nodes:
        # Also remove from pinger cache if needed
        if hasattr(request.app.state, "pinger"):
            request.app.state.pinger.remove_node(node.id)
        db.delete(node)
        
    db.delete(group)
    db.commit()
    
    # Sync to config.json
    save_config(db)
    _config_changed()
    
    return {"ok": True}

# --- NODES ---

def _validate_parent(db: Session, node_id: Optional[str], parent_id: Optional[str]):
    """Parent must exist, differ from the node, and not create a cycle."""
    if not parent_id:
        return
    if node_id and parent_id == node_id:
        raise HTTPException(status_code=400, detail="A node cannot be its own parent")
    parent = db.query(NodeDB).filter(NodeDB.id == parent_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent node not found")
    seen = set()
    current = parent
    while current is not None and current.id not in seen:
        if node_id and current.parent_id == node_id:
            raise HTTPException(status_code=400, detail=f"Dependency cycle: {parent.name} already depends on this node")
        seen.add(current.id)
        current = current.parent

@router.get("/nodes", response_model=List[Node])
def read_nodes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    nodes = db.query(NodeDB).offset(skip).limit(limit).all()
    return nodes

@router.post("/nodes", response_model=Node)
def create_node(node: NodeCreate, db: Session = Depends(get_db)):
    # IP validation is handled by Pydantic model (NodeCreate.validate_ip_address)
    
    if node.group_id:
        group = db.query(GroupDB).filter(GroupDB.id == node.group_id).first()
        if not group:
             raise HTTPException(status_code=404, detail="Group not found")

    _validate_parent(db, None, node.parent_id)
    new_node = NodeDB(**node.model_dump())
    db.add(new_node)
    db.commit()
    db.refresh(new_node)
    
    # Sync to config.json
    save_config(db)
    _config_changed()
    
    return new_node

@router.put("/nodes/{node_id}", response_model=Node)
def update_node(node_id: str, node: NodeCreate, request: Request, db: Session = Depends(get_db)):
    db_node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Check if node is being unpaused (enabled: false -> true)
    was_paused = db_node.enabled == False
    will_be_enabled = node.enabled == True

    _validate_parent(db, node_id, node.parent_id)
    for key, value in node.model_dump().items():
        setattr(db_node, key, value)
    
    db.commit()
    db.refresh(db_node)
    
    # Sync to config.json
    save_config(db)
    _config_changed()
    
    # Trigger immediate check if node was just unpaused
    # Trigger immediate check (unpause) or set status (pause)
    if hasattr(request.app.state, "pinger"):
        if was_paused and will_be_enabled:
            request.app.state.pinger.trigger_immediate_check(node_id)
            logger.info(f"Node {db_node.name} unpaused - triggering immediate check")
        elif not will_be_enabled and (not was_paused):
            # Ensure group is loaded
            if not db_node.group:
                 db_node.group = db.query(GroupDB).filter(GroupDB.id == db_node.group_id).first()
            request.app.state.pinger.set_paused(db_node)
    
    return db_node



@router.delete("/nodes/{node_id}")
def delete_node(node_id: str, request: Request, db: Session = Depends(get_db)):
    db_node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Children lose their dependency (SQLite does not enforce ON DELETE SET NULL by default)
    db.query(NodeDB).filter(NodeDB.parent_id == node_id).update({NodeDB.parent_id: None})

    # Remove from DB
    db.delete(db_node)
    db.commit()
    
    # Sync to config.json
    save_config(db)
    _config_changed()
    
    # Remove from Pinger Cache immediately
    if hasattr(request.app.state, "pinger"):
        request.app.state.pinger.remove_node(node_id)
        
    return {"ok": True}

# --- EXPORT / IMPORT (backup and restore) ---

@router.get("/export")
def export_config(db: Session = Depends(get_db)):
    """Full topology export: groups, nodes, dependencies, metric configuration. Secrets excluded."""
    from utils import build_export
    return build_export(db, app_config={})

@router.post("/import")
def import_config_endpoint(payload: dict, request: Request, db: Session = Depends(get_db)):
    """
    Upsert topology from an export. Nothing is deleted. Nodes with a 'metrics'
    list get their metric configuration replaced.
    """
    from cleanup import import_config
    if not isinstance(payload.get("groups"), list):
        raise HTTPException(status_code=400, detail="Payload must contain a 'groups' list")
    try:
        counts = import_config(db, payload)
    except Exception as e:
        db.rollback()
        logger.error(f"Import failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")
    save_config(db)
    _config_changed()
    return counts

# --- APP CONFIG ---

@router.get("/app")
def get_app_config():
    """Get current application configuration with masked secrets"""
    try:
        from storage import storage
        import copy
        
        # Deep copy to avoid modifying original
        config = copy.deepcopy(storage.config)
        
        # Mask sensitive data
        if "influxdb" in config and "token" in config["influxdb"]:
            token = config["influxdb"]["token"]
            if token and len(token) > 0:
                config["influxdb"]["token"] = "***REDACTED***"

        # Webhook and heartbeat URLs often embed a token (ntfy, Healthchecks.io)
        for section in ("webhook", "heartbeat"):
            if config.get(section, {}).get("url"):
                config[section]["url"] = "***REDACTED***"

        if "pushover" in config:
            if "token" in config["pushover"] and config["pushover"]["token"]:
                config["pushover"]["token"] = "***REDACTED***"
            if "user_key" in config["pushover"] and config["pushover"]["user_key"]:
                config["pushover"]["user_key"] = "***REDACTED***"
        
        logger.debug("App config fetched successfully")
        return config
    except Exception as e:
        logger.error(f"Failed to fetch app config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load configuration: {str(e)}")

@router.put("/app")
def update_app_config(config: dict, request: Request):
    """Update application configuration"""
    try:
        from utils import save_app_config
        from storage import storage
        
        # Restore secrets if redacted
        current_config = storage.config
        
        # InfluxDB
        if "influxdb" in config and config["influxdb"].get("token") == "***REDACTED***":
            config["influxdb"]["token"] = current_config.get("influxdb", {}).get("token", "")
            
        # Pushover
        if "pushover" in config:
            if config["pushover"].get("token") == "***REDACTED***":
                 config["pushover"]["token"] = current_config.get("pushover", {}).get("token", "")
            if config["pushover"].get("user_key") == "***REDACTED***":
                 config["pushover"]["user_key"] = current_config.get("pushover", {}).get("user_key", "")

        for section in ("webhook", "heartbeat"):
            if config.get(section, {}).get("url") == "***REDACTED***":
                config[section]["url"] = current_config.get(section, {}).get("url", "")

        # Save to file
        save_app_config(config)
        
        # Reload storage config
        storage.reload_config()
        _config_changed()
        
        logger.info(f"App config updated. Pushover enabled? {storage.config.get('pushover', {}).get('enabled')}")
        
        # Return masked config to prevent secret leakage
        return get_app_config()
    except Exception as e:
        logger.error(f"Failed to update app config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")
