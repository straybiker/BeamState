
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import List, Optional
import ipaddress
from discovery_engine import discovery_engine
from sqlalchemy.orm import Session
from database import get_db
from models import NodeDB, GroupDB
from utils import save_config

logger = logging.getLogger("BeamState.DiscoveryRouter")

router = APIRouter(prefix="/discovery", tags=["discovery"])

class ScanRequest(BaseModel):
    cidr: str
    communities: List[str] = ["public"]
    protocols: List[str] = ["icmp", "snmp"]

class DiscoveredDevice(BaseModel):
    ip: str
    latency: Optional[float]
    hostname: Optional[str]
    vendor: str
    type: str
    snmp_enabled: bool
    community: Optional[str]

@router.post("/scan")
async def start_scan(request: ScanRequest):
    """Start a network scan"""
    try:
        # Validate CIDR
        ipaddress.ip_network(request.cidr)
        
        # Check if already running
        if discovery_engine._scan_running:
             raise HTTPException(status_code=409, detail="Scan already in progress")

        results = await discovery_engine.scan_network(
            request.cidr, 
            request.communities,
            request.protocols
        )
        return results
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid CIDR format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
def get_status():
    """Get current scan status"""
    return {
        "running": discovery_engine._scan_running,
        "progress": discovery_engine._scan_progress,
        "total": discovery_engine._total_hosts,
        "stats": {
            "scanned": discovery_engine._stats_scanned,
            "icmp_found": discovery_engine._stats_found_icmp,
            "snmp_found": discovery_engine._stats_found_snmp
        },
        "results": discovery_engine._scan_results
    }

class ImportRequest(BaseModel):
    hosts: List[DiscoveredDevice]
    target_group_id: str
    protocols: List[str] = ["icmp", "snmp"]

@router.post("/import")
def import_nodes(request: ImportRequest, db: Session = Depends(get_db)):
    """Import discovered nodes into configuration"""
    
    # Verify group exists
    group = db.query(GroupDB).filter(GroupDB.id == request.target_group_id).first()
    if not group:
         raise HTTPException(status_code=404, detail="Target group not found")
         
    imported_count = 0
    updated_count = 0
    
    # Parse requested protocols
    use_icmp = "icmp" in request.protocols
    use_snmp = "snmp" in request.protocols
    
    try:
        for host in request.hosts:
            # Check if node IP already exists
            existing = db.query(NodeDB).filter(NodeDB.ip == host.ip).first()
            
            if existing:
                # Merge: Update existing node with new protocol info
                changed = False
                
                # If discovered SNMP AND snmp was enabled in settings, enable it and update details
                if use_snmp and host.snmp_enabled:
                    if not existing.monitor_snmp:
                        existing.monitor_snmp = True
                        changed = True
                    
                    # Always check if we found a better/different community
                    # But trust existing community if scan didn't find one
                    if host.community and host.community != existing.snmp_community:
                        existing.snmp_community = host.community
                        changed = True
                    
                    # If community was missing entirely, set default
                    if not existing.snmp_community:
                        existing.snmp_community = "public"
                        changed = True

                # If discovered ICMP (latency present) AND icmp was enabled in settings, enable ping monitoring
                if use_icmp and host.latency is not None:
                     if not existing.monitor_ping:
                         existing.monitor_ping = True
                         changed = True
                    
                # Update hostname if we found a better one
                if host.hostname and (not existing.name or existing.name == existing.ip):
                    existing.name = host.hostname
                    changed = True
                    
                if changed:
                    updated_count += 1
            else:
                # Create new node
                new_node = NodeDB(
                    name=host.hostname or host.ip,
                    ip=host.ip,
                    group_id=group.id,
                    monitor_snmp=host.snmp_enabled,
                    snmp_community=host.community or "public",
                    enabled=True
                )
                db.add(new_node)
                imported_count += 1
            
        db.commit()
        if imported_count > 0 or updated_count > 0:
            save_config(db)
            
        logger.info(f"Import complete: {imported_count} new, {updated_count} updated")
        return {
            "imported": imported_count, 
            "updated": updated_count,
            "skipped": len(request.hosts) - imported_count - updated_count
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Import failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
