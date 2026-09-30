from datetime import datetime, timezone, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.core.database import get_db
from backend.app.models.tool_invocation import ToolInvocation, InvocationStatus
from backend.app.schemas.approval import ApprovalRequest, ApprovalResponse
from backend.app.tools.base import tool_registry

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.post("", response_model=ApprovalResponse)
async def submit_approval(request: ApprovalRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ToolInvocation).filter(ToolInvocation.id == request.tool_invocation_id))
    invocation = result.scalar_one_or_none()

    if not invocation:
        raise HTTPException(status_code=404, detail="Tool invocation not found")

    if invocation.status != InvocationStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail=f"Invocation is already in {invocation.status.value} status")

    # Cryptographic hash verification if hash was generated
    if invocation.payload_sha256 and request.payload_sha256:
        if invocation.payload_sha256 != request.payload_sha256:
            raise HTTPException(status_code=400, detail="Cryptographic payload mismatch! Potential argument tampering.")

    # Check 10-minute TTL expiry
    now_utc = datetime.now(timezone.utc)
    if invocation.approval_expires_at:
        expiry = invocation.approval_expires_at if invocation.approval_expires_at.tzinfo else invocation.approval_expires_at.replace(tzinfo=timezone.utc)
        if expiry < now_utc:
            invocation.status = InvocationStatus.EXPIRED
            await db.commit()
            raise HTTPException(status_code=400, detail="Approval request has expired (10-minute TTL exceeded)")

    if request.action == "approve":
        invocation.status = InvocationStatus.APPROVED
        invocation.approved_by_id = request.approved_by_id
        invocation.approved_at = now_utc

        # Execute the approved tool
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
                invocation.status = InvocationStatus.FAILED
                invocation.error_message = str(e)
                invocation.executed_at = datetime.now(timezone.utc)
        else:
            invocation.status = InvocationStatus.FAILED
            invocation.error_message = f"Tool '{invocation.tool_name}' not found in registry"

    elif request.action == "reject":
        invocation.status = InvocationStatus.REJECTED
    else:
        raise HTTPException(status_code=400, detail="Invalid action: must be 'approve' or 'reject'")

    await db.commit()
    await db.refresh(invocation)

    return invocation


@router.get("/pending", response_model=List[ApprovalResponse])
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ToolInvocation)
        .filter(ToolInvocation.status == InvocationStatus.PENDING_APPROVAL)
        .order_by(ToolInvocation.created_at.desc())
    )
    return result.scalars().all()
