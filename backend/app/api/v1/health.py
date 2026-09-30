from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, Any

from backend.app.core.database import get_db

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/liveness")
async def check_liveness() -> Dict[str, Any]:
    return {"status": "alive", "app": "Amber", "version": "0.1.0"}

@router.get("/readiness")
async def check_readiness(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    # Check database
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = "disconnected"
        raise HTTPException(status_code=503, detail={"status": "not ready", "database": db_status})
    
    # Check redis if enabled (stubbed for now)
    redis_status = "disabled"
    
    return {"status": "ready", "database": db_status, "redis": redis_status}
