"""Order service."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderSide, OrderType, OrderStatus
from app.schemas.order import OrderCreate, OrderUpdate
from app.broker.paper import PaperBroker
from app.services.portfolio_service import PortfolioService
from app.services.memory_service import MemoryService
from app.services.market_service import MarketService
from app.config import get_settings


class OrderService:
    """Service for order operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.paper_broker = PaperBroker(db)
        self.portfolio_service = PortfolioService(db)
        self.memory_service = MemoryService()
        self.market_service = MarketService(db)
        self.settings = get_settings()

    async def create_order(self, user_id: str, order_data: OrderCreate) -> Order:
        """Create a new order."""
        # Enforce capital-aware sizing.
        est_price = order_data.price
        if est_price is None:
            quote = await self.market_service.get_live_quote(order_data.symbol)
            if not quote or not quote.get("last_price"):
                raise ValueError("Unable to get market price for sizing")
            est_price = quote["last_price"]

        notional = float(est_price) * order_data.quantity
        initial_capital = float(getattr(self.settings, "PAPER_INITIAL_CAPITAL", 500.0) or 500.0)
        per_trade_cap = initial_capital * 0.05  # 5% cap per trade

        if notional > per_trade_cap + 1e-6:
            raise ValueError("Order exceeds per-trade notional cap for paper trading")

        position = await self.portfolio_service.get_position(user_id, order_data.symbol)
        account = await self.portfolio_service.get_account_snapshot(user_id)
        cash = account["cash"]

        if order_data.side == OrderSide.BUY:
            if notional > cash + 1e-6:
                raise ValueError("Insufficient buying power for BUY order")
        else:  # SELL
            if position and position.quantity > 0:
                # Closing or reducing a long is allowed without cash check.
                pass
            else:
                # Opening/increasing a short: still respect per-trade cap (already checked).
                # Optional: require cash not deeply negative.
                if cash < -initial_capital:
                    raise ValueError("Insufficient buying power for short order")

        order = Order(
            user_id=user_id,
            symbol=order_data.symbol,
            side=order_data.side,
            order_type=order_data.order_type,
            quantity=order_data.quantity,
            price=order_data.price,
            trigger_price=order_data.trigger_price,
            strategy_id=order_data.strategy_id,
            signal_id=order_data.signal_id,
            status=OrderStatus.PENDING,
        )

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # Log creation event (non-blocking failure).
        await self.memory_service.log_order_event(order=order, event="created")

        # Execute through paper broker
        order = await self.paper_broker.place_order(order)

        await self.memory_service.log_order_event(order=order, event="broker_placed")

        # Update portfolio positions for filled/partial orders
        if order.status in {OrderStatus.FILLED, OrderStatus.PARTIAL_FILL, OrderStatus.PLACED}:
            await self.portfolio_service.update_position_from_order(order)
            await self.memory_service.log_order_event(order=order, event="post_portfolio_update")

        return order

    async def get_order(self, order_id: str, user_id: str) -> Optional[Order]:
        """Get order by ID (ensuring user ownership)."""
        result = await self.db.execute(
            select(Order).where(Order.id == order_id, Order.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_orders(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
    ) -> list[Order]:
        """Get all orders for a user."""
        query = select(Order).where(Order.user_id == user_id)

        if symbol:
            query = query.where(Order.symbol == symbol)
        if status:
            query = query.where(Order.status == status)

        query = query.order_by(desc(Order.created_at)).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def cancel_order(self, order_id: str, user_id: str) -> Optional[Order]:
        """Cancel an order."""
        order = await self.get_order(order_id, user_id)

        if not order:
            return None

        if order.status not in [OrderStatus.PENDING, OrderStatus.PLACED]:
            raise ValueError(f"Cannot cancel order with status: {order.status}")

        order = await self.paper_broker.cancel_order(order)

        await self.memory_service.log_order_event(order=order, event="cancelled")

        return order

    async def update_order(
        self, order_id: str, user_id: str, update_data: OrderUpdate
    ) -> Optional[Order]:
        """Update an order."""
        order = await self.get_order(order_id, user_id)

        if not order:
            return None

        if order.status not in [OrderStatus.PENDING]:
            raise ValueError(f"Cannot modify order with status: {order.status}")

        if update_data.quantity:
            order.quantity = update_data.quantity
        if update_data.price:
            order.price = update_data.price

        order.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(order)

        await self.memory_service.log_order_event(order=order, event="updated")

        return order

    async def get_order_count(self, user_id: str) -> int:
        """Get total order count for a user."""
        result = await self.db.execute(
            select(Order).where(Order.user_id == user_id)
        )
        return len(result.scalars().all())
