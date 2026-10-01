"""
Amber SRE - Telegram Bot Integration.
Dispatches instant on-call mobile push alerts with inline action buttons via Telegram Bot API.
"""

import html
import logging
from typing import Any, Dict, Optional
import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


async def send_telegram_incident_alert(
    incident_data: Dict[str, Any],
    tool_invocation: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Sends an immediate Telegram alert to configured chat/channel.
    Returns True if sent successfully, False otherwise.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.debug("Telegram Bot credentials not configured, skipping Telegram alert.")
        return False

    severity = incident_data.get("severity", "P1")
    title = incident_data.get("title", "Infrastructure Incident Detected")
    service = incident_data.get("service") or incident_data.get("source_service", "Unknown Service")
    root_cause = incident_data.get("root_cause_summary") or "Automated investigation in progress."
    incident_id = incident_data.get("id", "N/A")
    dashboard_url = settings.DASHBOARD_URL

    sev_icons = {
        "P0": "🚨 <b>[P0 CRITICAL OUTAGE]</b>",
        "P1": "🔥 <b>[P1 MAJOR INCIDENT]</b>",
        "P2": "⚠️ <b>[P2 DEGRADED]</b>",
        "P3": "⚡ <b>[P3 MINOR]</b>",
        "P4": "ℹ️ <b>[P4 NOTICE]</b>"
    }.get(severity, f"⚠️ <b>[{severity}]</b>")

    msg_lines = [
        f"{sev_icons}",
        f"<b>Title:</b> {html.escape(str(title))}",
        f"<b>Service:</b> <code>{html.escape(str(service))}</code>",
        f"<b>Status:</b> <code>{incident_data.get('status', 'TRIGGERED')}</code>",
        f"<b>Incident ID:</b> <code>{incident_id}</code>",
        "",
        f"<b>🔍 AI Root Cause:</b>\n<i>{html.escape(str(root_cause))}</i>",
    ]

    inline_keyboard = []

    if tool_invocation:
        tool_name = tool_invocation.get("tool_name", "action")
        tool_args = str(tool_invocation.get("tool_args", {}))
        sha256 = tool_invocation.get("payload_sha256", "N/A")[:12]
        approval_id = tool_invocation.get("id", "")

        msg_lines.extend([
            "",
            "<b>⚡ Proposed Remediation (Approval Required):</b>",
            f"• <b>Tool:</b> <code>{html.escape(tool_name)}</code>",
            f"• <b>Args:</b> <code>{html.escape(tool_args)}</code>",
            f"• <b>Token Hash:</b> <code>{sha256}...</code> (10m TTL)",
        ])

        inline_keyboard.append([
            {"text": "✅ 1-Click Approve", "url": f"{dashboard_url}?incident={incident_id}&action=approve&token={approval_id}"},
            {"text": "📊 Deep Proof", "url": f"{dashboard_url}?incident={incident_id}"}
        ])
    else:
        inline_keyboard.append([
            {"text": "📊 View Dashboard", "url": f"{dashboard_url}?incident={incident_id}"}
        ])

    text_body = "\n".join(msg_lines)
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text_body,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard}
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(api_url, json=payload)
            if resp.status_code == 200:
                logger.info(f"Successfully dispatched Telegram alert for Incident {incident_id}")
                return True
            else:
                logger.warning(f"Telegram API returned non-200: {resp.status_code} - {resp.text}")
                return False
    except Exception as e:
        logger.warning(f"Failed to deliver Telegram alert: {e}")
        return False
