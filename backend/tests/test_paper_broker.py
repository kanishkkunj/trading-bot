"""Paper broker tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderSide, OrderType, OrderStatus
from app.broker.paper import PaperBroker


@pytest.mark.asyncio
async def test_paper_broker_place_order(db_session: AsyncSession) -> None:
    """Test paper broker order placement."""
    broker = PaperBroker(db_session)

    order = Order(
        user_id="test-user",
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        status=OrderStatus.PENDING,
    )

    filled_order = await broker.place_order(order)

    assert filled_order.status == OrderStatus.FILLED
    assert filled_order.filled_quantity == 10
    assert filled_order.average_price is not None


@pytest.mark.asyncio
async def test_paper_broker_cancel_order(db_session: AsyncSession) -> None:
    """Test paper broker order cancellation."""
    broker = PaperBroker(db_session)

    order = Order(
        user_id="test-user",
        symbol="TCS.NS",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        status=OrderStatus.PLACED,
    )

    db_session.add(order)
    await db_session.commit()

    cancelled_order = await broker.cancel_order(order)

    assert cancelled_order.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_paper_broker_slippage(db_session: AsyncSession) -> None:
    """Test paper broker slippage application."""
    broker = PaperBroker(db_session)

    price = 1000.0

    buy_price = broker._apply_slippage(price, "BUY")
    sell_price = broker._apply_slippage(price, "SELL")

    # Buy price should be higher
    assert buy_price > price
    # Sell price should be lower
    assert sell_price < price


@pytest.mark.asyncio
async def test_paper_broker_get_account_info(db_session: AsyncSession) -> None:
    """Test paper broker account info."""
    broker = PaperBroker(db_session)

    info = await broker.get_account_info()

    assert info["broker"] == "PAPER"
    assert info["available_funds"] > 0
