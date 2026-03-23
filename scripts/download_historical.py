#!/usr/bin/env python3
"""Download bulk historical data."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.data.fetcher import DataFetcher
from app.db.session import AsyncSessionLocal


async def main() -> None:
    """Download historical data for all NIFTY 50 stocks."""
    print("📥 Downloading Historical Data")
    print("=" * 40)

    async with AsyncSessionLocal() as db:
        fetcher = DataFetcher(db)

        print("\nFetching NIFTY 50 data for the last year...")
        results = await fetcher.fetch_nifty50(timeframe="1d", days=365)

        print("\nResults:")
        for symbol, result in results.items():
            status = result.get("status", "unknown")
            if status == "success":
                print(f"  ✅ {symbol}: {result.get('count', 0)} candles")
            else:
                print(f"  ❌ {symbol}: {result.get('error', 'unknown error')}")

    print("\n" + "=" * 40)
    print("Download complete!")


if __name__ == "__main__":
    asyncio.run(main())
