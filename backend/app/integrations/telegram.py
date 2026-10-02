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


async def get_telegram_subscribers() -> set:
    """Retrieves all registered Telegram chat IDs from Redis and config."""
    subscribers = set()
    if settings.TELEGRAM_CHAT_ID:
        subscribers.add(str(settings.TELEGRAM_CHAT_ID).strip())

    if settings.REDIS_ENABLED:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            saved = await r.smembers("amber:telegram_subscribers")
            for s in saved:
                if s:
                    subscribers.add(str(s).strip())
            await r.aclose()
        except Exception as e:
            logger.debug(f"Redis subscriber fetch skipped: {e}")
    return subscribers


async def register_telegram_subscriber(chat_id: int | str) -> bool:
    """Registers a chat_id into the active subscriber broadcast list."""
    if not settings.REDIS_ENABLED or not chat_id:
        return False
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.sadd("amber:telegram_subscribers", str(chat_id).strip())
        await r.aclose()
        return True
    except Exception as e:
        logger.debug(f"Failed to register Telegram subscriber in Redis: {e}")
        return False


async def send_telegram_incident_alert(
    incident_data: Dict[str, Any],
    tool_invocation: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Sends an immediate Telegram alert to all registered subscribers.
    Returns True if sent to at least one subscriber, False otherwise.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    subscribers = await get_telegram_subscribers()

    if not token or not subscribers:
        logger.debug("Telegram Bot credentials or subscribers not configured, skipping Telegram alert.")
        return False

    severity = incident_data.get("severity", "P1")
    title = incident_data.get("title", "Infrastructure Incident Detected")
    service = incident_data.get("service") or incident_data.get("source_service", "Unknown Service")
    root_cause = incident_data.get("root_cause_summary") or "Automated investigation in progress."
    incident_id = incident_data.get("id", "N/A")
    dashboard_url = settings.DASHBOARD_URL
    safe_url = dashboard_url if (dashboard_url and dashboard_url.startswith("https://")) else "https://github.com/himanshu-xyz-1/Amber-Backend-under-development"

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
        status = tool_invocation.get("status", "PENDING_APPROVAL")

        if status == "PENDING_APPROVAL":
            msg_lines.extend([
                "",
                "<b>⚡ Proposed Remediation (HITL Approval Required):</b>",
                f"• <b>Tool:</b> <code>{html.escape(tool_name)}</code>",
                f"• <b>Args:</b> <code>{html.escape(tool_args)}</code>",
                f"• <b>Token Hash:</b> <code>{sha256}...</code> (10m TTL)",
            ])

            # Telegram strictly requires https:// scheme for inline button URLs
            inline_keyboard.append([
                {"text": "⚡ 1-Click Approve", "callback_data": f"approve:{approval_id}"},
                {"text": "❌ Reject", "callback_data": f"reject:{approval_id}"}
            ])
        else:
            msg_lines.extend([
                "",
                "<b>🟢 Autonomous Action Executed:</b>",
                f"• <b>Tool:</b> <code>{html.escape(tool_name)}</code>",
                f"• <b>Status:</b> <code>{html.escape(status)}</code>",
                "• <b>Permission:</b> Low-risk read-only diagnostic ran autonomously.",
            ])

        inline_keyboard.append([
            {"text": "📊 Web Dashboard", "url": f"{safe_url}?incident={incident_id}"}
        ])
    else:
        inline_keyboard.append([
            {"text": "📊 View Dashboard", "url": f"{safe_url}?incident={incident_id}"}
        ])

    text_body = "\n".join(msg_lines)
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    success_count = 0
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            for s_id in subscribers:
                try:
                    payload = {
                        "chat_id": s_id,
                        "text": text_body,
                        "parse_mode": "HTML",
                        "reply_markup": {"inline_keyboard": inline_keyboard}
                    }
                    resp = await client.post(api_url, json=payload)
                    if resp.status_code == 200:
                        success_count += 1
                        logger.info(f"Dispatched Telegram alert for Incident {incident_id} to subscriber {s_id}")
                    else:
                        logger.warning(f"Telegram API error for subscriber {s_id}: {resp.status_code} - {resp.text}")
                except Exception as sub_err:
                    logger.warning(f"Failed to deliver to subscriber {s_id}: {sub_err}")

        return success_count > 0
    except Exception as e:
        logger.warning(f"Failed to deliver Telegram alerts: {e}")
        return False
