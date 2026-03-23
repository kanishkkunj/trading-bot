
from __future__ import annotations
import sys
from pathlib import Path
# Ensure backend/app is in sys.path for module resolution
BACKEND_APP = Path(__file__).resolve().parent.parent
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))
sys.path.append(str(BACKEND_APP))
from app.api.ws import broadcast_ws_message
"""Paper trading execution powered by ML ensemble."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
import structlog
import yfinance as yf
from sqlalchemy import select

from app.engine.features import FeatureEngine
from app.institutional import (
    FundHoldingsTracker,
    FiiDiiTracker,
    InsiderTracker,
    SmartMoneyConfluence,
    SmartMoneyContext,
)
from app.models.signal import SignalAction, SignalStatus
from app.schemas.signal import SignalCreate
from app.schemas.order import OrderCreate
from app.models.order import OrderStatus
from app.services.signal_service import SignalService
from app.services.order_service import OrderService
from app.services.market_service import MarketService
from app.services.memory_service import MemoryService
from app.config import get_settings
from app.models.strategy import StrategyConfig
from app.ml.regime_detector import RegimeDetector

log = structlog.get_logger()


class PaperTradeService:
    """Run ML inference, emit signals, and place paper orders."""

    def __init__(
        self,
        db,
        tickers: Optional[list[str]] = None,
        flows_tracker: Optional[FiiDiiTracker] = None,
        insider_tracker: Optional[InsiderTracker] = None,
        fund_holdings: Optional[FundHoldingsTracker] = None,
        smart_money: Optional[SmartMoneyConfluence] = None,
    ):
        self.db = db
        self.signal_service = SignalService(db)
        self.order_service = OrderService(db)
        # Use DhanPaperTradeProvider for paper trading
        try:
            from app.data.provider_nse import DhanPaperTradeProvider
            self.paper_provider = DhanPaperTradeProvider()
        except Exception as e:
            self.paper_provider = None
        self.market_service = MarketService(db)
        self.memory_service = MemoryService()
        self.feature_engine = FeatureEngine()
        self.smart_money = smart_money or SmartMoneyConfluence()
        self.flows_tracker = flows_tracker
        self.insider_tracker = insider_tracker
        self.fund_holdings = fund_holdings
        self.tickers = tickers or MarketService.NIFTY50_SYMBOLS
        self.artifact_path = Path(__file__).resolve().parents[1] / "engine" / "artifacts" / "xgb_nifty50_ensemble.bin"
        self.history_days = 400
        self.settings = get_settings()
        self.regime_detector = RegimeDetector()
        # Log Zerodha API credentials status
        try:
            zc = self.market_service.zerodha
            log.info("zerodha_client_status", enabled=zc.enabled, api_key=zc.api_key, access_token=zc.access_token)
        except Exception as e:
            log.error("zerodha_client_init_error", error=str(e))

    async def run(self, user_id: str, top_k: int = 5) -> list[dict]:
        """Run ensemble inference and place top paper trades."""
        if not self.artifact_path.exists():
            raise FileNotFoundError(f"Model artifact missing: {self.artifact_path}")

        payload = joblib.load(self.artifact_path)
        model_long = payload.get("long")
        model_short = payload.get("short")
        weights = payload.get("weights", {"long": 0.5, "short": 0.5})
        ensemble_thr = payload.get("decision_threshold", 0.5)

        feature_cols = model_long.feature_names_ if model_long else []
        runtime_params = await self._load_runtime_params()
        strategy_mode = str(runtime_params.get("strategy_mode", "hybrid")).lower()
        use_regime_filter = bool(runtime_params.get("use_regime_filter", True))
        trend_boost = float(runtime_params.get("trend_bias_boost", 0.03))
        mr_boost = float(runtime_params.get("mean_reversion_bias_boost", 0.02))
        regime_floor = float(runtime_params.get("regime_confidence_floor", 0.55))
        results: list[dict] = []

        # Preload recall bias per symbol (fail-soft if Cognee disabled)
        recall_cache: dict[str, float] = {}
        if self.memory_service.enabled:
            for symbol in self.tickers:
                bias = await self._recall_bias(symbol)
                if bias is not None:
                    recall_cache[symbol] = bias

        for symbol in self.tickers:
            try:
                latest_row, latest_close, regime_input = await asyncio.get_event_loop().run_in_executor(
                    None, self._prepare_features, symbol, feature_cols
                )
                if latest_row is None:
                    log.info("skip_symbol_no_features", symbol=symbol)
                    continue

                live_quote = await self.market_service.get_live_quote(symbol)
                if not live_quote:
                    log.info("skip_symbol_no_live_quote", symbol=symbol)
                    continue
                live_price = live_quote.get("last_price")
                bid = live_quote.get("bid") or 0
                ask = live_quote.get("ask") or 0
                vol = live_quote.get("volume") or 0
                if bid <= 0 or ask <= 0:
                    log.info("skip_symbol_no_bid_ask", symbol=symbol, bid=bid, ask=ask)
                    continue
                mid = (bid + ask) / 2
                spread_pct = ((ask - bid) / mid) * 100 if mid > 0 else 100
                if spread_pct > 1.0:
                    log.info("skip_symbol_spread", symbol=symbol, spread_pct=spread_pct)
                    continue
                if vol < 10_000:
                    log.info("skip_symbol_low_volume", symbol=symbol, volume=vol)
                    continue

                use_price = float(live_price) if live_price else float(latest_close)
                if use_price <= 0:
                    log.info("skip_symbol_invalid_price", symbol=symbol, use_price=use_price)
                    continue

                proba_long = float(model_long.predict_proba(latest_row)[:, 1][0]) if model_long else 0.0
                proba_short = float(model_short.predict_proba(latest_row)[:, 1][0]) if model_short else 0.0
                proba = weights.get("long", 0.5) * proba_long + weights.get("short", 0.5) * proba_short

                sm_ctx: Optional[SmartMoneyContext] = None
                if self.smart_money:
                    try:
                        sm_ctx = self.smart_money.evaluate(
                            symbol,
                            flows=self.flows_tracker,
                            insiders=self.insider_tracker,
                            holdings=self.fund_holdings,
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning("smart_money_eval_failed", symbol=symbol, error=str(exc))

                if sm_ctx and sm_ctx.pledge_risk == "high":
                    continue

                action = SignalAction.HOLD
                confidence = proba
                min_conf = max(ensemble_thr, 0.55)  # prefer higher conviction trades
                regime_block = False
                prefer_trend = False

                regime_snapshot = None
                if use_regime_filter and regime_input:
                    try:
                        regime_snapshot = self.regime_detector.detect(**regime_input)
                        overrides = self.regime_detector.strategy_overrides(regime_snapshot)
                        if regime_snapshot.confidence < regime_floor:
                            regime_block = True
                        if "trend_following" in overrides.get("preferred_models", []):
                            prefer_trend = True
                        if (
                            strategy_mode == "mean_reversion"
                            and "mean_reversion" in overrides.get("disable", [])
                        ):
                            regime_block = True
                    except Exception as exc:  # noqa: BLE001
                        log.warning("regime_overlay_failed", symbol=symbol, error=str(exc))

                if proba >= min_conf:
                    action = SignalAction.BUY
                    confidence = proba
                elif proba <= (1 - min_conf):
                    action = SignalAction.SELL
                    confidence = 1 - proba

                if prefer_trend:
                    confidence = min(1.0, confidence + trend_boost)

                if strategy_mode == "mean_reversion":
                    confidence = min(1.0, confidence + mr_boost)

                if regime_block:
                    action = SignalAction.HOLD

                # Soft overlay: adjust confidence using smart-money bias
                if sm_ctx:
                    confidence = self._adjust_confidence(confidence, sm_ctx.combined)
                    if sm_ctx.combined in {"avoid_or_short", "promoter_distribution"}:
                        action = SignalAction.HOLD

                results.append(
                    {
                        "symbol": symbol,
                        "proba": proba,
                        "proba_long": proba_long,
                        "proba_short": proba_short,
                        "action": action,
                        "confidence": confidence,
                        "price": use_price,
                        "smart_money": sm_ctx,
                        "regime": getattr(regime_snapshot, "trend", None),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("paper_trade_inference_failed", symbol=symbol, error=str(exc))
                continue

        actionable = [r for r in results if r["action"] != SignalAction.HOLD]

        # Apply recall bias: boost symbols with recent positive decisions, penalize negatives
        for row in actionable:
            recall = recall_cache.get(row["symbol"], 0.0)
            row["confidence"] = max(0.0, min(1.0, row["confidence"] + recall))

        actionable.sort(key=lambda x: x["confidence"], reverse=True)
        actionable = actionable[:top_k]

        executed: list[dict] = []

        for row in actionable:
            size = self._position_size(row["price"])
            sm_ctx = row.get("smart_money")
            if sm_ctx and sm_ctx.crowded:
                size = max(1, int(size * 0.5))
            if size <= 0:
                continue

            features_tag = "ensemble_prob"
            if sm_ctx:
                features_tag = f"ensemble_prob;sm={sm_ctx.combined};crowded={sm_ctx.crowded}"
            regime_tag = row.get("regime")
            if regime_tag:
                features_tag = f"{features_tag};regime={regime_tag}"

            signal = await self.signal_service.create_signal(
                SignalCreate(
                    symbol=row["symbol"],
                    action=row["action"],
                    confidence=row["confidence"],
                    suggested_quantity=size,
                    suggested_price=row["price"],
                    model_version="nifty50-ensemble",
                    features_used=features_tag,
                    valid_until=datetime.utcnow() + timedelta(minutes=30),
                )
            )

            order = await self.order_service.create_order(
                user_id,
                OrderCreate(
                    symbol=row["symbol"],
                    side=row["action"].value,
                    order_type="MARKET",
                    quantity=size,
                    signal_id=signal.id,
                ),
            )

            if self.memory_service.enabled:
                features_payload = self._features_payload(feature_cols, latest_row)
                await self.memory_service.log_signal_context(
                    symbol=row["symbol"],
                    signal=row["action"].value,
                    features=features_payload,
                    decision=row["action"].value,
                    strategy_id="nifty50-ensemble",
                )

            await self.signal_service.update_signal_status(
                signal.id,
                SignalStatus.EXECUTED if order.status == OrderStatus.FILLED else SignalStatus.PENDING,
                order_id=order.id,
                reason=order.status_message,
            )

            # --- Emit real-time updates to WebSocket clients ---
            # Compute P&L for the emitted position (unrealized only, as this is a new trade)
            avg_price = row["price"]
            last_price = row["price"]
            pnl = (last_price - avg_price) * size if size > 0 else 0
            await broadcast_ws_message({
                "type": "position",
                "payload": {
                    "symbol": row["symbol"],
                    "qty": size,
                    "avgPrice": avg_price,
                    "pnl": pnl
                }
            })
            await broadcast_ws_message({
                "type": "quote",
                "payload": {
                    "symbol": row["symbol"],
                    "bid": row["price"] - 0.5,
                    "ask": row["price"] + 0.5,
                    "last": row["price"],
                    "ts": int(datetime.utcnow().timestamp() * 1000)
                }
            })
            # Emit running total P&L (sum of all open positions' unrealized P&L)
            from app.services.portfolio_service import PortfolioService
            portfolio_service = PortfolioService(self.db)
            positions = await portfolio_service.get_positions(user_id, only_open=True)
            total_unrealized_pnl = sum(getattr(p, "unrealized_pnl", 0) for p in positions)
            await broadcast_ws_message({
                "type": "pnl",
                "payload": {
                    "ts": int(datetime.utcnow().timestamp() * 1000),
                    "value": float(total_unrealized_pnl)
                }
            })
            # Add more event types as needed (risk, confidence, regime, etc.)

            executed.append(
                {
                    "symbol": row["symbol"],
                    "action": row["action"].value,
                    "probability": round(row["proba"], 4),
                    "price": row["price"],
                    "order_id": order.id,
                    "signal_id": signal.id,
                    "order_status": order.status.value,
                    "smart_money": getattr(sm_ctx, "combined", None),
                }
            )

        return executed

    async def _load_runtime_params(self) -> dict[str, Any]:
        """Load active strategy parameters (if present) to control live behavior."""
        try:
            result = await self.db.execute(
                select(StrategyConfig).where(StrategyConfig.is_active.is_(True))
            )
            active = result.scalar_one_or_none()
            return dict(active.parameters or {}) if active else {}
        except Exception:  # noqa: BLE001
            return {}

    def _prepare_features(self, symbol: str, feature_cols: list[str]):
        """Fetch latest history, compute features, and scale using recent stats."""
        df = yf.download(
            symbol,
            period=f"{self.history_days}d",
            interval="1d",
            auto_adjust=False,
            progress=False,
        )
        if df.empty:
            return None, None

        df.columns = [col[0].lower() if isinstance(col, tuple) else str(col).lower() for col in df.columns]
        df = df.reset_index()
        df.columns = [str(col).lower() for col in df.columns]
        df = df.rename(
            columns={
                "index": "date",  # yfinance leaves DatetimeIndex name in index column
                "datetime": "date",
                "date": "date",
                "adj close": "adj_close",
            }
        )
        df["ticker"] = symbol
        df = df.sort_values("date").reset_index(drop=True)

        feats = self.feature_engine.compute_features(df)
        if feats.empty:
            return None, None

        scale_cols = [c for c in feature_cols if c not in {"date", "ticker", "target", "dow", "month"}]
        hist = feats.iloc[:-1]
        latest = feats.iloc[-1:].copy()
        if hist.empty:
            return None, None

        means = hist[scale_cols].mean()
        stds = hist[scale_cols].std().replace(0, 1.0)
        latest[scale_cols] = (latest[scale_cols] - means) / stds

        latest = latest.reindex(columns=feature_cols, fill_value=0.0)
        latest = latest.fillna(0.0)

        latest_close = float(df.iloc[-1]["close"])

        recent = feats.tail(60)
        returns = recent.get("log_return", pd.Series(dtype=float)).replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
        if returns.size < 10:
            returns = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

        spread_bps = 10.0
        if "vwap" in recent.columns and "close" in recent.columns:
            spread_bps = float(
                ((recent["close"] - recent["vwap"]).abs() / recent["close"].replace(0, np.nan)).mean() * 10_000
            )
            if np.isnan(spread_bps):
                spread_bps = 10.0

        regime_input = {
            "features": {
                "volatility_pct": float(recent["close_pct_change"].std() * 100.0) if "close_pct_change" in recent else 0.0,
                "trend_strength": float(recent.get("trend_strength_20", pd.Series([0.0])).iloc[-1]) if not recent.empty else 0.0,
            },
            "returns": returns,
            "corr_mean": 0.5,
            "corr_spike": False,
            "spread_bps": float(max(1.0, spread_bps)),
            "depth_score": 0.6,
            "macro_flags": None,
        }
        return latest, latest_close, regime_input

    def _position_size(self, price: float) -> int:
        """Size positions to stay within 5% capital per trade; skip if price too high."""
        if price <= 0:
            return 0
        capital = float(getattr(self.settings, "PAPER_INITIAL_CAPITAL", 500.0) or 500.0)
        target_value = capital * 0.05
        qty = int(target_value / price)
        return max(0, min(qty, 200))

    async def _recall_bias(self, symbol: str) -> Optional[float]:
        """Compute a small confidence bias from recent Cognee signal memories."""
        try:
            memories = await self.memory_service.client.search_memories(scope="signal", tags=[symbol], limit=20)
            if not memories:
                return 0.0
            buys = sum(1 for m in memories if str(m.get("payload", {}).get("decision", "")).upper() == "BUY")
            sells = sum(1 for m in memories if str(m.get("payload", {}).get("decision", "")).upper() == "SELL")
            # Bias is small to avoid overpowering the model: +/- 2% per net signal, capped at 6%
            bias = max(-0.06, min(0.06, (buys - sells) * 0.02))
            return bias
        except Exception:  # noqa: BLE001
            return 0.0

    def _features_payload(self, feature_cols: list[str], latest_row) -> dict:
        """Serialize latest feature row for logging."""
        try:
            record = latest_row.iloc[0].to_dict()
            payload = {k: float(record.get(k, 0.0)) for k in feature_cols}
            return payload
        except Exception:  # noqa: BLE001
            return {}

    def _adjust_confidence(self, confidence: float, bias: str) -> float:
        """Nudge confidence based on smart-money confluence."""
        boost = {"strong_buy_signal", "fii_buy_dii_sell", "promoter_accumulation", "broad_accumulation"}
        drag = {"avoid_or_short", "promoter_distribution", "neutral"}
        if bias in boost:
            confidence = min(1.0, confidence + 0.05)
        elif bias in drag:
            confidence = max(0.0, confidence - 0.05 if bias != "neutral" else confidence)
        return confidence
