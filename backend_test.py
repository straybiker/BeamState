import requests
import time
import json
import os

BASE_URL = "http://localhost:8000"
PING_LOGS_PATH = "backend/data/ping_logs.json"

def clean_logs():
    print("Cleaning ping logs...")
    try:
        if os.path.exists(PING_LOGS_PATH):
            with open(PING_LOGS_PATH, 'w') as f:
                f.write("")
            print("Logs cleaned (emptied).")
        else:
            print("No logs found to clean.")
    except Exception as e:
        print(f"Error cleaning logs: {e}")

def test_backend():
    clean_logs()
    print(f"Testing Backend at {BASE_URL}...")
    
    # 1. Check Root
    try:
        r = requests.get(f"{BASE_URL}/")
        print(f"Root Status: {r.status_code} - {r.json()}")
    except Exception as e:
        print(f"Failed to connect to backend: {e}")
        return

    # 2. Check Existing Nodes
    print("Checking for existing nodes...")
    r = requests.get(f"{BASE_URL}/config/nodes")
    nodes = r.json()
    print(f"Found {len(nodes)} nodes.")

    if not nodes:
        print("No nodes found. Adding defaults (Google & Cloudflare)...")
        
        # Ensure Default Group Exists
        r = requests.get(f"{BASE_URL}/config/groups")
        groups = r.json()
        if not groups:
            print("Creating Default Group...")
            r = requests.post(f"{BASE_URL}/config/groups", json={"name": "Default", "interval": 60, "packet_count": 1})
            group_id = r.json()["id"]
        else:
            group_id = groups[0]["id"]

        # Add Google DNS
        requests.post(f"{BASE_URL}/config/nodes", json={
            "name": "Google DNS",
            "ip": "8.8.8.8",
            "group_id": group_id,
            "interval": 5
        })
        
        # Add Cloudflare DNS
        requests.post(f"{BASE_URL}/config/nodes", json={
            "name": "Cloudflare DNS",
            "ip": "1.1.1.1",
            "group_id": group_id,
            "interval": 5
        })
        print("Added defaults.")
    else:
        print("Using existing configuration.")

    # 3. Wait for Ping
    print("Waiting 10s for ping results...")
    time.sleep(10)

    # 4. Check Status
    r = requests.get(f"{BASE_URL}/status")
    status = r.json()
    print("Pinger Status:", json.dumps(status, indent=2))

if __name__ == "__main__":
    test_backend()
