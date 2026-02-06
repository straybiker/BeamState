import logging
import os
import sqlite3

logger = logging.getLogger("BeamState.MigrationV2")

def run_migrations():
    """Run database schema updates for Alert Conditions"""
    try:
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'beamstate.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if alert_condition column exists in node_metrics
        cursor.execute("PRAGMA table_info(node_metrics)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'alert_condition' not in columns:
            # Add alert_condition column (default 'gt' = greater than)
            cursor.execute("ALTER TABLE node_metrics ADD COLUMN alert_condition VARCHAR DEFAULT 'gt'")
            logger.info("Migration: Added alert_condition column to node_metrics table")
            
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Database migration v2 failed: {e}")
