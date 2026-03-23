"""Portfolio service."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderSide, OrderStatus
from app.models.position import Position
from app.services.market_service import MarketService
from app.config import get_settings


class PortfolioService:
    """Service for portfolio operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.market_service = MarketService(db)

    async def get_positions(
        self, user_id: str, only_open: bool = True
    ) -> list[Position]:
        """Get all positions for a user."""
        query = select(Position).where(Position.user_id == user_id)

        if only_open:
            query = query.where(Position.is_open == True)

        result = await self.db.execute(query)
        positions = list(result.scalars().all())

        # Update current prices
        for position in positions:
            await self._update_position_price(position)

        return positions

    async def get_position(self, user_id: str, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        result = await self.db.execute(
            select(Position).where(
                Position.user_id == user_id,
                Position.symbol == symbol,
                Position.is_open == True,
            )
        )
        position = result.scalar_one_or_none()

        if position:
            await self._update_position_price(position)

        return position

    async def get_account_snapshot(self, user_id: str) -> dict:
        """Compute cash/equity using initial capital and current positions (supports longs/shorts)."""
        settings = get_settings()
        initial_capital = float(getattr(settings, "PAPER_INITIAL_CAPITAL", 500.0) or 500.0)

        positions = await self.get_positions(user_id, only_open=False)

        long_cost = sum(p.cost_basis for p in positions if p.quantity > 0 and p.is_open)
        short_proceeds = sum(p.cost_basis for p in positions if p.quantity < 0 and p.is_open)
        realized = sum(p.realized_pnl for p in positions)

        # Cash increases with short proceeds, decreases with long cost and realized losses.
        cash = initial_capital + float(realized) + short_proceeds - long_cost
        open_value = sum(p.market_value for p in positions if p.is_open)
        equity = cash + open_value

        return {
            "initial_capital": initial_capital,
            "cash": round(float(cash), 2),
            "equity": round(float(equity), 2),
            "long_cost": round(float(long_cost), 2),
            "short_proceeds": round(float(short_proceeds), 2),
            "open_value": round(float(open_value), 2),
            "realized_pnl": round(float(realized), 2),
        }

    async def _update_position_price(self, position: Position) -> None:
        """Update position with current market price and compute PnL for longs/shorts."""
        quote = await self.market_service.get_live_quote(position.symbol)

        price = quote.get("last_price") if quote else None
        if price is None:
            price = float(position.current_price or position.average_entry_price)

        position.current_price = price
        position.last_price_update = datetime.utcnow()

        qty = float(position.quantity)
        entry = float(position.average_entry_price)
        cur = float(position.current_price)

        if qty > 0:
            position.unrealized_pnl = (cur - entry) * qty
        elif qty < 0:
            position.unrealized_pnl = (entry - cur) * abs(qty)
        else:
            position.unrealized_pnl = 0.0

        await self.db.commit()

    async def update_position_from_order(self, order: Order) -> Optional[Position]:
        """Update position based on a filled order."""
        position = await self.get_position(order.user_id, order.symbol)

        if order.side == OrderSide.BUY:
            if position:
                # Update existing position
                total_cost = (
                    float(position.average_entry_price) * position.quantity
                    + float(order.average_price) * order.filled_quantity
                )
                position.quantity += order.filled_quantity
                position.average_entry_price = total_cost / position.quantity
            else:
                # Create new position
                position = Position(
                    user_id=order.user_id,
                    symbol=order.symbol,
                    quantity=order.filled_quantity,
                    average_entry_price=order.average_price,
                    is_open=True,
                )
                self.db.add(position)

        elif order.side == OrderSide.SELL:
            if not position:
                # Enter short position
                position = Position(
                    user_id=order.user_id,
                    symbol=order.symbol,
                    quantity=-order.filled_quantity,
                    average_entry_price=order.average_price,
                    is_open=True,
                )
                self.db.add(position)
            else:
                # Closing or increasing short
                qty = position.quantity
                if qty > 0:
                    # Reduce long
                    realized_pnl = (
                        float(order.average_price) - float(position.average_entry_price)
                    ) * min(qty, order.filled_quantity)
                    position.realized_pnl += realized_pnl
                    position.quantity = qty - order.filled_quantity
                else:
                    # Increase short
                    total_cost = abs(qty) * float(position.average_entry_price) + (
                        order.filled_quantity * float(order.average_price)
                    )
                    position.quantity = qty - order.filled_quantity  # more negative
                    position.average_entry_price = total_cost / abs(position.quantity)

                if position.quantity == 0:
                    position.is_open = False
                    position.closed_at = datetime.utcnow()

        # Handle closing shorts with BUY
        if order.side == OrderSide.BUY and position and position.quantity < 0:
            close_qty = min(abs(position.quantity), order.filled_quantity)
            realized_pnl = (
                float(position.average_entry_price) - float(order.average_price)
            ) * close_qty
            position.realized_pnl += realized_pnl
            position.quantity += close_qty  # less negative
            if position.quantity == 0:
                position.is_open = False
                position.closed_at = datetime.utcnow()

        if position:
            await self.db.commit()
            await self.db.refresh(position)
        else:
            await self.db.commit()

        return position

    async def get_portfolio_summary(self, user_id: str) -> dict:
        """Get portfolio summary."""
        positions = await self.get_positions(user_id, only_open=True)

        total_market_value = sum(p.market_value for p in positions)
        total_cost_basis = sum(p.cost_basis for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)

        # Get realized PnL from closed positions
        result = await self.db.execute(
            select(func.sum(Position.realized_pnl)).where(
                Position.user_id == user_id,
                Position.is_open == False,
            )
        )
        total_realized_pnl = result.scalar() or 0

        return {
            "total_positions": len(positions),
            "open_positions": len([p for p in positions if p.is_open]),
            "total_market_value": round(total_market_value, 2),
            "total_cost_basis": round(total_cost_basis, 2),
            "total_realized_pnl": round(float(total_realized_pnl), 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_pnl": round(float(total_realized_pnl) + total_unrealized_pnl, 2),
        }

    async def get_daily_pnl(self, user_id: str) -> dict:
        """Get daily PnL."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Get today's realized PnL from closed positions
        result = await self.db.execute(
            select(func.sum(Position.realized_pnl)).where(
                Position.user_id == user_id,
                Position.closed_at >= today,
            )
        )
        daily_realized = result.scalar() or 0

        # Get current unrealized PnL
        positions = await self.get_positions(user_id, only_open=True)
        daily_unrealized = sum(p.unrealized_pnl for p in positions)

        return {
            "daily_realized_pnl": round(float(daily_realized), 2),
            "daily_unrealized_pnl": round(daily_unrealized, 2),
            "daily_total_pnl": round(float(daily_realized) + daily_unrealized, 2),
        }
