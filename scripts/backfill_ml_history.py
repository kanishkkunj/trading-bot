#!/usr/bin/env python3
"""Backfill 10-year historical data into dedicated ML tables.

Design goals:
- Deterministic upsert by (symbol, timeframe, timestamp)
- Resume-safe via checkpoint file
- AngelOne-first with yfinance fallback
- Separate ML tables: ml_candles and ml_features (linked by candle_id)
- Balanced validation: skip bad rows, continue, and report
- Gap marking and coverage report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Allow importing backend package in both host repo and backend container layouts.
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
APP_ROOT = REPO_ROOT
if not (APP_ROOT / "app").exists() and (BACKEND_ROOT / "app").exists():
    APP_ROOT = BACKEND_ROOT
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.market_service import MarketService  # noqa: E402


CHECKPOINT_PATH = REPO_ROOT / ".state" / "ml_backfill_checkpoint.json"
REPORT_PATH = REPO_ROOT / "logs" / f"ml_backfill_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"

SESSION_START_IST = time(9, 15)
SESSION_END_IST = time(15, 30)
BARS_PER_DAY_15M = 25


@dataclass
class BackfillConfig:
    symbols: list[str]
    timeframes: list[str]
    start_utc: datetime
    end_utc: datetime
    chunk_days: dict[str, int]
    feature_set: str = "core_v1"


class BackfillRunner:
    def __init__(self, db: AsyncSession, cfg: BackfillConfig) -> None:
        self.db = db
        self.cfg = cfg
        self.errors: list[dict[str, Any]] = []
        self.coverage: list[dict[str, Any]] = []
        self.run_id = str(uuid4())
        self.checkpoint = self._load_checkpoint()

    def _load_checkpoint(self) -> dict[str, Any]:
        if CHECKPOINT_PATH.exists():
            try:
                return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_checkpoint(self) -> None:
        CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_PATH.write_text(json.dumps(self.checkpoint, indent=2), encoding="utf-8")

    async def ensure_tables(self) -> None:
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS ml_backfill_runs (
                id VARCHAR(36) PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP NULL,
                status VARCHAR(20) NOT NULL,
                config JSONB NOT NULL,
                summary JSONB NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ml_candles (
                id VARCHAR(36) PRIMARY KEY,
                symbol VARCHAR(30) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open NUMERIC(15,4) NOT NULL,
                high NUMERIC(15,4) NOT NULL,
                low NUMERIC(15,4) NOT NULL,
                close NUMERIC(15,4) NOT NULL,
                volume BIGINT NOT NULL,
                source VARCHAR(30) NOT NULL,
                adjusted BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uix_ml_candles_symbol_tf_ts UNIQUE (symbol, timeframe, timestamp)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_ml_candles_symbol_tf_ts
            ON ml_candles(symbol, timeframe, timestamp);
            """,
            """
            CREATE TABLE IF NOT EXISTS ml_features (
                id VARCHAR(36) PRIMARY KEY,
                candle_id VARCHAR(36) NOT NULL REFERENCES ml_candles(id) ON DELETE CASCADE,
                feature_set VARCHAR(50) NOT NULL,
                rsi14 NUMERIC(18,8) NULL,
                ema21 NUMERIC(18,8) NULL,
                macd NUMERIC(18,8) NULL,
                macd_signal NUMERIC(18,8) NULL,
                atr14 NUMERIC(18,8) NULL,
                extra JSONB NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uix_ml_features_candle_set UNIQUE (candle_id, feature_set)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_ml_features_candle_id
            ON ml_features(candle_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS ml_data_gaps (
                id VARCHAR(36) PRIMARY KEY,
                run_id VARCHAR(36) NOT NULL,
                symbol VARCHAR(30) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,
                gap_start TIMESTAMP NOT NULL,
                gap_end TIMESTAMP NOT NULL,
                missing_points INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """,
        ]
        for stmt in ddl:
            await self.db.execute(text(stmt))
        await self.db.commit()

    async def mark_run_started(self) -> None:
        payload = {
            "id": self.run_id,
            "started_at": datetime.now(UTC).replace(tzinfo=None),
            "status": "running",
            "config": {
                "symbols": self.cfg.symbols,
                "timeframes": self.cfg.timeframes,
                "start_utc": self.cfg.start_utc.isoformat(),
                "end_utc": self.cfg.end_utc.isoformat(),
                "chunk_days": self.cfg.chunk_days,
            },
        }
        await self.db.execute(
            text(
                """
                INSERT INTO ml_backfill_runs (id, started_at, status, config)
                VALUES (:id, :started_at, :status, CAST(:config AS JSONB));
                """
            ),
            {**payload, "config": json.dumps(payload["config"])},
        )
        await self.db.commit()

    async def mark_run_finished(self) -> None:
        status = "completed" if not self.errors else "completed_errors"
        summary = {
            "errors": self.errors,
            "coverage": self.coverage,
            "checkpoint_path": str(CHECKPOINT_PATH),
            "report_path": str(REPORT_PATH),
        }
        await self.db.execute(
            text(
                """
                UPDATE ml_backfill_runs
                SET finished_at = :finished_at,
                    status = :status,
                    summary = CAST(:summary AS JSONB)
                WHERE id = :id;
                """
            ),
            {
                "id": self.run_id,
                "finished_at": datetime.now(UTC).replace(tzinfo=None),
                "status": status,
                "summary": json.dumps(summary),
            },
        )
        await self.db.commit()

    def _symbol_key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    def _checkpoint_end(self, symbol: str, timeframe: str) -> datetime | None:
        value = self.checkpoint.get(self._symbol_key(symbol, timeframe))
        if not value:
            return None
        return datetime.fromisoformat(value)

    def _set_checkpoint_end(self, symbol: str, timeframe: str, end_dt: datetime) -> None:
        self.checkpoint[self._symbol_key(symbol, timeframe)] = end_dt.isoformat()

    @staticmethod
    def _iter_chunks(start: datetime, end: datetime, chunk_days: int) -> list[tuple[datetime, datetime]]:
        out: list[tuple[datetime, datetime]] = []
        cur = start
        while cur < end:
            nxt = min(cur + timedelta(days=chunk_days), end)
            out.append((cur, nxt))
            cur = nxt
        return out

    @staticmethod
    def _normalize_df(df: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
        if df.empty:
            return df

        cols = {c.lower(): c for c in df.columns}
        req = ["open", "high", "low", "close", "volume", "timestamp"]
        for r in req:
            if r not in cols:
                raise ValueError(f"missing required column {r}")

        out = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(df[cols["timestamp"]], errors="coerce", utc=True)
                .dt.tz_convert("UTC")
                .dt.tz_localize(None),
                "open": pd.to_numeric(df[cols["open"]], errors="coerce"),
                "high": pd.to_numeric(df[cols["high"]], errors="coerce"),
                "low": pd.to_numeric(df[cols["low"]], errors="coerce"),
                "close": pd.to_numeric(df[cols["close"]], errors="coerce"),
                "volume": pd.to_numeric(df[cols["volume"]], errors="coerce").fillna(0).astype("int64"),
            }
        )

        out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])

        # Balanced quality rules: reject clearly bad rows, continue ingest.
        out = out[
            (out["open"] > 0)
            & (out["high"] > 0)
            & (out["low"] > 0)
            & (out["close"] > 0)
            & (out["high"] >= out[["open", "low", "close"]].max(axis=1))
            & (out["low"] <= out[["open", "high", "close"]].min(axis=1))
            & (out["volume"] >= 0)
        ]

        out = out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        out["symbol"] = symbol
        out["timeframe"] = timeframe
        return out

    @staticmethod
    def _filter_ist_session(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        ts_ist = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("Asia/Kolkata")
        mask = (
            (ts_ist.dt.dayofweek < 5)
            & (ts_ist.dt.time >= SESSION_START_IST)
            & (ts_ist.dt.time <= SESSION_END_IST)
        )
        return df.loc[mask].copy()

    def _fetch_yfinance(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> tuple[pd.DataFrame, bool, str]:
        import yfinance as yf

        yf_symbol = symbol
        if symbol.upper() == "NIFTY":
            yf_symbol = "^NSEI"
        elif symbol.upper() == "BANKNIFTY":
            yf_symbol = "^NSEBANK"

        interval_map = {"1d": "1d", "15m": "15m"}
        interval = interval_map[timeframe]

        # yfinance does not provide long-history 15m beyond ~60 days.
        if timeframe == "15m" and (end - start).days > 59:
            start = end - timedelta(days=59)

        ticker = yf.Ticker(yf_symbol)
        auto_adjust = timeframe == "1d"
        hist = ticker.history(start=start, end=end, interval=interval, auto_adjust=auto_adjust)
        if hist.empty:
            return pd.DataFrame(), auto_adjust, "yfinance"

        hist = hist.reset_index().rename(columns={
            "Datetime": "timestamp",
            "Date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        return hist[["timestamp", "open", "high", "low", "close", "volume"]], auto_adjust, "yfinance"

    def _fetch_angel(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> tuple[pd.DataFrame, bool, str]:
        from app.data.provider_nse import AngelOneDataProvider

        provider = AngelOneDataProvider()
        raw = provider.get_candle_data(symbol, timeframe, start, end)
        data = (raw or {}).get("data") if isinstance(raw, dict) else None
        if not data:
            return pd.DataFrame(), False, "angelone"

        frame = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        return frame, False, "angelone"

    async def _upsert_candles(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        stmt = text(
            """
            INSERT INTO ml_candles (
                id, symbol, timeframe, timestamp, open, high, low, close, volume,
                source, adjusted, created_at, updated_at
            ) VALUES (
                :id, :symbol, :timeframe, :timestamp, :open, :high, :low, :close, :volume,
                :source, :adjusted, NOW(), NOW()
            )
            ON CONFLICT (symbol, timeframe, timestamp)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                source = EXCLUDED.source,
                adjusted = EXCLUDED.adjusted,
                updated_at = NOW();
            """
        )
        await self.db.execute(stmt, rows)

    async def _upsert_features(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        stmt = text(
            """
            INSERT INTO ml_features (
                id, candle_id, feature_set, rsi14, ema21, macd, macd_signal, atr14, extra, created_at
            ) VALUES (
                :id, :candle_id, :feature_set, :rsi14, :ema21, :macd, :macd_signal, :atr14,
                CAST(:extra AS JSONB), NOW()
            )
            ON CONFLICT (candle_id, feature_set)
            DO UPDATE SET
                rsi14 = EXCLUDED.rsi14,
                ema21 = EXCLUDED.ema21,
                macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal,
                atr14 = EXCLUDED.atr14,
                extra = EXCLUDED.extra;
            """
        )
        await self.db.execute(stmt, rows)

    async def _mark_gaps(self, symbol: str, timeframe: str, points: list[tuple[datetime, datetime, int]]) -> None:
        if not points:
            return
        rows = [
            {
                "id": str(uuid4()),
                "run_id": self.run_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "gap_start": a,
                "gap_end": b,
                "missing_points": n,
            }
            for a, b, n in points
        ]
        await self.db.execute(
            text(
                """
                INSERT INTO ml_data_gaps (id, run_id, symbol, timeframe, gap_start, gap_end, missing_points)
                VALUES (:id, :run_id, :symbol, :timeframe, :gap_start, :gap_end, :missing_points);
                """
            ),
            rows,
        )

    @staticmethod
    def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
        out = df.sort_values("timestamp").copy()
        out["ema21"] = out["close"].ewm(span=21, adjust=False).mean()

        delta = out["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        out["rsi14"] = 100 - (100 / (1 + rs))

        ema12 = out["close"].ewm(span=12, adjust=False).mean()
        ema26 = out["close"].ewm(span=26, adjust=False).mean()
        out["macd"] = ema12 - ema26
        out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()

        tr1 = out["high"] - out["low"]
        tr2 = (out["high"] - out["close"].shift(1)).abs()
        tr3 = (out["low"] - out["close"].shift(1)).abs()
        out["atr14"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()

        return out

    @staticmethod
    def _detect_gaps(df: pd.DataFrame, timeframe: str) -> list[tuple[datetime, datetime, int]]:
        if len(df) < 2:
            return []
        out: list[tuple[datetime, datetime, int]] = []
        ts = pd.to_datetime(df["timestamp"]).sort_values().to_list()
        if timeframe == "15m":
            step = timedelta(minutes=15)
            for a, b in zip(ts[:-1], ts[1:]):
                diff = b - a
                missing = int(diff / step) - 1
                if missing > 0:
                    out.append((a, b, missing))
        else:
            # Keep weekend tolerance for daily bars.
            for a, b in zip(ts[:-1], ts[1:]):
                diff_days = (b.date() - a.date()).days
                if diff_days > 3:
                    out.append((a, b, diff_days - 1))
        return out

    async def _build_features_for_range(self, symbol: str, timeframe: str) -> None:
        rows = (
            await self.db.execute(
                text(
                    """
                    SELECT id, timestamp, open, high, low, close
                    FROM ml_candles
                    WHERE symbol = :symbol
                      AND timeframe = :timeframe
                      AND timestamp >= :start_utc
                      AND timestamp <= :end_utc
                    ORDER BY timestamp;
                    """
                ),
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start_utc": self.cfg.start_utc.replace(tzinfo=None),
                    "end_utc": self.cfg.end_utc.replace(tzinfo=None),
                },
            )
        ).mappings().all()

        if not rows:
            return

        frame = pd.DataFrame(rows)
        feat = self._compute_features(frame)
        feat = feat.dropna(subset=["rsi14", "ema21", "macd", "macd_signal", "atr14"])

        payload = [
            {
                "id": str(uuid4()),
                "candle_id": r["id"],
                "feature_set": self.cfg.feature_set,
                "rsi14": float(r["rsi14"]),
                "ema21": float(r["ema21"]),
                "macd": float(r["macd"]),
                "macd_signal": float(r["macd_signal"]),
                "atr14": float(r["atr14"]),
                "extra": json.dumps({}),
            }
            for _, r in feat.iterrows()
        ]
        await self._upsert_features(payload)

    async def _compute_coverage(self, symbol: str, timeframe: str) -> dict[str, Any]:
        eval_start = self.cfg.start_utc
        if timeframe == "15m":
            eval_start = max(self.cfg.start_utc, self.cfg.end_utc - timedelta(days=60))

        actual = (
            await self.db.execute(
                text(
                    """
                    SELECT COUNT(*) AS n
                    FROM ml_candles
                    WHERE symbol = :symbol
                      AND timeframe = :timeframe
                      AND timestamp >= :start_utc
                      AND timestamp <= :end_utc;
                    """
                ),
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start_utc": eval_start.replace(tzinfo=None),
                    "end_utc": self.cfg.end_utc.replace(tzinfo=None),
                },
            )
        ).scalar_one()

        if timeframe == "1d":
            expected = len(pd.bdate_range(self.cfg.start_utc.date(), self.cfg.end_utc.date()))
        else:
            expected_days = len(pd.bdate_range(eval_start.date(), self.cfg.end_utc.date()))
            expected = expected_days * BARS_PER_DAY_15M

        coverage_row = {
            "symbol": symbol,
            "timeframe": timeframe,
            "expected": expected,
            "actual": int(actual),
            "coverage_pct": round((float(actual) / float(expected) * 100.0) if expected > 0 else 0.0, 2),
        }
        self.coverage.append(coverage_row)
        return coverage_row

    async def _ingest_symbol_timeframe(self, symbol: str, timeframe: str) -> None:
        chunk_days = self.cfg.chunk_days[timeframe]
        effective_start = self.cfg.start_utc

        # Practical market-data limit: keep 15m ingestion to the most recent 60 days.
        if timeframe == "15m":
            effective_start = max(self.cfg.start_utc, self.cfg.end_utc - timedelta(days=60))

        chunks = self._iter_chunks(effective_start, self.cfg.end_utc, chunk_days)
        resume_from = self._checkpoint_end(symbol, timeframe)

        for start, end in chunks:
            if resume_from and end <= resume_from:
                continue

            chunk_df = pd.DataFrame()
            source = "none"
            adjusted = False

            # Source strategy:
            # - 1d: yfinance first to satisfy adjusted OHLC requirement
            # - 15m: AngelOne first, yfinance fallback
            if timeframe == "1d":
                try:
                    fetched, adj, src = self._fetch_yfinance(symbol, timeframe, start, end)
                    if not fetched.empty:
                        chunk_df, adjusted, source = fetched, adj, src
                except Exception as exc:
                    self.errors.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "window": [start.isoformat(), end.isoformat()],
                        "source": "yfinance",
                        "error": str(exc),
                    })

                if chunk_df.empty:
                    try:
                        fetched, adj, src = self._fetch_angel(symbol, timeframe, start, end)
                        if not fetched.empty:
                            chunk_df, adjusted, source = fetched, adj, src
                    except Exception as exc:
                        self.errors.append({
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "window": [start.isoformat(), end.isoformat()],
                            "source": "angelone",
                            "error": str(exc),
                        })
            else:
                try:
                    fetched, adj, src = self._fetch_angel(symbol, timeframe, start, end)
                    if not fetched.empty:
                        chunk_df, adjusted, source = fetched, adj, src
                except Exception as exc:
                    self.errors.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "window": [start.isoformat(), end.isoformat()],
                        "source": "angelone",
                        "error": str(exc),
                    })

                if chunk_df.empty:
                    try:
                        fetched, adj, src = self._fetch_yfinance(symbol, timeframe, start, end)
                        if not fetched.empty:
                            chunk_df, adjusted, source = fetched, adj, src
                    except Exception as exc:
                        self.errors.append({
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "window": [start.isoformat(), end.isoformat()],
                            "source": "yfinance",
                            "error": str(exc),
                        })

            if chunk_df.empty:
                self._set_checkpoint_end(symbol, timeframe, end)
                self._save_checkpoint()
                continue

            try:
                norm = self._normalize_df(chunk_df, symbol, timeframe)
                if timeframe == "15m":
                    norm = self._filter_ist_session(norm)

                if norm.empty:
                    self._set_checkpoint_end(symbol, timeframe, end)
                    self._save_checkpoint()
                    continue

                rows = [
                    {
                        "id": str(uuid4()),
                        "symbol": r["symbol"],
                        "timeframe": r["timeframe"],
                        "timestamp": pd.Timestamp(r["timestamp"]).to_pydatetime(),
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": int(r["volume"]),
                        "source": source,
                        "adjusted": adjusted,
                    }
                    for _, r in norm.iterrows()
                ]

                batch = 3000
                for i in range(0, len(rows), batch):
                    await self._upsert_candles(rows[i : i + batch])
                await self.db.commit()

                self._set_checkpoint_end(symbol, timeframe, end)
                self._save_checkpoint()

            except Exception as exc:
                await self.db.rollback()
                self.errors.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "window": [start.isoformat(), end.isoformat()],
                    "source": source,
                    "error": str(exc),
                })

        # Build linked features after raw candles complete for this symbol/timeframe.
        await self._build_features_for_range(symbol, timeframe)

        # Detect and store data gaps.
        rows = (
            await self.db.execute(
                text(
                    """
                    SELECT timestamp
                    FROM ml_candles
                    WHERE symbol = :symbol
                      AND timeframe = :timeframe
                      AND timestamp >= :start_utc
                      AND timestamp <= :end_utc
                    ORDER BY timestamp;
                    """
                ),
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start_utc": self.cfg.start_utc.replace(tzinfo=None),
                    "end_utc": self.cfg.end_utc.replace(tzinfo=None),
                },
            )
        ).mappings().all()
        ts_df = pd.DataFrame(rows)
        if not ts_df.empty:
            gaps = self._detect_gaps(ts_df, timeframe)
            await self._mark_gaps(symbol, timeframe, gaps)

        coverage_row = await self._compute_coverage(symbol, timeframe)
        if coverage_row["actual"] == 0:
            # Avoid locking in transient provider misses for an entire symbol/timeframe.
            self.checkpoint.pop(self._symbol_key(symbol, timeframe), None)
            self._save_checkpoint()
            self.errors.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "window": [self.cfg.start_utc.isoformat(), self.cfg.end_utc.isoformat()],
                    "source": "all",
                    "error": "No data ingested for symbol/timeframe; checkpoint cleared for retry",
                }
            )
        await self.db.commit()

    async def run(self) -> dict[str, Any]:
        await self.ensure_tables()
        await self.mark_run_started()

        # Use single-session sequential ingestion for correctness.
        for symbol in self.cfg.symbols:
            for tf in self.cfg.timeframes:
                await self._ingest_symbol_timeframe(symbol, tf)

        await self.mark_run_finished()

        result = {
            "run_id": self.run_id,
            "errors": self.errors,
            "coverage": self.coverage,
            "checkpoint_path": str(CHECKPOINT_PATH),
            "report_path": str(REPORT_PATH),
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


def build_config(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    lookback_days: int = 3652,
) -> BackfillConfig:
    end_utc = datetime.now(UTC).replace(microsecond=0)
    start_utc = end_utc - timedelta(days=lookback_days)

    final_symbols = symbols or list(MarketService.NIFTY50_SYMBOLS)
    final_timeframes = timeframes or ["15m", "1d"]

    # Requested set: 15m and 1d, with resume checkpoints and speed mode.
    return BackfillConfig(
        symbols=final_symbols,
        timeframes=final_timeframes,
        start_utc=start_utc,
        end_utc=end_utc,
        chunk_days={
            "1d": 365,
            "15m": 60,
        },
    )


async def _run(symbols: list[str] | None, timeframes: list[str] | None, lookback_days: int) -> int:
    cfg = build_config(symbols=symbols, timeframes=timeframes, lookback_days=lookback_days)

    async with AsyncSessionLocal() as db:
        runner = BackfillRunner(db, cfg)
        result = await runner.run()

    print("Run ID:", result["run_id"])
    print("Checkpoint:", result["checkpoint_path"])
    print("Report:", result["report_path"])
    print("Coverage rows:", len(result["coverage"]))
    print("Errors:", len(result["errors"]))

    # Soft success even with partial errors; details are in report.
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ML historical candles and features")
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated symbols (example: RELIANCE.NS,TCS.NS)",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default="15m,1d",
        help="Comma-separated timeframes (default: 15m,1d)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=3652,
        help="Historical lookback window in days (default ~10 years)",
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or None
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()] or None

    rc = asyncio.run(_run(symbols, timeframes, args.lookback_days))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
