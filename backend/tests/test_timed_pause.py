"""
Timed pause: duration arithmetic, pause/resume endpoints, automatic resume
in the monitor loop, and persistence through config export/import.

Run with:  TESTING=1 python -m pytest tests/test_timed_pause.py
"""
import os
import sys
import json
import time
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock

os.environ.setdefault("TESTING", "1")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from database import SessionLocal, init_db, engine  # noqa: E402
from models import Base, GroupDB, NodeDB  # noqa: E402
from monitor_manager import MonitorManager  # noqa: E402
from routers import config as config_router  # noqa: E402
import pause  # noqa: E402
import utils  # noqa: E402
import cleanup  # noqa: E402


class TestDurationArithmetic(unittest.TestCase):

    def test_fixed_units(self):
        now = 1_000_000.0
        self.assertEqual(pause.compute_paused_until(5, "minutes", now), now + 300)
        self.assertEqual(pause.compute_paused_until(2, "hours", now), now + 7200)
        self.assertEqual(pause.compute_paused_until(3, "days", now), now + 3 * 86400)

    def test_month_clamps_to_last_day(self):
        jan31 = datetime(2026, 1, 31, 10, 30).timestamp()
        self.assertEqual(datetime.fromtimestamp(pause.add_months(jan31, 1)), datetime(2026, 2, 28, 10, 30))
        leap = datetime(2028, 1, 31, 10, 30).timestamp()
        self.assertEqual(datetime.fromtimestamp(pause.add_months(leap, 1)), datetime(2028, 2, 29, 10, 30))

    def test_month_crosses_year(self):
        nov = datetime(2026, 11, 24, 8, 0).timestamp()
        self.assertEqual(datetime.fromtimestamp(pause.add_months(nov, 3)), datetime(2027, 2, 24, 8, 0))

    def test_invalid_durations(self):
        for value, unit in [(0, "hours"), (-1, "days"), (1.5, "hours"), (1, "weeks"),
                            (True, "days"), (None, "hours"), (13, "months")]:
            with self.assertRaises(ValueError, msg=(value, unit)):
                pause.compute_paused_until(value, unit, time.time())


class TestPresetConfig(unittest.TestCase):

    def test_missing_or_malformed_list_uses_builtin_presets(self):
        expected = {"presets": pause.DEFAULT_PRESETS}
        self.assertEqual(pause.sanitize_pause_config(None), expected)
        self.assertEqual(pause.sanitize_pause_config({}), expected)
        self.assertEqual(pause.sanitize_pause_config({"presets": "1 hour"}), expected)

    def test_presets_sorted_deduplicated_invalid_dropped(self):
        conf = {"presets": [
            {"value": 1, "unit": "months"}, {"value": 30, "unit": "days"},
            {"value": 0, "unit": "hours"}, {"value": 30, "unit": "days"},
            "junk", {"value": 2, "unit": "weeks"}, {"value": 15, "unit": "minutes"},
        ]}
        self.assertEqual(pause.sanitize_pause_config(conf), {"presets": [
            {"value": 15, "unit": "minutes"}, {"value": 30, "unit": "days"}, {"value": 1, "unit": "months"},
        ]})

    def test_empty_list_stays_empty(self):
        self.assertEqual(pause.sanitize_pause_config({"presets": []}), {"presets": []})

    def test_list_is_capped(self):
        conf = {"presets": [{"value": v, "unit": "minutes"} for v in range(1, 20)]}
        self.assertEqual(len(pause.sanitize_pause_config(conf)["presets"]), pause.MAX_PRESETS)

    def test_legacy_single_default_becomes_one_preset(self):
        self.assertEqual(pause.sanitize_pause_config({"default_value": 2, "default_unit": "days"}),
                         {"presets": [{"value": 2, "unit": "days"}]})

    def test_storage_converts_legacy_config_on_load(self):
        import pathlib
        import storage as storage_module
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"app_config": {"pause": {"default_value": 45, "default_unit": "minutes"}}}, tmp)
        tmp.close()
        original = storage_module.CONFIG_FILE
        try:
            storage_module.CONFIG_FILE = pathlib.Path(tmp.name)
            storage_module.storage.reload_config()
            self.assertEqual(storage_module.storage.config["pause"], {"presets": [{"value": 45, "unit": "minutes"}]})
        finally:
            storage_module.CONFIG_FILE = original
            storage_module.storage.reload_config()
            os.unlink(tmp.name)


class _DbTestCase(unittest.TestCase):

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        init_db()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.write(b"{}")
        self.tmp.close()
        self._orig_utils_path = utils.CONFIG_PATH
        self._orig_cleanup_path = cleanup.CONFIG_PATH
        utils.CONFIG_PATH = self.tmp.name
        cleanup.CONFIG_PATH = self.tmp.name

        db = SessionLocal()
        db.add(GroupDB(id="g1", name="Lab"))
        db.add(NodeDB(id="n1", name="switch", ip="10.0.0.1", group_id="g1"))
        db.commit()
        db.close()

    def tearDown(self):
        utils.CONFIG_PATH = self._orig_utils_path
        cleanup.CONFIG_PATH = self._orig_cleanup_path
        os.unlink(self.tmp.name)

    def node(self):
        db = SessionLocal()
        try:
            n = db.query(NodeDB).filter(NodeDB.id == "n1").first()
            return n.enabled, n.paused_until
        finally:
            db.close()

    def pause_until(self, until):
        db = SessionLocal()
        n = db.query(NodeDB).filter(NodeDB.id == "n1").first()
        n.enabled = False
        n.paused_until = until
        db.commit()
        db.close()


class TestPauseEndpoints(_DbTestCase):

    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(config_router.router)
        self.pinger = MagicMock()
        app.state.pinger = self.pinger
        self.client = TestClient(app)

    def test_timed_pause_sets_end_time(self):
        before = time.time()
        r = self.client.post("/config/nodes/n1/pause", json={"value": 2, "unit": "hours"})
        self.assertEqual(r.status_code, 200, r.text)
        enabled, until = self.node()
        self.assertFalse(enabled)
        self.assertAlmostEqual(until, before + 7200, delta=5)
        self.assertEqual(r.json()["paused_until"], until)
        self.pinger.set_paused.assert_called_once()

    def test_indefinite_pause_has_no_end_time(self):
        r = self.client.post("/config/nodes/n1/pause", json={"indefinite": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.node(), (False, None))

    def test_repause_replaces_timer_without_reentering_pause(self):
        self.client.post("/config/nodes/n1/pause", json={"value": 1, "unit": "hours"})
        self.client.post("/config/nodes/n1/pause", json={"value": 3, "unit": "days"})
        _, until = self.node()
        self.assertGreater(until, time.time() + 2 * 86400)
        self.pinger.set_paused.assert_called_once()

    def test_invalid_pause_is_rejected(self):
        for body in [{"value": 0, "unit": "hours"}, {"value": 1, "unit": "weeks"}, {}]:
            r = self.client.post("/config/nodes/n1/pause", json=body)
            self.assertEqual(r.status_code, 400, (body, r.text))
        self.assertEqual(self.node(), (True, None))

    def test_unknown_node(self):
        self.assertEqual(self.client.post("/config/nodes/nope/pause", json={"indefinite": True}).status_code, 404)
        self.assertEqual(self.client.post("/config/nodes/nope/resume").status_code, 404)

    def test_resume_clears_timer(self):
        self.client.post("/config/nodes/n1/pause", json={"value": 1, "unit": "days"})
        r = self.client.post("/config/nodes/n1/resume")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.node(), (True, None))
        self.pinger.trigger_immediate_check.assert_called_once_with("n1")

    def test_edit_without_timer_keeps_it(self):
        self.client.post("/config/nodes/n1/pause", json={"value": 1, "unit": "days"})
        _, until = self.node()
        r = self.client.put("/config/nodes/n1", json={"name": "switch-renamed", "ip": "10.0.0.1",
                                                     "group_id": "g1", "enabled": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.node(), (False, until))

    def test_edit_form_payload_keeps_pause(self):
        # The node edit form sends neither 'enabled' nor 'paused_until'
        self.client.post("/config/nodes/n1/pause", json={"value": 1, "unit": "days"})
        _, until = self.node()
        r = self.client.put("/config/nodes/n1", json={"name": "switch", "ip": "10.0.0.2", "group_id": "g1",
                                                     "monitor_ping": True, "monitor_snmp": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.node(), (False, until))
        self.pinger.trigger_immediate_check.assert_not_called()

    def test_put_enable_with_stale_timer_clears_it(self):
        self.client.post("/config/nodes/n1/pause", json={"value": 1, "unit": "days"})
        node = self.client.get("/config/nodes").json()[0]
        r = self.client.put("/config/nodes/n1", json={**node, "enabled": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.node(), (True, None))


class TestAutoResume(_DbTestCase):

    def test_expired_pause_resumes(self):
        self.pause_until(time.time() - 1)
        manager = MonitorManager()
        db = SessionLocal()
        self.assertEqual(manager.resume_expired(db), 1)
        db.close()
        self.assertEqual(self.node(), (True, None))
        self.assertEqual(manager.last_ping_time["n1"], 0)
        with open(self.tmp.name) as f:
            exported = json.load(f)["groups"][0]["nodes"][0]
        self.assertTrue(exported["enabled"])
        self.assertIsNone(exported["paused_until"])

    def test_pause_expired_during_downtime_resumes_on_first_loop(self):
        # End time a day in the past: the backend was off when it passed
        self.pause_until(time.time() - 86400)
        db = SessionLocal()
        self.assertEqual(MonitorManager().resume_expired(db), 1)
        db.close()
        self.assertEqual(self.node(), (True, None))

    def test_running_pause_stays(self):
        until = time.time() + 3600
        self.pause_until(until)
        db = SessionLocal()
        self.assertEqual(MonitorManager().resume_expired(db), 0)
        db.close()
        self.assertEqual(self.node(), (False, until))

    def test_indefinite_pause_never_resumes(self):
        self.pause_until(None)
        db = SessionLocal()
        self.assertEqual(MonitorManager().resume_expired(db, now=time.time() + 10 * 365 * 86400), 0)
        db.close()
        self.assertEqual(self.node(), (False, None))


class TestPersistence(_DbTestCase):

    def test_timer_survives_export_and_import(self):
        until = time.time() + 3600
        self.pause_until(until)
        db = SessionLocal()
        exported = utils.build_export(db, app_config={})
        db.close()

        Base.metadata.drop_all(bind=engine)
        init_db()
        db = SessionLocal()
        cleanup.import_config(db, exported)
        db.close()
        self.assertEqual(self.node(), (False, until))

    def test_import_drops_timer_on_enabled_node(self):
        db = SessionLocal()
        exported = utils.build_export(db, app_config={})
        exported["groups"][0]["nodes"][0]["paused_until"] = time.time() + 3600
        cleanup.import_config(db, exported)
        db.close()
        self.assertEqual(self.node(), (True, None))


if __name__ == "__main__":
    unittest.main()
