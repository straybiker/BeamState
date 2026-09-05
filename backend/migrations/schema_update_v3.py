"""
Migration v3: node dependencies, alert sample counts, persisted state history.

Adds
- nodes.parent_id              (upstream node for alert suppression)
- node_metrics.alert_min_samples (consecutive breaches before an alert raises)
The state_events table itself is created by SQLAlchemy metadata in init_db().
"""
import logging
import sqlite3
from database import DB_PATH

logger = logging.getLogger("BeamState.MigrationV3")


def _columns(cursor, table: str) -> list:
    cursor.execute(f"PRAGMA table_info({table})")
    return [col[1] for col in cursor.fetchall()]


def run_migrations():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if "parent_id" not in _columns(cursor, "nodes"):
            cursor.execute("ALTER TABLE nodes ADD COLUMN parent_id VARCHAR REFERENCES nodes(id)")
            logger.info("Migration v3: added nodes.parent_id")

        if "alert_min_samples" not in _columns(cursor, "node_metrics"):
            cursor.execute("ALTER TABLE node_metrics ADD COLUMN alert_min_samples INTEGER DEFAULT 1")
            logger.info("Migration v3: added node_metrics.alert_min_samples")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Database migration v3 failed: {e}")
