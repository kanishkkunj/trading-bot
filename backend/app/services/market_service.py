"""Market data service."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
import math

import pandas as pd
import yfinance as yf
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle
from app.schemas.market import CandleResponse, HistoricalDataRequest
from app.clients.zerodha_client import ZerodhaClient


class MarketService:
    """Service for market data operations."""

    # NIFTY 50 symbols mapping (Yahoo Finance format)
    NIFTY50_SYMBOLS = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
        "LT.NS", "HCLTECH.NS", "AXISBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS",
        "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ADANIENT.NS", "ULTRACEMCO.NS",
        "NESTLEIND.NS", "WIPRO.NS", "POWERGRID.NS", "NTPC.NS", "M&M.NS",
        "JSWSTEEL.NS", "TATASTEEL.NS", "GRASIM.NS", "ADANIPORTS.NS", "COALINDIA.NS",
        "HDFCLIFE.NS", "BRITANNIA.NS", "TECHM.NS", "INDUSINDBK.NS", "EICHERMOT.NS",
        "DRREDDY.NS", "APOLLOHOSP.NS", "BAJAJFINSV.NS", "TATAMOTORS.NS", "ONGC.NS",
        "DIVISLAB.NS", "HINDALCO.NS", "CIPLA.NS", "BPCL.NS", "HEROMOTOCO.NS",
        "SBILIFE.NS", "TATACONSUM.NS", "UPL.NS", "BAJAJ-AUTO.NS", "SHREECEM.NS",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.zerodha = ZerodhaClient()

    import asyncio

    async def get_historical_data(self, request: HistoricalDataRequest) -> list[CandleResponse]:
        """Get historical OHLCV data. Prefer DB, but refresh from AngelOne when stale; no yfinance fallback."""
        # First check database
        candles = await self._get_candles_from_db(
            request.symbol, request.timeframe, request.from_date, request.to_date
        )

        def _is_stale(candle_list: list[CandleResponse]) -> bool:
            if not candle_list:
                return True
            latest = max(c.timestamp for c in candle_list)
            # Consider stale if older than 2 hours from the requested end
            return latest < request.to_date - timedelta(hours=2)

        if candles and not _is_stale(candles):
            return candles

        # Try AngelOne with a strict timeout around the blocking SDK call.
        # This prevents the endpoint from hanging long enough for n8n HTTP nodes to abort.
        ANGEL_HIST_TIMEOUT_SEC = 10
        try:
            import logging

            logger = logging.getLogger("market_service")
            from app.data.provider_nse import AngelOneDataProvider

            provider = AngelOneDataProvider()
            data = await asyncio.wait_for(
                asyncio.to_thread(
                    provider.get_candle_data,
                    request.symbol,
                    request.timeframe,
                    request.from_date,
                    request.to_date,
                ),
                timeout=ANGEL_HIST_TIMEOUT_SEC,
            )
            if isinstance(data, dict) and data.get("status") and data.get("data"):
                def _normalize_ts(ts_raw: datetime | str) -> datetime:
                    ts = ts_raw
                    if isinstance(ts_raw, str):
                        ts = datetime.fromisoformat(ts_raw)
                    # AngelOne returns +05:30; store as naive UTC for DB consistency
                    if ts.tzinfo is not None:
                        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
                    return ts

                fresh: list[CandleResponse] = []
                for row in data["data"]:
                    fresh.append(CandleResponse(
                        symbol=request.symbol,
                        timeframe=request.timeframe,
                        timestamp=_normalize_ts(row[0]),
                        open=row[1],
                        high=row[2],
                        low=row[3],
                        close=row[4],
                        volume=row[5],
                    ))

                # Store/refresh in DB (idempotent per candle)
                try:
                    for c in fresh:
                        await self._store_candle(c)
                    await self.db.commit()
                except Exception:
                    await self.db.rollback()

                return fresh
            else:
                logger.error(
                    "AngelOne candle fetch failed or empty",
                    extra={
                        "symbol": request.symbol,
                        "timeframe": request.timeframe,
                        "from": request.from_date,
                        "to": request.to_date,
                        "response": data,
                    },
                )
        except asyncio.TimeoutError:
            import logging

            logging.getLogger("market_service").warning(
                "AngelOne historical fetch timed out for %s", request.symbol
            )
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger("market_service").error(
                f"AngelOne historical fetch raised for {request.symbol}", exc_info=exc
            )

        # If DB had stale data but AngelOne failed, return DB result to avoid empty
        if candles:
            return candles

        # No data available
        return []

    async def _get_candles_from_db(
        self, symbol: str, timeframe: str, from_date: datetime, to_date: datetime
    ) -> list[CandleResponse]:
        """Get candles from database."""
        result = await self.db.execute(
            select(Candle)
            .where(
                and_(
                    Candle.symbol == symbol,
                    Candle.timeframe == timeframe,
                    Candle.timestamp >= from_date,
                    Candle.timestamp <= to_date,
                )
            )
            .order_by(Candle.timestamp)
        )

        candles = result.scalars().all()

        if not candles:
            return []

        return [
            CandleResponse(
                symbol=c.symbol,
                timeframe=c.timeframe,
                timestamp=c.timestamp,
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=c.volume,
            )
            for c in candles
        ]

    async def _fetch_from_yfinance(
        self,
        symbol: str,
        timeframe: str,
        from_date: datetime,
        to_date: datetime,
        fetch_symbol: Optional[str] = None,
    ) -> list[CandleResponse]:
        """Fetch historical data from Yahoo Finance, storing under the requested symbol."""
        # Map timeframe to yfinance interval
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "1d": "1d",
            "1w": "1wk",
            "1M": "1mo",
        }

        interval = interval_map.get(timeframe, "1d")

        query_symbol = fetch_symbol or symbol

        try:
            ticker = yf.Ticker(query_symbol)
            df = ticker.history(
                start=from_date,
                end=to_date,
                interval=interval,
            )

            if df.empty:
                return []

            candles = []
            for timestamp, row in df.iterrows():
                # Normalize to naive UTC to align with DB schema
                ts = timestamp
                if ts.tzinfo is not None:
                    ts = ts.tz_convert("UTC").to_pydatetime().replace(tzinfo=None)
                else:
                    ts = ts.to_pydatetime()

                candle = CandleResponse(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=round(row["Open"], 4),
                    high=round(row["High"], 4),
                    low=round(row["Low"], 4),
                    close=round(row["Close"], 4),
                    volume=int(row["Volume"]),
                )
                candles.append(candle)

                # Store in database for future use
                await self._store_candle(candle)

            await self.db.commit()
            return candles

        except Exception as e:
            print(f"Error fetching data from yfinance: {e}")
            return []

    def _map_symbol_for_yf(self, symbol: str) -> str:
        """Map friendly symbols to Yahoo Finance symbols."""
        mapping = {
            "NIFTY": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
        }
        return mapping.get(symbol.upper(), symbol)

    async def _store_candle(self, candle: CandleResponse) -> None:
        """Store candle in database (idempotent)."""
        # Check if candle already exists
        result = await self.db.execute(
            select(Candle).where(
                and_(
                    Candle.symbol == candle.symbol,
                    Candle.timeframe == candle.timeframe,
                    Candle.timestamp == candle.timestamp,
                )
            )
        )

        if result.scalar_one_or_none():
            return

        db_candle = Candle(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            timestamp=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )
        self.db.add(db_candle)

    async def get_live_quote(self, symbol: str) -> Optional[dict]:
        """Get live quote. AngelOne first; fallback to yfinance when zero/error."""
        import logging
        from datetime import datetime

        logger = logging.getLogger("market_service")
        # Keep quote endpoint responsive for n8n. External providers can hang,
        # so each provider call is wrapped in a strict timeout.
        YF_TIMEOUT_SEC = 8
        ANGEL_TIMEOUT_SEC = 6

        # For index symbols, prefer yfinance first to stay consistent with historical source
        if symbol.upper() in {"NIFTY", "BANKNIFTY"}:
            try:
                quote = await asyncio.wait_for(self._get_live_quote_yf(symbol), timeout=YF_TIMEOUT_SEC)
                if quote.get("last_price", 0) > 0:
                    return quote
            except asyncio.TimeoutError:
                logger.warning("yfinance index quote timed out for %s", symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning("yfinance index quote failed for %s: %s", symbol, exc)

        # Try AngelOne websocket
        try:
            from app.data.provider_nse import AngelOneDataProvider
            provider = AngelOneDataProvider()
            result = await asyncio.wait_for(
                asyncio.to_thread(provider.stream_live_data, symbol),
                timeout=ANGEL_TIMEOUT_SEC,
            )
            logger.info(f"AngelOneDataProvider response for {symbol}: {result}")
            if result.get("last_price", 0) > 0:
                return {
                    "symbol": symbol,
                    "last_price": result.get("last_price", 0),
                    "change": result.get("change", 0),
                    "change_percent": result.get("change_percent", 0),
                    "bid": result.get("bid", 0),
                    "ask": result.get("ask", 0),
                    "bid_qty": result.get("bid_qty", 0),
                    "ask_qty": result.get("ask_qty", 0),
                    "volume": result.get("volume", 0),
                    "timestamp": result.get("timestamp", datetime.utcnow()),
                    "source": "angelone",
                }
        except asyncio.TimeoutError:
            logger.warning("AngelOne live quote timed out for %s", symbol)
        except Exception as e:
            logger.error(f"AngelOne live quote failed for {symbol}: {e}", exc_info=True)

        # Fallback to yfinance (use intraday history last close)
        try:
            quote = await asyncio.wait_for(self._get_live_quote_yf(symbol), timeout=YF_TIMEOUT_SEC)
            if quote.get("last_price", 0) > 0:
                return quote
        except asyncio.TimeoutError:
            logger.warning("yfinance fallback quote timed out for %s", symbol)
        except Exception as e:
            logger.error(f"yfinance live quote failed for {symbol}: {e}", exc_info=True)

        # Final fallback: use latest stored close so downstream n8n flow can continue.
        try:
            last_close = await self._get_latest_close_from_db(symbol)
            if last_close > 0:
                return {
                    "symbol": symbol,
                    "last_price": last_close,
                    "change": 0,
                    "change_percent": 0,
                    "bid": 0,
                    "ask": 0,
                    "bid_qty": 0,
                    "ask_qty": 0,
                    "volume": 0,
                    "timestamp": datetime.utcnow(),
                    "source": "db_fallback",
                }
        except Exception as e:
            logger.warning("DB fallback quote failed for %s: %s", symbol, e)

        # If all fail, return zeros
        return {
            "symbol": symbol,
            "last_price": 0,
            "change": 0,
            "change_percent": 0,
            "bid": 0,
            "ask": 0,
            "bid_qty": 0,
            "ask_qty": 0,
            "volume": 0,
            "timestamp": datetime.utcnow(),
            "source": "none",
        }

    async def _get_latest_close_from_db(self, symbol: str) -> float:
        """Get latest close from stored candles as a fallback quote source."""
        for timeframe in ("15m", "1h", "1d"):
            result = await self.db.execute(
                select(Candle.close)
                .where(
                    and_(
                        Candle.symbol == symbol,
                        Candle.timeframe == timeframe,
                    )
                )
                .order_by(Candle.timestamp.desc())
                .limit(1)
            )
            value = result.scalar_one_or_none()
            if value is not None:
                try:
                    price = float(value)
                    if price > 0:
                        return price
                except (TypeError, ValueError):
                    pass

        return 0.0

    async def _get_live_quote_yf(self, symbol: str) -> dict:
        """Get live-ish quote from yfinance using recent intraday history last close."""
        from datetime import datetime
        import yfinance as yf

        yf_symbol = self._map_symbol_for_yf(symbol)
        ticker = yf.Ticker(yf_symbol)

        # Use a slightly wider window to avoid empty results on holidays/early hours
        hist = ticker.history(period="5d", interval="15m")
        last_price = 0.0
        if not hist.empty:
            last_close = hist["Close"].dropna()
            if not last_close.empty:
                last_price = float(last_close.iloc[-1])

        if last_price == 0:
            data = ticker.fast_info
            last_price = float(data.get("last_price") or data.get("lastPrice") or 0)

        bid = 0.0
        ask = 0.0
        bid_qty = 0
        ask_qty = 0
        volume = 0
        try:
            info = ticker.fast_info
            bid = float(info.get("bid", 0) or 0)
            ask = float(info.get("ask", 0) or 0)
            bid_qty = int(info.get("bid_size", 0) or 0)
            ask_qty = int(info.get("ask_size", 0) or 0)
            volume = int(info.get("volume", 0) or 0)
        except Exception:
            pass

        return {
            "symbol": symbol,
            "last_price": last_price,
            "change": 0,
            "change_percent": 0,
            "bid": bid,
            "ask": ask,
            "bid_qty": bid_qty,
            "ask_qty": ask_qty,
            "volume": volume,
            "timestamp": datetime.utcnow(),
            "source": "yfinance",
        }

    async def get_nifty50_list(self) -> list[dict]:
        """Get NIFTY 50 stock list with basic info."""
        # Fast path: batch quote via Zerodha when configured (single network call).
        if self.zerodha.enabled:
            try:
                data = self.zerodha.get_quote(self.NIFTY50_SYMBOLS)
                return [
                    {
                        "symbol": sym,
                        "name": sym.replace(".NS", ""),
                        "last_price": payload.get("last_price", 0),
                        "change": payload.get("net_change", 0),
                        "change_percent": payload.get("change_percent", 0),
                    }
                    for sym, payload in data.items()
                    if payload
                ]
            except Exception as e:  # noqa: BLE001
                print(f"Error fetching NIFTY50 quotes from Zerodha: {e}")

        # Fallback: single yfinance multi-ticker download (avoids 50 serial calls).
        try:
            df = yf.download(
                tickers=" ".join(self.NIFTY50_SYMBOLS),
                period="1d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                group_by="ticker",
            )
            stocks: list[dict] = []
            for sym in self.NIFTY50_SYMBOLS:
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        row = df[sym].iloc[-1]
                        close = float(row["Close"])
                        open_px = float(row["Open"])
                    else:
                        row = df.iloc[-1]
                        close = float(row["Close"])
                        open_px = float(row["Open"])

                    # Skip symbols with missing/invalid prices to avoid NaN/inf in JSON
                    if not (math.isfinite(close) and math.isfinite(open_px) and open_px != 0):
                        continue

                    change = close - open_px
                    change_pct = (change / open_px) * 100
                    stocks.append(
                        {
                            "symbol": sym,
                            "name": sym.replace(".NS", ""),
                            "last_price": close,
                            "change": change,
                            "change_percent": change_pct,
                        }
                    )
                except Exception:
                    continue
            return stocks
        except Exception as e:  # noqa: BLE001
            print(f"Error fetching NIFTY50 quotes from yfinance: {e}")
            return []

    async def ingest_historical_data(
        self, symbol: str, timeframe: str, days: int = 365
    ) -> int:
        """Ingest historical data for a symbol."""
        to_date = datetime.utcnow()
        from_date = to_date - timedelta(days=days)

        request = HistoricalDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
        )

        candles = await self._fetch_from_yfinance(
            request.symbol, request.timeframe, request.from_date, request.to_date
        )

        return len(candles)
