import asyncio
from backtest_compare_3d import load_env_file, ClaudeComparator, simulated_neutral_research

load_env_file()


async def main() -> None:
    c = ClaudeComparator()
    payload = {
        "symbol": "NIFTY",
        "timeframe": "15m",
        "timestamp": "2026-03-17 10:00:00 IST",
        "livePrice": 23500.0,
        "candles": [],
        "indicators": {
            "ema9": 23490.0,
            "ema21": 23480.0,
            "rsi": 58.0,
            "macd": 15.0,
            "macdSignal": 12.0,
            "macdHistogram": 3.0,
        },
        "researchBrief": simulated_neutral_research(),
    }
    decision = await c.ask_claude(payload)
    print(decision)
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
