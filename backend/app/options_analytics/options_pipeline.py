"""Options chain ingestion, IV surface, Greeks, and storage to TimescaleDB."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import numpy as np
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.option_quote import OptionQuote, OptionType
from app.db.session import AsyncSessionLocal


@dataclass
class OptionContractSnapshot:
    """Normalized option snapshot used throughout the pipeline."""

    as_of: datetime
    underlying_symbol: str
    option_symbol: str
    expiry: datetime
    strike: float
    option_type: OptionType
    bid: Optional[float] = None
    ask: Optional[float] = None
    last_price: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    implied_vol: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None
    rho: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    underlying_price: Optional[float] = None
    data_source: str | None = None
    extra: dict | None = None


class OptionsPipeline:
    """Handles real-time ingestion, IV surface estimation, Greeks, and persistence."""

    def __init__(self, db: Optional[AsyncSession] = None, risk_free_rate: float = 0.06) -> None:
        self.db = db
        self.r = risk_free_rate

    async def _get_session(self) -> AsyncSession:
        if self.db:
            return self.db
        return AsyncSessionLocal()  # falls back to factory when not provided

    # --- Data ingestion ----------------------------------------------------
    async def ingest_chain(self, snapshots: Iterable[OptionContractSnapshot]) -> None:
        """Upsert an options chain into Timescale-backed option_quotes."""
        session = await self._get_session()
        rows = [self._snapshot_to_row(s) for s in snapshots]
        if not rows:
            return
        stmt = insert(OptionQuote).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[OptionQuote.underlying_symbol, OptionQuote.as_of, OptionQuote.option_symbol],
            set_={c.name: c for c in stmt.excluded if c.name != "id"},
        )
        async with session.begin():
            await session.execute(stmt)
        if self.db is None:
            await session.close()

    # --- Greeks and IV surface --------------------------------------------
    def black_scholes_greeks(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        option_type: OptionType,
    ) -> dict:
        """Compute delta, gamma, theta, vega, rho using Black-Scholes."""
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return {"delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}

        d1 = (math.log(S / K) + (self.r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        Nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
        Nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        pdf = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)

        if option_type == OptionType.CALL:
            delta = Nd1
            rho = K * T * math.exp(-self.r * T) * Nd2
        else:
            delta = Nd1 - 1
            rho = -K * T * math.exp(-self.r * T) * (1 - Nd2)

        gamma = pdf / (S * sigma * math.sqrt(T))
        vega = S * pdf * math.sqrt(T)
        theta = (
            -S * pdf * sigma / (2 * math.sqrt(T))
            - self.r * K * math.exp(-self.r * T) * Nd2
            if option_type == OptionType.CALL
            else -S * pdf * sigma / (2 * math.sqrt(T)) + self.r * K * math.exp(-self.r * T) * (1 - Nd2)
        )
        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho,
        }

    def smooth_iv_surface(self, strikes: np.ndarray, maturities: np.ndarray, ivs: np.ndarray) -> np.ndarray:
        """Simple surface smoothing via Gaussian kernel regression."""
        if strikes.size == 0:
            return ivs
        # Normalize inputs
        ks = (strikes - strikes.mean()) / (strikes.std() + 1e-6)
        ts = (maturities - maturities.mean()) / (maturities.std() + 1e-6)
        coords = np.stack([ks, ts], axis=1)
        smoothed = np.zeros_like(ivs)
        for i, pt in enumerate(coords):
            dist = np.linalg.norm(coords - pt, axis=1)
            w = np.exp(-0.5 * (dist / 0.6) ** 2)
            smoothed[i] = np.sum(w * ivs) / (np.sum(w) + 1e-8)
        return smoothed

    def enrich_with_greeks(self, chain: List[OptionContractSnapshot]) -> List[OptionContractSnapshot]:
        """Return chain with Greeks populated where missing."""
        enriched: List[OptionContractSnapshot] = []
        for snap in chain:
            if snap.delta is not None:
                enriched.append(snap)
                continue
            if snap.underlying_price is None or snap.implied_vol is None:
                enriched.append(snap)
                continue
            T = max((snap.expiry - snap.as_of).total_seconds() / (365 * 24 * 3600), 1e-6)
            greeks = self.black_scholes_greeks(
                S=snap.underlying_price,
                K=snap.strike,
                T=T,
                sigma=snap.implied_vol,
                option_type=snap.option_type,
            )
            enriched.append(
                OptionContractSnapshot(
                    **{**snap.__dict__, **greeks},
                )
            )
        return enriched

    # --- Helpers -----------------------------------------------------------
    def _snapshot_to_row(self, snap: OptionContractSnapshot) -> dict:
        return {
            "as_of": snap.as_of,
            "underlying_symbol": snap.underlying_symbol,
            "option_symbol": snap.option_symbol,
            "expiry": snap.expiry,
            "strike": snap.strike,
            "option_type": snap.option_type,
            "bid": snap.bid,
            "ask": snap.ask,
            "last_price": snap.last_price,
            "bid_size": snap.bid_size,
            "ask_size": snap.ask_size,
            "implied_vol": snap.implied_vol,
            "delta": snap.delta,
            "gamma": snap.gamma,
            "vega": snap.vega,
            "theta": snap.theta,
            "rho": snap.rho,
            "open_interest": snap.open_interest,
            "volume": snap.volume,
            "underlying_price": snap.underlying_price,
            "data_source": snap.data_source,
            "extra": snap.extra,
        }

    # --- Example orchestrator ---------------------------------------------
    async def process_realtime_chain(self, chain: List[OptionContractSnapshot]) -> None:
        """Example end-to-end step: fill greeks, smooth IV (in-place), upsert."""
        # Enrich Greeks
        chain = self.enrich_with_greeks(chain)
        # Smooth IV surface
        ivs = np.array([c.implied_vol or 0 for c in chain], dtype=float)
        strikes = np.array([c.strike for c in chain], dtype=float)
        maturities = np.array([max((c.expiry - c.as_of).days, 1) for c in chain], dtype=float)
        smoothed = self.smooth_iv_surface(strikes, maturities, ivs)
        for i, c in enumerate(chain):
            chain[i].implied_vol = float(smoothed[i]) if smoothed[i] else c.implied_vol
        await self.ingest_chain(chain)


async def example_realtime_usage() -> None:
    """Illustrative usage: fetch, enrich, store."""
    pipeline = OptionsPipeline()
    sample = OptionContractSnapshot(
        as_of=datetime.utcnow(),
        underlying_symbol="NIFTY",
        option_symbol="NIFTY24FEB18000CE",
        expiry=datetime.utcnow(),
        strike=18000,
        option_type=OptionType.CALL,
        bid=10.0,
        ask=11.0,
        last_price=10.5,
        implied_vol=0.25,
        open_interest=1000,
        volume=500,
        underlying_price=17950,
    )
    await pipeline.process_realtime_chain([sample])


if __name__ == "__main__":
    asyncio.run(example_realtime_usage())
