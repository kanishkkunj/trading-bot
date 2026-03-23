import asyncio
from datetime import datetime

import pytest

from app.models.order import Order, OrderSide, OrderType, OrderStatus
from app.services.memory_service import MemoryService


class FakeCogneeClient:
    def __init__(self) -> None:
        self.enabled = True
        self.calls = []

    async def upsert_memory(self, *, scope, tags, payload, idempotency_key=None):  # noqa: ANN001
        self.calls.append({
            "scope": scope,
            "tags": tags,
            "payload": payload,
            "idempotency_key": idempotency_key,
        })
        return {"ok": True}


@pytest.mark.asyncio
async def test_log_order_event_records_expected_tags_and_payload():
    client = FakeCogneeClient()
    service = MemoryService(client=client)

    order = Order(
        user_id="user-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=150.0,
        trigger_price=None,
        status=OrderStatus.PENDING,
    )
    order.created_at = datetime(2024, 1, 1)
    order.updated_at = datetime(2024, 1, 1)

    await service.log_order_event(order=order, event="created")

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["scope"] == "order"
    assert "order" in call["tags"] and "AAPL" in call["tags"]
    assert call["payload"]["order_id"] == order.id
    assert call["payload"]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_log_backtest_summary_sends_metrics_and_trades():
    client = FakeCogneeClient()
    service = MemoryService(client=client)

    metrics = {"total_return_pct": 12.3}
    trades = [{"action": "BUY", "price": 10}]

    await service.log_backtest_summary(
        symbol="AAPL",
        strategy_params={"lookback": 14},
        metrics=metrics,
        trades=trades,
    )

    call = client.calls[0]
    assert call["scope"] == "backtest"
    assert call["payload"]["metrics"] == metrics
    assert call["payload"]["trades"] == trades
