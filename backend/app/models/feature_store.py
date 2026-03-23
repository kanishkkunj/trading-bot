"""Feature store rows."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Integer, Numeric, DateTime, Boolean
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FeatureStoreRow(Base):
    """Feature vectors by timestamp/symbol."""

    __tablename__ = "feature_store"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    feature_set: Mapped[str] = mapped_column(String(50), nullable=False)
    horizon_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_values: Mapped[dict] = mapped_column(postgresql.JSONB, nullable=False)
    label_value: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    label_available: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    regime_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<FeatureStoreRow(symbol={self.symbol}, ts={self.as_of}, set={self.feature_set})>"
