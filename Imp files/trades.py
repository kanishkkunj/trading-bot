"""
Trades endpoints for paper trading
"""
from fastapi import APIRouter, status, Depends, HTTPException
from typing import List, Dict
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from app.schemas import (
    TradeCreate, TradeResponse, PortfolioResponse,
    PositionResponse, OrderResponse
)
from app.utils import logger, get_current_user
from app.database import get_db
from app.models import User, Trade, Candle
from app.services import PaperBroker, PositionManager

router = APIRouter(prefix="/trades", tags=["trades"])

# Global paper broker instance (in production, use per-user instances)
paper_brokers: Dict[str, PaperBroker] = {}

def get_user_broker(user_id: str) -> PaperBroker:
    """Get or create broker for user"""
    if user_id not in paper_brokers:
        paper_brokers[user_id] = PaperBroker()
    return paper_brokers[user_id]

def get_current_prices(db: Session, symbols: List[str]) -> Dict[str, float]:
    """Get latest prices for symbols"""
    prices = {}
    for symbol in symbols:
        latest = db.query(Candle).filter(
            Candle.symbol == symbol
        ).order_by(Candle.time.desc()).first()
        if latest:
            prices[symbol] = latest.close
    return prices

@router.post("/place-order", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    trade: TradeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Place a new trade order
    
    - **symbol**: Stock symbol (e.g., NIFTY)
    - **quantity**: Number of shares (1-100)
    - **side**: BUY or SELL
    - **order_type**: market or limit
    - **limit_price**: Price for limit orders (optional)
    """
    logger.info(f"Order: {trade.side} {trade.quantity} {trade.symbol}")
    
    try:
        broker = get_user_broker(str(current_user.id))
        
        # Get current price
        latest_candle = db.query(Candle).filter(
            Candle.symbol == trade.symbol
        ).order_by(Candle.time.desc()).first()
        
        if not latest_candle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No market data for {trade.symbol}"
            )
        
        current_price = latest_candle.close
        
        # Place order
        result = broker.place_order(
            symbol=trade.symbol,
            quantity=trade.quantity,
            side=trade.side,
            order_type=trade.order_type,
            limit_price=trade.limit_price
        )
        
        # Auto-execute market orders
        if trade.order_type == "market":
            order_id = result['order_id']
            broker.execute_order(order_id, current_price)
        
        return OrderResponse(
            order_id=result['order_id'],
            symbol=trade.symbol,
            quantity=trade.quantity,
            side=trade.side,
            status=result['status'],
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Order placement failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order placement failed"
        )

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get portfolio summary and performance metrics"""
    broker = get_user_broker(str(current_user.id))
    
    # Get current prices
    symbols = [pos.symbol for pos in broker.positions.values()]
    current_prices = get_current_prices(db, symbols)
    
    # If no symbols, add default prices
    if not current_prices:
        default_candle = db.query(Candle).order_by(Candle.time.desc()).first()
        if default_candle:
            current_prices[default_candle.symbol] = default_candle.close
    
    portfolio = broker.get_portfolio_value(current_prices)
    
    return PortfolioResponse(**portfolio)

@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active positions"""
    broker = get_user_broker(str(current_user.id))
    
    # Get current prices
    symbols = [pos.symbol for pos in broker.positions.values()]
    current_prices = get_current_prices(db, symbols)
    
    positions = broker.get_positions(current_prices)
    
    return [PositionResponse(**pos) for pos in positions]

@router.post("/positions/{symbol}/close")
async def close_position(
    symbol: str,
    exit_price: float,
    quantity: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Close an open position"""
    try:
        broker = get_user_broker(str(current_user.id))
        broker.close_position(symbol, exit_price, quantity)
        
        return {
            "message": "Position closed successfully",
            "symbol": symbol,
            "exit_price": exit_price,
        }
    except Exception as e:
        logger.error(f"Failed to close position: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/trades", response_model=List[TradeResponse])
async def list_trades(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List recent trades for current user"""
    # Get trades from database
    trades = db.query(Trade).filter(
        Trade.user_id == current_user.id
    ).order_by(Trade.created_at.desc()).limit(limit).all()
    
    return trades

@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific trade"""
    trade = db.query(Trade).filter(
        Trade.id == trade_id,
        Trade.user_id == current_user.id
    ).first()
    
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found"
        )
    
    return trade

@router.get("/stats")
async def get_trading_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get trading statistics"""
    broker = get_user_broker(str(current_user.id))
    
    return {
        "total_trades": broker.total_trades,
        "winning_trades": broker.winning_trades,
        "losing_trades": broker.total_trades - broker.winning_trades,
        "win_rate": (broker.winning_trades / broker.total_trades * 100) if broker.total_trades > 0 else 0,
        "realized_pnl": broker.realized_pnl,
        "total_capital": broker.initial_capital,
    }

@router.post("/reset")
async def reset_portfolio(current_user: User = Depends(get_current_user)):
    """Reset trading session"""
    broker = get_user_broker(str(current_user.id))
    broker.reset()
    
    return {
        "message": "Portfolio reset successfully",
        "capital": broker.initial_capital,
    }

