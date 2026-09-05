"""
Notification channels and the Notifier facade.

Notifier applies the global rules (enabled, maintenance mode) once and fans a
notification out to every configured channel. Callers never talk to a channel
directly.
"""
import time
import logging
from typing import Optional
import httpx

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


class WebhookClient:
    """
    Generic JSON webhook. Works with ntfy, Discord, Home Assistant, n8n and
    anything else that accepts a POST with a JSON body.
    """

    def __init__(self, url: Optional[str] = None):
        self.url = url

    def configure(self, url: str):
        self.url = url

    async def send(self, payload: dict) -> bool:
        if not self.url:
            logger.warning("Webhook URL not configured. Skipping notification.")
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.url, json=payload, timeout=10.0)
                if 200 <= response.status_code < 300:
                    logger.info(f"Webhook sent: {payload.get('title')}")
                    return True
                logger.error(f"Webhook failed: status={response.status_code}, response={response.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            return False


class Notifier:
    """
    Single entry point for alerts. Reads the live app config from storage on
    every call so UI changes apply without a restart.
    """

    def __init__(self, storage):
        self.storage = storage
        self.pushover = PushoverClient()
        self.webhook = WebhookClient()

    # --- Config helpers -------------------------------------------------

    def _pushover_conf(self) -> dict:
        return self.storage.config.get("pushover", {})

    def _webhook_conf(self) -> dict:
        return self.storage.config.get("webhook", {})

    def any_channel_enabled(self) -> bool:
        return bool(self._pushover_conf().get("enabled") or self._webhook_conf().get("enabled"))

    def maintenance_active(self) -> bool:
        return bool(self._pushover_conf().get("maintenance_mode", False))

    def notify_recovery(self) -> bool:
        return bool(self.storage.config.get("alerting", {}).get("notify_recovery", True))

    # --- Sending --------------------------------------------------------

    async def send(self, title: str, message: str, priority: int = 0, event: str = "alert", **context) -> bool:
        """
        Fan a notification out to all enabled channels.

        Args:
            title: Short title
            message: Body text
            priority: Pushover priority (-2..2); also forwarded in the webhook payload
            event: Machine-readable kind: node_down, node_up, metric_warning,
                   metric_critical, metric_resolved, alert_storm, test
            context: Extra fields for the webhook payload (node, ip, group, status, ...)
        """
        if not self.any_channel_enabled():
            logger.debug("No notification channel enabled. Skipping.")
            return False

        if self.maintenance_active():
            logger.warning(f"Maintenance Mode Active: Suppressing notification '{title}'")
            return False

        sent = False

        p_conf = self._pushover_conf()
        if p_conf.get("enabled"):
            token = p_conf.get("token")
            user_key = p_conf.get("user_key")
            if token and user_key:
                self.pushover.configure(token, user_key)
                sent = await self.pushover.send_notification(title, message, priority) or sent
            else:
                logger.warning("Pushover enabled but credentials missing. Skipping Pushover.")

        w_conf = self._webhook_conf()
        if w_conf.get("enabled"):
            url = w_conf.get("url")
            if url:
                self.webhook.configure(url)
                payload = {
                    "source": "beamstate",
                    "event": event,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "timestamp": time.time(),
                    **context,
                }
                sent = await self.webhook.send(payload) or sent
            else:
                logger.warning("Webhook enabled but URL missing. Skipping webhook.")

        return sent
