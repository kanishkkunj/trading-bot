"""Smart-money confluence helper combining FII/DII, insiders, and fund holdings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.institutional.fii_dii_tracker import FiiDiiTracker
from app.institutional.fund_holdings import FundHoldingsTracker
from app.institutional.insider_tracker import InsiderTracker


@dataclass
class SmartMoneyContext:
    symbol: str
    combined: str
    fii_bias: str
    dii_bias: str
    promoter_bias: str
    pledge_risk: str
    crowded: bool
    reason: str


class SmartMoneyConfluence:
    """Combines institutional flows, insider cues, and fund crowding."""

    def __init__(self, min_crowded_funds: int = 5, weight_cut: float = 0.02) -> None:
        self.min_crowded_funds = min_crowded_funds
        self.weight_cut = weight_cut

    def evaluate(
        self,
        symbol: str,
        flows: Optional[FiiDiiTracker] = None,
        insiders: Optional[InsiderTracker] = None,
        holdings: Optional[FundHoldingsTracker] = None,
    ) -> SmartMoneyContext:
        flow_bias = flows.smart_money_signal() if flows else "neutral"
        trend = flows.trend() if flows else None
        fii_bias = self._derive_fii_bias(flow_bias, trend.trend_fii if trend else 0.0)
        dii_bias = self._derive_dii_bias(flow_bias, trend.trend_dii if trend else 0.0)

        promoter_bias = insiders.promoter_bias(symbol) if insiders else "neutral"
        pledge = insiders.pledge_risk(symbol) if insiders else None
        pledge_risk = "high" if pledge and (pledge.pledge_pct >= getattr(insiders, "high_pledge", 0.4) or pledge.trend > 0.05) else "normal"

        crowded = False
        if holdings:
            crowded_trades = holdings.crowded_trades(min_funds=self.min_crowded_funds, weight_cut=self.weight_cut)
            crowded = any(ct.symbol == symbol for ct in crowded_trades)

        combined = self._combine_signals(holdings, fii_bias, dii_bias, promoter_bias)
        reason = self._build_reason(combined, crowded, pledge_risk)

        return SmartMoneyContext(
            symbol=symbol,
            combined=combined,
            fii_bias=fii_bias,
            dii_bias=dii_bias,
            promoter_bias=promoter_bias,
            pledge_risk=pledge_risk,
            crowded=crowded,
            reason=reason,
        )

    def _combine_signals(
        self,
        holdings: Optional[FundHoldingsTracker],
        fii_bias: str,
        dii_bias: str,
        promoter_bias: str,
    ) -> str:
        if holdings:
            combined = holdings.smart_money_signals(fii_bias=fii_bias, dii_bias=dii_bias, promoter_bias=promoter_bias)
            if combined != "neutral":
                return combined
        if promoter_bias != "neutral":
            return promoter_bias
        if fii_bias.startswith("fii"):
            return fii_bias
        return "neutral"

    def _derive_fii_bias(self, flow_bias: str, fii_trend: float) -> str:
        if flow_bias == "fii_buy_dii_sell":
            return "fii_buy_dii_sell"
        if fii_trend > 0:
            return "fii_buy"
        if fii_trend < 0:
            return "fii_sell"
        return flow_bias if flow_bias.startswith("fii") else "neutral"

    def _derive_dii_bias(self, flow_bias: str, dii_trend: float) -> str:
        if flow_bias == "dii_defensive":
            return "dii_defensive"
        if dii_trend > 0:
            return "dii_buy"
        if dii_trend < 0:
            return "dii_sell"
        return "neutral"

    def _build_reason(self, combined: str, crowded: bool, pledge_risk: str) -> str:
        reasons = []
        if combined != "neutral":
            reasons.append(f"smart_money={combined}")
        if crowded:
            reasons.append("crowded_trade")
        if pledge_risk == "high":
            reasons.append("pledge_risk_high")
        return ", ".join(reasons) if reasons else "neutral"
