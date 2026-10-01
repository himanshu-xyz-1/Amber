"""
Amber Integrations Module.
Exposes multi-channel alert dispatchers for Slack, Telegram, and WhatsApp.
"""

from .slack import send_slack_incident_alert
from .telegram import send_telegram_incident_alert
from .whatsapp import send_whatsapp_incident_alert
from .dispatcher import dispatch_incident_notifications

__all__ = [
    "send_slack_incident_alert",
    "send_telegram_incident_alert",
    "send_whatsapp_incident_alert",
    "dispatch_incident_notifications",
]
