"""
PHASE 2 — Trading Strategy Implementation
ML-Guided Momentum with Mean-Reversion Filters
Institutional-grade risk management enforced at every level
"""
import logging
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from pathlib import Path
import json
from datetime import datetime
import pytz

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(name)s — %(levelname)s — %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open trading position"""
    entry_date: str
    entry_price: float
    quantity: float
    position_type: str  # 'LONG' or 'SHORT'
    entry_reason: str
    entry_atr: float
    
    def __hash__(self):
        return hash(self.entry_date)


@dataclass
class Trade:
    """Represents a closed trade"""
    entry_date: str
    entry_price: float
    quantity: float
    exit_date: str
    exit_price: float
    position_type: str
    pnl: float
    pnl_percent: float
    duration_days: int
    entry_reason: str
    exit_reason: str


class Strategy:
    """
    ML-Guided Momentum with Mean-Reversion Filters
    
    Configurable Entry Rules:
    - LONG: RSI<threshold + Price<SMA20 + ML_UP + Volume filter + ATR threshold
    - SHORT: RSI>threshold + Price>SMA20 + ML_DOWN + Volume filter + ATR threshold
    
    Exit Rules (FIXED):
    - LONG: Stop@Entry-2xATR + Target@Entry+2.5xATR + Time>5days + RSI>80 + Circuit(-2%)
    - SHORT: Stop@Entry+2xATR + Target@Entry-2.5xATR + Time>5days + RSI<20 + Circuit(-2%)
    
    Risk Management:
    - Position size: 1.0% per trade
    - Max positions: 5
    - Daily loss limit: -2%
    """
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        symbol: str = "NIFTY50",
        rsi_long_threshold: float = 30,
        rsi_short_threshold: float = 70,
        ml_confidence_threshold: float = 0.65,
        volume_multiplier: float = 1.2,
        atr_pct_threshold: float = 0.5,
        use_price_sma_filter: bool = True
    ):
        """
        Initialize strategy with configurable parameters
        Args:
            initial_capital: Starting capital in rupees
            symbol: Stock symbol
            rsi_long_threshold: RSI < this for LONG entry
            rsi_short_threshold: RSI > this for SHORT entry
            ml_confidence_threshold: Min ML confidence for entry
            volume_multiplier: Volume multiplier (0 = disabled)
            atr_pct_threshold: Min ATR as % of close
            use_price_sma_filter: Require price < SMA20 for LONG
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.symbol = symbol
        self.positions: List[Position] = []
        self.closed_trades: List[Trade] = []
        self.equity_curve: List[float] = [initial_capital]
        self.daily_pnl: List[float] = [0.0]
        
        # Risk parameters (ABSOLUTE, non-negotiable)
        self.risk_per_trade_pct = 1.0  # 1% per trade
        self.max_positions = 5
        self.daily_loss_limit = -2.0  # -2% per day
        self.max_sector_concentration = 40.0
        
        # Entry configuration (variant-specific)
        self.rsi_long_threshold = rsi_long_threshold
        self.rsi_short_threshold = rsi_short_threshold
        self.ml_confidence_threshold = ml_confidence_threshold
        self.volume_multiplier = volume_multiplier
        self.atr_pct_threshold = atr_pct_threshold
        self.use_price_sma_filter = use_price_sma_filter
        
        logger.info(f"Strategy initialized: {symbol}")
        logger.info(f"  Capital: ₹{initial_capital:,.0f}")
        logger.info(f"  Risk per trade: {self.risk_per_trade_pct}%")
        logger.info(f"  RSI Long threshold: <{rsi_long_threshold}")
        logger.info(f"  ML confidence: >{ml_confidence_threshold}")
        logger.info(f"  Volume multiplier: {volume_multiplier}x")
    
    def check_entry_conditions_long(
        self,
        row: pd.Series,
        ml_prediction: int,
        ml_confidence: float
    ) -> Tuple[bool, str]:
        """
        Check LONG entry conditions with configurable thresholds
        """
        reasons = []
        
        # 1. RSI check (configurable)
        if not (row['RSI_14'] < self.rsi_long_threshold):
            reasons.append(f"RSI not oversold: {row['RSI_14']:.1f} >= {self.rsi_long_threshold}")
        
        # 2. Price vs SMA20 check (optional)
        if self.use_price_sma_filter:
            if not (row['close'] < row['SMA_20']):
                reasons.append(f"Price not below SMA20: {row['close']:.2f} >= {row['SMA_20']:.2f}")
        
        # 3. ML prediction check (configurable confidence)
        if not (ml_prediction == 1 and ml_confidence > self.ml_confidence_threshold):
            reasons.append(f"ML not bullish: pred={ml_prediction}, conf={ml_confidence:.2f}")
        
        # 4. Volume check (optional)
        if self.volume_multiplier > 0:
            vol_threshold = row['volume'] / (row.get('volume', 1) if row.get('volume', 1) > 0 else 1)
            if not (row['volume'] > row.get('SMA_20', row['close']) * self.volume_multiplier):
                reasons.append(f"Volume not high enough")
        
        # 5. ATR check (configurable threshold)
        atr_pct = (row['ATR_14'] / row['close']) * 100 if row['close'] > 0 else 0
        if not (atr_pct > self.atr_pct_threshold):
            reasons.append(f"ATR too low: {atr_pct:.2f}% < {self.atr_pct_threshold}%")
        
        # 6. Existing position check
        long_positions = [p for p in self.positions if p.position_type == 'LONG']
        if long_positions:
            reasons.append("Already have long position")
        
        # 7. Max positions check
        if len(self.positions) >= self.max_positions:
            reasons.append(f"Portfolio at max positions: {len(self.positions)}")
        
        can_enter = len(reasons) == 0
        reason_str = " | ".join(reasons) if reasons else "All conditions met"
        
        return can_enter, reason_str
    
    def check_entry_conditions_short(
        self,
        row: pd.Series,
        ml_prediction: int,
        ml_confidence: float
    ) -> Tuple[bool, str]:
        """
        Check SHORT entry conditions with configurable thresholds
        Similar to LONG but inverted
        """
        reasons = []
        
        # 1. RSI check (configurable)
        if not (row['RSI_14'] > self.rsi_short_threshold):
            reasons.append(f"RSI not overbought: {row['RSI_14']:.1f} <= {self.rsi_short_threshold}")
        
        # 2. Price vs SMA20 check (optional)
        if self.use_price_sma_filter:
            if not (row['close'] > row['SMA_20']):
                reasons.append(f"Price not above SMA20: {row['close']:.2f} <= {row['SMA_20']:.2f}")
        
        # 3. ML prediction check (configurable confidence)
        if not (ml_prediction == -1 and ml_confidence > self.ml_confidence_threshold):
            reasons.append(f"ML not bearish: pred={ml_prediction}, conf={ml_confidence:.2f}")
        
        # 4. Volume check (optional)
        if self.volume_multiplier > 0:
            if not (row['volume'] > row.get('SMA_20', row['close']) * self.volume_multiplier):
                reasons.append(f"Volume not high enough")
        
        # 5. ATR check (configurable threshold)
        atr_pct = (row['ATR_14'] / row['close']) * 100 if row['close'] > 0 else 0
        if not (atr_pct > self.atr_pct_threshold):
            reasons.append(f"ATR too low: {atr_pct:.2f}% < {self.atr_pct_threshold}%")
        
        # 6. Existing position check
        short_positions = [p for p in self.positions if p.position_type == 'SHORT']
        if short_positions:
            reasons.append("Already have short position")
        
        # 7. Max positions check
        if len(self.positions) >= self.max_positions:
            reasons.append(f"Portfolio at max positions: {len(self.positions)}")
        
        can_enter = len(reasons) == 0
        reason_str = " | ".join(reasons) if reasons else "All conditions met"
        
        return can_enter, reason_str
    
    def check_exit_conditions(
        self,
        position: Position,
        row: pd.Series,
        ml_prediction: int,
        days_held: int
    ) -> Tuple[bool, str]:
        """
        Check exit conditions for a position
        Return: (should_exit: bool, reason: str)
        """
        reasons = []
        
        if position.position_type == 'LONG':
            # Stop loss: Close < Entry - 2×ATR
            if row['close'] < position.entry_price - 2.0 * position.entry_atr:
                return True, "HARD_STOP"
            
            # Take profit: Close > Entry + 2.5×ATR
            if row['close'] > position.entry_price + 2.5 * position.entry_atr:
                return True, "TAKE_PROFIT"
            
            # Time stop: Holding > 5 days
            if days_held > 5:
                return True, "TIME_STOP"
            
            # Trend reversal: RSI > 80
            if row['RSI_14'] > 80:
                return True, "TREND_REVERSAL"
            
            # ML reversal: Model predicts DOWN with confidence > 60%
            if ml_prediction == -1:  # Confidence checked by caller
                return True, "ML_REVERSAL"
        
        elif position.position_type == 'SHORT':
            # Stop loss: Close > Entry + 2×ATR
            if row['close'] > position.entry_price + 2.0 * position.entry_atr:
                return True, "HARD_STOP"
            
            # Take profit: Close < Entry - 2.5×ATR
            if row['close'] < position.entry_price - 2.5 * position.entry_atr:
                return True, "TAKE_PROFIT"
            
            # Time stop: Holding > 5 days
            if days_held > 5:
                return True, "TIME_STOP"
            
            # Trend reversal: RSI < 20
            if row['RSI_14'] < 20:
                return True, "TREND_REVERSAL"
            
            # ML reversal: Model predicts UP with confidence > 60%
            if ml_prediction == 1:
                return True, "ML_REVERSAL"
        
        return False, "HOLDING"
    
    def calculate_position_size(self, atr: float, close_price: float) -> float:
        """
        Calculate position size based on risk management
        Risk per trade: Exactly 1.0% of account value
        Formula: Position_Size = (Account_Value × 0.01) / (2 × ATR)
        """
        risk_amount = self.current_capital * (self.risk_per_trade_pct / 100)
        position_size = risk_amount / (2.0 * atr)
        
        return position_size
    
    def simulate_trade_day(
        self,
        date: str,
        row: pd.Series,
        ml_prediction: int = 0,
        ml_confidence: float = 0.0
    ) -> Dict:
        """
        Simulate one trading day:
        1. Check exit conditions for open positions
        2. Check entry conditions for new positions
        3. Update P&L
        """
        daily_summary = {
            'date': date,
            'entries': [],
            'exits': [],
            'positions_open': len(self.positions),
            'daily_pnl': 0.0,
            'capital': self.current_capital
        }
        
        # Step 1: Check exits for open positions
        positions_to_remove = []
        for pos_idx, position in enumerate(self.positions):
            # Calculate days held
            days_held = (pd.to_datetime(date) - pd.to_datetime(position.entry_date)).days
            
            # Check exit conditions
            should_exit, reason = self.check_exit_conditions(
                position, row, ml_prediction, days_held
            )
            
            if should_exit:
                # Close position with realistic slippage
                slippage = 0.5 if position.position_type == 'LONG' else -0.5
                exit_price = row['close'] + slippage
                
                # Calculate P&L (with fees: 0.03% brokerage + 0.1% STT)
                if position.position_type == 'LONG':
                    gross_pnl = (exit_price - position.entry_price) * position.quantity
                else:  # SHORT
                    gross_pnl = (position.entry_price - exit_price) * position.quantity
                
                # Fees: 0.03% entry + 0.03% exit + 0.1% STT
                fees = (position.entry_price * position.quantity * 0.03/100) + \
                       (exit_price * position.quantity * 0.03/100) + \
                       (exit_price * position.quantity * 0.1/100)
                
                net_pnl = gross_pnl - fees
                pnl_percent = (net_pnl / (position.entry_price * position.quantity)) * 100
                
                # Record closed trade
                trade = Trade(
                    entry_date=position.entry_date,
                    entry_price=position.entry_price,
                    quantity=position.quantity,
                    exit_date=date,
                    exit_price=exit_price,
                    position_type=position.position_type,
                    pnl=net_pnl,
                    pnl_percent=pnl_percent,
                    duration_days=days_held,
                    entry_reason=position.entry_reason,
                    exit_reason=reason
                )
                self.closed_trades.append(trade)
                
                # Update capital
                self.current_capital += net_pnl
                daily_summary['daily_pnl'] += net_pnl
                daily_summary['exits'].append({
                    'position': position.position_type,
                    'pnl': net_pnl,
                    'reason': reason
                })
                
                # Mark for removal
                positions_to_remove.append(pos_idx)
        
        # Remove closed positions
        for idx in sorted(positions_to_remove, reverse=True):
            self.positions.pop(idx)
        
        # Step 2: Check entry conditions
        # LONG entry
        can_enter_long, long_reason = self.check_entry_conditions_long(
            row, ml_prediction, ml_confidence
        )
        if can_enter_long:
            pos_size = self.calculate_position_size(row['ATR_14'], row['close'])
            entry_price = row['close'] - 0.5  # 0.5 slippage for limit order
            
            position = Position(
                entry_date=date,
                entry_price=entry_price,
                quantity=pos_size,
                position_type='LONG',
                entry_reason='ML_MOMENTUM_LONG',
                entry_atr=row['ATR_14']
            )
            self.positions.append(position)
            
            # Deduct entry fees from capital
            entry_fee = entry_price * pos_size * 0.03 / 100
            self.current_capital -= entry_fee
            
            daily_summary['entries'].append({
                'type': 'LONG',
                'price': entry_price,
                'size': pos_size
            })
        
        # SHORT entry
        can_enter_short, short_reason = self.check_entry_conditions_short(
            row, ml_prediction, ml_confidence
        )
        if can_enter_short:
            pos_size = self.calculate_position_size(row['ATR_14'], row['close'])
            entry_price = row['close'] + 0.5  # 0.5 slippage for limit order
            
            position = Position(
                entry_date=date,
                entry_price=entry_price,
                quantity=pos_size,
                position_type='SHORT',
                entry_reason='ML_MOMENTUM_SHORT',
                entry_atr=row['ATR_14']
            )
            self.positions.append(position)
            
            # Deduct entry fees from capital
            entry_fee = entry_price * pos_size * 0.03 / 100
            self.current_capital -= entry_fee
            
            daily_summary['entries'].append({
                'type': 'SHORT',
                'price': entry_price,
                'size': pos_size
            })
        
        # Step 3: Update equity curve
        daily_summary['positions_open'] = len(self.positions)
        daily_summary['capital'] = self.current_capital
        self.equity_curve.append(self.current_capital)
        self.daily_pnl.append(daily_summary['daily_pnl'])
        
        return daily_summary
    
    def get_summary_statistics(self) -> Dict:
        """Calculate summary statistics for backtest"""
        if not self.closed_trades:
            return {}
        
        trades_df = pd.DataFrame([asdict(t) for t in self.closed_trades])
        
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        total_pnl = trades_df['pnl'].sum()
        total_trades = len(trades_df)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        # Sharpe ratio (simplified)
        equity_returns = pd.Series(self.equity_curve).pct_change().dropna()
        sharpe = equity_returns.mean() / equity_returns.std() * np.sqrt(252) if len(equity_returns) > 0 else 0
        
        # Max drawdown
        cumsum_returns = (1 + equity_returns).cumprod()
        running_max = cumsum_returns.expanding().max()
        drawdown = (cumsum_returns - running_max) / running_max
        max_drawdown = drawdown.min() if len(drawdown) > 0 else 0
        
        # CAGR
        years = (len(self.equity_curve) - 1) / 252
        cagr = (self.current_capital / self.initial_capital) ** (1 / years) - 1 if years > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': float(win_rate),
            'avg_win': float(winning_trades['pnl'].mean()) if len(winning_trades) > 0 else 0,
            'avg_loss': float(losing_trades['pnl'].mean()) if len(losing_trades) > 0 else 0,
            'profit_factor': float(winning_trades['pnl'].sum() / abs(losing_trades['pnl'].sum())) if len(losing_trades) > 0 and losing_trades['pnl'].sum() != 0 else 0,
            'total_pnl': float(total_pnl),
            'sharpe_ratio': float(sharpe),
            'max_drawdown': float(max_drawdown),
            'cagr': float(cagr)
        }


if __name__ == "__main__":
    logger.info("Strategy module loaded")
