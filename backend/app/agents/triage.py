import json
import logging
import time
from typing import Any, Dict

from google import genai
from backend.app.core.config import settings
from .state import AmberGraphState

logger = logging.getLogger(__name__)


def _get_gemini_client():
    if settings.GEMINI_API_KEY:
        try:
            return genai.Client(api_key=settings.GEMINI_API_KEY)
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")
    return None


async def triage_node(state: AmberGraphState) -> dict:
    """
    Triage node for incident severity classification.
    Uses Gemini 3.8 Flash for structured classification with sub-second deterministic fallback.
    """
    start_time = time.time()
    alert_payload = state.get("alert_payload", {})
    source = state.get("alert_source", "UNKNOWN")
    title = alert_payload.get("title", "")
    message = alert_payload.get("message", "")
    service = alert_payload.get("service") or alert_payload.get("source_service", "core-service")

    severity = "P2"
    reasoning = "Standard operational alert triage."

    client = _get_gemini_client()
    if client:
        prompt = f"""
You are an expert SRE Triage Engine. Classify this infrastructure alert into exactly ONE severity level:
- P0: Total customer outage, complete service unavailability, critical DB down.
- P1: Significant customer impact, degraded primary user flow, redundancy loss.
- P2: Moderate performance degradation, non-blocking service issue, elevated error rate.
- P3: Minor issue, internal metric threshold exceeded, non-customer-facing.
- P4: Informational or low-priority notice.

Alert Source: {source}
Service: {service}
Title: {title}
Message: {message}
Payload Context: {json.dumps(alert_payload)}

Return your answer strictly in this valid JSON format with no markdown wrappers:
{{
  "severity": "P0" | "P1" | "P2" | "P3" | "P4",
  "reasoning": "1 concise sentence explaining why this severity was assigned.",
  "affected_service": "{service}"
}}
"""
        try:
            res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            raw_text = res.text.strip()
            # Clean possible markdown block wrappers
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            parsed = json.loads(raw_text.strip())
            severity = parsed.get("severity", severity)
            reasoning = parsed.get("reasoning", reasoning)
            service = parsed.get("affected_service", service)
        except Exception as e:
            logger.warning(f"Gemini triage call failed, falling back to heuristics: {e}")
            # Heuristic fallback if API error
            combined = f"{title} {message}".lower()
            if any(k in combined for k in ["critical", "connection pool", "crash", "oom", "exhausted"]):
                severity = "P0"
                reasoning = "Heuristic match: critical infrastructure starvation detected."
            elif any(k in combined for k in ["error", "timeout", "degraded"]):
                severity = "P1"
                reasoning = "Heuristic match: service error/timeout detected."
    else:
        # Fast heuristic fallback if no API key
        combined = f"{title} {message}".lower()
        if any(k in combined for k in ["critical", "connection pool", "crash", "oom", "exhausted"]):
            severity = "P0"
            reasoning = "Heuristic match: critical infrastructure starvation detected."

    elapsed_time = time.time() - start_time
    logger.info(f"Triage completed in {elapsed_time:.3f}s: {severity} ({reasoning})")

    return {
        "severity": severity,
        "triage_reasoning": f"[{elapsed_time:.2f}s] {reasoning}",
        "affected_service": service,
        "current_node": "triage"
    }
