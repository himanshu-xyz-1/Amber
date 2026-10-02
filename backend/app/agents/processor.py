import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.incident import Incident, IncidentSeverity, IncidentStatus
from backend.app.models.alert import Alert
from backend.app.models.tool_invocation import ToolInvocation, RiskLevel, InvocationStatus
from backend.app.agents.graph import run_incident_graph

logger = logging.getLogger(__name__)


def compute_args_hash(args: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 hash of sorted JSON args."""
    canonical_json = json.dumps(args, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


async def process_alert_into_incident(alert_id: uuid.UUID, source: str, raw_payload: Dict[str, Any]):
    """
    Background worker that runs the full autonomous incident lifecycle:
    1. Alert Correlation & Deduplication
    2. LangGraph Agent Execution (Triage -> RAG -> Diagnostics -> Guardrail)
    3. Tool Invocation Creation (HITL approval token with SHA-256 binding & 10m TTL)
    """
    start_time = datetime.now(timezone.utc)
    logger.info(f"Starting autonomous pipeline for Alert {alert_id} from {source}")

    try:
        async with AsyncSessionLocal() as session:
            # 1. Fetch Alert
            alert_res = await session.execute(select(Alert).filter(Alert.id == alert_id))
            alert = alert_res.scalar_one_or_none()
            if not alert:
                logger.error(f"Alert {alert_id} not found in database")
                return

            # 2. Correlate with active incidents with matching fingerprint (sliding window)
            five_mins_ago = start_time - timedelta(minutes=5)
            inc_res = await session.execute(
                select(Incident)
                .filter(Incident.fingerprint == alert.fingerprint)
                .filter(Incident.status.in_([IncidentStatus.TRIGGERED, IncidentStatus.INVESTIGATING, IncidentStatus.PROPOSED]))
                .order_by(Incident.created_at.desc())
            )
            incident = inc_res.scalars().first()

            if not incident:
                # Create new Incident
                title = alert.title or f"{source} Incident: {raw_payload.get('title') or raw_payload.get('message') or 'Alert Storm'}"
                incident = Incident(
                    title=title,
                    description=json.dumps(raw_payload),
                    severity=IncidentSeverity.P1,
                    status=IncidentStatus.TRIGGERED,
                    fingerprint=alert.fingerprint,
                    source_service=raw_payload.get("service") or raw_payload.get("source_service") or "payment-db-prod",
                    created_at=start_time
                )
                session.add(incident)
                await session.commit()
                await session.refresh(incident)

            # Link alert to incident
            alert.incident_id = incident.id
            incident.status = IncidentStatus.INVESTIGATING
            await session.commit()

            # 3. Execute LangGraph Agent Pipeline
            graph_result = await run_incident_graph(
                incident_id=str(incident.id),
                alert_payload=raw_payload,
                source=source
            )

            # 4. Update Incident with Agent Findings
            severity_str = graph_result.get("severity", "P1")
            try:
                incident.severity = IncidentSeverity[severity_str]
            except KeyError:
                incident.severity = IncidentSeverity.P1

            incident.root_cause_summary = graph_result.get("root_cause_summary")
            incident.remediation_plan = {
                "plan": graph_result.get("remediation_plan"),
                "matched_runbooks": graph_result.get("matched_runbooks", [])
            }
            incident.graph_state = graph_result
            incident.current_agent_node = graph_result.get("current_node", "completed")

            # 5. Handle Proposed Tools & Guardrail HITL Tokens
            proposed_tools = graph_result.get("proposed_tools", [])
            requires_approval = graph_result.get("requires_approval", False)

            if proposed_tools:
                for tool in proposed_tools:
                    tool_name = tool.get("tool_name", "query_db_metrics")
                    tool_args = tool.get("args", {})
                    risk_level_str = tool.get("risk_level", "LOW")
                    risk_level = RiskLevel.HIGH if risk_level_str == "HIGH" else RiskLevel.LOW
                    
                    payload_sha256 = compute_args_hash(tool_args)
                    approval_expires = start_time + timedelta(minutes=10)

                    tool_inv = ToolInvocation(
                        incident_id=incident.id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        risk_level=risk_level,
                        reversible=tool.get("reversible", False),
                        status=InvocationStatus.PENDING_APPROVAL if risk_level == RiskLevel.HIGH else InvocationStatus.EXECUTING,
                        payload_sha256=payload_sha256,
                        approval_expires_at=approval_expires if risk_level == RiskLevel.HIGH else None,
                        created_at=start_time
                    )
                    session.add(tool_inv)

                incident.status = IncidentStatus.PROPOSED if requires_approval else IncidentStatus.EXECUTING

            await session.commit()
            logger.info(f"Autonomous incident pipeline completed for Incident {incident.id} with status {incident.status.value}")

            # 6. Multi-Channel On-Call Alert Broadcast (Slack, Telegram, WhatsApp)
            from backend.app.integrations import dispatch_incident_notifications
            inc_dict = {
                "id": str(incident.id),
                "title": incident.title,
                "severity": incident.severity.value,
                "status": incident.status.value,
                "service": incident.source_service,
                "root_cause_summary": incident.root_cause_summary,
                "timestamp": start_time.timestamp()
            }
            primary_inv = None
            if proposed_tools and 'tool_inv' in locals():
                primary_inv = {
                    "id": str(tool_inv.id),
                    "tool_name": tool_inv.tool_name,
                    "tool_args": tool_inv.tool_args,
                    "payload_sha256": tool_inv.payload_sha256,
                    "risk_level": tool_inv.risk_level.value
                }
            await dispatch_incident_notifications(inc_dict, primary_inv)

    except Exception as e:
        logger.exception(f"Error in autonomous incident processing pipeline: {e}")
