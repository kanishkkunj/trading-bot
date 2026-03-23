"""Pre-trade risk checks: margin, buying power, compliance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, Tuple

import structlog

from app.ml.base import safe_import

log = structlog.get_logger()

# Maximum age of market data before it is treated as stale in live execution.
_DEFAULT_DATA_MAX_AGE_SECONDS = 300  # 5 minutes
# No new entry orders accepted this many minutes before market close.
_ENTRY_CUTOFF = time(15, 15)


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

    def check_data_freshness(
        self,
        data_age_seconds: float,
        max_age_seconds: float = _DEFAULT_DATA_MAX_AGE_SECONDS,
    ) -> CheckResult:
        """Return a failed CheckResult when market data is too old.

        Only enforced when FEATURE_STRICT_FRESHNESS is enabled so that paper
        and backtest paths are not broken by missing timestamps.
        """
        from app.core.feature_flags import strict_freshness_enabled

        if not strict_freshness_enabled():
            return CheckResult(True)
        if data_age_seconds > max_age_seconds:
            log.warning(
                "pre_trade_stale_data",
                data_age_seconds=round(data_age_seconds, 1),
                max_age_seconds=max_age_seconds,
            )
            return CheckResult(False, f"Market data is stale ({data_age_seconds:.0f}s > {max_age_seconds:.0f}s limit)")
        return CheckResult(True)

    def check_market_close_window(
        self,
        now: datetime | None = None,
        cutoff: time = _ENTRY_CUTOFF,
    ) -> CheckResult:
        """Return a failed CheckResult if we are inside the market-close window.

        No new directional entries are allowed after *cutoff* (default 15:15 IST)
        to avoid being caught with open positions at market close.
        """
        current = (now or datetime.now()).time()
        if current >= cutoff:
            log.warning("pre_trade_close_window", current_time=str(current), cutoff=str(cutoff))
            return CheckResult(False, f"Market close window: no new entries after {cutoff}")
        return CheckResult(True)

    def check_tail_risk(
        self,
        tail_risk_score: float,
        threshold: float | None = None,
    ) -> CheckResult:
        """Hard-block new entries when the tail risk score is at or above threshold.

        The default threshold mirrors TAIL_RISK_BLOCK_THRESHOLD (0.70) from
        tail_risk.py and is consistent with the MiroFish advisory hard-block
        that already exists in the n8n workflow.
        """
        from app.risk.tail_risk import TAIL_RISK_BLOCK_THRESHOLD

        limit = threshold if threshold is not None else TAIL_RISK_BLOCK_THRESHOLD
        if tail_risk_score >= limit:
            log.warning(
                "pre_trade_tail_risk_block",
                score=round(tail_risk_score, 4),
                threshold=limit,
            )
            return CheckResult(
                False,
                f"Tail risk score {tail_risk_score:.3f} \u2265 {limit:.2f} \u2014 entry blocked",
            )
        return CheckResult(True)

    def _log(self, symbol: str, side: str, qty: float, reason: str) -> None:
        payload = {"symbol": symbol, "side": side, "qty": qty, "reason": reason}
        if self.cognee and hasattr(self.cognee, "save"):
            try:
                self.cognee.save(kind="risk_check", data=payload)
            except Exception:  # pragma: no cover - external
                log.warning("cognee_save_failed", reason=reason)
        log.warning("pre_trade_failed", **payload)
