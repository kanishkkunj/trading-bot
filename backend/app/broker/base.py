"""Abstract broker interface."""

from abc import ABC, abstractmethod
from typing import Optional

from app.models.order import Order


class BaseBroker(ABC):
    """Abstract base class for broker adapters."""

    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """Place an order with the broker."""
        pass

    @abstractmethod
    async def cancel_order(self, order: Order) -> Order:
        """Cancel an existing order."""
        pass

    @abstractmethod
    async def modify_order(self, order: Order, new_quantity: Optional[int] = None, new_price: Optional[float] = None) -> Order:
        """Modify an existing order."""
        pass

    @abstractmethod
    async def get_order_status(self, order: Order) -> Order:
        """Get current status of an order."""
        pass

    @abstractmethod
    async def get_positions(self) -> list[dict]:
        """Get current positions."""
        pass

    @abstractmethod
    async def get_account_info(self) -> dict:
        """Get account information."""
        pass
