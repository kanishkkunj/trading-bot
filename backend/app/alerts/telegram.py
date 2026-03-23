"""Telegram alert provider (placeholder for Sprint 3)."""

from typing import Optional

import httpx


class TelegramAlert:
    """Telegram bot alert provider."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message via Telegram."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False

    async def send_trade_alert(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        pnl: Optional[float] = None,
    ) -> bool:
        """Send a trade alert."""
        message = f"""
<b>Trade Alert</b>

Symbol: <code>{symbol}</code>
Action: <b>{action}</b>
Quantity: {quantity}
Price: ₹{price:.2f}
"""
        if pnl is not None:
            emoji = "🟢" if pnl > 0 else "🔴"
            message += f"PnL: {emoji} ₹{pnl:.2f}"

        return await self.send_message(message)

    async def send_daily_report(
        self,
        date: str,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        daily_pnl: float,
        total_pnl: float,
    ) -> bool:
        """Send daily PnL report."""
        emoji = "🟢" if daily_pnl > 0 else "🔴"
        message = f"""
<b>Daily Report - {date}</b>

Total Trades: {total_trades}
Winning: {winning_trades}
Losing: {losing_trades}

Daily PnL: {emoji} ₹{daily_pnl:.2f}
Total PnL: ₹{total_pnl:.2f}
"""
        return await self.send_message(message)

    async def send_risk_alert(self, message: str) -> bool:
        """Send a risk alert."""
        formatted_message = f"""
🚨 <b>RISK ALERT</b> 🚨

{message}
"""
        return await self.send_message(formatted_message)
