"""
Amber SRE Engine - Approval & Remediation Execution Service.
Shared service for executing human-in-the-loop (HITL) remediations
across Web Dashboard, Telegram Bot, and Slack integrations.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.models.tool_invocation import ToolInvocation, InvocationStatus
from backend.app.models.incident import Incident, IncidentStatus
from backend.app.tools.base import tool_registry

logger = logging.getLogger(__name__)


class ApprovalExecutionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def execute_tool_approval(
    tool_invocation_id: str,
    action: str,
    db: AsyncSession,
    approved_by_id: Optional[uuid.UUID] = None,
    payload_sha256: Optional[str] = None,
    approver_label: str = "Authorized SRE",
) -> ToolInvocation:
    """
    Validates and executes or rejects a tool invocation.
    Ensures cryptographic hash verification and 10-minute TTL enforcement.
    Updates the parent incident status upon successful remediation.
    """
    try:
        inv_uuid = uuid.UUID(str(tool_invocation_id))
    except ValueError:
        raise ApprovalExecutionError("Invalid tool invocation UUID format.", status_code=400)

    result = await db.execute(select(ToolInvocation).filter(ToolInvocation.id == inv_uuid))
    invocation = result.scalar_one_or_none()

    if not invocation:
        raise ApprovalExecutionError(f"Tool invocation '{tool_invocation_id}' not found.", status_code=404)

    if invocation.status in [InvocationStatus.EXECUTED, InvocationStatus.EXECUTING, InvocationStatus.APPROVED]:
        logger.info(f"Tool invocation '{tool_invocation_id}' is already approved/executed ({invocation.status.value}); returning cached execution.")
        return invocation

    if invocation.status != InvocationStatus.PENDING_APPROVAL:
        raise ApprovalExecutionError(
            f"Invocation cannot be approved: current status is {invocation.status.value}.",
            status_code=400
        )

    # 1. Cryptographic hash verification
    if invocation.payload_sha256 and payload_sha256:
        if invocation.payload_sha256 != payload_sha256:
            raise ApprovalExecutionError(
                "Cryptographic payload mismatch! Potential argument tampering.",
                status_code=400
            )

    # 2. Check 10-minute TTL expiry
    now_utc = datetime.now(timezone.utc)
    if invocation.approval_expires_at:
        expiry = (
            invocation.approval_expires_at
            if invocation.approval_expires_at.tzinfo
            else invocation.approval_expires_at.replace(tzinfo=timezone.utc)
        )
        if expiry < now_utc:
            invocation.status = InvocationStatus.EXPIRED
            await db.commit()
            raise ApprovalExecutionError(
                "Approval request has expired (10-minute TTL exceeded).",
                status_code=400
            )

    # 3. Action handling
    if action == "approve":
        invocation.status = InvocationStatus.APPROVED
        invocation.approved_by_id = approved_by_id
        invocation.approved_at = now_utc

        tool = tool_registry.get(invocation.tool_name)
        if tool:
            invocation.status = InvocationStatus.EXECUTING
            try:
                tool_res = await tool.execute(**(invocation.tool_args or {}))
                invocation.execution_result = tool_res.data
                invocation.health_check_passed = tool_res.success
                invocation.executed_at = datetime.now(timezone.utc)
                invocation.status = InvocationStatus.EXECUTED if tool_res.success else InvocationStatus.FAILED
                if not tool_res.success:
                    invocation.error_message = tool_res.error
            except Exception as e:
                logger.exception(f"Error executing approved tool {invocation.tool_name}: {e}")
                invocation.status = InvocationStatus.FAILED
                invocation.error_message = str(e)
                invocation.executed_at = datetime.now(timezone.utc)
        else:
            invocation.status = InvocationStatus.FAILED
            invocation.error_message = f"Tool '{invocation.tool_name}' not found in registry"

        # Update parent incident if remediation was executed
        if invocation.incident_id:
            inc_res = await db.execute(select(Incident).filter(Incident.id == invocation.incident_id))
            incident = inc_res.scalar_one_or_none()
            if incident:
                if invocation.status == InvocationStatus.EXECUTED:
                    incident.status = IncidentStatus.RESOLVED
                    incident.resolved_at = datetime.now(timezone.utc)
                    # Notify target application if an external callback webhook was provided in the alert payload
                    try:
                        raw_payload = {}
                        if incident.description:
                            try:
                                raw_payload = json.loads(incident.description)
                            except Exception:
                                pass
                        callback_url = raw_payload.get("target_service_url") or raw_payload.get("raw_payload", {}).get("target_service_url")
                        if callback_url:
                            import httpx
                            async with httpx.AsyncClient(timeout=3.0) as client:
                                await client.post(
                                    callback_url,
                                    json={
                                        "incident_id": str(incident.id),
                                        "tool_name": invocation.tool_name,
                                        "result": invocation.execution_result,
                                        "approver": approver_label
                                    }
                                )
                    except Exception:
                        pass
                elif invocation.status == InvocationStatus.FAILED:
                    incident.status = IncidentStatus.FAILED

    elif action == "reject":
        invocation.status = InvocationStatus.REJECTED
        if invocation.incident_id:
            inc_res = await db.execute(select(Incident).filter(Incident.id == invocation.incident_id))
            incident = inc_res.scalar_one_or_none()
            if incident and incident.status == IncidentStatus.PROPOSED:
                incident.status = IncidentStatus.ESCALATED
    else:
        raise ApprovalExecutionError("Invalid action: must be 'approve' or 'reject'.", status_code=400)

    await db.commit()
    await db.refresh(invocation)
    return invocation
