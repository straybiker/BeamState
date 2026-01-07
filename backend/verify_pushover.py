import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from monitor_manager import MonitorManager
from models import NodeDB, GroupDB
from notifications import PushoverClient
from routers import config as config_router
from utils import save_app_config

# Mock storage
mock_storage = MagicMock()
mock_storage.config = {
    "pushover": {
        "enabled": True,
        "token": "TEST_TOKEN",
        "user_key": "TEST_USER",
        "priority": 1,
        "message_template": "Node {name} is DOWN"
    },
    "influxdb": {
        "token": "INFLUX_TOKEN"
    }
}

class TestPushoverIntegration(unittest.TestCase):
    
    @patch('monitor_manager.storage', mock_storage)
    @patch('httpx.AsyncClient.post', new_callable=AsyncMock)
    def test_send_down_alert(self, mock_post):
        """Test that _send_down_alert calls Pushover API"""
        # Setup
        mm = MonitorManager()
        node = NodeDB(id="1", name="TestNode", ip="1.2.3.4", group=GroupDB(name="TestGroup"))
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Act
        asyncio.run(mm._send_down_alert(node))
        
        # Assert
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        payload = kwargs['data']
        
        self.assertEqual(payload['token'], "TEST_TOKEN")
        self.assertEqual(payload['user'], "TEST_USER")
        self.assertEqual(payload['priority'], 1)
        self.assertEqual(payload['message'], "Node TestNode is DOWN")

    @patch('storage.storage', mock_storage)
    def test_config_masking(self):
        """Test API masking of secrets"""
        # GET masking
        config = config_router.get_app_config()
        self.assertEqual(config['pushover']['token'], "***REDACTED***")
        self.assertEqual(config['pushover']['user_key'], "***REDACTED***")
        self.assertEqual(config['influxdb']['token'], "***REDACTED***")
        
        # PUT unmasking (Restore secrets)
        new_config = config.copy()
        # Simulate frontend sending back redacted values
        new_config['pushover']['token'] = "***REDACTED***"
        new_config['pushover']['user_key'] = "***REDACTED***" 
        
        # Setup mock for util save_app_config to capture result
        with patch('utils.save_app_config') as mock_save:
            config_router.update_app_config(new_config, MagicMock())
            
            # Verify the saved config has restored values
            saved_config = mock_save.call_args[0][0]
            self.assertEqual(saved_config['pushover']['token'], "TEST_TOKEN")
            self.assertEqual(saved_config['pushover']['user_key'], "TEST_USER")


if __name__ == '__main__':
    unittest.main()
