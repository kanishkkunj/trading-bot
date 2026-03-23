"""Zerodha Kite Connect broker adapter (placeholder for Sprint 4)."""

from typing import Optional

from app.broker.base import BaseBroker
from app.models.order import Order


class ZerodhaBroker(BaseBroker):
    """Zerodha Kite Connect broker adapter."""

    def __init__(self, api_key: str, api_secret: str, access_token: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.base_url = "https://api.kite.trade"

    async def place_order(self, order: Order) -> Order:
        """Place an order via Kite Connect."""
        # TODO: Implement in Sprint 4
        raise NotImplementedError("Zerodha integration coming in Sprint 4")

    async def cancel_order(self, order: Order) -> Order:
        """Cancel an order via Kite Connect."""
        # TODO: Implement in Sprint 4
        raise NotImplementedError("Zerodha integration coming in Sprint 4")

    async def modify_order(
        self,
        order: Order,
        new_quantity: Optional[int] = None,
        new_price: Optional[float] = None,
    ) -> Order:
        """Modify an order via Kite Connect."""
        # TODO: Implement in Sprint 4
        raise NotImplementedError("Zerodha integration coming in Sprint 4")

    async def get_order_status(self, order: Order) -> Order:
        """Get order status from Kite Connect."""
        # TODO: Implement in Sprint 4
        raise NotImplementedError("Zerodha integration coming in Sprint 4")

    async def get_positions(self) -> list[dict]:
        """Get positions from Kite Connect."""
        # TODO: Implement in Sprint 4
        raise NotImplementedError("Zerodha integration coming in Sprint 4")

    async def get_account_info(self) -> dict:
        """Get account info from Kite Connect."""
        # TODO: Implement in Sprint 4
        raise NotImplementedError("Zerodha integration coming in Sprint 4")
