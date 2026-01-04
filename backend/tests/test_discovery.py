
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add backend to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discovery_engine import discovery_engine

@pytest.fixture
def mock_snmp():
    with patch("discovery_engine.getCmd") as mock_get_cmd:
        yield mock_get_cmd

@pytest.fixture
def mock_ping():
    with patch("discovery_engine.ping") as mock_ping_func:
        yield mock_ping_func

@pytest.mark.asyncio
async def test_ping_sweep_finds_hosts(mock_ping):
    # Setup mock to return latency for one IP and None for others
    def side_effect(dest_addr, **kwargs):
        if dest_addr == "192.168.1.10":
            return 0.05 # 50ms
        return None
    
    mock_ping.side_effect = side_effect
    
    # We mock _probe_host to avoid SNMP logic in this specific test or rely on it failing gracefully
    # But integration test of scan_network calls both.
    # Let's mock _probe_host to return a dummy result immediately
    with patch.object(discovery_engine, '_probe_host', new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = {
            "ip": "192.168.1.10",
            "latency": 50.0,
            "hostname": "test-host",
            "vendor": "TestVendor",
            "type": "TestType",
            "snmp_enabled": False,
            "community": None
        }
        
        # Scan a small subnet
        results = await discovery_engine.scan_network("192.168.1.10/32")
        
        assert len(results) == 1
        assert results[0]["ip"] == "192.168.1.10"
        assert discovery_engine._scan_progress > 0

@pytest.mark.asyncio
async def test_snmp_identification(mock_snmp):
    # Test that _identify_device logic works
    # Mocking snmp response for Ubiquiti
    
    # Mock varBinds for Unifi
    # sysDescr, sysObjectID, sysName
    varBinds = [
        (None, "Linux 4.4.153 #1 SMP Wed Oct 23 16:09:47 CST 2019 mips64 ... Unifi-UAP-AC-Pro ..."), # sysDescr
        (None, "1.3.6.1.4.1.41112.1.4"), # sysOID
        (None, "UAP-Lobby") # sysName
    ]
    
    mock_snmp.return_value = (None, None, None, varBinds)
    
    host_info = {
        "ip": "192.168.1.20",
        "latency": 10.0
    }
    
    result = await discovery_engine._probe_host(host_info, ["public"])
    
    assert result["snmp_enabled"] is True
    assert result["vendor"] == "Ubiquiti"
    assert result["type"] == "Access Point"
    assert result["hostname"] == "UAP-Lobby"

@pytest.mark.asyncio
async def test_snmp_identification_synology(mock_snmp):
    varBinds = [
        (None, "Linux DiskStation 4.4.59+ #25556 SMP PREEMPT Mon Mar 4 14:32:20 CST 2019 x86_64 GNU/Linux synology_apollolake_918+"), 
        (None, "1.3.6.1.4.1.6574.1.2"), 
        (None, "MyNAS") 
    ]
    mock_snmp.return_value = (None, None, None, varBinds)
    
    host_info = {"ip": "192.168.1.30", "latency": 20.0}
    result = await discovery_engine._probe_host(host_info, ["public"])
    
    assert result["vendor"] == "Synology"
    assert result["type"] == "NAS"
    assert result["hostname"] == "MyNAS"
