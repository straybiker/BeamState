"""Base classes for monitoring protocols"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class MonitorResult:
    """Standardized result from any monitor"""
    success: bool
    latency_ms: Optional[float]
    protocol: str  # "icmp", "snmp"
    raw_data: Dict[str, Any]
    error: Optional[str] = None


class BaseMonitor:
    """Base class for all monitors"""
    
    async def check(self, ip: str, **kwargs) -> MonitorResult:
        """
        Perform health check on the given IP.
        Returns MonitorResult with success/failure and latency.
        """
        raise NotImplementedError("Subclasses must implement check()")
