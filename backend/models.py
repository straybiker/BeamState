from pydantic import BaseModel, field_validator
from typing import Optional, List
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import re

Base = declarative_base()

# SQLAlchemy Models (DB)
class GroupDB(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    interval = Column(Integer, default=60) # Seconds between pings
    packet_count = Column(Integer, default=1) # Number of packets to send

    nodes = relationship("NodeDB", back_populates="group", cascade="all, delete-orphan")

class NodeDB(Base):
    __tablename__ = "nodes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    ip = Column(String, index=True) # IPv4
    group_id = Column(Integer, ForeignKey("groups.id"))
    
    # Overrides (if null, use group default)
    interval = Column(Integer, nullable=True)
    packet_count = Column(Integer, nullable=True)
    enabled = Column(Boolean, default=True)

    group = relationship("GroupDB", back_populates="nodes")

# Pydantic Models (API)
class NodeBase(BaseModel):
    name: str
    ip: str
    group_id: Optional[int] = None
    interval: Optional[int] = None
    packet_count: Optional[int] = None
    enabled: bool = True
    
    @field_validator('ip')
    @classmethod
    def validate_ip_address(cls, v: str) -> str:
        # Check format: must be 4 octets separated by dots
        ip_pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
        match = re.match(ip_pattern, v)
        if not match:
            raise ValueError('Invalid IP address format')
        # Check each octet is 0-255
        octets = [int(g) for g in match.groups()]
        if not all(0 <= octet <= 255 for octet in octets):
            raise ValueError('IP address octets must be between 0 and 255')
        return v

class NodeCreate(NodeBase):
    pass

class Node(NodeBase):
    id: int
    class Config:
        from_attributes = True

class GroupBase(BaseModel):
    name: str
    interval: int = 60
    packet_count: int = 1

class GroupCreate(GroupBase):
    pass

class Group(GroupBase):
    id: int
    nodes: List[Node] = []
    class Config:
        from_attributes = True
