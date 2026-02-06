import sqlite3
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BeamState.Migrations")

DB_PATH = "data/beamstate.db"

def run_migrations():
    """Run database migrations to update schema"""
    logger.info("Checking for database migrations...")
    
    if not os.path.exists(DB_PATH):
        logger.info(f"Database file {DB_PATH} not found. Skipping migration (will be created by app).")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Add alert columns to node_metrics
        # Check if columns exist
        cursor.execute("PRAGMA table_info(node_metrics)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "warning_threshold" not in columns:
            logger.info("Migrating: Adding warning_threshold to node_metrics")
            cursor.execute("ALTER TABLE node_metrics ADD COLUMN warning_threshold FLOAT")
            
        if "critical_threshold" not in columns:
            logger.info("Migrating: Adding critical_threshold to node_metrics")
            cursor.execute("ALTER TABLE node_metrics ADD COLUMN critical_threshold FLOAT")
            
        if "alert_enabled" not in columns:
            logger.info("Migrating: Adding alert_enabled to node_metrics")
            cursor.execute("ALTER TABLE node_metrics ADD COLUMN alert_enabled BOOLEAN DEFAULT 0")

        # 2. Add metric_source to metric_definitions
        cursor.execute("PRAGMA table_info(metric_definitions)")
        def_columns = [info[1] for info in cursor.fetchall()]

        if "metric_source" not in def_columns:
            logger.info("Migrating: Adding metric_source to metric_definitions")
            cursor.execute("ALTER TABLE metric_definitions ADD COLUMN metric_source VARCHAR DEFAULT 'snmp'")
            
        conn.commit()
        logger.info("Migrations completed successfully.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_migrations()
