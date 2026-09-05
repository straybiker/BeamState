"""
Regression tests for configuration persistence and SNMP node selection.

Run with:  TESTING=1 python -m pytest tests/test_config_roundtrip.py
"""
import os
import sys
import json
import tempfile
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("TESTING", "1")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db, engine  # noqa: E402
from models import Base, GroupDB, NodeDB, MetricDefinitionDB, NodeMetricDB  # noqa: E402
import utils  # noqa: E402
import cleanup  # noqa: E402


class TestConfigRoundTrip(unittest.TestCase):
    """export -> import must not lose any group, node or metric setting."""

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        init_db()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self._orig_utils_path = utils.CONFIG_PATH
        self._orig_cleanup_path = cleanup.CONFIG_PATH
        utils.CONFIG_PATH = self.tmp.name
        cleanup.CONFIG_PATH = self.tmp.name

    def tearDown(self):
        utils.CONFIG_PATH = self._orig_utils_path
        cleanup.CONFIG_PATH = self._orig_cleanup_path
        os.unlink(self.tmp.name)

    def test_everything_survives_export_and_import(self):
        db = SessionLocal()
        definition = MetricDefinitionDB(id="d1", name="CPU Utilization", oid_template="1.3.6.1.2.1.25.3.3.1.2.{index}",
                                        metric_type="gauge", unit="percent", requires_index=True)
        group = GroupDB(
            id="g1", name="Switches", interval=30, packet_count=2, max_retries=2,
            monitor_ping=False, monitor_snmp=True,
            snmp_community="lab-ro", snmp_port=1161, is_default=True,
        )
        node = NodeDB(id="n1", name="core", ip="10.0.0.1", group_id="g1", max_retries=7, notification_priority=2)
        child = NodeDB(id="n2", name="ap", ip="10.0.0.2", group_id="g1", parent_id="n1")
        metric = NodeMetricDB(id="m1", node_id="n1", metric_definition_id="d1", interface_index=196608,
                              collection_interval=30, warning_threshold=70.0, critical_threshold=90.0,
                              alert_condition="gt", alert_min_samples=3, enabled=True)
        db.add_all([definition, group, node, child, metric])
        db.commit()

        utils.save_config(db)
        db.close()

        with open(self.tmp.name) as f:
            written = json.load(f)
        self.assertIn("exported_at", written)
        g = written["groups"][0]
        for key in ("monitor_ping", "monitor_snmp", "snmp_community", "snmp_port", "is_default"):
            self.assertIn(key, g, f"export dropped group field '{key}'")
        core = next(n for n in g["nodes"] if n["id"] == "n1")
        self.assertEqual(core["metrics"][0]["definition"], "CPU Utilization")
        self.assertEqual(core["metrics"][0]["alert_min_samples"], 3)

        # Simulate a restore on a fresh database: keep only the metric definitions
        Base.metadata.drop_all(bind=engine)
        init_db()
        db = SessionLocal()
        db.add(MetricDefinitionDB(id="d1-new", name="CPU Utilization", oid_template="x", metric_type="gauge"))
        db.commit()

        counts = cleanup.import_config(db, written)
        self.assertEqual(counts["groups_created"], 1)
        self.assertEqual(counts["nodes_created"], 2)
        self.assertEqual(counts["metrics"], 1)

        g = db.query(GroupDB).filter(GroupDB.id == "g1").one()
        self.assertFalse(g.monitor_ping)
        self.assertTrue(g.monitor_snmp)
        self.assertEqual(g.snmp_community, "lab-ro")
        self.assertEqual(g.snmp_port, 1161)
        self.assertTrue(g.is_default)

        n = db.query(NodeDB).filter(NodeDB.id == "n1").one()
        self.assertEqual(n.max_retries, 7)
        self.assertEqual(n.notification_priority, 2)

        c = db.query(NodeDB).filter(NodeDB.id == "n2").one()
        self.assertEqual(c.parent_id, "n1")

        m = db.query(NodeMetricDB).filter(NodeMetricDB.node_id == "n1").one()
        self.assertEqual(m.metric_definition_id, "d1-new")  # matched by name, not by id
        self.assertEqual(m.interface_index, 196608)
        self.assertEqual(m.warning_threshold, 70.0)
        self.assertEqual(m.alert_min_samples, 3)
        db.close()

    def test_import_never_deletes(self):
        db = SessionLocal()
        db.add(GroupDB(id="g-keep", name="Keep me"))
        db.add(NodeDB(id="n-keep", name="keeper", ip="10.0.0.9", group_id="g-keep"))
        db.commit()

        cleanup.import_config(db, {"groups": [{"id": "g-new", "name": "New", "nodes": []}]})

        self.assertEqual(db.query(GroupDB).count(), 2)
        self.assertEqual(db.query(NodeDB).count(), 1)
        db.close()


class TestSnmpNodeSelection(unittest.TestCase):
    """The SNMP collector must apply the same inheritance rule as MonitorManager."""

    @classmethod
    def setUpClass(cls):
        from monitors.snmp_data_collector import SNMPDataCollector
        cls.active = staticmethod(SNMPDataCollector._snmp_active)

    @staticmethod
    def _node(node_snmp, group_snmp=True, group_enabled=True):
        group = MagicMock(spec=GroupDB)
        group.enabled = group_enabled
        group.monitor_snmp = group_snmp
        node = MagicMock(spec=NodeDB)
        node.group = group
        node.monitor_snmp = node_snmp
        return node

    def test_inherits_group_setting_when_override_is_null(self):
        self.assertTrue(self.active(self._node(None, group_snmp=True)))
        self.assertFalse(self.active(self._node(None, group_snmp=False)))

    def test_node_override_wins(self):
        self.assertTrue(self.active(self._node(True, group_snmp=False)))
        self.assertFalse(self.active(self._node(False, group_snmp=True)))

    def test_paused_group_or_orphan_is_skipped(self):
        self.assertFalse(self.active(self._node(True, group_enabled=False)))
        orphan = MagicMock(spec=NodeDB)
        orphan.group = None
        orphan.monitor_snmp = True
        self.assertFalse(self.active(orphan))


if __name__ == "__main__":
    unittest.main()
