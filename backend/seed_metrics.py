"""
Seed default metric definitions for SNMP monitoring
"""
from database import SessionLocal
from models import MetricDefinitionDB
import logging

logger = logging.getLogger("BeamState.SeedMetrics")

DEFAULT_METRICS = [
    # Interface Metrics (Generic - works on all devices)
    {
        "name": "Interface Bytes In",
        "oid_template": "1.3.6.1.2.1.2.2.1.10.{index}",
        "metric_type": "counter",
        "unit": "bytes",
        "category": "interface",
        "device_type": "generic",
        "requires_index": True
    },
    {
        "name": "Interface Bytes Out",
        "oid_template": "1.3.6.1.2.1.2.2.1.16.{index}",
        "metric_type": "counter",
        "unit": "bytes",
        "category": "interface",
        "device_type": "generic",
        "requires_index": True
    },
    {
        "name": "Interface Errors In",
        "oid_template": "1.3.6.1.2.1.2.2.1.14.{index}",
        "metric_type": "counter",
        "unit": "errors",
        "category": "interface",
        "device_type": "generic",
        "requires_index": True
    },
    {
        "name": "Interface Errors Out",
        "oid_template": "1.3.6.1.2.1.2.2.1.20.{index}",
        "metric_type": "counter",
        "unit": "errors",
        "category": "interface",
        "device_type": "generic",
        "requires_index": True
    },
    {
        "name": "Interface Status",
        "oid_template": "1.3.6.1.2.1.2.2.1.8.{index}",
        "metric_type": "gauge",
        "unit": "status",
        "category": "interface",
        "device_type": "generic",
        "requires_index": True
    },
    {
        "name": "Traffic In (HC)",
        "oid_template": "1.3.6.1.2.1.31.1.1.1.6.{index}",
        "metric_type": "counter",
        "unit": "bytes",
        "category": "interface",
        "device_type": "generic",
        "requires_index": True
    },
    {
        "name": "Traffic Out (HC)",
        "oid_template": "1.3.6.1.2.1.31.1.1.1.10.{index}",
        "metric_type": "counter",
        "unit": "bytes",
        "category": "interface",
        "device_type": "generic",
        "requires_index": True
    },
    
    # System Metrics (Generic)
    {
        "name": "CPU Utilization",
        "oid_template": "1.3.6.1.2.1.25.3.3.1.2.{index}",
        "metric_type": "gauge",
        "unit": "percent",
        "category": "system",
        "device_type": "generic",
        "requires_index": True  # CPU index, usually 1
    },
    
    # EdgeSwitch / Unifi Switch Specific
    {
        "name": "Temperature",
        "oid_template": "1.3.6.1.4.1.4413.1.1.43.1.8.1.5.1.0",
        "metric_type": "gauge",
        "unit": "celsius",
        "category": "system",
        "device_type": "generic",
        "requires_index": False
    },
    {
        "name": "CPU % (Alt. OID)",
        "oid_template": "1.3.6.1.4.1.4413.1.1.1.1.4.6.1.3.1",
        "metric_type": "gauge",
        "unit": "percent",
        "category": "system",
        "device_type": "generic",
        "requires_index": False
    },
    {
        "name": "CPU Load (%)",
        "oid_template": "1.3.6.1.4.1.4413.1.1.43.1.8.1.4.1.0",
        "metric_type": "gauge",
        "unit": "percent",
        "category": "system",
        "device_type": "generic",
        "requires_index": False
    }
]

def seed_metric_definitions():
    """Seed the database with default metric definitions"""
    db = SessionLocal()
    try:
        count = 0
        # Add default metrics if they don't exist
        for metric_data in DEFAULT_METRICS:
            existing = db.query(MetricDefinitionDB).filter(
                MetricDefinitionDB.name == metric_data["name"]
            ).first()
            
            if not existing:
                metric = MetricDefinitionDB(**metric_data)
                db.add(metric)
                count += 1
                logger.info(f"Adding new metric definition: {metric_data['name']}")
        
        if count > 0:
            db.commit()
            logger.info(f"Seeded {count} new metric definitions")
        else:
            logger.info("All default metrics already exist")
            
    except Exception as e:
        logger.error(f"Error seeding metric definitions: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_metric_definitions()
