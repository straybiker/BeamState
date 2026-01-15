
import json
import os

try:
    with open('config.json', 'r') as f:
        data = json.load(f)
        pushover = data.get('app_config', {}).get('pushover', {})
        print(f"Pushover Config in File: {pushover}")
        
        maintenance = pushover.get('maintenance_mode')
        print(f"Maintenance Mode in File: {maintenance}")
        
except Exception as e:
    print(f"Error: {e}")
