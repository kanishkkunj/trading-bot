#!/usr/bin/env python3
"""Seed database with sample data."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, init_db

from app.models.strategy import StrategyConfig





async def seed_strategies(db: AsyncSession) -> None:
    """Seed sample strategies."""
    from sqlalchemy import select

    # Check if strategies exist
    result = await db.execute(select(StrategyConfig))
    if result.scalars().first():
        print("Strategies already exist, skipping...")
        return

    strategies = [
        StrategyConfig(
            name="SMA Crossover",
            description="Simple moving average crossover strategy",
            version="1.0.0",
            parameters={
                "fast_period": 20,
                "slow_period": 50,
                "rsi_period": 14,
                "rsi_overbought": 70,
                "rsi_oversold": 30,
            },
            symbols=["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"],
            is_default=True,
        ),
        StrategyConfig(
            name="Momentum",
            description="Momentum-based strategy with volume confirmation",
            version="1.0.0",
            parameters={
                "lookback_period": 20,
                "momentum_threshold": 0.05,
                "volume_multiplier": 1.5,
            },
            symbols=["INFY.NS", "ICICIBANK.NS", "ITC.NS"],
            is_default=False,
        ),
        StrategyConfig(
            name="Mean Reversion",
            description="Bollinger Bands mean reversion strategy",
            version="1.0.0",
            parameters={
                "bb_period": 20,
                "bb_std_dev": 2.0,
                "rsi_period": 14,
            },
            symbols=["HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS"],
            is_default=False,
        ),
    ]

    for strategy in strategies:
        db.add(strategy)

    await db.commit()
    print(f"Created {len(strategies)} sample strategies")


async def seed_market_data(db: AsyncSession) -> None:
    """Seed sample market data."""
    from app.data.fetcher import DataFetcher

    fetcher = DataFetcher(db)

    # Fetch data for a few key stocks
    symbols = ["RELIANCE.NS", "TCS.NS", "NIFTY50.NS"]

    for symbol in symbols:
        try:
            count = await fetcher.fetch_and_store(symbol, "1d", days=30)
            print(f"Fetched {count} candles for {symbol}")
        except Exception as e:
            print(f"Failed to fetch data for {symbol}: {e}")


async def main() -> None:
    """Main seed function."""
    print("🌱 Seeding database...")
    print("=" * 40)


    async with AsyncSessionLocal() as db:
        # Seed strategies
        print("\n📊 Creating sample strategies...")
        await seed_strategies(db)

        # Seed market data
        print("\n📈 Fetching sample market data...")
        await seed_market_data(db)

    print("\n" + "=" * 40)
    print("✅ Database seeding complete!")


if __name__ == "__main__":
    asyncio.run(main())
