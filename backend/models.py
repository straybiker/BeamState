import uuid
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
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, index=True)
    interval = Column(Integer, default=60) # Seconds between pings
    packet_count = Column(Integer, default=1) # Number of packets to send
    max_retries = Column(Integer, default=4) # Number of retries before marking DOWN
    enabled = Column(Boolean, default=True)
    
    # Monitoring protocols
    monitor_ping = Column(Boolean, default=True)
    monitor_snmp = Column(Boolean, default=False)
    
    # SNMP settings
    snmp_community = Column(String, default="public")
    snmp_port = Column(Integer, default=161)
    
    # Default group for new nodes
    is_default = Column(Boolean, default=False)

    nodes = relationship("NodeDB", back_populates="group", cascade="all, delete-orphan")

class NodeDB(Base):
    __tablename__ = "nodes"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    ip = Column(String, index=True) # IPv4
    group_id = Column(String, ForeignKey("groups.id"))
    
    # Overrides (if null, use group default)
    interval = Column(Integer, nullable=True)
    packet_count = Column(Integer, nullable=True)
    max_retries = Column(Integer, nullable=True)
    enabled = Column(Boolean, default=True)
    
    # Monitoring protocol overrides
    monitor_ping = Column(Boolean, nullable=True)
    monitor_snmp = Column(Boolean, nullable=True)
    
    # SNMP overrides
    snmp_community = Column(String, nullable=True)
    snmp_port = Column(Integer, nullable=True)
    
    # Notification overrides
    notification_priority = Column(Integer, nullable=True)  # -2 to 2, None = use app default

    group = relationship("GroupDB", back_populates="nodes")
    node_metrics = relationship("NodeMetricDB", back_populates="node", cascade="all, delete-orphan")
    interfaces = relationship("NodeInterfaceDB", back_populates="node", cascade="all, delete-orphan")

class MetricDefinitionDB(Base):
    __tablename__ = "metric_definitions"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)  # e.g., "Interface Traffic In"
    oid_template = Column(String, nullable=False)  # e.g., "1.3.6.1.2.1.2.2.1.10.{index}"
    metric_type = Column(String, nullable=False)  # "counter", "gauge", "string"
    unit = Column(String, nullable=True)  # "bytes", "percent", "celsius"
    category = Column(String, nullable=True)  # "interface", "system", "poe"
    device_type = Column(String, nullable=True)  # "unifi_switch", "unifi_ap", "generic"
    requires_index = Column(Boolean, default=False)  # True if OID needs interface index
    enabled = Column(Boolean, default=True)
    
    node_metrics = relationship("NodeMetricDB", back_populates="metric_definition")

class NodeMetricDB(Base):
    __tablename__ = "node_metrics"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    node_id = Column(String, ForeignKey("nodes.id", ondelete="CASCADE"))
    metric_definition_id = Column(String, ForeignKey("metric_definitions.id"))
    interface_index = Column(Integer, nullable=True)  # For per-interface metrics
    interface_name = Column(String, nullable=True)  # e.g., "eth0", "port1"
    collection_interval = Column(Integer, default=60)  # Seconds
    enabled = Column(Boolean, default=True)
    
    node = relationship("NodeDB", back_populates="node_metrics")
    metric_definition = relationship("MetricDefinitionDB", back_populates="node_metrics")

class NodeInterfaceDB(Base):
    __tablename__ = "node_interfaces"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    node_id = Column(String, ForeignKey("nodes.id", ondelete="CASCADE"))
    index = Column(Integer, nullable=False)  # ifIndex
    name = Column(String, nullable=True)     # ifDescr
    alias = Column(String, nullable=True)    # ifAlias
    type = Column(String, nullable=True)     # ifType
    mac_address = Column(String, nullable=True) # ifPhysAddress
    admin_status = Column(String, nullable=True) # ifAdminStatus
    oper_status = Column(String, nullable=True)  # ifOperStatus
    enabled = Column(Boolean, default=False) # Monitoring enabled
    
    node = relationship("NodeDB", back_populates="interfaces")

# Pydantic Models (API)
class NodeBase(BaseModel):
    name: str
    ip: str
    group_id: Optional[str] = None
    interval: Optional[int] = None
    packet_count: Optional[int] = None
    max_retries: Optional[int] = None
    enabled: bool = True
    monitor_ping: Optional[bool] = None
    monitor_snmp: Optional[bool] = None
    snmp_community: Optional[str] = None
    snmp_port: Optional[int] = None
    notification_priority: Optional[int] = None  # -2 to 2, None = use app default
    
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
    id: str
    class Config:
        from_attributes = True

class GroupBase(BaseModel):
    name: str
    interval: int = 60
    packet_count: int = 1
    max_retries: int = 4
    enabled: bool = True
    monitor_ping: bool = True
    monitor_snmp: bool = False
    snmp_community: str = "public"
    snmp_port: int = 161
    is_default: bool = False

class GroupCreate(GroupBase):
    pass

class Group(GroupBase):
    id: str
    nodes: List[Node] = []
    class Config:
        from_attributes = True

# Pydantic models for Metric Definitions and Node Metrics
class MetricDefinitionBase(BaseModel):
    name: str
    oid_template: str
    metric_type: str  # "counter", "gauge", "string"
    unit: Optional[str] = None
    category: Optional[str] = None
    device_type: Optional[str] = None
    requires_index: bool = False
    enabled: bool = True

class MetricDefinitionCreate(MetricDefinitionBase):
    pass

class MetricDefinition(MetricDefinitionBase):
    id: str
    class Config:
        from_attributes = True

class NodeMetricBase(BaseModel):
    node_id: str
    metric_definition_id: str
    interface_index: Optional[int] = None
    interface_name: Optional[str] = None
    collection_interval: int = 60
    enabled: bool = True

class NodeMetricCreate(NodeMetricBase):
    pass

class NodeMetric(NodeMetricBase):
    id: str
    class Config:
        from_attributes = True

class NodeInterfaceBase(BaseModel):
    node_id: str
    index: int
    name: Optional[str] = None
    alias: Optional[str] = None
    type: Optional[str] = None
    mac_address: Optional[str] = None
    admin_status: Optional[str] = None
    oper_status: Optional[str] = None
    enabled: bool = False

class NodeInterface(NodeInterfaceBase):
    id: str
    class Config:
        from_attributes = True
