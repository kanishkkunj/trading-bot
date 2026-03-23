"""Admin API routes."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_redis
from app.config import get_settings

router = APIRouter()
logger = structlog.get_logger()


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Health check endpoint."""
    health_status = {
        "status": "healthy",
        "version": "0.1.0",
        "environment": get_settings().ENVIRONMENT,
        "services": {},
    }

    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        health_status["services"]["database"] = {
            "status": "healthy",
            "type": "postgresql",
        }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        health_status["services"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health_status["status"] = "unhealthy"

    # Check Redis
    try:
        await redis.ping()
        health_status["services"]["redis"] = {
            "status": "healthy",
            "type": "redis",
        }
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        health_status["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health_status["status"] = "unhealthy"

    # Overall status
    if health_status["status"] == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=health_status,
        )

    return health_status


@router.get("/diagnostics")
async def diagnostics(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Detailed diagnostics endpoint."""
    diagnostics_info = {
        "version": "0.1.0",
        "environment": get_settings().ENVIRONMENT,
        "database": {},
        "redis": {},
        "system": {},
    }

    # Database diagnostics
    try:
        # Connection count
        result = await db.execute(text("SELECT count(*) FROM pg_stat_activity"))
        connections = result.scalar()
        diagnostics_info["database"]["connections"] = connections

        # Table counts
        tables = ["users", "orders", "positions", "signals", "candles", "audit_logs"]
        for table in tables:
            try:
                result = await db.execute(text(f"SELECT count(*) FROM {table}"))
                count = result.scalar()
                diagnostics_info["database"][f"{table}_count"] = count
            except Exception:
                diagnostics_info["database"][f"{table}_count"] = 0

    except Exception as e:
        diagnostics_info["database"]["error"] = str(e)

    # Redis diagnostics
    try:
        info = await redis.info()
        diagnostics_info["redis"]["connected_clients"] = info.get("connected_clients", 0)
        diagnostics_info["redis"]["used_memory_human"] = info.get("used_memory_human", "N/A")
        diagnostics_info["redis"]["total_commands_processed"] = info.get(
            "total_commands_processed", 0
        )
    except Exception as e:
        diagnostics_info["redis"]["error"] = str(e)

    return diagnostics_info


@router.post("/kill-switch")
async def trigger_kill_switch() -> dict:
    """Trigger emergency kill switch (placeholder)."""
    # TODO: Implement kill switch in Sprint 3
    return {"status": "not_implemented", "message": "Kill switch coming in Sprint 3"}
