"""Risk manager module (placeholder for Sprint 3)."""

from dataclasses import dataclass
from typing import Optional

from app.models.order import Order


@dataclass
class RiskLimits:
    """Risk limits configuration."""

    max_daily_loss_pct: float = 2.0
    max_risk_per_trade_pct: float = 0.5
    max_concurrent_positions: int = 5
    max_sector_concentration_pct: float = 40.0
    circuit_breaker_slippage_pct: float = 1.0
    circuit_breaker_rejection_count: int = 3
    auto_kill_on_drawdown_pct: float = 5.0


class RiskManager:
    """Risk manager for validating orders and positions."""

    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self.kill_switch_active = False
        self.daily_pnl = 0.0
        self.rejection_count = 0

    def check_order(self, order: Order, portfolio_value: float) -> tuple[bool, str]:
        """Check if an order passes risk checks."""
        if self.kill_switch_active:
            return False, "Kill switch is active"

        # Check daily loss limit
        daily_loss_pct = (self.daily_pnl / portfolio_value) * 100 if portfolio_value > 0 else 0
        if daily_loss_pct <= -self.limits.max_daily_loss_pct:
            return False, f"Daily loss limit exceeded: {abs(daily_loss_pct):.2f}%"

        # Check position size
        order_value = (order.price or 0) * order.quantity
        if portfolio_value > 0:
            position_pct = (order_value / portfolio_value) * 100
            if position_pct > self.limits.max_risk_per_trade_pct * 10:  # Allow larger for now
                return False, f"Position size too large: {position_pct:.2f}%"

        return True, "OK"

    def update_daily_pnl(self, pnl: float) -> None:
        """Update daily PnL."""
        self.daily_pnl += pnl

    def activate_kill_switch(self) -> None:
        """Activate kill switch."""
        self.kill_switch_active = True

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch."""
        self.kill_switch_active = False

    def record_rejection(self) -> None:
        """Record an order rejection."""
        self.rejection_count += 1

    def check_circuit_breakers(self) -> dict[str, bool]:
        """Check if any circuit breakers should trigger."""
        return {
            "rejection_rate": self.rejection_count >= self.limits.circuit_breaker_rejection_count,
            "kill_switch": self.kill_switch_active,
        }
