import httpx
import logging
from typing import Optional

logger = logging.getLogger("BeamState.Notifications")

class PushoverClient:
    API_URL = "https://api.pushover.net/1/messages.json"

    def __init__(self, token: Optional[str] = None, user_key: Optional[str] = None):
        self.token = token
        self.user_key = user_key

    def configure(self, token: str, user_key: str):
        """Update credentials at runtime"""
        self.token = token
        self.user_key = user_key

    async def send_notification(self, title: str, message: str, priority: int = 0) -> bool:
        """
        Send a notification via Pushover.
        
        Args:
            title: Notification title
            message: Notification body
            priority: Priority (-2 to 2)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.token or not self.user_key:
            logger.warning("Pushover credentials not configured. Skipping notification.")
            return False

        payload = {
            "token": self.token,
            "user": self.user_key,
            "title": title,
            "message": message,
            "priority": priority
        }

        # Priority 2 (Emergency) requires retry and expire
        if priority == 2:
            payload["retry"] = 60   # Retry every 60 seconds
            payload["expire"] = 3600 # Expire after 1 hour


        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.API_URL, data=payload, timeout=10.0)
                
                if response.status_code == 200:
                    logger.info(f"Notification sent: {title}")
                    return True
                else:
                    logger.error(f"Failed to send notification: status={response.status_code}, response={response.text}")
                    return False
        except Exception as e:
            logger.error(f"Error sending Pushover notification: {e}")
            return False
