"""Order tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import OrderSide, OrderType, OrderStatus
from app.schemas.order import OrderCreate
from app.schemas.auth import UserCreate
from app.services.order_service import OrderService
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_create_order(db_session: AsyncSession) -> None:
    """Test order creation."""
    # Create a user first
    auth_service = AuthService(db_session)
    user_data = UserCreate(
        email="order@example.com",
        password="password123",
        full_name="Order User",
    )
    user = await auth_service.register_user(user_data)

    # Create order
    order_service = OrderService(db_session)
    order_data = OrderCreate(
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
    )

    order = await order_service.create_order(user.id, order_data)

    assert order.symbol == "RELIANCE.NS"
    assert order.side == OrderSide.BUY
    assert order.quantity == 10
    assert order.user_id == user.id


@pytest.mark.asyncio
async def test_get_user_orders(db_session: AsyncSession) -> None:
    """Test getting user orders."""
    # Create user
    auth_service = AuthService(db_session)
    user_data = UserCreate(
        email="orders@example.com",
        password="password123",
        full_name="Orders User",
    )
    user = await auth_service.register_user(user_data)

    # Create multiple orders
    order_service = OrderService(db_session)

    for i in range(3):
        order_data = OrderCreate(
            symbol=f"STOCK{i}.NS",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        await order_service.create_order(user.id, order_data)

    # Get orders
    orders = await order_service.get_user_orders(user.id)

    assert len(orders) == 3


@pytest.mark.asyncio
async def test_cancel_order(db_session: AsyncSession) -> None:
    """Test order cancellation."""
    # Create user
    auth_service = AuthService(db_session)
    user_data = UserCreate(
        email="cancel@example.com",
        password="password123",
        full_name="Cancel User",
    )
    user = await auth_service.register_user(user_data)

    # Create order
    order_service = OrderService(db_session)
    order_data = OrderCreate(
        symbol="TCS.NS",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
    )
    order = await order_service.create_order(user.id, order_data)

    # Cancel order
    cancelled = await order_service.cancel_order(order.id, user.id)

    assert cancelled.status == OrderStatus.CANCELLED
