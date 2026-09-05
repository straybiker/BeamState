"""Availability computed from persisted state events."""
import os
import sys
import unittest

os.environ.setdefault("TESTING", "1")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db, engine  # noqa: E402
from models import Base, StateEventDB  # noqa: E402
from availability import compute_availability  # noqa: E402

H = 3600.0


class TestAvailability(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        init_db()
        self.now = 1_800_000_000.0
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _event(self, node, ts, old, new, reason="x"):
        self.db.add(StateEventDB(timestamp=ts, node_id=node, node_name=node, ip="1.1.1.1",
                                 group_name="g", old_status=old, new_status=new, reason=reason))

    def test_one_outage_in_window(self):
        # DOWN from -6h to -3h inside a 24h window
        self._event("n1", self.now - 6 * H, "PENDING", "DOWN")
        self._event("n1", self.now - 3 * H, "DOWN", "UP")
        self.db.commit()

        stats = compute_availability(24, {"n1": "UP"}, now=self.now)["n1"]
        self.assertEqual(stats["down_count"], 1)
        self.assertEqual(stats["downtime_seconds"], 3 * 3600)
        self.assertAlmostEqual(stats["availability"], 100 * (1 - 3 / 24), places=2)

    def test_state_carried_in_from_before_window(self):
        # Went DOWN 30h ago, came back 20h ago: the first 4h of the 24h window are downtime
        self._event("n1", self.now - 30 * H, "PENDING", "DOWN")
        self._event("n1", self.now - 20 * H, "DOWN", "UP")
        self.db.commit()

        stats = compute_availability(24, now=self.now)["n1"]
        self.assertEqual(stats["down_count"], 0)  # the transition itself is outside the window
        self.assertEqual(stats["downtime_seconds"], 4 * 3600)

    def test_paused_time_excluded_and_pending_not_counted(self):
        self._event("n1", self.now - 12 * H, "UP", "PAUSED")
        self._event("n1", self.now - 6 * H, "PAUSED", "UP")
        self._event("n1", self.now - 1 * H, "UP", "PENDING")
        self._event("n1", self.now - 0.5 * H, "PENDING", "UP")
        self.db.commit()

        stats = compute_availability(24, now=self.now)["n1"]
        self.assertEqual(stats["monitored_seconds"], 18 * 3600)
        self.assertEqual(stats["downtime_seconds"], 0)
        self.assertEqual(stats["availability"], 100.0)

    def test_node_without_history_uses_current_status(self):
        stats = compute_availability(24, {"fresh": "UP"}, now=self.now)["fresh"]
        self.assertEqual(stats["availability"], 100.0)
        self.assertEqual(stats["down_count"], 0)


if __name__ == "__main__":
    unittest.main()
