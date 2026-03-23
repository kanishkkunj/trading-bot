"""Paper trading broker simulator."""

import random
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.base import BaseBroker
from app.models.order import Order, OrderType, OrderStatus
from app.services.market_service import MarketService


class PaperBroker(BaseBroker):
    """Paper trading broker simulator with realistic fill simulation."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.market_service = MarketService(db)

        # Simulation parameters
        self.slippage_pct = 0.02  # 0.02% slippage
        self.rejection_rate = 0.05  # 5% rejection rate
        self.partial_fill_rate = 0.1  # 10% partial fill rate

    async def place_order(self, order: Order) -> Order:
        """Simulate placing an order."""
        # Check for random rejection
        if random.random() < self.rejection_rate:
            order.status = OrderStatus.REJECTED
            order.status_message = "Simulated rejection: Insufficient liquidity"
            order.updated_at = datetime.utcnow()
            await self.db.commit()
            return order

        # Get current market price
        quote = await self.market_service.get_live_quote(order.symbol)

        if not quote or not quote.get("last_price"):
            order.status = OrderStatus.REJECTED
            order.status_message = "Unable to get market price"
            order.updated_at = datetime.utcnow()
            await self.db.commit()
            return order

        market_price = quote["last_price"]

        # Determine fill price based on order type
        if order.order_type == OrderType.MARKET:
            fill_price = self._apply_slippage(market_price, order.side)
        elif order.order_type == OrderType.LIMIT:
            if order.price is None:
                order.status = OrderStatus.REJECTED
                order.status_message = "Limit price required"
                order.updated_at = datetime.utcnow()
                await self.db.commit()
                return order

            # Check if limit order can be filled
            if (order.side == "BUY" and order.price >= market_price) or \
               (order.side == "SELL" and order.price <= market_price):
                fill_price = order.price
            else:
                # Limit not reached, order stays open
                order.status = OrderStatus.PLACED
                order.placed_at = datetime.utcnow()
                order.updated_at = datetime.utcnow()
                await self.db.commit()
                return order
        else:
            # Other order types default to market for paper trading
            fill_price = self._apply_slippage(market_price, order.side)

        # Simulate fill
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_price = fill_price
        order.placed_at = datetime.utcnow()
        order.filled_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(order)

        return order

    async def cancel_order(self, order: Order) -> Order:
        """Cancel an order."""
        if order.status not in [OrderStatus.PENDING, OrderStatus.PLACED]:
            raise ValueError(f"Cannot cancel order with status: {order.status}")

        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(order)

        return order

    async def modify_order(
        self,
        order: Order,
        new_quantity: Optional[int] = None,
        new_price: Optional[float] = None,
    ) -> Order:
        """Modify an order."""
        if order.status != OrderStatus.PLACED:
            raise ValueError(f"Cannot modify order with status: {order.status}")

        if new_quantity:
            order.quantity = new_quantity
        if new_price:
            order.price = new_price

        order.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(order)

        return order

    async def get_order_status(self, order: Order) -> Order:
        """Get order status (no-op for paper broker)."""
        return order

    async def get_positions(self) -> list[dict]:
        """Get positions (returns empty for paper broker)."""
        return []

    async def get_account_info(self) -> dict:
        """Get account info for paper trading."""
        return {
            "broker": "PAPER",
            "account_id": "PAPER_ACCOUNT",
            "available_funds": 1000000.0,
            "used_funds": 0.0,
            "total_funds": 1000000.0,
        }

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply realistic slippage to price."""
        slippage = price * (self.slippage_pct / 100)

        if side == "BUY":
            # Buy at slightly higher price
            return round(price + slippage, 4)
        else:
            # Sell at slightly lower price
            return round(price - slippage, 4)
