"""Ping monitoring implementation"""
import asyncio
import logging
import time
from typing import Tuple, List, Optional
from ping3 import ping
from .base import BaseMonitor, MonitorResult

logger = logging.getLogger("BeamState.PingMonitor")


class PingMonitor(BaseMonitor):
    """ICMP ping health check monitor"""
    
    async def check(self, ip: str, count: int = 1, timeout: int = 5) -> MonitorResult:
        """
        Perform ICMP ping check.
        
        Args:
            ip: Target IP address
            count: Number of ping packets
            timeout: Timeout in seconds
            
        Returns:
            MonitorResult with success/failure and latency
        """
        latency, packet_loss, raw_responses = await self.ping_ip(ip, count, timeout)
        
        success = packet_loss < 100
        
        return MonitorResult(
            success=success,
            latency_ms=latency,
            protocol="icmp",
            raw_data={
                "packet_loss": packet_loss,
                "responses": raw_responses
            }
        )
    
    async def ping_ip(self, ip: str, count: int = 1, timeout: int = 2) -> Tuple[Optional[float], float, List]:
        """
        Perform ICMP ping (moved from node_pinger.py).
        
        Returns:
            Tuple of (avg_latency_ms, packet_loss_percent, raw_responses)
        """
        success_count = 0
        total_latency = 0.0
        raw_responses = []
        
        for _ in range(count):
            try:
                # ping3.ping returns latency in seconds, None on timeout, or False on error
                latency_sec = ping(ip, timeout=timeout)
                raw_responses.append(latency_sec)
                if latency_sec is not None and latency_sec is not False:
                    total_latency += latency_sec * 1000  # to ms
                    success_count += 1
                else:
                    logger.debug(f"Ping returned {latency_sec} for {ip}")
            except Exception as e:
                logger.debug(f"Ping error for {ip}: {e}")
                raw_responses.append(f"Exception: {str(e)}")
            
            # Small delay between packets if count > 1
            if count > 1:
                await asyncio.sleep(0.5)

        if success_count == 0:
            return None, 100.0, raw_responses  # No response, 100% loss
        
        avg_latency = total_latency / success_count
        packet_loss = ((count - success_count) / count) * 100.0
        
        return avg_latency, packet_loss, raw_responses
