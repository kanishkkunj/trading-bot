"""Market-hour scheduler (placeholder for Sprint 3)."""

from datetime import datetime, time
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


class MarketScheduler:
    """Scheduler for market-hour jobs."""

    # Indian market hours (IST)
    MARKET_OPEN = time(9, 15)
    MARKET_CLOSE = time(15, 30)
    # No new directional entry orders after this time (15 min before close)
    ENTRY_CUTOFF = time(15, 15)

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    def start(self) -> None:
        """Start the scheduler."""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True

    def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False

    def add_signal_generation_job(self, func: Callable, interval_minutes: int = 15) -> None:
        """Add signal generation job during market hours."""
        # Run every N minutes during market hours (9:15 AM - 3:30 PM IST)
        self.scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=f"{self.MARKET_OPEN.hour}-{self.MARKET_CLOSE.hour}",
                minute=f"*/{interval_minutes}",
            ),
            id="signal_generation",
            replace_existing=True,
        )

    def add_eod_report_job(self, func: Callable) -> None:
        """Add end-of-day report job."""
        # Run at 3:35 PM IST
        self.scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=15,
                minute=35,
            ),
            id="eod_report",
            replace_existing=True,
        )

    def add_market_open_job(self, func: Callable) -> None:
        """Add market open preparation job."""
        # Run at 9:00 AM IST
        self.scheduler.add_job(
            func,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=9,
                minute=0,
            ),
            id="market_open_prep",
            replace_existing=True,
        )

    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        now = datetime.now()

        # Check if weekday (Monday = 0, Friday = 4)
        if now.weekday() > 4:
            return False

        # Check market hours
        current_time = now.time()
        return self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE

    def is_within_entry_window(self) -> bool:
        """Return True only when new directional entries are safe.

        Entries are blocked from ENTRY_CUTOFF (15:15) to market close so that
        the bot is never caught opening fresh positions minutes before session end.
        """
        if not self.is_market_open():
            return False
        return datetime.now().time() < self.ENTRY_CUTOFF
