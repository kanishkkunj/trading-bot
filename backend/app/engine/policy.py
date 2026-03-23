"""Decision policy combiner (placeholder for Sprint 2)."""

from dataclasses import dataclass
from typing import Optional

from app.models.signal import SignalAction


@dataclass
class Decision:
    """Trading decision."""

    action: SignalAction
    confidence: float
    suggested_quantity: int = 0
    suggested_price: Optional[float] = None
    reason: str = ""


class DecisionPolicy:
    """Combines ML score + rules + risk constraints into a decision."""

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        min_quantity: int = 1,
        max_quantity: int = 1000,
    ):
        self.confidence_threshold = confidence_threshold
        self.min_quantity = min_quantity
        self.max_quantity = max_quantity

    def decide(
        self,
        ml_score: float,
        rules_passed: bool,
        current_position: int,
        available_capital: float,
        current_price: float,
        institutional_bias: str | None = None,
        crowded: bool = False,
    ) -> Decision:
        """Make a trading decision with optional institutional overlays."""
        # Check confidence threshold
        if ml_score < self.confidence_threshold:
            return Decision(
                action=SignalAction.HOLD,
                confidence=ml_score,
                reason="Confidence below threshold",
            )

        # Check rules
        if not rules_passed:
            return Decision(
                action=SignalAction.HOLD,
                confidence=ml_score,
                reason="Rules filter failed",
            )

        # Respect institutional red flags
        if institutional_bias in {"avoid_or_short", "high_pledge_risk"}:
            return Decision(
                action=SignalAction.HOLD,
                confidence=ml_score,
                reason="Institutional red flag",
            )

        # Determine action based on current position
        if current_position == 0 and ml_score > 0.7:
            # Buy signal
            quantity = self._calculate_position_size(available_capital, current_price)
            if crowded:
                quantity = max(self.min_quantity, int(quantity * 0.5))
            return Decision(
                action=SignalAction.BUY,
                confidence=ml_score,
                suggested_quantity=quantity,
                suggested_price=current_price,
                reason=self._reason_with_institution("ML score indicates buy opportunity", institutional_bias, crowded),
            )
        elif current_position > 0 and ml_score < 0.3:
            # Sell signal
            return Decision(
                action=SignalAction.SELL,
                confidence=1 - ml_score,
                suggested_quantity=current_position,
                suggested_price=current_price,
                reason="ML score indicates sell opportunity",
            )

        return Decision(
            action=SignalAction.HOLD,
            confidence=ml_score,
                reason=self._reason_with_institution("No clear signal", institutional_bias, crowded),
        )

    def _reason_with_institution(self, base: str, institutional_bias: str | None, crowded: bool) -> str:
        """Append institutional context to the decision reason when present."""
        suffixes = []
        if institutional_bias and institutional_bias != "neutral":
            suffixes.append(f"institutional={institutional_bias}")
        if crowded:
            suffixes.append("crowded_trade")
        if not suffixes:
            return base
        return f"{base} ({'; '.join(suffixes)})"

    def _calculate_position_size(self, available_capital: float, price: float) -> int:
        """Calculate position size based on available capital."""
        if price <= 0:
            return self.min_quantity

        # Use 10% of available capital per trade
        position_value = available_capital * 0.1
        quantity = int(position_value / price)

        return max(self.min_quantity, min(quantity, self.max_quantity))
