import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("TESTING", "1")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from monitor_manager import MonitorManager  # noqa: E402
from models import NodeDB, GroupDB  # noqa: E402


def create_mock_node(node_id, name, ip, enabled=True, group_id="g1"):
    node = MagicMock(spec=NodeDB)
    node.id = node_id
    node.name = name
    node.ip = ip
    node.enabled = enabled
    node.group_id = group_id
    node.node_metrics = []

    group = MagicMock(spec=GroupDB)
    group.id = group_id
    group.name = "TestGroup"
    group.enabled = True
    node.group = group

    node.interval = 60
    node.packet_count = 3
    node.max_retries = 3
    node.monitor_ping = True
    node.monitor_snmp = False
    return node


class TestPauseLogic(unittest.IsolatedAsyncioTestCase):

    async def test_pause_immediate_update(self):
        """set_paused updates the cached status immediately and resets failure state"""
        manager = MonitorManager()
        node = create_mock_node("n1", "TestNode", "192.168.1.1")

        manager.latest_results["n1"] = {"node_id": "n1", "status": "UP", "timestamp": 12345}
        manager.get_node_state("n1")["status"] = "PENDING"
        manager.get_node_state("n1")["failure_count"] = 2

        manager.set_paused(node)

        result = manager.latest_results.get("n1")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "PAUSED")
        self.assertEqual(manager.node_states["n1"]["status"], "PAUSED")
        self.assertEqual(manager.node_states["n1"]["failure_count"], 0)

    async def test_unpause_immediate_trigger(self):
        """trigger_immediate_check schedules the node for the next loop iteration"""
        manager = MonitorManager()
        manager.last_ping_time.pop("n1", None)

        manager.trigger_immediate_check("n1")

        self.assertIn("n1", manager.last_ping_time)
        self.assertEqual(manager.last_ping_time["n1"], 0)


if __name__ == "__main__":
    unittest.main()
