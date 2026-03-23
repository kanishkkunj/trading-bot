#!/usr/bin/env python3
"""
Backtest Claude trading model on historical NIFTY data.

Simulates the trading system on past prices to see how much it would have earned.
Uses the exact same Claude prompts and indicators as the live system.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
import yfinance as yf

# Configuration
NIFTY_SYMBOL = "^NSEI"  # NSE NIFTY Index
STARTING_CAPITAL = 100_000  # INR
MAX_CAPITAL_PER_TRADE = 30_000
MAX_DAILY_LOSS = 2_000
MAX_OPEN_POSITIONS = 3
CONFIDENCE_THRESHOLD = 6  # On 1-10 scale

# OpenRouter API config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CLAUDE_MODEL = "anthropic/claude-sonnet-4-5"


class TechnicalIndicators:
    """Compute technical indicators for market data."""

    @staticmethod
    def compute_ema(series: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def compute_macd(series: pd.Series, fast=12, slow=26, signal=9) -> tuple:
        """MACD and Signal line."""
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range."""
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        return atr


class BacktestEngine:
    """Simulates trading with Claude decisions on historical data."""

    def __init__(self, starting_capital: float = STARTING_CAPITAL):
        self.cash = starting_capital
        self.initial_capital = starting_capital
        self.positions: dict[str, dict] = {}  # symbol -> {qty, entry_price, entry_time}
        self.trades: list[dict] = []  # closed trades
        self.daily_loss: dict[str, float] = {}  # date -> cumulative loss
        self.equity_curve: list[dict] = []

    def add_trade(self, row: pd.Series, decision: dict, actual_price: float):
        """Record a trade and update position."""
        symbol = decision.get("symbol", "NIFTY")
        action = decision.get("action")
        qty = decision.get("quantity", 0)
        entry_price = decision.get("entry_price", actual_price)

        if action == "BUY":
            qty = int(qty)
            if qty <= 0:
                return False

            position_size = qty * entry_price
            if position_size > MAX_CAPITAL_PER_TRADE:
                print(f"  ⚠️  Trade rejected: position size {position_size:,.0f} exceeds max {MAX_CAPITAL_PER_TRADE:,.0f}")
                return False

            if position_size > self.cash:
                print(f"  ⚠️  Trade rejected: insufficient capital (need {position_size:,.0f}, have {self.cash:,.0f})")
                return False

            self.cash -= position_size
            self.positions[symbol] = {
                "qty": qty,
                "entry_price": actual_price,
                "entry_time": row.name,
                "stop_loss": decision.get("stop_loss", 0),
                "target": decision.get("target_price", 0),
            }
            self.trades.append(
                {
                    "time": row.name,
                    "action": "BUY",
                    "symbol": symbol,
                    "qty": qty,
                    "price": actual_price,
                    "cost": position_size,
                    "reason": decision.get("reason", ""),
                }
            )
            print(f"  ✅ BUY: {qty} @ {actual_price:.2f} (cost: {position_size:,.0f})")
            return True

        elif action == "SELL":
            if symbol not in self.positions:
                return False

            pos = self.positions[symbol]
            exit_price = actual_price
            qty = pos["qty"]
            pnl = (exit_price - pos["entry_price"]) * qty
            position_cost = pos["entry_price"] * qty

            self.cash += exit_price * qty
            self.trades.append(
                {
                    "time": row.name,
                    "action": "SELL",
                    "symbol": symbol,
                    "qty": qty,
                    "price": exit_price,
                    "proceeds": exit_price * qty,
                    "entry_price": pos["entry_price"],
                    "pnl": pnl,
                    "pnl_pct": (pnl / position_cost) * 100 if position_cost > 0 else 0,
                    "reason": decision.get("reason", ""),
                }
            )
            del self.positions[symbol]

            # Track daily loss
            date_key = row.name.date()
            if pnl < 0:
                self.daily_loss[date_key] = self.daily_loss.get(date_key, 0) + pnl
                if self.daily_loss[date_key] < -MAX_DAILY_LOSS:
                    print(f"  ⚠️  Daily loss limit breached: {self.daily_loss[date_key]:,.0f}")

            print(f"  ✅ SELL: {qty} @ {exit_price:.2f} (P&L: {pnl:+,.0f} / {pnl/position_cost*100:+.2f}%)")
            return True

        return False

    def get_mark_to_market(self, current_price: float, symbol: str = "NIFTY") -> float:
        """Calculate unrealized P&L."""
        if symbol not in self.positions:
            return 0
        pos = self.positions[symbol]
        return (current_price - pos["entry_price"]) * pos["qty"]

    def get_equity(self, current_price: float, symbol: str = "NIFTY") -> float:
        """Total equity = cash + unrealized P&L."""
        m2m = self.get_mark_to_market(current_price, symbol)
        return self.cash + m2m

    def get_stats(self) -> dict:
        """Generate backtest statistics."""
        closed_trades = [t for t in self.trades if "pnl" in t]
        won_trades = [t for t in closed_trades if t["pnl"] > 0]
        lost_trades = [t for t in closed_trades if t["pnl"] < 0]

        total_pnl = sum(t.get("pnl", 0) for t in self.trades)
        total_traded = len([t for t in self.trades if t["action"] in ("BUY", "SELL")])

        return {
            "starting_capital": self.initial_capital,
            "final_capital": self.cash,
            "total_pnl": total_pnl,
            "return_pct": (total_pnl / self.initial_capital) * 100 if self.initial_capital > 0 else 0,
            "total_trades": len(self.trades),
            "completed_trades": len(closed_trades),
            "winning_trades": len(won_trades),
            "losing_trades": len(lost_trades),
            "win_rate": (len(won_trades) / len(closed_trades) * 100) if closed_trades else 0,
            "avg_win": sum(t["pnl"] for t in won_trades) / len(won_trades) if won_trades else 0,
            "avg_loss": sum(t["pnl"] for t in lost_trades) / len(lost_trades) if lost_trades else 0,
            "max_win": max([t["pnl"] for t in won_trades], default=0),
            "max_loss": min([t["pnl"] for t in lost_trades], default=0),
            "profit_factor": (
                abs(sum(t["pnl"] for t in won_trades) / sum(t["pnl"] for t in lost_trades))
                if lost_trades
                else 0
            ),
        }


class ClaudeBacktester:
    """Backtest Claude trading decisions on historical data."""

    def __init__(self):
        self.engine = BacktestEngine(STARTING_CAPITAL)
        self.http_client = httpx.AsyncClient(timeout=60)

    async def call_claude(self, payload: dict) -> Optional[dict]:
        """Call Claude API and get trading decision."""
        if not OPENROUTER_API_KEY:
            print("❌ OPENROUTER_API_KEY not set. Using mock response for demo.")
            # Return mock response for testing without API key
            return {"action": "HOLD", "confidence": 5, "reason": "Demo mode (no API key)"}

        # Claude system prompt (same as live system)
        system_prompt = """
You are an intraday trading expert for Indian stock markets (NSE).
You will receive a JSON object with market data, technical indicators, and research brief.
Your objective is to produce a tradable BUY/SELL decision when there is directional evidence.

Respond ONLY with a strict JSON object and nothing else:
{
  "action": "BUY" | "SELL" | "HOLD",
  "symbol": "string",
  "entry_price": number,
  "target_price": number,
  "stop_loss": number,
  "quantity": number,
  "confidence": number (1-10),
  "reason": "string (max 100 chars)"
}

Decision framework:
1) Hard blockers -> action MUST be HOLD:
   - Time after 14:45 IST for new entries
   - Missing/invalid data
   - Risk exceeds limits

2) Build directional view from strategy evidence:
   - Trend: prefer BUY if price above EMAs, SELL if below
   - Mean reversion: stretched prices favor reversion
   - Momentum: MACD/RSI confirmation
   - If strategySignals exist, use as prior (+1 confidence if aligned)

3) HOLD policy:
   - Only for mixed/flat evidence
   - Before 14:45 IST with no blockers: if confidence >= 6, choose BUY/SELL (not HOLD)

4) Risk/price:
   - Stop loss risk never exceeds 1.5% of entry
   - For BUY: stop < entry < target
   - entry_price near current live price

5) Confidence: 1-10 scale (6-7 moderate, 8-9 strong, 10 exceptional)
"""

        try:
            response = await self.http_client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://github.com/tradecraft/backtest",
                    "X-Title": "Tradecraft Backtest",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "messages": [{"role": "user", "content": f"{json.dumps(payload)}"}],
                    "system": system_prompt,
                    "max_tokens": 512,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract response content
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"].strip()
                # Try to parse JSON from response
                if content.startswith("{"):
                    decision = json.loads(content)
                    return decision

        except Exception as e:
            print(f"❌ Claude API error: {e}")
            return None

        return None

    async def backtest(self, ticker: str = NIFTY_SYMBOL, days: int = 30):
        """Run backtest on historical data."""
        print(f"\n[BACKTEST] Claude Backtest Engine")
        print("=" * 60)
        print(f"Symbol: {ticker}")
        print(f"Period: Last {days} days (15-min candles)")
        print(f"Starting Capital: INR {STARTING_CAPITAL:,.0f}")
        print(f"Max Per Trade: INR {MAX_CAPITAL_PER_TRADE:,.0f}")
        print(f"Max Daily Loss: INR {MAX_DAILY_LOSS:,.0f}")
        print("=" * 60)

        # Fetch historical data
        print(f"\n[*] Fetching historical data...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        try:
            df = yf.download(ticker, start=start_date, end=end_date, interval="15m", progress=False)
        except Exception as e:
            print(f"[ERROR] Failed to fetch data: {e}")
            return

        if df.empty:
            print(f"[ERROR] No data fetched for {ticker}")
            return

        # Handle multi-level columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Time"})
        elif "Date" in df.columns:
            df = df.rename(columns={"Date": "Time"})
        df = df.set_index("Time")
        print(f"[OK] Fetched {len(df)} candles from {df.index[0]} to {df.index[-1]}")

        # Compute technical indicators
        print(f"\n[*] Computing technical indicators...")
        try:
            close = df["Close"].astype(float)
            high = df["High"].astype(float)
            low = df["Low"].astype(float)
            
            df["EMA9"] = TechnicalIndicators.compute_ema(close, 9)
            df["EMA21"] = TechnicalIndicators.compute_ema(close, 21)
            df["RSI"] = TechnicalIndicators.compute_rsi(close, 14)
            macd, signal, hist = TechnicalIndicators.compute_macd(close)
            df["MACD"] = macd
            df["MACD_Signal"] = signal
            df["MACD_Hist"] = hist
            df["ATR"] = TechnicalIndicators.compute_atr(df)

            # Support/Resistance (simple rolling high/low)
            df["Support20"] = low.rolling(window=20).min()
            df["Resistance20"] = high.rolling(window=20).max()

            # Z-score for mean reversion
            ma50 = close.rolling(window=50).mean()
            std50 = close.rolling(window=50).std()
            df["MA50"] = ma50
            df["STD50"] = std50
            df["ZScore"] = (close - ma50) / (std50 + 1e-9)
        except Exception as e:
            print(f"[ERROR] Computing indicators failed: {e}")
            return

        print(f"✅ Indicators computed")

        # Simulate trading
        print(f"\n🔄 Simulating trading...\n")
        decisions_count = {"BUY": 0, "SELL": 0, "HOLD": 0}
        trades_executed = 0

        for idx, (time, row) in enumerate(df.iterrows()):
            # Skip rows with missing data
            if pd.isna(row["EMA9"]) or pd.isna(row["EMA21"]):
                continue

            # Every 5 candles (approximately 75 mins), check for trading signal
            if idx % 5 != 0:
                continue

            # Build payload for Claude (same as n8n workflow)
            payload = {
                "timestamp_ist": time.strftime("%Y-%m-%d %H:%M:%S IST"),
                "now_ist": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                "symbol": "NIFTY",
                "last_price": float(row["Close"]),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "volume": float(row["Volume"]),
                "indicators": {
                    "ema9": float(row["EMA9"]) if not pd.isna(row["EMA9"]) else None,
                    "ema21": float(row["EMA21"]) if not pd.isna(row["EMA21"]) else None,
                    "rsi": float(row["RSI"]) if not pd.isna(row["RSI"]) else None,
                    "macd": float(row["MACD"]) if not pd.isna(row["MACD"]) else None,
                    "macd_signal": float(row["MACD_Signal"]) if not pd.isna(row["MACD_Signal"]) else None,
                    "macd_histogram": float(row["MACD_Hist"]) if not pd.isna(row["MACD_Hist"]) else None,
                    "atr": float(row["ATR"]) if not pd.isna(row["ATR"]) else None,
                },
                "support_resistance": {
                    "support_20": float(row["Support20"]) if not pd.isna(row["Support20"]) else None,
                    "resistance_20": float(row["Resistance20"]) if not pd.isna(row["Resistance20"]) else None,
                },
                "mean_reversion": {
                    "z_score": float(row["ZScore"]) if not pd.isna(row["ZScore"]) else None,
                    "ma_50": float(row["MA50"]) if not pd.isna(row["MA50"]) else None,
                },
            }

            # Call Claude
            print(f"⏰ {time.strftime('%Y-%m-%d %H:%M IST')} | Price: ₹{row['Close']:.2f}", end=" | ")
            decision = await self.call_claude(payload)

            if not decision:
                print("⚠️  Claude error")
                continue

            action = decision.get("action", "HOLD")
            confidence = decision.get("confidence", 0)
            quantity = decision.get("quantity", 1)
            entry_price = decision.get("entry_price", row["Close"])

            decisions_count[action] = decisions_count.get(action, 0) + 1

            # Check confidence threshold
            if action != "HOLD" and confidence < CONFIDENCE_THRESHOLD:
                print(f"{action} (confidence {confidence}/10 < threshold) → SKIPPED")
                continue

            # Execute trade
            print(f"{action} | Confidence: {confidence}/10 | Qty: {quantity}")
            if self.engine.add_trade(row, decision, row["Close"]):
                trades_executed += 1

        # Print summary
        print(f"\n📊 BACKTEST RESULTS")
        print("=" * 60)
        stats = self.engine.get_stats()

        print(f"Decisions made: BUY={decisions_count['BUY']} | SELL={decisions_count['SELL']} | HOLD={decisions_count['HOLD']}")
        print(f"Trades executed: {trades_executed}")
        print(f"\n💰 Financial Summary:")
        print(f"  Starting Capital:    ₹{stats['starting_capital']:>12,.0f}")
        print(f"  Total P&L:           ₹{stats['total_pnl']:>12,.0f} ({stats['return_pct']:>+6.2f}%)")
        print(f"  Final Capital:       ₹{stats['final_capital']:>12,.0f}")
        print(f"\n📈 Trade Statistics:")
        print(f"  Completed Trades:    {stats['completed_trades']:>12}")
        print(f"  Winning Trades:      {stats['winning_trades']:>12}")
        print(f"  Losing Trades:       {stats['losing_trades']:>12}")
        print(f"  Win Rate:            {stats['win_rate']:>11.1f}%")
        print(f"  Avg Win:             ₹{stats['avg_win']:>12,.0f}")
        print(f"  Avg Loss:            ₹{stats['avg_loss']:>12,.0f}")
        print(f"  Max Win:             ₹{stats['max_win']:>12,.0f}")
        print(f"  Max Loss:            ₹{stats['max_loss']:>12,.0f}")
        print(f"  Profit Factor:       {stats['profit_factor']:>12.2f}")
        print("=" * 60)

        # Show individual trades
        if self.engine.trades:
            print(f"\n📋 Trade Log ({len(self.engine.trades)} actions):")
            for i, trade in enumerate(self.engine.trades[-20:], 1):  # Show last 20
                if trade["action"] == "BUY":
                    print(
                        f"  {i}. BUY  @ {trade['price']:.2f} | Qty: {trade['qty']} | "
                        f"Cost: ₹{trade['cost']:,.0f}"
                    )
                else:
                    pnl = trade.get("pnl", 0)
                    print(
                        f"  {i}. SELL @ {trade['price']:.2f} | Entry: {trade.get('entry_price', 0):.2f} | "
                        f"P&L: ₹{pnl:+,.0f} ({trade.get('pnl_pct', 0):+.2f}%)"
                    )

        await self.http_client.aclose()


async def main():
    """Main entry point."""
    backtest = ClaudeBacktester()
    await backtest.backtest(days=30)


if __name__ == "__main__":
    asyncio.run(main())
