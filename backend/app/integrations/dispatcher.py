"""
Amber SRE - Multi-Channel Notification Dispatcher.
Coordinates concurrent broadcast of on-call incident notifications across Slack, Telegram, and WhatsApp.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .slack import send_slack_incident_alert
from .telegram import send_telegram_incident_alert
from .whatsapp import send_whatsapp_incident_alert

logger = logging.getLogger(__name__)


async def dispatch_incident_notifications(
    incident_data: Dict[str, Any],
    tool_invocation: Optional[Dict[str, Any]] = None
) -> Dict[str, bool]:
    """
    Broadcasts incident alerts across all configured channels concurrently.
    Returns status map of channel deliveries.
    """
    tasks = {
        "slack": send_slack_incident_alert(incident_data, tool_invocation),
        "telegram": send_telegram_incident_alert(incident_data, tool_invocation),
        "whatsapp": send_whatsapp_incident_alert(incident_data, tool_invocation)
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    status_map = {}
    for (channel, _), result in zip(tasks.items(), results):
        if isinstance(result, Exception):
            logger.error(f"Error dispatching to {channel}: {result}")
            status_map[channel] = False
        else:
            status_map[channel] = bool(result)

    active_sent = [k for k, v in status_map.items() if v]
    if active_sent:
        logger.info(f"Dispatched alerts for incident {incident_data.get('id')} to: {', '.join(active_sent)}")
    else:
        logger.debug(f"No external notification channels responded or configured for incident {incident_data.get('id')}")

    return status_map
