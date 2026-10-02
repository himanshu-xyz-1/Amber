import pytest
import uuid
from datetime import datetime, timezone, timedelta

from backend.app.models.tool_invocation import ToolInvocation, InvocationStatus, RiskLevel
from backend.app.models.incident import Incident, IncidentStatus, IncidentSeverity
from backend.app.services.approval_service import execute_tool_approval, ApprovalExecutionError
from backend.app.core.database import AsyncSessionLocal, Base, engine


@pytest.mark.asyncio
async def test_execute_tool_approval_not_found():
    async with AsyncSessionLocal() as session:
        random_id = str(uuid.uuid4())
        with pytest.raises(ApprovalExecutionError) as exc_info:
            await execute_tool_approval(random_id, "approve", session)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_tool_approval_invalid_uuid():
    async with AsyncSessionLocal() as session:
        with pytest.raises(ApprovalExecutionError) as exc_info:
            await execute_tool_approval("invalid-uuid-format", "approve", session)
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_execute_tool_approval_lifecycle():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Create an incident
        incident = Incident(
            title="Database Connection Exhaustion",
            severity=IncidentSeverity.P1,
            status=IncidentStatus.PROPOSED,
            fingerprint="test-fp-1234",
            source_service="auth-db"
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        # Create a tool invocation
        tool_inv = ToolInvocation(
            incident_id=incident.id,
            tool_name="kill_db_connections",
            tool_args={"pids": [101]},
            risk_level=RiskLevel.HIGH,
            status=InvocationStatus.PENDING_APPROVAL,
            payload_sha256="abc123sha",
            approval_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        session.add(tool_inv)
        await session.commit()
        await session.refresh(tool_inv)

        inv_id = str(tool_inv.id)

        # 1. Execute rejection test
        rejected = await execute_tool_approval(inv_id, "reject", session)
        assert rejected.status == InvocationStatus.REJECTED

        # 2. Re-open and execute approval test
        rejected.status = InvocationStatus.PENDING_APPROVAL
        await session.commit()

        approved = await execute_tool_approval(inv_id, "approve", session, payload_sha256="abc123sha")
        assert approved.status == InvocationStatus.EXECUTED
        assert approved.health_check_passed is True
        assert approved.execution_result is not None
