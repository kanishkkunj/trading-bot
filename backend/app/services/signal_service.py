"""Signal service."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal, SignalAction, SignalStatus
from app.schemas.signal import SignalCreate


class SignalService:
    """Service for signal operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_signal(self, signal_data: SignalCreate) -> Signal:
        """Create a new trading signal."""
        signal = Signal(
            symbol=signal_data.symbol,
            action=signal_data.action,
            confidence=signal_data.confidence,
            suggested_quantity=signal_data.suggested_quantity,
            suggested_price=signal_data.suggested_price,
            model_version=signal_data.model_version,
            features_used=signal_data.features_used,
            valid_until=signal_data.valid_until
            or (datetime.utcnow() + timedelta(minutes=15)),
        )

        self.db.add(signal)
        await self.db.commit()
        await self.db.refresh(signal)

        return signal

    async def get_signal(self, signal_id: str) -> Optional[Signal]:
        """Get signal by ID."""
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        return result.scalar_one_or_none()

    async def get_signals(
        self,
        skip: int = 0,
        limit: int = 100,
        symbol: Optional[str] = None,
        action: Optional[SignalAction] = None,
        status: Optional[SignalStatus] = None,
        min_confidence: Optional[float] = None,
    ) -> list[Signal]:
        """Get signals with optional filters."""
        query = select(Signal)

        if symbol:
            query = query.where(Signal.symbol == symbol)
        if action:
            query = query.where(Signal.action == action)
        if status:
            query = query.where(Signal.status == status)
        if min_confidence:
            query = query.where(Signal.confidence >= min_confidence)

        query = query.order_by(desc(Signal.created_at)).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_signal_status(
        self,
        signal_id: str,
        status: SignalStatus,
        order_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[Signal]:
        """Update signal status."""
        signal = await self.get_signal(signal_id)

        if not signal:
            return None

        signal.status = status
        if order_id:
            signal.order_id = order_id
        if reason:
            signal.status_reason = reason

        if status == SignalStatus.EXECUTED:
            signal.executed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(signal)

        return signal

    async def expire_old_signals(self) -> int:
        """Expire signals past their valid_until time."""
        result = await self.db.execute(
            select(Signal).where(
                Signal.status == SignalStatus.PENDING,
                Signal.valid_until < datetime.utcnow(),
            )
        )

        expired_signals = result.scalars().all()
        count = 0

        for signal in expired_signals:
            signal.status = SignalStatus.EXPIRED
            count += 1

        if count > 0:
            await self.db.commit()

        return count

    async def get_signal_count(self) -> int:
        """Get total signal count."""
        result = await self.db.execute(select(Signal))
        return len(result.scalars().all())
