"""WhatsApp alert provider (placeholder for Sprint 3)."""

from typing import Optional


class WhatsAppAlert:
    """WhatsApp alert provider (via Twilio or similar)."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str, to_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_number = to_number

    async def send_message(self, message: str) -> bool:
        """Send a message via WhatsApp."""
        # TODO: Implement in Sprint 3
        # This would use Twilio API or similar
        return True

    async def send_trade_alert(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        pnl: Optional[float] = None,
    ) -> bool:
        """Send a trade alert."""
        message = f"Trade Alert: {action} {quantity} {symbol} @ ₹{price:.2f}"
        if pnl is not None:
            message += f" | PnL: ₹{pnl:.2f}"
        return await self.send_message(message)
