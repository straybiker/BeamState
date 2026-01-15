
import sys
import os
import asyncio
import json

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from storage import storage
from utils import save_app_config

def test_maintenance_mode():
    print("--- Verifying Maintenance Mode Logic ---")
    
    # 1. Check initial state
    print(f"Initial Config: {storage.config.get('pushover', {})}")
    
    # 2. Simulate enabling maintenance mode via App Config update
    current_config = storage.config.copy()
    
    # Construct app config payload like frontend sends
    app_config_payload = {
        "pushover": {
            "enabled": True,
            "maintenance_mode": True,
            "token": "test_token",
            "user_key": "test_key"
        }
    }
    
    print("\nSimulating frontend update...")
    try:
        # Save to file (this simulates what update_app_config does)
        save_app_config(app_config_payload)
        
        # Reload storage
        storage.reload_config()
        
        # Check new state
        pushover_conf = storage.config.get('pushover', {})
        maintenance_active = pushover_conf.get('maintenance_mode')
        
        print(f"New Config: {pushover_conf}")
        print(f"Maintenance Mode Active? {maintenance_active}")
        
        if maintenance_active is True:
            print("SUCCESS: Maintenance mode persisted and reloaded correctly.")
        else:
            print("FAILURE: Maintenance mode NOT found in storage config.")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_maintenance_mode()
