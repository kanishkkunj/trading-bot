"""Persistence helpers for institutional intelligence (Timescale-backed)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.institutional.fii_dii_tracker import FlowSnapshot
from app.institutional.insider_tracker import InsiderEvent
from app.institutional.fund_holdings import HoldingsSnapshot
from app.models.institutional import FiiDiiFlow, InsiderActivity, FundHoldingSnapshot


class InstitutionalStorage:
    """Persist and hydrate institutional trackers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_flow_snapshot(self, snap: FlowSnapshot) -> FiiDiiFlow:
        rec = FiiDiiFlow(
            as_of=snap.as_of,
            fii_cash=snap.fii_cash,
            fii_futures=snap.fii_futures,
            dii_cash=snap.dii_cash,
            dii_futures=snap.dii_futures,
            sector_flows=snap.sector_flows,
        )
        self.db.add(rec)
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def load_flow_history(self, limit: int = 60) -> List[FlowSnapshot]:
        result = await self.db.execute(
            select(FiiDiiFlow).order_by(FiiDiiFlow.as_of.desc()).limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return [
            FlowSnapshot(
                as_of=row.as_of,
                fii_cash=float(row.fii_cash or 0.0),
                fii_futures=float(row.fii_futures or 0.0),
                dii_cash=float(row.dii_cash or 0.0),
                dii_futures=float(row.dii_futures or 0.0),
                sector_flows=row.sector_flows or {},
            )
            for row in rows
        ]

    async def save_insider_event(self, ev: InsiderEvent) -> InsiderActivity:
        rec = InsiderActivity(
            as_of=ev.as_of,
            symbol=ev.symbol,
            actor=ev.actor,
            action=ev.action,
            quantity=ev.quantity,
            value=ev.value,
            pledge_pct=ev.pledge_pct,
        )
        self.db.add(rec)
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def load_insider_events(
        self,
        symbol: Optional[str] = None,
        window_days: int = 90,
        limit: int = 500,
    ) -> List[InsiderEvent]:
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        stmt = select(InsiderActivity).where(InsiderActivity.as_of >= cutoff)
        if symbol:
            stmt = stmt.where(InsiderActivity.symbol == symbol)
        stmt = stmt.order_by(InsiderActivity.as_of.desc()).limit(limit)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [
            InsiderEvent(
                as_of=row.as_of,
                symbol=row.symbol,
                actor=row.actor or "",
                action=row.action,
                quantity=float(row.quantity) if row.quantity is not None else 0.0,
                value=float(row.value) if row.value is not None else 0.0,
                pledge_pct=float(row.pledge_pct) if row.pledge_pct is not None else None,
            )
            for row in rows
        ]

    async def save_fund_holding_snapshot(
        self,
        snap: HoldingsSnapshot,
        as_of: Optional[datetime] = None,
    ) -> FundHoldingSnapshot:
        rec = FundHoldingSnapshot(
            as_of=as_of or datetime.utcnow(),
            fund=snap.fund,
            symbol_weights=snap.symbol_weights,
        )
        self.db.add(rec)
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def load_fund_holdings(
        self,
        fund: Optional[str] = None,
        limit: int = 200,
    ) -> List[HoldingsSnapshot]:
        stmt = select(FundHoldingSnapshot).order_by(FundHoldingSnapshot.as_of.desc()).limit(limit)
        if fund:
            stmt = select(FundHoldingSnapshot).where(FundHoldingSnapshot.fund == fund).order_by(
                FundHoldingSnapshot.as_of.desc()
            ).limit(limit)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [HoldingsSnapshot(fund=row.fund, symbol_weights=row.symbol_weights or {}) for row in rows]

    async def hydrate_trackers(
        self,
        flows_tracker,
        insider_tracker,
        holdings_tracker,
        flow_limit: int = 60,
        insider_window_days: int = 90,
    ) -> None:
        """Load recent persistence into in-memory trackers for immediate signals."""
        flows = await self.load_flow_history(limit=flow_limit)
        for snap in flows:
            flows_tracker.ingest(snap)

        insiders = await self.load_insider_events(window_days=insider_window_days)
        for ev in insiders:
            insider_tracker.ingest(ev)

        holdings = await self.load_fund_holdings(limit=200)
        for snap in holdings:
            holdings_tracker.ingest(snap)
