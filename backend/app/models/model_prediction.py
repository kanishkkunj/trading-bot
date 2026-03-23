"""Model predictions."""

from datetime import datetime
from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, Integer, Enum
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PredictionType(str, PyEnum):
    """Prediction output type."""

    CLASSIFICATION = "CLASSIFICATION"
    REGRESSION = "REGRESSION"


class ModelPrediction(Base):
    """Per-symbol prediction outputs and metadata."""

    __tablename__ = "model_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    horizon_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prediction_type: Mapped[PredictionType] = mapped_column(Enum(PredictionType), nullable=False)
    prediction_value: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    prediction_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    probabilities: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    feature_set: Mapped[str | None] = mapped_column(String(50), nullable=True)
    feature_store_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    regime_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ModelPrediction(model={self.model_name}, symbol={self.symbol}, as_of={self.as_of})>"
        )
