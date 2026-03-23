#!/usr/bin/env python3
"""
Capital-aware replay comparison for Tradecraft.

Runs a 30-day NIFTY 15m replay, asks Claude for directional decisions, and
simulates deployment with INR 10,000 starting capital, derivatives sizing,
fees, slippage, and compounding.

Historical option-chain candles are not freely available in this environment,
so option premium PnL uses a conservative underlying-linked proxy.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import pandas as pd
import yfinance as yf


SYMBOL = "^NSEI"
DAYS = 30
INTERVAL = "15m"
CHECK_EVERY_N_CANDLES = 5
CONFIDENCE_THRESHOLD = 7
MODEL = "anthropic/claude-sonnet-4-5"

INITIAL_CAPITAL_INR = 10_000.0
CAPITAL_RESERVE_RATIO = 0.05
NIFTY_LOT_SIZE = 75
FUTURES_MARGIN_RATE = 0.12
MIN_OPTION_PREMIUM = 50.0
OPTION_PREMIUM_RATE = 0.0035
OPTION_RETURN_MULTIPLIER = 8.0
THETA_DECAY_PER_BAR = 0.0012
MAX_OPTION_RETURN = 2.5
SLIPPAGE_RATE = 0.0005

# Trade quality filters
MIN_BARS_BETWEEN_TRADES = 16      # ~4 hours gap between any two entries on 15m bars
MAX_TRADES_PER_DAY = 2            # Never more than 2 entries in the same calendar day
ATR_PERIOD = 14                   # ATR lookback for dynamic TP/SL
ATR_SL_MULTIPLIER = 1.2           # SL = entry ± ATR_SL_MULTIPLIER × ATR
ATR_TP_MULTIPLIER = 1.8           # TP = entry ± ATR_TP_MULTIPLIER × ATR (R:R = 1.5)
ATR_MIN_REGIME_PCT = 0.40         # Skip if ATR < 40th percentile (choppy session)
ROUND_TRIP_FEE_ESTIMATE = 70.0    # Conservative single-lot round-trip fee in INR
MIN_EXPECTED_GROSS_MULTIPLIER = 3.0
MIN_EXPECTED_GROSS = ROUND_TRIP_FEE_ESTIMATE * MIN_EXPECTED_GROSS_MULTIPLIER  # Only trade if expected gross > 3× fees
MAX_LOSS_CAPITAL_PCT = 0.0125     # Hard cap: max loss/trade = 1.25% of current capital
POST_SL_COOLDOWN_BARS = 24        # After SL_HIT, skip new entries for next 24 bars
OPEN_CLOSE_MIN_CONF = 9           # open/close windows require confidence >= 9 + trend confirmations
ADX_PERIOD = 14
ADX_MIN = 20.0
RSI_BUY_MIN = 45.0
RSI_BUY_MAX = 65.0
RSI_SELL_MIN = 35.0
RSI_SELL_MAX = 55.0

# Accuracy tracker: adaptive confidence gate
ACCURACY_WINDOW = 20              # Rolling window of last N executed trades
ACCURACY_FLOOR = 0.45             # If win-rate < 45% over window, raise confidence gate by 1
CONFIDENCE_CEILING = 10          # Maximum auto-raised confidence threshold


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as file_handle:
        for raw in file_handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key and key not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


def extract_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    first = stripped.find("{")
    last = stripped.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(stripped[first : last + 1])
        except json.JSONDecodeError:
            return None
    return None


def extract_decision_heuristic(text: str, live_price: float) -> Optional[dict[str, Any]]:
    if not text:
        return None

    upper = text.upper()
    explicit = re.search(r"(?:ACTION|RECOMMENDATION)[^A-Z]*(BUY|SELL|HOLD)", upper)
    action = explicit.group(1) if explicit else None

    if action is None:
        bullish_score = len(re.findall(r"\bBULLISH\b|\bUPTREND\b|\bLONG\b", upper))
        bearish_score = len(re.findall(r"\bBEARISH\b|\bDOWNTREND\b|\bSHORT\b", upper))
        if bullish_score > bearish_score:
            action = "BUY"
        elif bearish_score > bullish_score:
            action = "SELL"
        else:
            action = "HOLD"

    confidence_match = re.search(r"confidence[^0-9]*([0-9]{1,2})(?:\s*/\s*10)?", text, flags=re.IGNORECASE)
    confidence = int(confidence_match.group(1)) if confidence_match else 5
    confidence = max(1, min(10, confidence))

    return {
        "action": action,
        "symbol": "NIFTY",
        "entry_price": float(live_price),
        "target_price": float(live_price),
        "stop_loss": float(live_price),
        "quantity": 1,
        "confidence": confidence if action == "HOLD" else max(confidence, 6),
        "reason": "Heuristic parse from non-JSON model output",
    }


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = series.ewm(span=fast, adjust=False).mean()
    slow_ema = series.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Average True Range — measures session volatility."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> pd.Series:
    """Average Directional Index for trend-strength filtering."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr_smooth = tr.rolling(window=period, min_periods=period).mean()

    plus_di = 100 * (plus_dm.rolling(window=period, min_periods=period).mean() / (atr_smooth + 1e-9))
    minus_di = 100 * (minus_dm.rolling(window=period, min_periods=period).mean() / (atr_smooth + 1e-9))
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)).fillna(0.0)
    return dx.rolling(window=period, min_periods=period).mean().fillna(0.0)


def get_session_phase(ts: Any) -> str:
    """Classify intraday timestamp into NIFTY session phase (IST).

    open_volatility  09:15–09:59  — high-spread, false breakouts
    mid_trend        10:00–13:29  — primary directional window
    lunch_chop       13:30–14:14  — low volume, choppy
    close_reversal   14:15–15:30  — reversal / position-squaring
    """
    # Convert to IST (UTC+5:30)
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        ist_offset = timedelta(hours=5, minutes=30)
        ts_ist = ts.astimezone(timezone.utc).replace(tzinfo=None) + ist_offset
    else:
        # Assume already in IST or UTC; heuristic: yfinance timestamps for India are UTC
        ts_ist = ts.replace(tzinfo=None) + timedelta(hours=5, minutes=30) if hasattr(ts, 'replace') else ts
    hour = ts_ist.hour
    minute = ts_ist.minute
    total_minutes = hour * 60 + minute
    if total_minutes < 600:       # before 10:00
        return "open_volatility"
    if total_minutes < 810:       # before 13:30
        return "mid_trend"
    if total_minutes < 855:       # before 14:15
        return "lunch_chop"
    return "close_reversal"


def simulated_neutral_research() -> dict[str, Any]:
    return {
        "overallSentiment": "NEUTRAL",
        "sentimentScore": 0.0,
        "confidence": 0,
        "bullishSignals": 0,
        "bearishSignals": 0,
        "neutralSignals": 0,
        "topHeadlines": [],
        "redditConsensus": "NEUTRAL",
        "nseAnnouncementFlag": False,
        "sources": {"newsCount": 0, "redditCount": 0, "nseCount": 0},
        "pastLessons": [],
        "summary": "No replay/news source available; neutral fallback used.",
    }


def _news_text(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or item.get("snippet") or "")
    return f"{title} {summary}".strip()


def _score_news_sentiment(text: str) -> int:
    low = text.lower()
    bullish_tokens = ["surge", "gain", "rally", "up", "bull", "beat", "strong", "record high", "growth"]
    bearish_tokens = ["fall", "drop", "slump", "down", "bear", "miss", "weak", "selloff", "concern"]
    bullish = sum(1 for token in bullish_tokens if token in low)
    bearish = sum(1 for token in bearish_tokens if token in low)
    return bullish - bearish


def build_research_from_news(news_items: list[dict[str, Any]], source_name: str) -> dict[str, Any]:
    if not news_items:
        out = simulated_neutral_research()
        out["summary"] = f"No news found from {source_name} for the replay window."
        out["sources"] = {"newsCount": 0, "redditCount": 0, "nseCount": 0}
        return out

    scored: list[tuple[dict[str, Any], int]] = []
    for item in news_items:
        scored.append((item, _score_news_sentiment(_news_text(item))))

    total_score = sum(score for _, score in scored)
    news_count = len(scored)
    sentiment_score = total_score / max(1, news_count)

    if sentiment_score > 0.25:
        overall = "BULLISH"
    elif sentiment_score < -0.25:
        overall = "BEARISH"
    else:
        overall = "NEUTRAL"

    top_headlines = []
    for item, _ in scored[:5]:
        title = str(item.get("title") or "").strip()
        if title:
            top_headlines.append(title)

    return {
        "overallSentiment": overall,
        "sentimentScore": round(float(sentiment_score), 3),
        "confidence": min(80, 20 + news_count * 10),
        "bullishSignals": sum(1 for _, score in scored if score > 0),
        "bearishSignals": sum(1 for _, score in scored if score < 0),
        "neutralSignals": sum(1 for _, score in scored if score == 0),
        "topHeadlines": top_headlines,
        "redditConsensus": "NEUTRAL",
        "nseAnnouncementFlag": False,
        "sources": {"newsCount": news_count, "redditCount": 0, "nseCount": 0},
        "pastLessons": [],
        "summary": f"Historical news replay via {source_name} with {news_count} headlines.",
    }


@dataclass
class DecisionRow:
    timestamp: datetime
    action: str
    confidence: int
    instrument: str
    lots: int
    lot_size: int
    quantity: int
    entry_price: float
    target_price: float
    stop_loss: float
    instrument_entry_price: float
    instrument_exit_price: float
    capital_before: float
    capital_committed: float
    fees: float
    reason: str
    executed: bool
    outcome: str
    exit_price: float
    gross_pnl: float
    pnl: float
    pnl_pct: float
    bars_to_outcome: int
    capital_after: float
    skip_reason: str


class ClaudeComparator:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.client = httpx.AsyncClient(timeout=60)
        self.rows: list[DecisionRow] = []
        self.debug = os.getenv("BACKTEST_DEBUG", "0") == "1"
        self.research_source = "unknown"
        self.backend_replay_available: Optional[bool] = None
        self.yahoo_news_cache: list[dict[str, Any]] = []
        self.capital = INITIAL_CAPITAL_INR
        # Walk-forward accuracy tracker: adaptive confidence gate
        self.dynamic_confidence_threshold: int = CONFIDENCE_THRESHOLD
        self._recent_outcomes: list[str] = []   # "TP" or "SL" for last N executed trades
        # Trade frequency controls
        self._trades_today: int = 0
        self._today_date: Optional[str] = None  # "YYYY-MM-DD" string

    async def close(self) -> None:
        await self.client.aclose()

    async def _try_backend_replay_research(self, ts: datetime) -> Optional[dict[str, Any]]:
        if self.backend_replay_available is False:
            return None

        candidates = [
            "http://localhost:3001/api/research/replay",
            "http://127.0.0.1:3001/api/research/replay",
            "http://localhost:3001/api/research/historical",
            "http://127.0.0.1:3001/api/research/historical",
        ]
        ts_iso = ts.astimezone(timezone.utc).isoformat()

        for url in candidates:
            try:
                response = await self.client.get(
                    url,
                    params={"symbol": "NIFTY", "timestamp": ts_iso, "timeframe": INTERVAL},
                    timeout=5,
                )
            except Exception:
                continue

            if response.status_code in {404} or response.status_code >= 500 or response.status_code != 200:
                continue

            try:
                payload = response.json()
            except Exception:
                continue

            if isinstance(payload, dict):
                if isinstance(payload.get("researchBrief"), dict):
                    self.backend_replay_available = True
                    self.research_source = "backend-replay"
                    return payload["researchBrief"]
                if "overallSentiment" in payload and "sentimentScore" in payload:
                    self.backend_replay_available = True
                    self.research_source = "backend-replay"
                    return payload

        self.backend_replay_available = False
        return None

    def _load_yahoo_news_cache(self) -> None:
        if self.yahoo_news_cache:
            return
        try:
            ticker = yf.Ticker(SYMBOL)
            raw_news = ticker.news or []
            if isinstance(raw_news, list):
                self.yahoo_news_cache = [item for item in raw_news if isinstance(item, dict)]
        except Exception:
            self.yahoo_news_cache = []

    def _get_yahoo_news_for_timestamp(self, ts: datetime) -> list[dict[str, Any]]:
        self._load_yahoo_news_cache()
        if not self.yahoo_news_cache:
            return []

        ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
        start_utc = ts_utc - timedelta(days=3)

        selected: list[tuple[datetime, dict[str, Any]]] = []
        for item in self.yahoo_news_cache:
            published = item.get("providerPublishTime")
            if not isinstance(published, (int, float)):
                continue
            published_dt = datetime.fromtimestamp(published, tz=timezone.utc)
            if start_utc <= published_dt <= ts_utc:
                selected.append((published_dt, item))

        selected.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in selected[:5]]

    async def get_research_brief(self, ts: datetime) -> dict[str, Any]:
        replay = await self._try_backend_replay_research(ts)
        if replay:
            return replay

        news_items = self._get_yahoo_news_for_timestamp(ts)
        self.research_source = "yahoo-news-fallback"
        return build_research_from_news(news_items, "Yahoo News")

    async def ask_claude(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.api_key:
            return {
                "action": "HOLD",
                "symbol": "NIFTY",
                "entry_price": payload.get("livePrice", 0),
                "target_price": payload.get("livePrice", 0),
                "stop_loss": payload.get("livePrice", 0),
                "quantity": 1,
                "confidence": 5,
                "reason": "No OPENROUTER_API_KEY; fallback HOLD",
                "_parse_mode": "api_fallback",
            }

        system_prompt = (
            "You are an intraday NIFTY derivatives trading system.\n\n"
            "RULES (NON-NEGOTIABLE):\n"
            "1. Your ENTIRE response must be a single JSON object. No preamble, no explanation, no markdown fences.\n"
            "2. Start your response with { and end with }. Nothing else outside that object.\n"
            "3. If you are uncertain about direction, set action to HOLD. Uncertainty is virtuous.\n"
            "4. confidence must be an integer 1-10. Only output BUY or SELL if confidence >= 7.\n"
            "5. target_price and stop_loss MUST differ from entry_price at all times.\n"
            "6. reason must be 5-20 words — concise and specific. No generic phrases.\n"
            "7. Read trading_constraints carefully. Only suggest BUY/SELL if expected gross > min_expected_gross.\n"
            "8. In open_volatility/close_reversal session phases, only trade if confidence >= 8 and trend_confirmation is true.\n"
            "9. If pastLessons contains a matching pattern, use it to adjust or veto the trade.\n\n"
            "CONFIDENCE RUBRIC:\n"
            "- 8-10: Multi-signal alignment + trend regime confirmation\n"
            "- 6-7: Partial alignment / mixed evidence\n"
            "- <6: No trade (HOLD)\n\n"
            "OUTPUT SCHEMA (exact — no extra fields):\n"
            "{\"action\":\"BUY\",\"symbol\":\"NIFTY\",\"entry_price\":24500.0,"
            "\"target_price\":24700.0,\"stop_loss\":24350.0,\"quantity\":1,"
            "\"confidence\":8,\"reason\":\"MACD bullish cross + RSI recovering from oversold\"}\n\n"
            "EXAMPLES:\n"
            "Input: RSI=28, MACD turning up, EMA9 < EMA21, price near support, session=mid_trend\n"
            "Output: {\"action\":\"BUY\",\"symbol\":\"NIFTY\",\"entry_price\":23800.0,"
            "\"target_price\":24150.0,\"stop_loss\":23600.0,\"quantity\":1,"
            "\"confidence\":8,\"reason\":\"RSI oversold bounce + MACD turning bullish at support\"}\n\n"
            "Input: RSI=72, price near resistance, MACD histogram shrinking, session=open_volatility\n"
            "Output: {\"action\":\"HOLD\",\"symbol\":\"NIFTY\",\"entry_price\":24900.0,"
            "\"target_price\":24900.0,\"stop_loss\":24900.0,\"quantity\":1,"
            "\"confidence\":3,\"reason\":\"Overbought resistance + open volatility window — skip\"}\n\n"
            "Input: EMA9 crossed below EMA21, RSI=55 falling, MACD_HIST negative and growing, session=mid_trend\n"
            "Output: {\"action\":\"SELL\",\"symbol\":\"NIFTY\",\"entry_price\":24200.0,"
            "\"target_price\":23900.0,\"stop_loss\":24350.0,\"quantity\":1,"
            "\"confidence\":8,\"reason\":\"EMA death cross + MACD bearish momentum in trend window\"}"
        )

        fallback = {
            "action": "HOLD",
            "symbol": "NIFTY",
            "entry_price": payload.get("livePrice", 0),
            "target_price": payload.get("livePrice", 0),
            "stop_loss": payload.get("livePrice", 0),
            "quantity": 1,
            "confidence": 5,
            "reason": "API/parsing fallback HOLD",
            "_parse_mode": "api_fallback",
        }

        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload)},
        ]

        last_text = ""
        for attempt in range(2):
            messages = list(base_messages)
            if attempt == 1:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "RETRY: Your prior output was not valid JSON. "
                            "Return ONLY one valid JSON object now. No markdown, no prose."
                        ),
                    }
                )
            try:
                response = await self.client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "HTTP-Referer": "https://github.com/tradecraft/backtest",
                        "X-Title": "Tradecraft Replay Capital Backtest",
                    },
                    json={
                        "model": MODEL,
                        "messages": messages,
                        "max_tokens": 320,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                data = response.json()
                text = ""
                if "choices" in data and data["choices"]:
                    text = str(data["choices"][0]["message"]["content"])
                last_text = text
                if self.debug:
                    preview = text.replace("\n", " ")[:400]
                    print(f"[DEBUG] Attempt {attempt + 1} raw output preview: {preview}")

                parsed = extract_json(text)
                if parsed is not None:
                    parsed["_parse_mode"] = "parsed_json"
                    return parsed

                # Diagnostic only: we track heuristic extractability, but do not execute it as a trade signal.
                heuristic = extract_decision_heuristic(text, float(payload.get("livePrice", 0)))
                if heuristic is not None and attempt == 1:
                    heuristic["_parse_mode"] = "heuristic_fallback"
                    heuristic["reason"] = "Heuristic detected from non-JSON output (diagnostic only)"
                    return heuristic

            except Exception:
                if self.debug:
                    import traceback

                    print(f"[DEBUG] API exception during ask_claude attempt {attempt + 1}")
                    traceback.print_exc()

        parse_fail = {
            "action": "HOLD",
            "symbol": "NIFTY",
            "entry_price": payload.get("livePrice", 0),
            "target_price": payload.get("livePrice", 0),
            "stop_loss": payload.get("livePrice", 0),
            "quantity": 1,
            "confidence": 0,
            "reason": "NO_TRADE_PARSE_FAIL",
            "_parse_mode": "parse_fail",
            "_raw_preview": last_text.replace("\n", " ")[:240],
        }
        return parse_fail

    @staticmethod
    def evaluate_first_hit(
        action: str,
        entry: float,
        target: float,
        stop: float,
        future_df: pd.DataFrame,
    ) -> tuple[str, float, float, float, int]:
        if future_df.empty:
            return "NO_FUTURE_DATA", entry, 0.0, 0.0, 0

        for bars, (_, row) in enumerate(future_df.iterrows(), start=1):
            high = float(row["High"])
            low = float(row["Low"])

            if action == "BUY":
                tp_hit = high >= target
                sl_hit = low <= stop
                if tp_hit and sl_hit:
                    exit_price = stop
                    pnl = exit_price - entry
                    return "SL_HIT_SAME_CANDLE", exit_price, pnl, (pnl / entry) * 100, bars
                if sl_hit:
                    exit_price = stop
                    pnl = exit_price - entry
                    return "SL_HIT", exit_price, pnl, (pnl / entry) * 100, bars
                if tp_hit:
                    exit_price = target
                    pnl = exit_price - entry
                    return "TP_HIT", exit_price, pnl, (pnl / entry) * 100, bars

            if action == "SELL":
                tp_hit = low <= target
                sl_hit = high >= stop
                if tp_hit and sl_hit:
                    exit_price = stop
                    pnl = entry - exit_price
                    return "SL_HIT_SAME_CANDLE", exit_price, pnl, (pnl / entry) * 100, bars
                if sl_hit:
                    exit_price = stop
                    pnl = entry - exit_price
                    return "SL_HIT", exit_price, pnl, (pnl / entry) * 100, bars
                if tp_hit:
                    exit_price = target
                    pnl = entry - exit_price
                    return "TP_HIT", exit_price, pnl, (pnl / entry) * 100, bars

        last_close = float(future_df.iloc[-1]["Close"])
        pnl = (last_close - entry) if action == "BUY" else (entry - last_close)
        return "NO_HIT_CLOSE_LAST", last_close, pnl, (pnl / entry) * 100, len(future_df)

    @staticmethod
    def estimate_round_trip_fees(instrument: str, entry_price: float, exit_price: float, quantity: int) -> float:
        if quantity <= 0:
            return 0.0

        entry_turnover = entry_price * quantity
        exit_turnover = exit_price * quantity
        total_turnover = entry_turnover + exit_turnover
        brokerage = 40.0

        if instrument == "FUTURES":
            stt = exit_turnover * 0.0002
            exchange_txn = total_turnover * 0.00002
            stamp_duty = entry_turnover * 0.00002
        else:
            stt = exit_turnover * 0.000625
            exchange_txn = total_turnover * 0.00035
            stamp_duty = entry_turnover * 0.00003

        sebi = total_turnover * 0.000001
        gst = 0.18 * (brokerage + exchange_txn + sebi)
        slippage = total_turnover * SLIPPAGE_RATE
        return brokerage + stt + exchange_txn + stamp_duty + sebi + gst + slippage

    def record_outcome(self, outcome: str) -> None:
        """Record executed trade outcome and update adaptive confidence threshold."""
        label = "TP" if outcome == "TP_HIT" else "SL"
        self._recent_outcomes.append(label)
        if len(self._recent_outcomes) > ACCURACY_WINDOW:
            self._recent_outcomes.pop(0)
        # Check accuracy every 5 trades once we have enough data
        if len(self._recent_outcomes) >= 10 and len(self._recent_outcomes) % 5 == 0:
            win_rate = self._recent_outcomes.count("TP") / len(self._recent_outcomes)
            if win_rate < ACCURACY_FLOOR:
                new_threshold = min(CONFIDENCE_CEILING, self.dynamic_confidence_threshold + 1)
                if new_threshold != self.dynamic_confidence_threshold:
                    self.dynamic_confidence_threshold = new_threshold
                    print(f"  [ADAPTIVE] Win-rate={win_rate:.0%} < {ACCURACY_FLOOR:.0%} — raising confidence gate to {new_threshold}")
            else:
                # Slowly relax back toward base threshold when performance recovers
                if self.dynamic_confidence_threshold > CONFIDENCE_THRESHOLD:
                    self.dynamic_confidence_threshold = max(CONFIDENCE_THRESHOLD, self.dynamic_confidence_threshold - 1)
                    print(f"  [ADAPTIVE] Win-rate={win_rate:.0%} — relaxing confidence gate to {self.dynamic_confidence_threshold}")

    def check_daily_limit(self, ts: Any) -> bool:
        """Return True if we have not yet hit the daily trade cap."""
        date_key = str(ts)[:10]  # "YYYY-MM-DD"
        if date_key != self._today_date:
            self._today_date = date_key
            self._trades_today = 0
        return self._trades_today < MAX_TRADES_PER_DAY

    def increment_daily_count(self) -> None:
        self._trades_today += 1

    @staticmethod
    def estimate_option_entry_price(underlying_price: float, capital_before: float) -> float:
        deployable_capital = max(0.0, capital_before * (1 - CAPITAL_RESERVE_RATIO))
        max_affordable_premium = deployable_capital / NIFTY_LOT_SIZE
        baseline_premium = max(MIN_OPTION_PREMIUM, underlying_price * OPTION_PREMIUM_RATE)
        return min(baseline_premium, max_affordable_premium)

    def plan_trade(self, action: str, underlying_price: float, capital_before: float) -> tuple[Optional[dict[str, Any]], str]:
        if action not in {"BUY", "SELL"}:
            return None, "NON_DIRECTIONAL_SIGNAL"

        deployable_capital = capital_before * (1 - CAPITAL_RESERVE_RATIO)
        if deployable_capital <= 0:
            return None, "NO_DEPLOYABLE_CAPITAL"

        futures_margin = underlying_price * NIFTY_LOT_SIZE * FUTURES_MARGIN_RATE
        futures_fees_est = self.estimate_round_trip_fees("FUTURES", underlying_price, underlying_price, NIFTY_LOT_SIZE)
        futures_required = futures_margin + futures_fees_est
        if capital_before >= futures_required:
            return {
                "instrument": "FUTURES",
                "lots": 1,
                "lot_size": NIFTY_LOT_SIZE,
                "quantity": NIFTY_LOT_SIZE,
                "capital_committed": futures_margin,
                "instrument_entry_price": underlying_price,
            }, ""

        option_entry_price = self.estimate_option_entry_price(underlying_price, capital_before)
        if option_entry_price < MIN_OPTION_PREMIUM:
            return None, "INSUFFICIENT_CAPITAL_FOR_OPTION_LOT"

        per_lot_qty = NIFTY_LOT_SIZE
        per_lot_premium = option_entry_price * per_lot_qty
        estimated_fees = self.estimate_round_trip_fees("OPTIONS", option_entry_price, option_entry_price, per_lot_qty)
        per_lot_required = per_lot_premium + estimated_fees
        lots = int(deployable_capital // per_lot_required)
        if lots < 1:
            return None, "INSUFFICIENT_CAPITAL_FOR_OPTION_LOT"

        quantity = lots * per_lot_qty
        capital_committed = option_entry_price * quantity
        instrument = "LONG_CALL" if action == "BUY" else "LONG_PUT"
        return {
            "instrument": instrument,
            "lots": lots,
            "lot_size": per_lot_qty,
            "quantity": quantity,
            "capital_committed": capital_committed,
            "instrument_entry_price": option_entry_price,
        }, "FUTURES_UNAFFORDABLE_USED_OPTIONS"

    @staticmethod
    def estimate_option_exit_price(
        option_entry_price: float,
        underlying_entry: float,
        underlying_exit: float,
        action: str,
        bars_to_outcome: int,
    ) -> float:
        underlying_return = (underlying_exit - underlying_entry) / max(underlying_entry, 1e-9)
        directional_return = underlying_return if action == "BUY" else -underlying_return
        option_return = directional_return * OPTION_RETURN_MULTIPLIER
        option_return -= max(0, bars_to_outcome - 1) * THETA_DECAY_PER_BAR
        option_return = max(-0.95, min(MAX_OPTION_RETURN, option_return))
        return max(0.5, option_entry_price * (1 + option_return))

    def settle_trade(
        self,
        trade_spec: dict[str, Any],
        action: str,
        underlying_entry: float,
        underlying_exit: float,
        bars_to_outcome: int,
    ) -> tuple[float, float, float]:
        instrument = str(trade_spec["instrument"])
        quantity = int(trade_spec["quantity"])
        instrument_entry_price = float(trade_spec["instrument_entry_price"])

        if instrument == "FUTURES":
            instrument_exit_price = underlying_exit
            points = (underlying_exit - underlying_entry) if action == "BUY" else (underlying_entry - underlying_exit)
            gross_pnl = points * quantity
            fees = self.estimate_round_trip_fees("FUTURES", instrument_entry_price, instrument_exit_price, quantity)
            return instrument_exit_price, gross_pnl, fees

        instrument_exit_price = self.estimate_option_exit_price(
            option_entry_price=instrument_entry_price,
            underlying_entry=underlying_entry,
            underlying_exit=underlying_exit,
            action=action,
            bars_to_outcome=bars_to_outcome,
        )
        gross_pnl = (instrument_exit_price - instrument_entry_price) * quantity
        fees = self.estimate_round_trip_fees("OPTIONS", instrument_entry_price, instrument_exit_price, quantity)
        return instrument_exit_price, gross_pnl, fees

    async def run(self) -> None:
        print("\n=== Tradecraft Capital Backtest (v3 — ATR + Quality Filters) ===")
        print(f"Symbol: {SYMBOL} | Interval: {INTERVAL} | Days: {DAYS}")
        print(f"Starting capital: INR {INITIAL_CAPITAL_INR:,.2f}")
        print(f"Confidence gate: {CONFIDENCE_THRESHOLD} (adaptive, ceiling={CONFIDENCE_CEILING})")
        print(f"Min bars between trades: {MIN_BARS_BETWEEN_TRADES} | Max trades/day: {MAX_TRADES_PER_DAY}")
        print(f"Edge filter: projected gross >= {MIN_EXPECTED_GROSS_MULTIPLIER:.1f}x fees | Max loss/trade: {MAX_LOSS_CAPITAL_PCT*100:.2f}%")
        print(f"Post-SL cooldown: {POST_SL_COOLDOWN_BARS} bars | ADX gate: > {ADX_MIN:.0f}")
        print("Execution model: futures when margin allows, else long options lots")
        print("Research mode: backend replay if available, else Yahoo fallback")
        print("Options note: option PnL still uses a proxy model (real broker option candles not integrated yet).")

        end = datetime.now()
        start = end - timedelta(days=DAYS)
        df = yf.download(SYMBOL, start=start, end=end, interval=INTERVAL, progress=False)
        if df.empty:
            print("No historical data fetched.")
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Time"})
        else:
            df = df.rename(columns={"Date": "Time"})
        df = df.set_index("Time").sort_index()

        close = df["Close"].astype(float)
        df["EMA9"] = ema(close, 9)
        df["EMA21"] = ema(close, 21)
        df["RSI"] = rsi(close, 14)
        macd_line, macd_signal, macd_hist = macd(close)
        df["MACD"] = macd_line
        df["MACD_SIGNAL"] = macd_signal
        df["MACD_HIST"] = macd_hist
        df["ADX"] = adx(df, ADX_PERIOD)

        df["ATR"] = atr(df)

        # Build 1H context to reduce false trades in open/close windows.
        one_h = df[["Open", "High", "Low", "Close", "Volume"]].resample("1h").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
        one_h_close = one_h["Close"].astype(float)
        one_h["EMA9_1H"] = ema(one_h_close, 9)
        one_h["EMA21_1H"] = ema(one_h_close, 21)
        one_h_macd, one_h_sig, one_h_hist = macd(one_h_close)
        one_h["MACD_1H"] = one_h_macd
        one_h["MACD_SIGNAL_1H"] = one_h_sig
        one_h["MACD_HIST_1H"] = one_h_hist

        df["EMA9_1H"] = one_h["EMA9_1H"].reindex(df.index, method="ffill")
        df["EMA21_1H"] = one_h["EMA21_1H"].reindex(df.index, method="ffill")
        df["MACD_HIST_1H"] = one_h["MACD_HIST_1H"].reindex(df.index, method="ffill")

        # ATR regime filter: 40th-percentile floor — skip candles below this (choppy sessions)
        atr_series_full = df["ATR"].dropna()
        atr_regime_floor = float(atr_series_full.quantile(ATR_MIN_REGIME_PCT)) if len(atr_series_full) > 0 else 0.0
        print(f"ATR 40th-percentile regime floor: {atr_regime_floor:.2f}")

        next_free_index = 0
        model_calls = 0
        parsed_json_count = 0
        heuristic_fallback_count = 0
        parse_fail_count = 0
        sl_cooldown_until = -1
        require_extra_confirmation = False

        for idx, (ts, row) in enumerate(df.iterrows()):
            if idx % CHECK_EVERY_N_CANDLES != 0:
                continue
            if (
                pd.isna(row["EMA9"])
                or pd.isna(row["EMA21"])
                or pd.isna(row["RSI"])
                or pd.isna(row["ATR"])
                or pd.isna(row["ADX"])
                or pd.isna(row["EMA9_1H"])
                or pd.isna(row["EMA21_1H"])
                or pd.isna(row["MACD_HIST_1H"])
            ):
                continue

            current_atr = float(row["ATR"])

            # ATR regime gate: skip choppy candles — no API call, save cost
            if current_atr < atr_regime_floor:
                continue

            capital_before = self.capital
            session_phase = get_session_phase(ts)

            # pastLessons: last 3 SL-hit rows as in-context learning signals
            recent_losses = [r for r in self.rows if r.outcome in {"SL_HIT", "SL_HIT_SAME_CANDLE"}][-3:]
            past_lessons = [
                f"SL hit at {r.timestamp.strftime('%H:%M')} on {r.action} near {r.entry_price:.0f} — review conditions before similar trade"
                for r in recent_losses
            ]

            research_brief = await self.get_research_brief(ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts)
            research_brief["pastLessons"] = past_lessons

            # Recent 5 candles — gives Claude candle-structure context
            recent_start = max(0, idx - 5)
            recent_df = df.iloc[recent_start:idx]
            recent_candles = [
                {
                    "time": str(t)[:16],
                    "open": round(float(rv["Open"]), 2),
                    "high": round(float(rv["High"]), 2),
                    "low": round(float(rv["Low"]), 2),
                    "close": round(float(rv["Close"]), 2),
                    "volume": int(rv.get("Volume", 0) or 0),
                }
                for t, rv in recent_df.iterrows()
            ]

            trades_so_far_today = self._trades_today if self._today_date == str(ts)[:10] else 0
            trend_state = "neutral"
            if float(row["EMA9"]) > float(row["EMA21"]) and float(row["MACD_HIST"]) > 0:
                trend_state = "bullish_confirmed"
            elif float(row["EMA9"]) < float(row["EMA21"]) and float(row["MACD_HIST"]) < 0:
                trend_state = "bearish_confirmed"

            trend_state_1h = "neutral"
            if float(row["EMA9_1H"]) > float(row["EMA21_1H"]) and float(row["MACD_HIST_1H"]) > 0:
                trend_state_1h = "bullish_confirmed"
            elif float(row["EMA9_1H"]) < float(row["EMA21_1H"]) and float(row["MACD_HIST_1H"]) < 0:
                trend_state_1h = "bearish_confirmed"

            payload = {
                "symbol": "NIFTY",
                "timeframe": INTERVAL,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S IST"),
                "session_phase": session_phase,
                "livePrice": float(row["Close"]),
                "recent_candles": recent_candles,
                "indicators": {
                    "ema9": round(float(row["EMA9"]), 2),
                    "ema21": round(float(row["EMA21"]), 2),
                    "rsi": round(float(row["RSI"]), 2),
                    "macd": round(float(row["MACD"]), 4),
                    "macdSignal": round(float(row["MACD_SIGNAL"]), 4),
                    "macdHistogram": round(float(row["MACD_HIST"]), 4),
                    "adx": round(float(row["ADX"]), 2),
                    "atr": round(current_atr, 2),
                    "atr_regime": "trending" if current_atr >= atr_regime_floor else "choppy",
                    "trend_state": trend_state,
                    "trend_state_1h": trend_state_1h,
                },
                "trading_constraints": {
                    "capital_inr": round(capital_before, 2),
                    "round_trip_fee_estimate_inr": ROUND_TRIP_FEE_ESTIMATE,
                    "min_expected_gross_inr": round(MIN_EXPECTED_GROSS, 2),
                    "max_loss_per_trade_inr": round(capital_before * MAX_LOSS_CAPITAL_PCT, 2),
                    "max_trades_per_day": MAX_TRADES_PER_DAY,
                    "trades_today_so_far": trades_so_far_today,
                    "instruction": (
                        "Only recommend BUY or SELL if the expected gross PnL clearly exceeds "
                        "min_expected_gross_inr. In open_volatility or close_reversal sessions "
                        "only trade at confidence >=9 with trend_confirmation true on BOTH 15m and 1h contexts. "
                        "If ADX <= 20 or trend is mixed, output HOLD."
                    ),
                },
                "researchBrief": research_brief,
            }

            decision = await self.ask_claude(payload)
            if not decision:
                continue

            model_calls += 1
            parse_mode = str(decision.get("_parse_mode", "unknown"))
            if parse_mode == "parsed_json":
                parsed_json_count += 1
            elif parse_mode == "heuristic_fallback":
                heuristic_fallback_count += 1
            else:
                parse_fail_count += 1

            action = str(decision.get("action", "HOLD")).upper()
            confidence = int(decision.get("confidence", 0))
            entry_price = float(decision.get("entry_price", row["Close"]))
            reason = str(decision.get("reason", ""))[:160]

            # ATR-based dynamic TP/SL — overrides whatever fixed levels Claude suggests
            sl_distance = ATR_SL_MULTIPLIER * current_atr
            tp_distance = ATR_TP_MULTIPLIER * current_atr
            if action == "BUY":
                target_price = entry_price + tp_distance
                stop_loss = entry_price - sl_distance
            elif action == "SELL":
                target_price = entry_price - tp_distance
                stop_loss = entry_price + sl_distance
            else:
                target_price = entry_price
                stop_loss = entry_price

            executed = False
            outcome = "SKIPPED"
            exit_price = float(row["Close"])
            instrument = "NONE"
            lots = 0
            lot_size = NIFTY_LOT_SIZE
            quantity = 0
            instrument_entry_price = 0.0
            instrument_exit_price = 0.0
            capital_committed = 0.0
            fees = 0.0
            gross_pnl = 0.0
            net_pnl = 0.0
            pnl_pct = 0.0
            bars_to_outcome = 0
            capital_after = capital_before
            skip_reason = ""
            prev_rsi = float(df.iloc[idx - 1]["RSI"]) if idx > 0 else float(row["RSI"])

            trend_confirmed_15m = (
                (action == "BUY" and float(row["EMA9"]) > float(row["EMA21"]) and float(row["MACD_HIST"]) > 0)
                or (action == "SELL" and float(row["EMA9"]) < float(row["EMA21"]) and float(row["MACD_HIST"]) < 0)
            )
            trend_confirmed_1h = (
                (action == "BUY" and float(row["EMA9_1H"]) > float(row["EMA21_1H"]) and float(row["MACD_HIST_1H"]) > 0)
                or (action == "SELL" and float(row["EMA9_1H"]) < float(row["EMA21_1H"]) and float(row["MACD_HIST_1H"]) < 0)
            )
            adx_ok = float(row["ADX"]) > ADX_MIN
            directional_rsi_ok = (
                (action == "BUY" and RSI_BUY_MIN <= float(row["RSI"]) <= RSI_BUY_MAX)
                or (action == "SELL" and RSI_SELL_MIN <= float(row["RSI"]) <= RSI_SELL_MAX)
            )
            extra_confirmation_ok = (
                (action == "BUY" and 50.0 <= float(row["RSI"]) <= 62.0 and float(row["RSI"]) >= prev_rsi + 0.5)
                or (action == "SELL" and 38.0 <= float(row["RSI"]) <= 50.0 and float(row["RSI"]) <= prev_rsi - 0.5)
            )
            no_trade_zone_ok = trend_confirmed_15m and adx_ok

            # --- Gate 0: Parse reliability gate ---
            if parse_mode != "parsed_json":
                skip_reason = "NO_TRADE_PARSE_FAIL"
                outcome = "NO_TRADE_PARSE_FAIL"

            # --- Gate 1: Explicit HOLD signal vs confidence-gated directional signal ---
            elif action not in {"BUY", "SELL"}:
                skip_reason = "HOLD_SIGNAL"
                outcome = "HOLD_SIGNAL"
            elif confidence < self.dynamic_confidence_threshold:
                skip_reason = "LOW_CONFIDENCE"
                outcome = "LOW_CONFIDENCE"
            elif not directional_rsi_ok:
                skip_reason = "DIRECTIONAL_RSI_FILTER"
                outcome = "FILTERED_DIRECTIONAL_RSI"
            elif not no_trade_zone_ok:
                if not adx_ok:
                    skip_reason = "NO_TRADE_ZONE_ADX_WEAK"
                    outcome = "FILTERED_ADX"
                else:
                    skip_reason = "NO_TRADE_ZONE_TREND_MISALIGN_15M"
                    outcome = "FILTERED_TREND"

            # --- Gate 2: Data-driven session phase filter ---
            elif session_phase in {"open_volatility", "close_reversal"} and (
                confidence < OPEN_CLOSE_MIN_CONF or not trend_confirmed_15m or not trend_confirmed_1h
            ):
                skip_reason = f"SESSION_PHASE_FILTERED_{session_phase.upper()}"
                outcome = "FILTERED_SESSION"

            # --- Gate 2b: Post-SL friction rules ---
            elif idx <= sl_cooldown_until:
                skip_reason = "POST_SL_COOLDOWN"
                outcome = "FILTERED_POST_SL"
            elif require_extra_confirmation and not extra_confirmation_ok:
                skip_reason = "POST_SL_EXTRA_CONFIRMATION_FAIL"
                outcome = "FILTERED_POST_SL_CONFIRMATION"

            # --- Gate 3: Bars cooldown (position open OR post-trade cooldown) ---
            elif idx < next_free_index:
                skip_reason = "POSITION_ALREADY_OPEN_OR_COOLDOWN"

            # --- Gate 4: Daily trade cap ---
            elif not self.check_daily_limit(ts):
                skip_reason = "DAILY_TRADE_LIMIT_REACHED"
                outcome = "FILTERED_DAILY_LIMIT"

            else:
                # Sanity-check ATR-derived levels (edge case: ATR extremely small)
                if action == "BUY" and (target_price <= entry_price or stop_loss >= entry_price):
                    target_price = entry_price * 1.008
                    stop_loss = entry_price * 0.994
                if action == "SELL" and (target_price >= entry_price or stop_loss <= entry_price):
                    target_price = entry_price * 0.992
                    stop_loss = entry_price * 1.006

                trade_spec, plan_note = self.plan_trade(action, entry_price, capital_before)
                if trade_spec is None:
                    skip_reason = plan_note
                    outcome = "SKIPPED_NO_CAPITAL"
                else:
                    instrument = str(trade_spec["instrument"])
                    lots = int(trade_spec["lots"])
                    lot_size = int(trade_spec["lot_size"])
                    quantity = int(trade_spec["quantity"])
                    capital_committed = float(trade_spec["capital_committed"])
                    instrument_entry_price = float(trade_spec["instrument_entry_price"])

                    # Pre-trade edge test: projected gross at TP must exceed 3x projected fees.
                    _, projected_gross_tp, projected_fees_tp = self.settle_trade(
                        trade_spec=trade_spec,
                        action=action,
                        underlying_entry=entry_price,
                        underlying_exit=target_price,
                        bars_to_outcome=8,
                    )
                    if projected_gross_tp < projected_fees_tp * MIN_EXPECTED_GROSS_MULTIPLIER:
                        skip_reason = "EDGE_TOO_WEAK_BELOW_3X_FEES"
                        outcome = "FILTERED_EDGE"
                    else:
                        # Pre-trade risk cap: estimated stop-loss net must be within INR cap.
                        _, projected_gross_sl, projected_fees_sl = self.settle_trade(
                            trade_spec=trade_spec,
                            action=action,
                            underlying_entry=entry_price,
                            underlying_exit=stop_loss,
                            bars_to_outcome=2,
                        )
                        projected_net_sl = projected_gross_sl - projected_fees_sl
                        max_loss_inr = capital_before * MAX_LOSS_CAPITAL_PCT
                        if (-projected_net_sl) > max_loss_inr:
                            skip_reason = "LOSS_CAP_EXCEEDED"
                            outcome = "FILTERED_RISK_CAP"
                        else:
                            future = df.iloc[idx + 1:]
                            outcome, exit_price, _, _, bars_to_outcome = self.evaluate_first_hit(
                                action, entry_price, target_price, stop_loss, future,
                            )

                            if outcome == "NO_FUTURE_DATA" or bars_to_outcome <= 0:
                                outcome = "NO_FUTURE_DATA"
                                skip_reason = "NO_FUTURE_DATA"
                            else:
                                instrument_exit_price, gross_pnl, fees = self.settle_trade(
                                    trade_spec=trade_spec,
                                    action=action,
                                    underlying_entry=entry_price,
                                    underlying_exit=exit_price,
                                    bars_to_outcome=bars_to_outcome,
                                )
                                net_pnl = gross_pnl - fees
                                capital_after = capital_before + net_pnl
                                pnl_pct = (net_pnl / capital_before) * 100 if capital_before else 0.0
                                self.capital = capital_after
                                executed = True
                                # Enforce both trade-resolution gap AND minimum cooldown between entries
                                next_free_index = idx + max(bars_to_outcome + 1, MIN_BARS_BETWEEN_TRADES)
                                skip_reason = plan_note
                                # Update feedback loops
                                self.record_outcome(outcome)
                                self.increment_daily_count()
                                if outcome in {"SL_HIT", "SL_HIT_SAME_CANDLE"}:
                                    sl_cooldown_until = idx + POST_SL_COOLDOWN_BARS
                                    require_extra_confirmation = True
                                elif outcome == "TP_HIT":
                                    require_extra_confirmation = False

            self.rows.append(
                DecisionRow(
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    action=action,
                    confidence=confidence,
                    instrument=instrument,
                    lots=lots,
                    lot_size=lot_size,
                    quantity=quantity,
                    entry_price=entry_price,
                    target_price=target_price,
                    stop_loss=stop_loss,
                    instrument_entry_price=instrument_entry_price,
                    instrument_exit_price=instrument_exit_price,
                    capital_before=capital_before,
                    capital_committed=capital_committed,
                    fees=fees,
                    reason=reason,
                    executed=executed,
                    outcome=outcome,
                    exit_price=exit_price,
                    gross_pnl=gross_pnl,
                    pnl=net_pnl,
                    pnl_pct=pnl_pct,
                    bars_to_outcome=bars_to_outcome,
                    capital_after=capital_after,
                    skip_reason=skip_reason,
                )
            )

        if not self.rows:
            print("No decision rows generated.")
            return

        out_df = pd.DataFrame([asdict(row) for row in self.rows])
        candidate_paths = [
            "backtestV2.csv",
            "backtestV2.generated.csv",
            f"backtestV2.generated.{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        ]
        out_path = ""
        last_write_error: Optional[Exception] = None
        for candidate in candidate_paths:
            try:
                out_df.to_csv(candidate, index=False)
                out_path = candidate
                break
            except PermissionError as exc:
                last_write_error = exc
                continue

        if not out_path:
            raise RuntimeError(f"Unable to write results CSV to any candidate path: {candidate_paths}") from last_write_error

        executed_df = out_df[out_df["executed"] == True]  # noqa: E712
        tp_hits = int((executed_df["outcome"] == "TP_HIT").sum())
        sl_hits = int(executed_df["outcome"].isin(["SL_HIT", "SL_HIT_SAME_CANDLE"]).sum())
        total_executed = len(executed_df)
        total_fees = float(executed_df["fees"].sum()) if total_executed else 0.0
        gross_pnl_total = float(executed_df["gross_pnl"].sum()) if total_executed else 0.0
        net_pnl_total = float(executed_df["pnl"].sum()) if total_executed else 0.0
        skipped_for_capital = int(out_df["skip_reason"].isin(["INSUFFICIENT_CAPITAL_FOR_OPTION_LOT", "SKIPPED_NO_CAPITAL"]).sum())
        option_trades = int(executed_df["instrument"].isin(["LONG_CALL", "LONG_PUT"]).sum())
        futures_trades = int((executed_df["instrument"] == "FUTURES").sum())
        final_capital = float(out_df.iloc[-1]["capital_after"])
        return_pct = ((final_capital / INITIAL_CAPITAL_INR) - 1) * 100
        win_rate = (tp_hits / total_executed * 100) if total_executed else 0.0
        win_rate_frac = (tp_hits / total_executed) if total_executed else 0.0
        loss_rate_frac = 1 - win_rate_frac if total_executed else 0.0
        wins_df = executed_df[executed_df["pnl"] > 0]
        losses_df = executed_df[executed_df["pnl"] <= 0]
        avg_win = float(wins_df["pnl"].mean()) if len(wins_df) else 0.0
        avg_loss_abs = float((-losses_df["pnl"]).mean()) if len(losses_df) else 0.0
        avg_fees = float(executed_df["fees"].mean()) if total_executed else 0.0
        expectancy = (win_rate_frac * avg_win) - (loss_rate_frac * avg_loss_abs) - avg_fees
        parsed_json_pct = (parsed_json_count / model_calls * 100) if model_calls else 0.0
        heuristic_pct = (heuristic_fallback_count / model_calls * 100) if model_calls else 0.0
        parse_fail_pct = (parse_fail_count / model_calls * 100) if model_calls else 0.0

        print("\n--- Summary ---")
        print(f"Total decision checks: {len(out_df)}")
        print(f"Executed trades: {total_executed} | Win rate: {win_rate:.1f}%")
        print(f"Option trades: {option_trades}")
        print(f"Futures trades: {futures_trades}")
        print(f"TP hits: {tp_hits}")
        print(f"SL hits: {sl_hits}")
        print(f"Skipped for capital constraints: {skipped_for_capital}")
        print(f"Final adaptive confidence gate: {self.dynamic_confidence_threshold}")
        print(f"JSON compliance - parsed_json: {parsed_json_pct:.1f}%")
        print(f"JSON compliance - heuristic_fallback: {heuristic_pct:.1f}%")
        print(f"JSON compliance - parse_fail: {parse_fail_pct:.1f}%")
        print(f"Avg win: INR {avg_win:,.2f} | Avg loss: INR {avg_loss_abs:,.2f} | Avg fees: INR {avg_fees:,.2f}")
        print(f"Expectancy/trade: INR {expectancy:,.2f}")
        print(f"Gross PnL: INR {gross_pnl_total:,.2f}")
        print(f"Fees + slippage: INR {total_fees:,.2f}")
        print(f"Net PnL: INR {net_pnl_total:,.2f}")
        print(f"Final capital: INR {final_capital:,.2f}")
        print(f"Return on initial capital: {return_pct:.2f}%")
        print("Real option data: NOT integrated yet (proxy still in use).")
        print(f"Research source used: {self.research_source}")
        print(f"Results CSV: {out_path}")


async def main() -> None:
    load_env_file()
    runner = ClaudeComparator()
    try:
        await runner.run()
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())