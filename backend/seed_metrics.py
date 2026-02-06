"""
Seed default metric definitions for SNMP monitoring
"""
from database import SessionLocal
from models import MetricDefinitionDB
import logging

logger = logging.getLogger("BeamState.SeedMetrics")

import json
import os

def load_metrics_from_file():
    """Load metrics from snmp.json"""
    file_path = os.path.join(os.path.dirname(__file__), "snmp.json")
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"snmp.json not found at {file_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing snmp.json: {e}")
        return []

def seed_metric_definitions():
    """Seed the database with default metric definitions from file"""
    db = SessionLocal()
    try:
        count = 0
        metrics_data = load_metrics_from_file()
        
        # Add default metrics if they don't exist, or update if changed
        for metric_data in metrics_data:
            existing = db.query(MetricDefinitionDB).filter(
                MetricDefinitionDB.name == metric_data["name"]
            ).first()
            
            if not existing:
                metric = MetricDefinitionDB(**metric_data)
                db.add(metric)
                count += 1
                logger.info(f"Adding new metric definition: {metric_data['name']}")
            else:
                # Update fields if changed
                changed = False
                if existing.unit != metric_data["unit"]:
                    existing.unit = metric_data["unit"]
                    changed = True
                if existing.oid_template != metric_data["oid_template"]:
                    existing.oid_template = metric_data["oid_template"]
                    changed = True
                
                if changed:
                    count += 1 # Count updates too
                    logger.info(f"Updated metric definition: {metric_data['name']}")
        
        # Add internal ICMP metrics
        icmp_metrics = [
            {
                "name": "ICMP Latency",
                "oid_template": "internal.icmp.latency", # Placeholder, not used for SNMP
                "metric_type": "gauge",
                "unit": "ms",
                "category": "system",
                "device_type": "generic",
                "metric_source": "icmp",
                "requires_index": False
            },
            {
                "name": "ICMP Packet Loss",
                "oid_template": "internal.icmp.loss",
                "metric_type": "gauge",
                "unit": "percent",
                "category": "system",
                "device_type": "generic",
                "metric_source": "icmp",
                "requires_index": False
            }
        ]
        
        for m_data in icmp_metrics:
            existing = db.query(MetricDefinitionDB).filter(MetricDefinitionDB.name == m_data["name"]).first()
            if not existing:
                metric = MetricDefinitionDB(**m_data)
                db.add(metric)
                count += 1
                logger.info(f"Adding new ICMP metric: {m_data['name']}")
        
        if count > 0:
            db.commit()
            logger.info(f"Seeded {count} new metric definitions")
        else:
            logger.info("All metrics from file already exist")
            
    except Exception as e:
        logger.error(f"Error seeding metric definitions: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_metric_definitions()
