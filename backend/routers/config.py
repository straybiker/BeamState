from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import Group, GroupCreate, GroupDB, Node, NodeCreate, NodeDB
from utils import save_config
import uuid

import logging
logger = logging.getLogger("BeamState.Config")

router = APIRouter(prefix="/config", tags=["configuration"])

# --- GROUPS ---

@router.get("/groups", response_model=List[Group])
def read_groups(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    groups = db.query(GroupDB).offset(skip).limit(limit).all()
    return groups

@router.post("/groups", response_model=Group)
def create_group(group: GroupCreate, db: Session = Depends(get_db)):
    db_group = db.query(GroupDB).filter(GroupDB.name == group.name).first()
    if db_group:
        raise HTTPException(status_code=400, detail="Group already exists")
    
    # Generate explicit UUID if not provided by DB default? 
    # Actually DB default will handle it, but for persistence efficiency might differ 
    # But relying on DB default is fine.
    
    new_group = GroupDB(**group.model_dump())
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    
    # Sync to config.json
    save_config(db)
    
    return new_group

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
        
    db.commit()
    db.refresh(db_group)
    
    # Sync to config.json
    save_config(db)
    
    # Trigger immediate check for all nodes in group if it was just unpaused
    if was_paused and will_be_enabled:
        if hasattr(request.app.state, "pinger"):
            nodes = db.query(NodeDB).filter(NodeDB.group_id == group_id).all()
            for node in nodes:
                if node.enabled:  # Only trigger for enabled nodes
                    request.app.state.pinger.trigger_immediate_check(str(node.id))
            logger.info(f"Group {db_group.name} unpaused - triggering immediate checks for {len(nodes)} nodes")
    
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
    
    return {"ok": True}

# --- NODES ---

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
             
    new_node = NodeDB(**node.model_dump())
    db.add(new_node)
    db.commit()
    db.refresh(new_node)
    
    # Sync to config.json
    save_config(db)
    
    return new_node

@router.put("/nodes/{node_id}", response_model=Node)
def update_node(node_id: str, node: NodeCreate, request: Request, db: Session = Depends(get_db)):
    db_node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Check if node is being unpaused (enabled: false -> true)
    was_paused = db_node.enabled == False
    will_be_enabled = node.enabled == True
    
    for key, value in node.model_dump().items():
        setattr(db_node, key, value)
    
    db.commit()
    db.refresh(db_node)
    
    # Sync to config.json
    save_config(db)
    
    # Trigger immediate check if node was just unpaused
    if was_paused and will_be_enabled:
        if hasattr(request.app.state, "pinger"):
            request.app.state.pinger.trigger_immediate_check(node_id)
            logger.info(f"Node {db_node.name} unpaused - triggering immediate check")
    
    return db_node



@router.delete("/nodes/{node_id}")
def delete_node(node_id: str, request: Request, db: Session = Depends(get_db)):
    db_node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Remove from DB
    db.delete(db_node)
    db.commit()
    
    # Sync to config.json
    save_config(db)
    
    # Remove from Pinger Cache immediately
    if hasattr(request.app.state, "pinger"):
        request.app.state.pinger.remove_node(node_id)
        
    return {"ok": True}

# --- APP CONFIG ---

@router.get("/app")
def get_app_config():
    """Get current application configuration with masked secrets"""
    from storage import storage
    import copy
    
    # Deep copy to avoid modifying original
    config = copy.deepcopy(storage.config)
    
    # Mask sensitive data
    if "influxdb" in config and "token" in config["influxdb"]:
        token = config["influxdb"]["token"]
        if token and len(token) > 0:
            config["influxdb"]["token"] = "***REDACTED***"
    
    return config

@router.put("/app")
def update_app_config(config: dict, request: Request):
    """Update application configuration"""
    from utils import save_app_config
    from storage import storage
    
    # Save to file
    save_app_config(config)
    
    # Reload storage config
    storage.reload_config()
    
    return storage.config
