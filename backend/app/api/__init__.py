"""API route handlers."""

# Import routers for side-effect registration in app.main
from app.api import admin, market, orders, portfolio, signals, strategy, backtest, risk, paper
from app.api import settings, bot, mirofish
