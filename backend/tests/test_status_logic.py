"""
Node status derivation in MonitorManager:
- metric alerts make a reachable node DEGRADED, never DOWN
- DOWN -> UP sends a recovery notification
- a DOWN parent suppresses the child's DOWN alert and its recovery
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TESTING", "1")
_state_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
_state_tmp.close()
os.environ["ALERT_STATE_FILE"] = _state_tmp.name

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from monitor_manager import MonitorManager  # noqa: E402
from monitors.base import MonitorResult  # noqa: E402
from models import NodeDB, GroupDB, NodeMetricDB, MetricDefinitionDB  # noqa: E402
import trace_manager as tm  # noqa: E402


def ok_ping(latency=5.0):
    return MonitorResult(success=True, latency_ms=latency, protocol="icmp", raw_data={"packet_loss": 0.0, "responses": [0.005]})


def failed_ping():
    return MonitorResult(success=False, latency_ms=None, protocol="icmp", raw_data={"packet_loss": 100.0, "responses": [None]})


def make_node(node_id, name, group, parent=None):
    node = NodeDB(id=node_id, name=name, ip="10.0.0.1", enabled=True, monitor_ping=True, monitor_snmp=False,
                  interval=60, packet_count=1, max_retries=1)
    node.group = group
    node.node_metrics = []
    node.parent = parent
    node.parent_id = parent.id if parent else None
    return node


class TestStatusLogic(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        tm.trace_manager.persist = False
        self.manager = MonitorManager()
        self.manager.metric_processor.alert_states = {}
        self.manager.metric_processor.COOLDOWN_SECONDS = 0
        self.manager.notifier.send = AsyncMock(return_value=True)
        self.manager.notifier.any_channel_enabled = lambda: True
        self.manager.notifier.notify_recovery = lambda: True
        self.group = GroupDB(id="g1", name="Lab", enabled=True, interval=60, packet_count=1, max_retries=1,
                             monitor_ping=True, monitor_snmp=False)
        self.storage_patch = patch("monitor_manager.storage.write_monitor_result", new=AsyncMock())
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()

    async def _run(self, node, result):
        self.manager.last_ping_time[node.id] = 0
        with patch.object(self.manager.ping_monitor, "check", new=AsyncMock(return_value=result)):
            await self.manager.process_node(node)
        await self._settle()
        return self.manager.latest_results[node.id]["status"]

    @staticmethod
    async def _settle():
        """Let fire-and-forget alert/trace tasks finish."""
        import asyncio
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _events(self):
        return [c.kwargs.get("event") for c in self.manager.notifier.send.call_args_list]

    async def test_metric_alert_makes_node_degraded_not_down(self):
        node = make_node("n1", "Switch", self.group)
        metric = NodeMetricDB(id="m1", warning_threshold=100.0, critical_threshold=200.0, alert_condition="gt",
                              alert_min_samples=1, enabled=True,
                              metric_definition=MetricDefinitionDB(name="ICMP Latency", unit="ms", metric_type="gauge", metric_source="icmp"))
        node.node_metrics = [metric]

        self.assertEqual(await self._run(node, ok_ping(5.0)), "UP")
        self.assertEqual(await self._run(node, ok_ping(380.0)), "DEGRADED")
        self.assertEqual(await self._run(node, ok_ping(3.0)), "UP")

        # No node_down / node_up notifications for a metric excursion
        events = self._events()
        self.assertNotIn("node_down", events)
        self.assertNotIn("node_up", events)
        self.assertIn("metric_critical", events)
        self.assertIn("metric_resolved", events)

    async def test_down_then_recovery_notifies_with_downtime(self):
        node = make_node("n2", "NAS", self.group)

        self.assertEqual(await self._run(node, failed_ping()), "PENDING")
        self.assertEqual(await self._run(node, failed_ping()), "DOWN")
        down_calls = [c for c in self.manager.notifier.send.call_args_list if c.kwargs.get("event") == "node_down"]
        self.assertEqual(len(down_calls), 1)

        self.assertEqual(await self._run(node, ok_ping()), "UP")
        up_calls = [c for c in self.manager.notifier.send.call_args_list if c.kwargs.get("event") == "node_up"]
        self.assertEqual(len(up_calls), 1)
        self.assertIn("back UP after", up_calls[0].args[1])

    async def test_parent_down_suppresses_child_alert_and_recovery(self):
        router = make_node("r1", "Router", self.group)
        child = make_node("c1", "AP", self.group, parent=router)

        # Router goes DOWN first
        await self._run(router, failed_ping())
        self.assertEqual(await self._run(router, failed_ping()), "DOWN")
        self.assertIn("node_down", self._events())
        self.manager.notifier.send.reset_mock()

        # Child follows: alert must be suppressed
        await self._run(child, failed_ping())
        self.assertEqual(await self._run(child, failed_ping()), "DOWN")
        self.manager.notifier.send.assert_not_called()

        # Child recovers: no recovery message either, since no DOWN alert went out
        self.assertEqual(await self._run(child, ok_ping()), "UP")
        self.manager.notifier.send.assert_not_called()

    async def test_snmp_uptime_drop_reports_reboot(self):
        node = make_node("n4", "Switch", self.group)
        node.monitor_ping = False
        node.monitor_snmp = True
        state = self.manager.get_node_state(node.id)

        self.manager._check_reboot(node, state, 500_000, 0)       # first reading, nothing to compare
        self.manager._check_reboot(node, state, 800_000, 0)       # uptime grows: fine
        await self._settle()
        self.assertNotIn("node_reboot", self._events())

        self.manager._check_reboot(node, state, 3_000, 0)         # uptime reset: reboot
        await self._settle()
        self.assertIn("node_reboot", self._events())
        call = next(c for c in self.manager.notifier.send.call_args_list if c.kwargs.get("event") == "node_reboot")
        self.assertIn("rebooted", call.args[1])
        self.assertEqual(call.kwargs["previous_uptime_seconds"], 8000)

    async def test_failure_count_exposed_for_dashboard(self):
        node = make_node("n3", "Printer", self.group)
        node.max_retries = 3
        await self._run(node, failed_ping())
        result = self.manager.latest_results["n3"]
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["max_retries"], 3)


if __name__ == "__main__":
    unittest.main()
