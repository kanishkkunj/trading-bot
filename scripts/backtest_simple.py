#!/usr/bin/env python3
"""
Simple Backtest of Claude Trading Model on Historical Data
Simulates the trading system on past NIFTY prices to calculate P&L.
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
import numpy as np
import pandas as pd
import yfinance as yf

# Configuration
STARTING_CAPITAL = 100_000  # INR
MAX_CAPITAL_PER_TRADE = 30_000
MAX_DAILY_LOSS = 2_000
CONFIDENCE_THRESHOLD = 6

# API Config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CLAUDE_MODEL = "anthropic/claude-sonnet-4-5"


def load_env_file(env_path: str = ".env") -> None:
    """Load key=value pairs from .env into process env if not already set."""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def extract_json_object(text: str) -> Optional[dict]:
    """Extract JSON from plain text or markdown fenced blocks."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("{"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            return None

    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(s[first:last + 1])
        except json.JSONDecodeError:
            return None
    return None


class TechnicalIndicators:
    """Compute technical indicators."""

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)
        return 100 - (100 / (1 + rs))


class BacktestEngine:
    """Simulate trades with Claude decisions."""

    def __init__(self):
        self.cash = STARTING_CAPITAL
        self.positions = {}
        self.trades = []
        self.daily_pnl = {}

    def buy(self, time, symbol, qty, price, confidence, reason=""):
        cost = qty * price
        if cost > self.cash:
            return False
        if cost > MAX_CAPITAL_PER_TRADE:
            return False
        self.cash -= cost
        self.positions[symbol] = {"qty": qty, "entry": price, "time": time}
        self.trades.append({
            "time": time,
            "type": "BUY",
            "qty": qty,
            "price": price,
            "cost": cost,
            "conf": confidence,
        })
        print(f"[BUY]  {time.strftime('%H:%M')} | {qty} @ {price:.0f} | Cost: {cost:,.0f} | Conf: {confidence}/10")
        return True

    def sell(self, time, symbol, price, confidence, reason=""):
        if symbol not in self.positions:
            return False
        pos = self.positions[symbol]
        qty = pos["qty"]
        entry = pos["entry"]
        pnl = (price - entry) * qty
        self.cash += price * qty
        self.trades.append({
            "time": time,
            "type": "SELL",
            "qty": qty,
            "price": price,
            "entry": entry,
            "pnl": pnl,
            "conf": confidence,
        })
        del self.positions[symbol]
        print(f"[SELL] {time.strftime('%H:%M')} | {qty} @ {price:.0f} | Entry: {entry:.0f} | P&L: {pnl:+,.0f} | Conf: {confidence}/10")
        
        # Track daily P&L
        date = time.date()
        if pnl < 0:
            self.daily_pnl[date] = self.daily_pnl.get(date, 0) + pnl
        return True

    def get_stats(self):
        closed = [t for t in self.trades if "pnl" in t]
        won = [t for t in closed if t["pnl"] > 0]
        lost = [t for t in closed if t["pnl"] < 0]
        total_pnl = sum(t.get("pnl", 0) for t in self.trades)
        
        return {
            "start_capital": STARTING_CAPITAL,
            "final_capital": self.cash,
            "total_pnl": total_pnl,
            "return_pct": (total_pnl / STARTING_CAPITAL) * 100,
            "total_trades": len([t for t in self.trades if t["type"] in ("BUY", "SELL")]),
            "closed_trades": len(closed),
            "wins": len(won),
            "losses": len(lost),
            "win_rate": (len(won) / len(closed) * 100) if closed else 0,
            "avg_win": sum(t["pnl"] for t in won) / len(won) if won else 0,
            "avg_loss": sum(t["pnl"] for t in lost) / len(lost) if lost else 0,
        }


class ClaudeBacktest:
    """Backtest Claude on historical data."""

    def __init__(self):
        self.engine = BacktestEngine()
        self.client = httpx.AsyncClient(timeout=60)
        self.decision_stats = {
            "checks": 0,
            "api_errors": 0,
            "parse_fail": 0,
            "hold": 0,
            "buy": 0,
            "sell": 0,
            "low_conf": 0,
            "executed_buy": 0,
            "executed_sell": 0,
        }
        self._printed_demo_note = False

    async def ask_claude(self, data: dict) -> Optional[dict]:
        """Call Claude for trading decision."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            if not self._printed_demo_note:
                print("[INFO] OPENROUTER_API_KEY not found. Running in demo mode (always HOLD).")
                self._printed_demo_note = True
            return {"action": "HOLD", "confidence": 5, "reason": "Demo"}

        system = """You are a trading expert. Decide BUY/SELL/HOLD based on market data.
Respond with ONLY valid JSON:
{"action": "BUY"|"SELL"|"HOLD", "confidence": 1-10, "quantity": int, "entry_price": float, 
 "stop_loss": float, "target_price": float, "reason": "str"}"""

        try:
            resp = await self.client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/tradecraft",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "messages": [{"role": "user", "content": json.dumps(data)}],
                    "system": system,
                    "max_tokens": 256,
                },
            )
            resp.raise_for_status()
            result = resp.json()
            if "choices" in result:
                content = result["choices"][0]["message"]["content"].strip()
                parsed = extract_json_object(content)
                if parsed is not None:
                    return parsed
                self.decision_stats["parse_fail"] += 1
                if self.decision_stats["parse_fail"] <= 3:
                    preview = content.replace("\n", " ")
                    print(f"[WARN] Could not parse Claude JSON. Sample: {preview[:140]}")
        except Exception as e:
            self.decision_stats["api_errors"] += 1
            print(f"[ERROR] Claude: {e}")
        return None

    async def run(self, days: int = 30):
        """Run backtest on historical data."""
        print("\n" + "="*70)
        print("CLAUDE BACKTEST - Historical NIFTY Data")
        print("="*70)
        print(f"Period: Last {days} days | Candle: 15-min")
        print(f"Start Capital: INR {STARTING_CAPITAL:,.0f}")
        print(f"Max Per Trade: INR {MAX_CAPITAL_PER_TRADE:,.0f}")
        print(f"Confidence Threshold: {CONFIDENCE_THRESHOLD}/10")
        print("="*70 + "\n")

        env_key_present = bool(os.getenv("OPENROUTER_API_KEY"))
        print(f"[*] OpenRouter key loaded: {env_key_present}")

        # Fetch data
        print("[*] Fetching historical data...")
        end = datetime.now()
        start = end - timedelta(days=days)
        
        try:
            df = yf.download("^NSEI", start=start, end=end, interval="15m", progress=False)
        except Exception as e:
            print(f"[ERROR] Failed to fetch: {e}")
            return

        if df.empty:
            print("[ERROR] No data fetched")
            return

        # Clean columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.reset_index()
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Time"})
        else:
            df = df.rename(columns={"Date": "Time"})
        
        df = df.set_index("Time").sort_index()
        print(f"[OK] Fetched {len(df)} candles\n")

        # Compute indicators
        print("[*] Computing indicators...")
        close = df["Close"].astype(float)
        df["EMA9"] = TechnicalIndicators.ema(close, 9)
        df["EMA21"] = TechnicalIndicators.ema(close, 21)
        df["RSI"] = TechnicalIndicators.rsi(close, 14)
        print("[OK] Indicators ready\n")

        # Simulate trading
        print("[*] Simulating trades...\n")
        print("-" * 70)
        eligible_rows = 0
        
        for idx, (time, row) in enumerate(df.iterrows()):
            if pd.isna(row["EMA9"]) or pd.isna(row["EMA21"]):
                continue

            # Check every 5 candles (~75 mins)
            if idx % 5 != 0:
                continue

            eligible_rows += 1
            self.decision_stats["checks"] += 1

            # Build payload
            payload = {
                "time": time.strftime("%Y-%m-%d %H:%M IST"),
                "symbol": "NIFTY",
                "price": float(row["Close"]),
                "ema9": float(row["EMA9"]),
                "ema21": float(row["EMA21"]),
                "rsi": float(row["RSI"]),
                "volume": float(row["Volume"]),
            }

            # Get Claude decision
            decision = await self.ask_claude(payload)
            if not decision:
                continue

            action = decision.get("action", "HOLD")
            conf = int(decision.get("confidence", 0))
            qty = int(decision.get("quantity", 1))

            if action == "HOLD":
                self.decision_stats["hold"] += 1
                continue
            if action == "BUY":
                self.decision_stats["buy"] += 1
            elif action == "SELL":
                self.decision_stats["sell"] += 1

            # Execute if confidence >= threshold
            if conf < CONFIDENCE_THRESHOLD:
                self.decision_stats["low_conf"] += 1
                continue

            if action == "BUY":
                if self.engine.buy(time, "NIFTY", qty, float(row["Close"]), conf):
                    self.decision_stats["executed_buy"] += 1
            elif action == "SELL":
                if self.engine.sell(time, "NIFTY", float(row["Close"]), conf):
                    self.decision_stats["executed_sell"] += 1

        print("\n" + "="*70)
        print("BACKTEST RESULTS")
        print("="*70)

        print("\nDecision diagnostics:")
        print(f"  Eligible candles checked: {eligible_rows}")
        print(f"  Claude calls:             {self.decision_stats['checks']}")
        print(f"  HOLD decisions:           {self.decision_stats['hold']}")
        print(f"  BUY decisions:            {self.decision_stats['buy']}")
        print(f"  SELL decisions:           {self.decision_stats['sell']}")
        print(f"  Low confidence skipped:   {self.decision_stats['low_conf']}")
        print(f"  Parse failures:           {self.decision_stats['parse_fail']}")
        print(f"  API errors:               {self.decision_stats['api_errors']}")
        print(f"  Executed BUY:             {self.decision_stats['executed_buy']}")
        print(f"  Executed SELL:            {self.decision_stats['executed_sell']}")

        stats = self.engine.get_stats()
        print(f"\nFinancial:")
        print(f"  Start Capital:  INR {stats['start_capital']:>12,.0f}")
        print(f"  Total P&L:      INR {stats['total_pnl']:>12,.0f}")
        print(f"  Return:         {stats['return_pct']:>13.2f}%")
        print(f"  Final Capital:  INR {stats['final_capital']:>12,.0f}")
        
        print(f"\nTrades:")
        print(f"  Total Actions:  {stats['total_trades']:>13}")
        print(f"  Closed Trades:  {stats['closed_trades']:>13}")
        print(f"  Wins:           {stats['wins']:>13}")
        print(f"  Losses:         {stats['losses']:>13}")
        print(f"  Win Rate:       {stats['win_rate']:>12.1f}%")
        print(f"  Avg Win:        INR {stats['avg_win']:>12,.0f}")
        print(f"  Avg Loss:       INR {stats['avg_loss']:>12,.0f}")
        
        print("="*70 + "\n")
        await self.client.aclose()


async def main():
    load_env_file()
    bt = ClaudeBacktest()
    await bt.run(days=30)


if __name__ == "__main__":
    asyncio.run(main())
