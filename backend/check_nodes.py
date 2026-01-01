
from database import SessionLocal
from models import NodeDB

def check_nodes():
    db = SessionLocal()
    nodes = db.query(NodeDB).all()
    print(f"Total Nodes: {len(nodes)}")
    for node in nodes:
        print(f"'{node.name}': SNMP={node.monitor_snmp}, GroupSNMP={node.group.monitor_snmp if node.group else 'N/A'}")
    db.close()

if __name__ == "__main__":
    check_nodes()
