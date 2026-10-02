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


from backend.app.services.approval_service import execute_tool_approval, ApprovalExecutionError


@router.post("", response_model=ApprovalResponse)
async def submit_approval(request: ApprovalRequest, db: AsyncSession = Depends(get_db)):
    try:
        invocation = await execute_tool_approval(
            tool_invocation_id=str(request.tool_invocation_id),
            action=request.action,
            db=db,
            approved_by_id=request.approved_by_id,
            payload_sha256=request.payload_sha256,
        )
        return invocation
    except ApprovalExecutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/pending", response_model=List[ApprovalResponse])
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ToolInvocation)
        .filter(ToolInvocation.status == InvocationStatus.PENDING_APPROVAL)
        .order_by(ToolInvocation.created_at.desc())
    )
    return result.scalars().all()
