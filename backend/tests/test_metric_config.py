"""Saving a node's metric list must keep the IDs of unchanged metrics."""
import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("TESTING", "1")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db, engine  # noqa: E402
from models import Base, GroupDB, NodeDB, MetricDefinitionDB, NodeMetricDB, NodeMetricCreate  # noqa: E402
from routers.metrics import set_node_metrics  # noqa: E402


def payload(def_id, idx=None, **overrides):
    base = dict(node_id="n1", metric_definition_id=def_id, interface_index=idx, collection_interval=60,
                warning_threshold=None, critical_threshold=None, alert_condition="gt", alert_min_samples=1, enabled=True)
    base.update(overrides)
    return NodeMetricCreate(**base)


class TestMetricConfigSave(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        init_db()
        self.db = SessionLocal()
        self.db.add_all([
            GroupDB(id="g1", name="G"),
            NodeDB(id="n1", name="sw", ip="10.0.0.1", group_id="g1"),
            MetricDefinitionDB(id="d-cpu", name="CPU", oid_template="1.2.3", metric_type="gauge"),
            MetricDefinitionDB(id="d-in", name="Traffic In", oid_template="1.2.4.{index}", metric_type="counter", requires_index=True),
        ])
        self.db.commit()
        self.request = MagicMock()
        self.request.app.state.pinger = None

    def tearDown(self):
        self.db.close()

    def _ids(self):
        return {(m.metric_definition_id, m.interface_index): m.id
                for m in self.db.query(NodeMetricDB).filter(NodeMetricDB.node_id == "n1").all()}

    def test_removing_one_metric_keeps_the_others_ids(self):
        set_node_metrics("n1", [payload("d-cpu"), payload("d-in", 1), payload("d-in", 2)], self.request, self.db)
        before = self._ids()
        self.assertEqual(len(before), 3)

        # Uncheck interface 2 traffic
        set_node_metrics("n1", [payload("d-cpu"), payload("d-in", 1)], self.request, self.db)
        after = self._ids()

        self.assertEqual(set(after), {("d-cpu", None), ("d-in", 1)})
        self.assertEqual(after[("d-cpu", None)], before[("d-cpu", None)])
        self.assertEqual(after[("d-in", 1)], before[("d-in", 1)])

    def test_threshold_edit_updates_in_place(self):
        set_node_metrics("n1", [payload("d-cpu")], self.request, self.db)
        cpu_id = self._ids()[("d-cpu", None)]

        set_node_metrics("n1", [payload("d-cpu", warning_threshold=80.0, alert_min_samples=3)], self.request, self.db)
        row = self.db.query(NodeMetricDB).filter(NodeMetricDB.id == cpu_id).one()
        self.assertEqual(row.warning_threshold, 80.0)
        self.assertEqual(row.alert_min_samples, 3)

    def test_removed_metric_runtime_state_is_cleared(self):
        set_node_metrics("n1", [payload("d-cpu"), payload("d-in", 1)], self.request, self.db)
        traffic_id = self._ids()[("d-in", 1)]

        pinger = MagicMock()
        pinger.metric_processor.alert_states = {traffic_id: "CRITICAL", "other": "WARNING"}
        pinger.metric_processor.breach_counts = {traffic_id: {"level": "CRITICAL", "count": 1}}
        pinger.snmp_collector.current_values = {traffic_id: {"value": 1}}
        self.request.app.state.pinger = pinger

        set_node_metrics("n1", [payload("d-cpu")], self.request, self.db)

        self.assertNotIn(traffic_id, pinger.metric_processor.alert_states)
        self.assertIn("other", pinger.metric_processor.alert_states)
        self.assertNotIn(traffic_id, pinger.snmp_collector.current_values)
        pinger.metric_processor._save_alert_states.assert_called_once()


if __name__ == "__main__":
    unittest.main()
