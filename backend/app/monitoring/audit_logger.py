"""Audit trail and trade reconstruction helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

log = structlog.get_logger()


class AuditLogger:
    """Persists audit events for compliance and reconstruction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        rec = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.utcnow(),
        )
        self.db.add(rec)
        await self.db.commit()
        await self.db.refresh(rec)
        log.info("audit_logged", action=action, entity=entity_type, entity_id=entity_id)
        return rec

    async def log_decision(
        self,
        signal_id: str,
        decision: str,
        reason: str,
        features: Optional[Dict[str, Any]] = None,
        model_version: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AuditLog:
        payload = {
            "decision": decision,
            "reason": reason,
            "features": features or {},
            "model_version": model_version,
        }
        return await self.log_action(
            action="decision_made",
            entity_type="signal",
            entity_id=signal_id,
            user_id=user_id,
            details=payload,
        )

    async def log_order(self, order_id: str, status: str, reason: Optional[str] = None, user_id: Optional[str] = None) -> AuditLog:
        payload = {"status": status, "reason": reason}
        return await self.log_action(
            action="order_status",
            entity_type="order",
            entity_id=order_id,
            user_id=user_id,
            details=payload,
        )

    async def log_api_access(
        self,
        path: str,
        method: str,
        user_id: Optional[str],
        ip_address: Optional[str],
        user_agent: Optional[str],
        status_code: int,
    ) -> AuditLog:
        payload = {"path": path, "method": method, "status_code": status_code}
        return await self.log_action(
            action="api_access",
            entity_type="http_request",
            user_id=user_id,
            details=payload,
            ip_address=ip_address,
            user_agent=user_agent,
        )
