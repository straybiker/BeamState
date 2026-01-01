"""SNMP monitoring implementation"""
import asyncio
import logging
import time
from typing import Optional, Tuple
from pysnmp.hlapi.asyncio import *
from .base import BaseMonitor, MonitorResult

logger = logging.getLogger("BeamState.SNMPMonitor")


class SNMPMonitor(BaseMonitor):
    """SNMP v2c health check monitor"""
    
    # OID for sysUpTime (1.3.6.1.2.1.1.3.0)
    SYS_UPTIME_OID = ObjectIdentity('1.3.6.1.2.1.1.3.0')
    
    async def check(self, ip: str, community: str = "public", port: int = 161, timeout: int = 5) -> MonitorResult:
        """
        Perform SNMP health check by querying sysUpTime.
        
        Args:
            ip: Target IP address
            community: SNMP community string
            port: SNMP port (default 161)
            timeout: Timeout in seconds
            
        Returns:
            MonitorResult with success/failure and latency
        """
        start_time = time.time()
        
        try:
            # Perform SNMP GET
            uptime, error = await self._snmp_get(ip, community, self.SYS_UPTIME_OID, port, timeout)
            
            latency_ms = (time.time() - start_time) * 1000
            
            if error:
                logger.debug(f"SNMP check failed for {ip}: {error}")
                return MonitorResult(
                    success=False,
                    latency_ms=None,
                    protocol="snmp",
                    raw_data={},
                    error=error
                )
            
            logger.debug(f"SNMP check succeeded for {ip}, uptime: {uptime}")
            return MonitorResult(
                success=True,
                latency_ms=round(latency_ms, 2),
                protocol="snmp",
                raw_data={"uptime_ticks": uptime}
            )
            
        except Exception as e:
            logger.error(f"SNMP check exception for {ip}: {e}")
            return MonitorResult(
                success=False,
                latency_ms=None,
                protocol="snmp",
                raw_data={},
                error=str(e)
            )
    
    async def _snmp_get(self, ip: str, community: str, oid: ObjectIdentity, port: int, timeout: int) -> Tuple[Optional[int], Optional[str]]:
        """
        Perform SNMP GET operation.
        
        Returns:
            Tuple of (value, error_message)
        """
        try:
            iterator = getCmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1),  # SNMPv2c
                UdpTransportTarget((ip, port), timeout=timeout, retries=0),
                ContextData(),
                ObjectType(oid)
            )
            
            errorIndication, errorStatus, errorIndex, varBinds = await iterator
            
            if errorIndication:
                return None, str(errorIndication)
            elif errorStatus:
                return None, f"{errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}"
            else:
                # Extract value from varBinds
                for varBind in varBinds:
                    value = varBind[1]
                    return int(value), None
                    
        except Exception as e:
            return None, f"SNMP exception: {str(e)}"
        
        return None, "No data returned"
