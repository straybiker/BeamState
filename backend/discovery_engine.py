
import asyncio
import logging
import ipaddress
import socket
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from ping3 import ping
from pysnmp.hlapi.asyncio import *

logger = logging.getLogger("BeamState.Discovery")

class DiscoveryEngine:
    """Network discovery engine using ICMP and SNMP"""
    
    def __init__(self):
        self.snmp_engine = SnmpEngine()
        self._scan_running = False
        self._scan_results = []
        # Stats
        self._scan_progress = 0
        self._total_hosts = 0
        self._stats_scanned = 0
        self._stats_found_icmp = 0
        self._stats_found_snmp = 0
    
    async def scan_network(self, cidr: str, communities: List[str] = ["public"], protocols: List[str] = ["icmp", "snmp"]) -> List[Dict]:
        """
        Scan a network CIDR for active hosts.
        
        Args:
            cidr: Network in CIDR notation (e.g., 192.168.1.0/24)
            communities: List of SNMP community strings to try
            protocols: List of protocols to use ["icmp", "snmp"]
            
        Returns:
            List of discovered devices
        """
        if self._scan_running:
            raise Exception("Scan already in progress")
            
        self._scan_running = True
        self._scan_results = []
        self._scan_progress = 0
        self._stats_scanned = 0
        self._stats_found_icmp = 0
        self._stats_found_snmp = 0
        
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            hosts = list(network.hosts())
            self._total_hosts = len(hosts)
            
            logger.info(f"Starting discovery scan for {cidr} ({len(hosts)} hosts) protocols={protocols}")
            
            # Filter protocols
            use_icmp = "icmp" in protocols
            use_snmp = "snmp" in protocols
            
            if not use_icmp and not use_snmp:
                 return []
            
            # If ICMP is disabled, we must try SNMP on ALL hosts (slower)
            # If ICMP is enabled, we ping first, then SNMP only on responders
            
            active_hosts = []
            
            # Chunk processing
            chunk_size = 50
            
            for i in range(0, len(hosts), chunk_size):
                chunk = hosts[i:i+chunk_size]
                
                # Step 1: Identification (ICMP OR direct assumption)
                chunk_active = []
                
                if use_icmp:
                    # Ping Sweep
                    tasks = [self._ping_host(str(ip)) for ip in chunk]
                    results = await asyncio.gather(*tasks)
                    
                    for ip, latency in results:
                        self._scan_progress += 1
                        self._stats_scanned += 1
                        # Strictly check for numeric latency (ping3 returns False on error)
                        if latency is not None and latency is not False:
                            self._stats_found_icmp += 1
                            chunk_active.append({"ip": ip, "latency": latency})
                else:
                    # No ICMP, assume all are active/candidates for SNMP
                    # We fake "active" so the loop continues to SNMP
                    for ip in chunk:
                         self._scan_progress += 1
                         self._stats_scanned += 1
                         chunk_active.append({"ip": str(ip), "latency": None})
                
                # Step 2: SNMP Probe
                if use_snmp and chunk_active:
                     probe_tasks = [self._probe_host(h, communities) for h in chunk_active]
                     probe_results = await asyncio.gather(*probe_tasks)
                     
                     for res in probe_results:
                         if res["snmp_enabled"]:
                             self._stats_found_snmp += 1
                         
                         # Decision to include in results:
                         # - If ICMP was used and found it -> Include (even if no SNMP)
                         # - If only SNMP was used -> Include ONLY if SNMP found it
                         
                         if use_icmp and res["latency"] is not None:
                             self._scan_results.append(res)
                         elif not use_icmp and res["snmp_enabled"]:
                              self._scan_results.append(res)
                
                elif use_icmp:
                    # ICMP only, just add what we found
                     for host in chunk_active:
                         # convert to full result dict (stub)
                         self._scan_results.append({
                             "ip": host["ip"], 
                             "latency": host["latency"],
                             "hostname": None, 
                             "vendor": "Unknown", 
                             "type": "Generic", 
                             "snmp_enabled": False, 
                             "community": None
                         })

            return self._scan_results
            
        except Exception as e:
            logger.error(f"Discovery scan failed: {e}")
            raise
        finally:
            self._scan_running = False

    async def _ping_host(self, ip: str) -> Tuple[str, Optional[float]]:
        """Ping a single host using ping3 in a thread"""
        try:
            loop = asyncio.get_running_loop()
            # Run blocking ping in thread pool
            latency = await loop.run_in_executor(
                None, 
                lambda: ping(ip, timeout=1, unit='ms')
            )
            # ping3 returns False on error, None on timeout
            if latency is False:
                latency = None
                
            return ip, latency
        except Exception:
            return ip, None

    async def _probe_host(self, host: Dict, communities: List[str]) -> Dict:
        """Probe a host for SNMP details"""
        ip = host["ip"]
        result = {
            "ip": ip,
            "latency": host["latency"],
            "hostname": None,
            "vendor": "Unknown",
            "type": "Generic",
            "snmp_enabled": False,
            "community": None
        }
        
        # Try DNS/NetBIOS resolution first (basic)
        try:
            result["hostname"] = await self._resolve_hostname(ip)
        except Exception:
            pass

        # Try SNMP
        for community in communities:
            try:
                # Get sysDescr (1.3.6.1.2.1.1.1.0) and sysObjectID (1.3.6.1.2.1.1.2.0)
                errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                    self.snmp_engine,
                    CommunityData(community, mpModel=1),
                    UdpTransportTarget((ip, 161), timeout=1.5, retries=1),
                    ContextData(),
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')), # sysDescr
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.1.2.0')), # sysObjectID
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.1.5.0'))  # sysName
                )
                
                if not errorIndication and not errorStatus:
                    result["snmp_enabled"] = True
                    result["community"] = community
                    
                    sys_descr = str(varBinds[0][1])
                    sys_oid = str(varBinds[1][1])
                    sys_name = str(varBinds[2][1])
                    
                    # Update hostname if sysName is better
                    if sys_name and sys_name != "None" and not result["hostname"]:
                        result["hostname"] = sys_name

                    # Identify Vendor/Type
                    result["vendor"], result["type"] = self._identify_device(sys_descr, sys_oid)
                    break # Found working community
                    
            except Exception as e:
                pass
                
        return result

    async def _resolve_hostname(self, ip: str) -> Optional[str]:
        """Resolve hostname via DNS"""
        try:
            loop = asyncio.get_running_loop()
            name, _, _ = await loop.run_in_executor(None, lambda: socket.gethostbyaddr(ip))
            return name
        except Exception:
            return None

    def _identify_device(self, descr: str, oid: str) -> Tuple[str, str]:
        """Heuristic to identify device vendor and type based on SNMP data"""
        descr_lower = descr.lower()
        
        # Vendors
        vendor = "Unknown"
        if "linux" in descr_lower: vendor = "Linux"
        if "windows" in descr_lower: vendor = "Windows"
        if "synology" in descr_lower: vendor = "Synology"
        if "ubiquiti" in descr_lower or "unifi" in descr_lower or "uap" in descr_lower: vendor = "Ubiquiti"
        if "cisco" in descr_lower: vendor = "Cisco"
        if "hp" in descr_lower or "procurve" in descr_lower: vendor = "HP"
        if "mikrotik" in descr_lower: vendor = "MikroTik"
        
        # Types
        dtype = "Device"
        if "linux" in descr_lower: dtype = "Server"
        if "nas" in descr_lower or "synology" in descr_lower: dtype = "NAS"
        if "switch" in descr_lower: dtype = "Switch"
        if "uap" in descr_lower or "access point" in descr_lower: dtype = "Access Point"
        if "printer" in descr_lower: dtype = "Printer"
        
        return vendor, dtype

# Global instance
discovery_engine = DiscoveryEngine()
