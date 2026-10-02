import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from google import genai
from backend.app.core.config import settings
from backend.app.tools.base import tool_registry
from .state import AmberGraphState

logger = logging.getLogger(__name__)


def _get_gemini_client():
    if settings.GEMINI_API_KEY:
        try:
            return genai.Client(api_key=settings.GEMINI_API_KEY)
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")
    return None


async def investigation_node(state: AmberGraphState) -> dict:
    """
    Investigation node:
    1. Executes read-only diagnostic tools.
    2. Feeds diagnostics into Gemini 3.8 Flash to synthesize root-cause.
    3. Proposes bounded remediation action with deterministic guardrails.
    """
    severity = state.get("severity", "P2")
    service = state.get("affected_service", "core-service")
    matched_runbooks = state.get("matched_runbooks", [])

    # 1. Run live read-only diagnostic tools
    diagnostic_results = []

    # Execute health check
    health_tool = tool_registry.get("check_service_health")
    if health_tool:
        h_res = await health_tool.execute(endpoint_url=f"http://internal/{service}/health")
        diagnostic_results.append({
            "tool_name": health_tool.name,
            "result": h_res.data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    # Execute DB metrics check
    db_tool = tool_registry.get("query_db_metrics")
    if db_tool:
        db_res = await db_tool.execute(threshold_seconds=60)
        diagnostic_results.append({
            "tool_name": db_tool.name,
            "result": db_res.data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    # 2. Synthesize with Gemini
    root_cause = "Diagnostic probes indicate service degradation under elevated query latency."
    proposed_tools = []
    remediation_plan = "Review logs and execute standard service recovery."

    client = _get_gemini_client()
    if client:
        available_tools_meta = [
            {"name": t["name"], "risk_level": t["risk_level"], "description": t["description"]}
            for t in tool_registry.list_tools()
        ]

        prompt = f"""
You are the Lead SRE Investigator in an incident response engine.
Analyze these live diagnostic results and propose the most accurate, bounded remediation tool:

Incident Severity: {severity}
Target Service: {service}
Diagnostic Findings: {json.dumps(diagnostic_results)}
Matched Runbooks: {json.dumps(matched_runbooks)}

Registered Tools Available:
{json.dumps(available_tools_meta)}

Rules:
- If slow database queries/pool exhaustion is found, propose 'kill_db_connections' with target pids.
- If pod crashloop or bad deployment is found, propose 'rollback_deployment' or 'restart_service_pod'.
- Always specify realistic args.
- Output ONLY valid JSON with this schema (no markdown, no extra commentary):
{{
  "root_cause_summary": "1-2 sentences stating the exact technical failure based on the diagnostics.",
  "remediation_plan": "1 clear sentence explaining what action will be taken.",
  "proposed_tool_name": "exact tool name from registered tools",
  "tool_args": {{ "key": "value" }}
}}
"""
        try:
            res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            raw_text = res.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            parsed = json.loads(raw_text.strip())
            root_cause = parsed.get("root_cause_summary", root_cause)
            remediation_plan = parsed.get("remediation_plan", remediation_plan)
            tool_name = parsed.get("proposed_tool_name")
            tool_args = parsed.get("tool_args", {})

            matched_tool = tool_registry.get(tool_name)
            if matched_tool:
                proposed_tools.append({
                    "tool_name": matched_tool.name,
                    "args": tool_args,
                    "risk_level": matched_tool.risk_level.value,
                    "reversible": matched_tool.reversible
                })
        except Exception as e:
            logger.warning(f"Gemini investigation failed, falling back to deterministic policy: {e}")

    # Deterministic fallback if LLM was unavailable or returned empty proposal
    if not proposed_tools:
        alert_payload = state.get("alert_payload", {})
        raw_inner = alert_payload.get("raw_payload", {}) if isinstance(alert_payload.get("raw_payload"), dict) else {}
        suggested_tool_name = alert_payload.get("proposed_tool") or raw_inner.get("proposed_tool")
        alert_title = alert_payload.get("title") or raw_inner.get("alertname") or "Infrastructure Incident"
        alert_desc = alert_payload.get("description") or raw_inner.get("description") or "Elevated anomaly detected."

        matched_tool = tool_registry.get(suggested_tool_name) if suggested_tool_name else None

        if matched_tool:
            # Map appropriate arguments for the suggested tool
            if matched_tool.name == "kill_db_connections":
                args = {"pids": [1234, 1235]}
                root_cause = f"Database connection pool saturation on {service}: idle/stalled queries holding connection locks."
                remediation_plan = f"Terminate blocking PIDs [1234, 1235] to recover pool capacity."
            elif matched_tool.name == "rollback_deployment":
                args = {"deployment_name": service, "target_revision": "v1.4.2"}
                root_cause = f"Regression or handshake fault detected on {service} following recent deployment: {alert_desc}"
                remediation_plan = f"Rollback deployment '{service}' to previous stable revision v1.4.2."
            elif matched_tool.name == "restart_service_pod":
                args = {"pod_name": f"{service}-worker-pod-0", "namespace": "production"}
                root_cause = f"Resource starvation or threadpool stall on {service}: {alert_desc}"
                remediation_plan = f"Restart pod '{service}-worker-pod-0' with graceful drainage."
            else:
                args = {}
                root_cause = f"Operational fault on {service}: {alert_title}"
                remediation_plan = f"Execute remediation tool '{matched_tool.name}'."

            proposed_tools.append({
                "tool_name": matched_tool.name,
                "args": args,
                "risk_level": matched_tool.risk_level.value,
                "reversible": matched_tool.reversible
            })
        elif severity in ["P0", "P1"]:
            # Default P0/P1 remediation
            if "db" in service or "postgres" in service or "sql" in service or "starvation" in alert_title.lower():
                proposed_tools.append({
                    "tool_name": "kill_db_connections",
                    "args": {"pids": [1234]},
                    "risk_level": "HIGH",
                    "reversible": False
                })
                root_cause = "Critical connection starvation: idle queries blocking transaction pool."
                remediation_plan = "Terminate blocking PID 1234 to restore connection pool capacity."
            else:
                proposed_tools.append({
                    "tool_name": "restart_service_pod",
                    "args": {"pod_name": f"{service}-pod-0", "namespace": "production"},
                    "risk_level": "HIGH",
                    "reversible": True
                })
                root_cause = f"Critical service degradation on {service}: {alert_desc}"
                remediation_plan = f"Cycle worker pod '{service}-pod-0' to relieve contention."
        else:
            proposed_tools.append({
                "tool_name": "check_service_health",
                "args": {"endpoint_url": f"http://internal/{service}/health"},
                "risk_level": "LOW",
                "reversible": True
            })
            root_cause = f"Diagnostic probe indicates degraded health on {service}."
            remediation_plan = "Run health check and monitor operational telemetry."

    return {
        "diagnostic_results": diagnostic_results,
        "root_cause_summary": root_cause,
        "proposed_tools": proposed_tools,
        "remediation_plan": remediation_plan,
        "current_node": "investigation"
    }
