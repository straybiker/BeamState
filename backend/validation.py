"""Input validation utilities for BeamState backend"""
import re
import logging

logger = logging.getLogger("BeamState.Validation")

def validate_ip_address(ip: str) -> bool:
    """Validate IPv4 address format"""
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip)
    if not match:
        logger.warning(f"Invalid IP format: {ip}")
        return False
    
    octets = [int(g) for g in match.groups()]
    if not all(0 <= octet <= 255 for octet in octets):
        logger.warning(f"IP address octets out of range: {ip}")
        return False
    
    return True

def validate_oid(oid: str, requires_index: bool = False) -> bool:
    """
    Validate SNMP OID format
    
    Args:
        oid: OID string (e.g., "1.3.6.1.2.1.1.1.0" or "1.3.6.1.2.1.2.2.1.10.{index}")
        requires_index: Whether the OID should contain {index} placeholder
    
    Returns:
        True if valid, False otherwise
    """
    # Remove {index} placeholder for validation
    oid_clean = oid.replace("{index}", "1")
    
    # Basic OID pattern: starts with digit, contains only digits and dots
    pattern = r'^\d+(\.\d+)*$'
    if not re.match(pattern, oid_clean):
        logger.warning(f"Invalid OID format: {oid}")
        return False
    
    # Check for {index} requirement
    if requires_index and "{index}" not in oid:
        logger.warning(f"OID requires {{index}} placeholder but missing: {oid}")
        return False
    
    if not requires_index and "{index}" in oid:
        logger.warning(f"OID contains {{index}} but requires_index is False: {oid}")
        return False
    
    return True

def validate_port(port: int) -> bool:
    """Validate port number is in valid range"""
    if not (1 <= port <= 65535):
        logger.warning(f"Port out of range (1-65535): {port}")
        return False
    return True

def validate_snmp_community(community: str) -> bool:
    """Validate SNMP community string"""
    if not community or len(community) > 255:
        logger.warning(f"Invalid SNMP community length: {len(community) if community else 0}")
        return False
    return True
