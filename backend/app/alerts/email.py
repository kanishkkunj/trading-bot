"""Email alert provider (placeholder for Sprint 3)."""

from typing import Optional


class EmailAlert:
    """Email alert provider."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: list[str],
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails

    async def send_email(
        self,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """Send an email."""
        # TODO: Implement in Sprint 3
        # This would use aiosmtplib or similar
        return True

    async def send_daily_report(self, report_data: dict) -> bool:
        """Send daily report via email."""
        subject = f"TradeCraft Daily Report - {report_data.get('date')}"
        body = f"""
Daily Trading Report

Date: {report_data.get('date')}
Total Trades: {report_data.get('total_trades')}
Daily PnL: ₹{report_data.get('daily_pnl', 0):.2f}

View full details in the dashboard.
"""
        return await self.send_email(subject, body)
