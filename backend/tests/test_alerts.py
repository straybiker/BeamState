import asyncio
import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics_processor import MetricProcessor
from models import NodeDB, NodeMetricDB, MetricDefinitionDB, GroupDB

class TestMetricProcessor(unittest.IsolatedAsyncioTestCase):
    async def test_alert_logic(self):
        # Mock Pushover
        pushover = MagicMock()
        pushover.send_notification = AsyncMock(return_value=True)
        
        processor = MetricProcessor(pushover)
        
        # Mock Node and Metric
        node = NodeDB(id="test-node", name="Test Node", ip="192.168.1.1", enabled=True)
        node.group = GroupDB(name="Test Group")
        
        # Test 1: Gauge Metric with Warning Threshold (GT explicit)
        metric_def = MetricDefinitionDB(
            name="CPU Load", 
            metric_type="gauge", 
            unit="percent", 
            metric_source="snmp"
        )
        metric = NodeMetricDB(
            id="test-metric-1",
            warning_threshold=80.0,
            critical_threshold=90.0,
            alert_enabled=True, # Should be ignored now
            alert_condition='gt',
            metric_definition=metric_def
        )
        
        # 1. Normal Value (50) -> No Alert
        await processor.process_metric(node, metric, 50)
        pushover.send_notification.assert_not_called()
        
        # 2. Warning Value (85) -> Warning Alert
        await processor.process_metric(node, metric, 85)
        pushover.send_notification.assert_called_once()
        args = pushover.send_notification.call_args[0]
        self.assertIn("WARNING", args[0])
        self.assertIn(">= 80.0", args[1]) # Check symbol and value
        pushover.send_notification.reset_mock()
        
        # 3. Critical Value (95) -> Critical Alert
        await processor.process_metric(node, metric, 95)
        pushover.send_notification.assert_called_once()
        args = pushover.send_notification.call_args[0]
        self.assertIn("CRITICAL", args[0])
        pushover.send_notification.reset_mock()

        # Test 2: Lower Than (LT) Logic (e.g. Battery)
        metric_lt = NodeMetricDB(
            id="test-metric-lt",
            warning_threshold=20.0,
            critical_threshold=10.0,
            alert_condition='lt',
            metric_definition=MetricDefinitionDB(name="Battery", unit="V", metric_type="gauge")
        )
        
        # Value 25 (OK)
        await processor.process_metric(node, metric_lt, 25)
        pushover.send_notification.assert_not_called()
        
        # Value 15 (Warning <= 20)
        await processor.process_metric(node, metric_lt, 15)
        pushover.send_notification.assert_called_once()
        self.assertIn("WARNING", pushover.send_notification.call_args[0][0])
        self.assertIn("<= 20.0", pushover.send_notification.call_args[0][1])
        pushover.send_notification.reset_mock()
        
        # Value 5 (Critical <= 10)
        await processor.process_metric(node, metric_lt, 5)
        pushover.send_notification.assert_called_once()
        self.assertIn("CRITICAL", pushover.send_notification.call_args[0][0])
        pushover.send_notification.reset_mock()
        
        # Test 3: Implicit Disable (No thresholds)
        metric_disabled = NodeMetricDB(
            id="test-metric-none",
            warning_threshold=None,
            critical_threshold=None,
            metric_definition=metric_def
        )
        await processor.process_metric(node, metric_disabled, 1000)
        pushover.send_notification.assert_not_called()
        
        # Test 4: Paused Node Suppression
        node_paused = NodeDB(id="paused-node", name="Paused Node", ip="1.1.1.1", enabled=False)
        metric_paused = NodeMetricDB(
            id="test-metric-paused",
            warning_threshold=50.0,
            metric_definition=metric_def
        )
        await processor.process_metric(node_paused, metric_paused, 100) # Should trigger if enabled
        pushover.send_notification.assert_not_called()
        
    async def test_counter_rate_logic(self):
        pushover = MagicMock()
        pushover.send_notification = AsyncMock(return_value=True)
        processor = MetricProcessor(pushover)
        
        node = NodeDB(id="test-node-2", name="Router", ip="10.0.0.1", enabled=True)
        node.group = GroupDB(name="Default")
        
        # Counter Metric
        metric_def = MetricDefinitionDB(
            name="Traffic In", 
            metric_type="counter", 
            unit="bytes", 
            metric_source="snmp"
        )
        metric = NodeMetricDB(
            id="test-metric-2",
            alert_enabled=True,
            warning_threshold=1000.0, # 1 kbps
            metric_definition=metric_def
        )
        
        import time
        start_time = time.time()
        
        # First process: No rate (just initializing)
        # Mock time in calculate_rate if possible, but for now we rely on time.time()
        # We can just mock time.time but IsolatedAsyncioTestCase makes patching tricky sometimes.
        # We can just sleep slightly or assume processor uses time.time()
        
        # Run 1: 1000 bytes
        res1 = await processor.process_metric(node, metric, 1000)
        self.assertIsNone(res1) # Should recover from None return in previous logic? 
        # Wait, I updated process_metric to return dict or None. 
        # But if rate IS None, it returns None?
        # Let's check logic:
        # if metric_type == 'counter':
        #    rate = ...
        #    if rate is None: return None
        # So yes, return None on first run.
        
        # Run 2: 2000 bytes after 1 second
        # We need to simulate time passing.
        # But since we can't easily mock time inside the class without dependency injection of a clock,
        # we can manually inject previous value to test just the calc relative to "now".
        
        processor.previous_values["test-metric-2"] = {
            "value": 1000,
            "timestamp": start_time - 1.0 # 1 second ago
        }
        
        res2 = await processor.process_metric(node, metric, 2000)
        # Delta = 1000 bytes. Time = 1 sec.
        # Rate = 1000 bytes/sec * 8 = 8000 bps
        
        self.assertIsNotNone(res2)
        rate = res2['rate']
        self.assertAlmostEqual(rate, 8000.0, delta=1.0)
        
        # Check Alert (Threshold is 1000, rate is 8000 -> Should Alert)
        # But wait, did we mock pushover properly for this call?
        # `processor` in this method has `pushover` mock but `send_notification` wasn't set locally here?
        # It was passed in constructor. `pushover` is a Mock.
        
        # We need to ensure we await `send_notification`? No, it's awaited in process_metric.
        # Check call
        # pushover.send_notification was called?
        # We didn't set return value for the NEW mock instance in this method?
        # MagicMock returns a new MagicMock by default, which is awaitable if configured? 
        # AsyncMock is safer.
        pushover.send_notification = AsyncMock(return_value=True)
        # Re-run logic to ensure it hits alerting
        await processor._check_thresholds(node, metric, rate)
        pushover.send_notification.assert_called()

if __name__ == '__main__':
    unittest.main()
