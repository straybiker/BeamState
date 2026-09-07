"""
Migration v4: device capability probing.

Adds
- metric_definitions.instance_oid  (name column that labels indexed instances)
The node_capabilities table itself is created by SQLAlchemy metadata in init_db().
"""
import logging
import sqlite3
from database import DB_PATH

logger = logging.getLogger("BeamState.MigrationV4")


def run_migrations():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(metric_definitions)")
        columns = [col[1] for col in cursor.fetchall()]
        if "instance_oid" not in columns:
            cursor.execute("ALTER TABLE metric_definitions ADD COLUMN instance_oid VARCHAR")
            logger.info("Migration v4: added metric_definitions.instance_oid")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Database migration v4 failed: {e}")
