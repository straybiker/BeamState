from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import Group, GroupCreate, GroupDB, Node, NodeCreate, NodeDB

import logging
logger = logging.getLogger("NetSentry.Config")

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
    new_group = GroupDB(**group.dict())
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group

@router.delete("/groups/{group_id}")
def delete_group(group_id: int, request: Request, db: Session = Depends(get_db)):
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
             
    new_node = NodeDB(**node.dict())
    db.add(new_node)
    db.commit()
    db.refresh(new_node)
    return new_node

@router.put("/nodes/{node_id}", response_model=Node)
def update_node(node_id: int, node: NodeCreate, db: Session = Depends(get_db)):
    db_node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    for key, value in node.dict().items():
        setattr(db_node, key, value)
    
    db.commit()
    db.refresh(db_node)
    return db_node



@router.delete("/nodes/{node_id}")
def delete_node(node_id: int, request: Request, db: Session = Depends(get_db)):
    db_node = db.query(NodeDB).filter(NodeDB.id == node_id).first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Remove from DB
    db.delete(db_node)
    db.commit()
    
    # Remove from Pinger Cache immediately
    if hasattr(request.app.state, "pinger"):
        request.app.state.pinger.remove_node(node_id)
        
    return {"ok": True}
