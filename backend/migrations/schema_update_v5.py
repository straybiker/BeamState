"""
Migration v5: timed pause.

Adds
- nodes.paused_until  (epoch seconds at which a paused node resumes monitoring)
"""
import logging
import sqlite3
from database import DB_PATH

logger = logging.getLogger("BeamState.MigrationV5")


def run_migrations():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(nodes)")
        columns = [col[1] for col in cursor.fetchall()]
        if "paused_until" not in columns:
            cursor.execute("ALTER TABLE nodes ADD COLUMN paused_until FLOAT")
            logger.info("Migration v5: added nodes.paused_until")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Database migration v5 failed: {e}")
