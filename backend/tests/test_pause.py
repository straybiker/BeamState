
import unittest
import asyncio
import sys
import os
from unittest.mock import MagicMock

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from monitor_manager import MonitorManager
from models import NodeDB, GroupDB

# Mock database objects
def create_mock_node(node_id, name, ip, enabled=True, group_id=1):
    node = MagicMock(spec=NodeDB)
    node.id = node_id
    node.name = name
    node.ip = ip
    node.enabled = enabled
    node.group_id = group_id
    
    group = MagicMock(spec=GroupDB)
    group.id = group_id
    group.name = "TestGroup"
    group.enabled = True
    node.group = group
    
    # Defaults
    node.interval = 60
    node.packet_count = 3
    node.max_retries = 3
    node.monitor_ping = True
    node.monitor_snmp = False
    
    return node

class TestPauseLogic(unittest.IsolatedAsyncioTestCase):
    
    async def test_pause_immediate_update(self):
        """Test that set_paused updates status immediately"""
        print("\nRunning test_pause_immediate_update...")
        manager = MonitorManager()
        node = create_mock_node(1, "TestNode", "192.168.1.1")
        
        # 1. Simulate initial state (UP)
        manager.latest_results[1] = {
            "node_id": 1, 
            "status": "UP", 
            "timestamp": 12345
        }
        
        # 2. Call set_paused
        print("Pausing node...")
        manager.set_paused(node)
        
        # 3. Check status
        result = manager.latest_results.get(1)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "PAUSED")
        print("Success: Node status is IMMEDIATELY set to PAUSED")

    async def test_unpause_immediate_trigger(self):
        """Test that trigger_immediate_check prepares node for check"""
        print("\nRunning test_unpause_immediate_trigger...")
        manager = MonitorManager()
        node_id = "1"
        
        # 1. Ensure node is NOT in ping cache
        if 1 in manager.last_ping_time:
            del manager.last_ping_time[1]
            
        # 2. Unpause (trigger immediate check)
        print("Unpausing node (triggering check)...")
        manager.trigger_immediate_check(node_id)
        
        # 3. Verify it was added to cache with 0 timestamp
        self.assertIn(1, manager.last_ping_time)
        self.assertEqual(manager.last_ping_time[1], 0)
        print("Success: Node scheduled for immediate check (timestamp=0)")

if __name__ == "__main__":
    with open("test_result.txt", "w") as f:
        runner = unittest.TextTestRunner(stream=f, verbosity=2)
        unittest.main(testRunner=runner, exit=False)
