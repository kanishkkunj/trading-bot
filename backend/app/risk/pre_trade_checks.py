"""Pre-trade risk checks: margin, buying power, compliance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import structlog

from app.ml.base import safe_import

log = structlog.get_logger()


@dataclass
class CheckResult:
    allowed: bool
    reason: str | None = None


class PreTradeChecker:
    """Evaluate pre-trade risk constraints."""

    def __init__(self, margin_provider: any = None, cognee_client: any = None) -> None:
        self.margin_provider = margin_provider
        self.cognee = cognee_client or safe_import("cognee", "cognee")

    def check(self, symbol: str, side: str, quantity: float, price: float, buying_power: float) -> CheckResult:
        notional = quantity * price
        if notional > buying_power:
            self._log(symbol, side, quantity, reason="insufficient_buying_power")
            return CheckResult(False, "Buying power exceeded")
        if self.margin_provider:
            margin = self.margin_provider.required_margin(symbol, side, notional)
            if margin > buying_power:
                self._log(symbol, side, quantity, reason="margin_exceeded")
                return CheckResult(False, "Margin exceeded")
        return CheckResult(True)

    def _log(self, symbol: str, side: str, qty: float, reason: str) -> None:
        payload = {"symbol": symbol, "side": side, "qty": qty, "reason": reason}
        if self.cognee and hasattr(self.cognee, "save"):
            try:
                self.cognee.save(kind="risk_check", data=payload)
            except Exception:  # pragma: no cover - external
                log.warning("cognee_save_failed", reason=reason)
        log.warning("pre_trade_failed", **payload)
