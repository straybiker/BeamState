
from database import SessionLocal
from models import NodeDB, NodeMetricDB, NodeInterfaceDB, MetricDefinitionDB

def check_db():
    db = SessionLocal()
    try:
        nodes = db.query(NodeDB).all()
        print(f"Total Nodes: {len(nodes)}")
        for node in nodes:
            print(f"Node: {node.name} (ID: {node.id})")
            print(f"  - SNMP Enabled (Node): {node.monitor_snmp}")
            print(f"  - Group SNMP: {node.group.monitor_snmp if node.group else 'N/A'}")
            
            metrics = db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node.id).all()
            print(f"  - Configured Metrics: {len(metrics)}")
            for m in metrics:
                print(f"    - Metric: {m.metric_definition_id} (Enabled: {m.enabled})")
            
            interfaces = db.query(NodeInterfaceDB).filter(NodeInterfaceDB.node_id == node.id).all()
            print(f"  - Interfaces: {len(interfaces)}")

        defs = db.query(MetricDefinitionDB).all()
        print(f"Metric Definitions: {len(defs)}")

    finally:
        db.close()

if __name__ == "__main__":
    check_db()
