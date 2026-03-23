"""Trade management: breakeven stops, pyramiding, and hedges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import structlog

log = structlog.get_logger()


@dataclass
class TradeState:
    entry_price: float
    stop: float
    quantity: float
    pyramids: int = 0
    hedge: Optional[str] = None


class TradeManager:
    """Manage active trades with conservative pyramiding and hedging."""

    def __init__(self, max_pyramids: int = 2, pyramid_factor: float = 0.5) -> None:
        self.max_pyramids = max_pyramids
        self.pyramid_factor = pyramid_factor

    def breakeven(self, state: TradeState, last_price: float, r_multiple: float) -> None:
        if r_multiple >= 1.0 and state.stop < state.entry_price:
            state.stop = state.entry_price
            log.info("move_to_breakeven", price=last_price)

    def pyramid(self, state: TradeState, last_price: float, r_multiple: float) -> Optional[float]:
        if state.pyramids >= self.max_pyramids or r_multiple < 1.5:
            return None
        add_qty = state.quantity * self.pyramid_factor
        state.pyramids += 1
        state.quantity += add_qty
        state.stop = max(state.stop, state.entry_price)  # never lower stop
        log.info("pyramid", added=add_qty, new_qty=state.quantity, r=r_multiple)
        return add_qty

    def correlation_hedge(self, exposure: Dict[str, float], sector_map: Dict[str, str]) -> Optional[str]:
        long_sector_weight = sum(w for s, w in exposure.items() if w > 0 and sector_map.get(s) == "tech")
        defensives = [s for s, w in exposure.items() if w < 0 and sector_map.get(s) == "defensive"]
        if long_sector_weight > 0.3 and not defensives:
            return "add_defensive_short"
        return None

    def manage(
        self,
        state: TradeState,
        last_price: float,
        r_multiple: float,
        exposure: Dict[str, float],
        sector_map: Dict[str, str],
    ) -> Dict[str, Optional[float]]:
        self.breakeven(state, last_price, r_multiple)
        add = self.pyramid(state, last_price, r_multiple)
        hedge = self.correlation_hedge(exposure, sector_map)
        return {"new_stop": state.stop, "added_qty": add, "hedge": hedge}
