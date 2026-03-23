"""FastAPI application entry point."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, market, orders, portfolio, signals, strategy, backtest, risk, paper
from app.api import ws as ws_router
from app.api import settings, bot, mirofish
from app.config import get_settings

logger = structlog.get_logger()


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    app_settings = get_settings()

    app = FastAPI(
        title="TradeCraft API",
        description="Algorithmic Trading Platform for Indian Markets",
        version="0.1.0",
        docs_url="/docs" if app_settings.is_development else None,
        redoc_url="/redoc" if app_settings.is_development else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
    app.include_router(market.router, prefix="/api/v1/market", tags=["Market Data"])
    app.include_router(orders.router, prefix="/api/v1/orders", tags=["Orders"])
    app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
    app.include_router(signals.router, prefix="/api/v1/signals", tags=["Signals"])
    app.include_router(strategy.router, prefix="/api/v1/strategy", tags=["Strategy"])
    app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["Backtest"])
    app.include_router(risk.router, prefix="/api/v1/risk", tags=["Risk Management"])
    app.include_router(paper.router, prefix="/api/v1/paper", tags=["Paper Trading"])
    app.include_router(settings.router, prefix="/api/v1/settings", tags=["Settings"])
    app.include_router(bot.router, prefix="/api/v1/bot", tags=["Bot Control"])
    app.include_router(mirofish.router, prefix="/api/v1/mirofish", tags=["MiroFish Bridge"])
    app.include_router(ws_router.router)

    return app


app = create_application()


@app.on_event("startup")
async def startup_event() -> None:
    """Handle application startup."""
    logger.info("TradeCraft API starting up", version="0.1.0")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Handle application shutdown."""
    logger.info("TradeCraft API shutting down")
