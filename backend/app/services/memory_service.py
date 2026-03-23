"""Memory logging service backed by Cognee."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.clients.cognee_client import CogneeClient
from app.models.order import Order


class MemoryService:
    """High-level helpers to send trading memories."""

    def __init__(self, client: Optional[CogneeClient] = None) -> None:
        self.client = client or CogneeClient()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    async def log_order_event(
        self,
        *,
        order: Order,
        event: str,
        notes: Optional[str] = None,
    ) -> None:
        """Capture order lifecycle events."""

        tags: list[str] = ["order", order.symbol, order.status.value.lower(), event.lower()]
        payload: dict[str, Any] = {
            "order_id": order.id,
            "user_id": order.user_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.order_type.value,
            "status": order.status.value,
            "quantity": order.quantity,
            "price": float(order.price) if order.price else None,
            "trigger_price": float(order.trigger_price) if order.trigger_price else None,
            "strategy_id": order.strategy_id,
            "signal_id": order.signal_id,
            "event": event,
            "notes": notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        }
        await self.client.upsert_memory(scope="order", tags=tags, payload=payload, idempotency_key=f"order-{order.id}-{event}")

    async def log_backtest_summary(
        self,
        *,
        symbol: str,
        strategy_params: dict[str, Any],
        metrics: dict[str, Any],
        trades: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        """Persist backtest summary and top trades."""

        tags = ["backtest", symbol]
        payload: dict[str, Any] = {
            "symbol": symbol,
            "strategy_params": strategy_params,
            "metrics": metrics,
        }
        if trades is not None:
            payload["trades"] = list(trades)[:20]  # cap size

        await self.client.upsert_memory(scope="backtest", tags=tags, payload=payload)

    async def log_signal_context(
        self,
        *,
        symbol: str,
        signal: str,
        features: dict[str, Any],
        decision: str,
        strategy_id: Optional[str] = None,
    ) -> None:
        """Capture model/feature context used for a decision tick."""

        tags = ["signal", symbol, decision.lower()]
        if strategy_id:
            tags.append(str(strategy_id))

        payload = {
            "symbol": symbol,
            "signal": signal,
            "decision": decision,
            "features": features,
            "strategy_id": strategy_id,
        }

        await self.client.upsert_memory(scope="signal", tags=tags, payload=payload)
