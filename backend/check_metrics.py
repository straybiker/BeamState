
from database import SessionLocal
from models import NodeDB, NodeMetricDB

def check_metrics():
    db = SessionLocal()
    target_names = ["Edgeswitch", "192.168.1.14"]
    for name in target_names:
        node = db.query(NodeDB).filter(NodeDB.name == name).first()
        if node:
            metrics = db.query(NodeMetricDB).filter(NodeMetricDB.node_id == node.id).all()
            print(f"Node '{name}' (ID: {node.id}) Metrics: {len(metrics)}")
            for m in metrics:
                print(f"  - {m.metric_definition.name} (Iface: {m.interface_name}, Index: {m.interface_index}, Enabled: {m.enabled})")
        else:
            print(f"Node '{name}' not found")
    db.close()

if __name__ == "__main__":
    check_metrics()
