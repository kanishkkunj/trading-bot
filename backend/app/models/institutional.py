"""Institutional intelligence persistence models (Timescale-backed)."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FiiDiiFlow(Base):
    """Daily FII/DII flow snapshot."""

    __tablename__ = "fii_dii_flows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fii_cash: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    fii_futures: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    dii_cash: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    dii_futures: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    sector_flows: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FiiDiiFlow(as_of={self.as_of}, fii_cash={self.fii_cash}, dii_cash={self.dii_cash})>"


class InsiderActivity(Base):
    """Promoter/insider activity, bulk-block deals, and pledges."""

    __tablename__ = "insider_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # buy/sell/pledge
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    pledge_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InsiderActivity(symbol={self.symbol}, action={self.action}, as_of={self.as_of})>"


class FundHoldingSnapshot(Base):
    """Mutual fund / FII/DII holdings by symbol weight."""

    __tablename__ = "fund_holdings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fund: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    symbol_weights: Mapped[dict] = mapped_column(postgresql.JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FundHoldingSnapshot(fund={self.fund}, as_of={self.as_of})>"
