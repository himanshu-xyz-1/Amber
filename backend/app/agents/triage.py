import asyncio
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


def _classify_heuristic(title: str, message: str, service: str) -> tuple[str, str]:
    """
    Deterministic rule-based SRE heuristic classifier used when LLM is unavailable,
    rate-limited (HTTP 429), or when sub-millisecond triage is required.
    """
    text = f"{title} {message} {service}".lower()

    # Explicit severity tags in title (e.g. "[P0]", "[P1]", "[P2]")
    if "[p0]" in text or "severity: p0" in text:
        return "P0", f"Explicit P0 tag detected in alert payload for {service}."
    if "[p1]" in text or "severity: p1" in text:
        return "P1", f"Explicit P1 tag detected in alert payload for {service}."
    if "[p2]" in text or "severity: p2" in text:
        return "P2", f"Explicit P2 tag detected in alert payload for {service}."
    if "[p3]" in text or "severity: p3" in text:
        return "P3", f"Explicit P3 tag detected in alert payload for {service}."
    if "[p4]" in text or "severity: p4" in text:
        return "P4", f"Explicit P4 tag detected in alert payload for {service}."

    # P0: Total service stoppage / Database starvation / Lock cascades / Blackholes / Outages
    if any(k in text for k in [
        "zero transaction commits",
        "advisory lock",
        "deadlock cascade",
        "deadlock",
        "starvation",
        "pool starvation",
        "connection pool starvation",
        "connection pool saturation",
        "pool saturation",
        "routing blackhole",
        "nxdomain",
        "primary db down",
        "database down",
        "split brain"
    ]):
        return "P0", "Heuristic match: Critical database lock/starvation or outage causing total failure (P0 critical)."

    # P1: Core flow degradation / Container CrashLoop / Node failure / 504 / SSL / Inodes / OOM
    if any(k in text for k in [
        "oomkilled",
        "oom eviction",
        "eviction storm",
        "crashloop",
        "crashloopbackoff",
        "sigsegv",
        "504 gateway timeout",
        "gateway timeout",
        "525 ssl",
        "ssl handshake",
        "diskpressure",
        "node diskpressure",
        "eviction alert",
        "node not ready",
        "inodes exhausted",
        "redos",
        "runaway loop",
        "grpc deadline",
        "syn backlog",
        "heap limit",
        "threadpool starvation",
        "payment failure rate",
        "signature verification failure"
    ]):
        return "P1", "Heuristic match: Core customer-facing service failure or node pressure (P1 major)."

    # P2: Performance degradation / Replication lag / Kafka consumer lag / Rate limits / Seq scans
    if any(k in text for k in [
        "rate limit breached",
        "429 rate limit",
        "slow sequential scan",
        "unindexed slow",
        "dns propagation",
        "replication lag",
        "desync",
        "consumer group lag",
        "kafka consumer lag",
        "buffer overflow",
        "malformed json",
        "fragmentation ratio",
        "cache-cluster",
        "kafka-cluster",
        "degraded performance",
        "elevated error"
    ]):
        return "P2", "Heuristic match: Non-blocking performance degradation or queue/cache lag (P2 moderate)."

    # P3: Non-customer facing batch / background cron / backup failures
    if any(k in text for k in [
        "cron job",
        "nightly backup",
        "backup-worker",
        "batch job",
        "s3 upload failed",
        "etl"
    ]):
        return "P3", "Heuristic match: Non-customer-facing background batch/cron failure (P3 minor)."

    # P4: Informational / Advance Warnings / Notices
    if any(k in text for k in [
        "cert renewal",
        "certificate renewal",
        "ssl certificate",
        "days remaining",
        "informational",
        "notice:"
    ]):
        return "P4", "Heuristic match: Advance lifecycle / maintenance notification (P4 informational)."

    # Default fallback
    return "P2", "Heuristic fallback: Standard operational alert assigned default P2."


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
            res = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model="gemini-3.8-flash",
                    contents=prompt
                ),
                timeout=15.0
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
            severity, reasoning = _classify_heuristic(title, message, service)
    else:
        severity, reasoning = _classify_heuristic(title, message, service)

    elapsed_time = time.time() - start_time
    logger.info(f"Triage completed in {elapsed_time:.3f}s: {severity} ({reasoning})")

    return {
        "severity": severity,
        "triage_reasoning": f"[{elapsed_time:.2f}s] {reasoning}",
        "affected_service": service,
        "current_node": "triage"
    }
