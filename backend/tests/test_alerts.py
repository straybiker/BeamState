import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, AsyncMock

os.environ.setdefault("TESTING", "1")
# Keep alert state out of the real data directory
_state_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
_state_tmp.close()
os.environ["ALERT_STATE_FILE"] = _state_tmp.name

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics_processor import MetricProcessor  # noqa: E402
from models import NodeDB, NodeMetricDB, MetricDefinitionDB, GroupDB  # noqa: E402


def make_notifier():
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)
    return notifier


def make_processor(notifier):
    p = MetricProcessor(notifier)
    p.alert_states = {}
    p.COOLDOWN_SECONDS = 0
    return p


class TestMetricProcessor(unittest.IsolatedAsyncioTestCase):
    async def test_alert_logic(self):
        notifier = make_notifier()
        processor = make_processor(notifier)

        node = NodeDB(id="test-node", name="Test Node", ip="192.168.1.1", enabled=True)
        node.group = GroupDB(name="Test Group", enabled=True)

        # Test 1: Gauge Metric with Warning Threshold (GT explicit)
        metric_def = MetricDefinitionDB(name="CPU Load", metric_type="gauge", unit="percent", metric_source="snmp")
        metric = NodeMetricDB(
            id="test-metric-1",
            warning_threshold=80.0,
            critical_threshold=90.0,
            alert_condition='gt',
            alert_min_samples=1,
            metric_definition=metric_def
        )

        # 1. Normal Value (50) -> No Alert
        await processor.process_metric(node, metric, 50)
        notifier.send.assert_not_called()

        # 2. Warning Value (85) -> Warning Alert
        await processor.process_metric(node, metric, 85)
        notifier.send.assert_called_once()
        args, kwargs = notifier.send.call_args
        self.assertIn("WARNING", args[0])
        self.assertIn(">= 80.0", args[1])
        self.assertEqual(kwargs["event"], "metric_warning")
        notifier.send.reset_mock()

        # 3. Critical Value (95) -> Critical Alert
        await processor.process_metric(node, metric, 95)
        notifier.send.assert_called_once()
        args, kwargs = notifier.send.call_args
        self.assertIn("CRITICAL", args[0])
        self.assertEqual(kwargs["event"], "metric_critical")
        self.assertEqual(processor.get_node_alert_status(node), (None, None))  # node.node_metrics is empty here
        notifier.send.reset_mock()

        # 4. Back to normal -> RESOLVED
        await processor.process_metric(node, metric, 10)
        notifier.send.assert_called_once()
        self.assertEqual(notifier.send.call_args.kwargs["event"], "metric_resolved")
        notifier.send.reset_mock()

        # Test 2: Lower Than (LT) Logic (e.g. Battery)
        metric_lt = NodeMetricDB(
            id="test-metric-lt",
            warning_threshold=20.0,
            critical_threshold=10.0,
            alert_condition='lt',
            alert_min_samples=1,
            metric_definition=MetricDefinitionDB(name="Battery", unit="V", metric_type="gauge")
        )

        await processor.process_metric(node, metric_lt, 25)
        notifier.send.assert_not_called()

        await processor.process_metric(node, metric_lt, 15)
        notifier.send.assert_called_once()
        self.assertIn("WARNING", notifier.send.call_args.args[0])
        self.assertIn("<= 20.0", notifier.send.call_args.args[1])
        notifier.send.reset_mock()

        await processor.process_metric(node, metric_lt, 5)
        notifier.send.assert_called_once()
        self.assertIn("CRITICAL", notifier.send.call_args.args[0])
        notifier.send.reset_mock()

        # Test 3: Implicit Disable (No thresholds)
        metric_disabled = NodeMetricDB(
            id="test-metric-none",
            warning_threshold=None,
            critical_threshold=None,
            metric_definition=metric_def
        )
        await processor.process_metric(node, metric_disabled, 1000)
        notifier.send.assert_not_called()

        # Test 4: Paused Node Suppression
        node_paused = NodeDB(id="paused-node", name="Paused Node", ip="1.1.1.1", enabled=False)
        node_paused.group = GroupDB(name="G", enabled=True)
        metric_paused = NodeMetricDB(id="test-metric-paused", warning_threshold=50.0, metric_definition=metric_def)
        await processor.process_metric(node_paused, metric_paused, 100)
        notifier.send.assert_not_called()

        # Test 5: Paused Group Suppression
        node_in_paused_group = NodeDB(id="n-pg", name="N", ip="1.1.1.2", enabled=True)
        node_in_paused_group.group = GroupDB(name="Paused Group", enabled=False)
        metric_pg = NodeMetricDB(id="test-metric-pg", warning_threshold=50.0, metric_definition=metric_def)
        await processor.process_metric(node_in_paused_group, metric_pg, 100)
        notifier.send.assert_not_called()

    async def test_min_samples_requires_consecutive_breaches(self):
        notifier = make_notifier()
        processor = make_processor(notifier)
        node = NodeDB(id="n1", name="Switch", ip="10.0.0.2", enabled=True)
        node.group = GroupDB(name="G", enabled=True)
        metric = NodeMetricDB(
            id="m-latency",
            warning_threshold=100.0,
            alert_condition='gt',
            alert_min_samples=3,
            metric_definition=MetricDefinitionDB(name="ICMP Latency", unit="ms", metric_type="gauge", metric_source="icmp")
        )
        node.node_metrics = [metric]

        # Two breaches: still no alert, node not degraded
        await processor.process_metric(node, metric, 380)
        await processor.process_metric(node, metric, 250)
        notifier.send.assert_not_called()
        self.assertEqual(processor.get_node_alert_status(node)[0], None)

        # A normal sample resets the streak
        await processor.process_metric(node, metric, 5)
        await processor.process_metric(node, metric, 300)
        await processor.process_metric(node, metric, 300)
        notifier.send.assert_not_called()

        # Third consecutive breach raises the alert
        await processor.process_metric(node, metric, 300)
        notifier.send.assert_called_once()
        self.assertEqual(processor.get_node_alert_status(node), ("WARNING", "m-latency"))

        # Recovery is immediate (no sample counting on the way down)
        notifier.send.reset_mock()
        await processor.process_metric(node, metric, 5)
        self.assertEqual(notifier.send.call_args.kwargs["event"], "metric_resolved")
        self.assertEqual(processor.get_node_alert_status(node)[0], None)

    async def test_counter_rate_logic(self):
        notifier = make_notifier()
        processor = make_processor(notifier)

        node = NodeDB(id="test-node-2", name="Router", ip="10.0.0.1", enabled=True)
        node.group = GroupDB(name="Default", enabled=True)

        metric_def = MetricDefinitionDB(name="Traffic In", metric_type="counter", unit="bytes", metric_source="snmp")
        metric = NodeMetricDB(
            id="test-metric-2",
            warning_threshold=1000.0, # 1 kbps
            alert_min_samples=1,
            metric_definition=metric_def
        )

        import time
        start_time = time.time()

        # First sample: no rate yet
        res1 = await processor.process_metric(node, metric, 1000)
        self.assertIsNone(res1)

        # Second sample one second later: 1000 bytes -> 8000 bps
        processor.previous_values["test-metric-2"] = {"value": 1000, "timestamp": start_time - 1.0}
        res2 = await processor.process_metric(node, metric, 2000)
        self.assertIsNotNone(res2)
        self.assertAlmostEqual(res2['rate'], 8000.0, delta=50.0)

        # Rate above the 1000 bps warning threshold -> alert
        notifier.send.assert_called_once()
        self.assertIn("WARNING", notifier.send.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
