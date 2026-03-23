"""Risk management tests."""

import pytest

from app.engine.risk import RiskManager, RiskLimits
from app.models.order import Order, OrderSide, OrderType


def test_risk_manager_initialization() -> None:
    """Test risk manager initialization."""
    limits = RiskLimits(
        max_daily_loss_pct=2.0,
        max_risk_per_trade_pct=0.5,
    )
    manager = RiskManager(limits)

    assert manager.limits.max_daily_loss_pct == 2.0
    assert manager.kill_switch_active is False


def test_risk_manager_check_order_passes() -> None:
    """Test risk check when order should pass."""
    manager = RiskManager()

    order = Order(
        user_id="test",
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=1000.0,
    )

    passed, reason = manager.check_order(order, portfolio_value=100000.0)

    assert passed is True
    assert reason == "OK"


def test_risk_manager_kill_switch_blocks() -> None:
    """Test that kill switch blocks orders."""
    manager = RiskManager()
    manager.activate_kill_switch()

    order = Order(
        user_id="test",
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
    )

    passed, reason = manager.check_order(order, portfolio_value=100000.0)

    assert passed is False
    assert "Kill switch" in reason


def test_risk_manager_daily_loss_limit() -> None:
    """Test daily loss limit enforcement."""
    manager = RiskManager(RiskLimits(max_daily_loss_pct=2.0))

    # Simulate 3% daily loss
    manager.update_daily_pnl(-3000.0)

    order = Order(
        user_id="test",
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
    )

    passed, reason = manager.check_order(order, portfolio_value=100000.0)

    assert passed is False
    assert "Daily loss limit" in reason


def test_risk_manager_circuit_breakers() -> None:
    """Test circuit breaker detection."""
    manager = RiskManager(RiskLimits(circuit_breaker_rejection_count=3))

    # Record rejections
    for _ in range(3):
        manager.record_rejection()

    breakers = manager.check_circuit_breakers()

    assert breakers["rejection_rate"] is True
