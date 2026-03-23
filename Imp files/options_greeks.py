"""
Options Greeks Optimizer
=======================

Black-Scholes pricing and Greeks calculation for options hedging strategies.

Author: TradeCraft Phase 2
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import fsolve
from scipy.stats import norm

logger = logging.getLogger(__name__)


class OptionType(Enum):
    """Option type"""
    CALL = "CALL"
    PUT = "PUT"


@dataclass
class OptionContract:
    """Option contract specification"""
    symbol: str
    strike: float
    expiry_days: int
    option_type: OptionType
    spot_price: float
    volatility: float
    risk_free_rate: float = 0.05


@dataclass
class GreeksResult:
    """Greeks calculation result"""
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


class OptionsGreeks:
    """
    Black-Scholes option pricing and Greeks calculator.
    
    Supports:
    - European Call and Put options
    - Greeks: Delta, Gamma, Theta, Vega, Rho
    - Implied Volatility calculation
    - Delta-neutral hedging
    """
    
    @staticmethod
    def black_scholes(
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        volatility: float,
        option_type: OptionType,
    ) -> GreeksResult:
        """
        Black-Scholes option pricing and Greeks.
        
        Args:
            spot: Spot price of underlying
            strike: Strike price
            time_to_expiry: Time to expiry (fraction of year)
            risk_free_rate: Risk-free interest rate (annual)
            volatility: Volatility (annual, decimal)
            option_type: CALL or PUT
            
        Returns:
            GreeksResult with price and Greeks
            
        Reference:
            https://en.wikipedia.org/wiki/Black%E2%80%93Scholes_model
        """
        
        # Validate inputs
        if spot <= 0 or strike <= 0 or time_to_expiry <= 0 or volatility <= 0:
            raise ValueError("All inputs must be positive")
        
        # Calculate d1 and d2
        d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / (
            volatility * np.sqrt(time_to_expiry)
        )
        d2 = d1 - volatility * np.sqrt(time_to_expiry)
        
        if option_type == OptionType.CALL:
            # Call option
            price = (
                spot * norm.cdf(d1)
                - strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
            )
            
            delta = norm.cdf(d1)
            
        else:  # PUT
            # Put option
            price = (
                strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2)
                - spot * norm.cdf(-d1)
            )
            
            delta = norm.cdf(d1) - 1
        
        # Greeks (common to both call and put for gamma, vega, rho)
        gamma = norm.pdf(d1) / (spot * volatility * np.sqrt(time_to_expiry))
        
        vega = spot * norm.pdf(d1) * np.sqrt(time_to_expiry) / 100  # Per 1% change in vol
        
        if option_type == OptionType.CALL:
            theta = (
                -spot * norm.pdf(d1) * volatility / (2 * np.sqrt(time_to_expiry))
                - risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
            ) / 365  # Per day
            
            rho = strike * time_to_expiry * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2) / 100
        else:  # PUT
            theta = (
                -spot * norm.pdf(d1) * volatility / (2 * np.sqrt(time_to_expiry))
                + risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2)
            ) / 365  # Per day
            
            rho = -strike * time_to_expiry * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) / 100
        
        return GreeksResult(
            price=float(price),
            delta=float(delta),
            gamma=float(gamma),
            theta=float(theta),
            vega=float(vega),
            rho=float(rho),
        )
    
    @staticmethod
    def implied_volatility(
        market_price: float,
        spot: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        option_type: OptionType,
        initial_guess: float = 0.2,
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson method.
        
        Args:
            market_price: Market price of option
            spot: Spot price
            strike: Strike price
            time_to_expiry: Time to expiry (fraction of year)
            risk_free_rate: Risk-free rate
            option_type: CALL or PUT
            initial_guess: Initial volatility guess (default 0.2 = 20%)
            
        Returns:
            Implied volatility (annual, decimal)
        """
        
        def objective(vol):
            """Objective function: BS price - market price"""
            try:
                greeks = OptionsGreeks.black_scholes(
                    spot, strike, time_to_expiry, risk_free_rate, vol, option_type
                )
                return greeks.price - market_price
            except:
                return float('inf')
        
        def vega_fn(vol):
            """Vega for Newton-Raphson"""
            try:
                greeks = OptionsGreeks.black_scholes(
                    spot, strike, time_to_expiry, risk_free_rate, vol, option_type
                )
                return greeks.vega
            except:
                return 0.01
        
        # Solve using fsolve (wrapper around root finding)
        try:
            result = fsolve(objective, initial_guess, xtol=1e-6)
            iv = result[0]
            
            # Validate
            if iv > 0 and iv < 5.0:  # Reasonable bounds
                return float(iv)
            else:
                logger.warning(f"Implied volatility out of bounds: {iv}")
                return initial_guess
        except Exception as e:
            logger.warning(f"IV calculation failed: {e}")
            return initial_guess
    
    @staticmethod
    def delta_hedge_ratio(
        portfolio_delta: float,
        hedge_delta: float,
    ) -> float:
        """
        Calculate delta-neutral hedge ratio.
        
        Args:
            portfolio_delta: Current portfolio delta
            hedge_delta: Delta of hedge instrument (e.g., -0.5 for OTM put)
            
        Returns:
            Hedge quantity (negative = short, positive = long)
        """
        if hedge_delta == 0:
            return 0.0
        
        return -portfolio_delta / hedge_delta
    
    @staticmethod
    def bull_call_spread(
        spot: float,
        long_strike: float,
        short_strike: float,
        expiry_days: int,
        volatility: float,
        risk_free_rate: float = 0.05,
    ) -> Dict:
        """
        Bull Call Spread: Long ATM Call + Short OTM Call
        
        Strategy for moderately bullish outlook.
        Reduces cost by selling OTM call.
        """
        time_to_expiry = expiry_days / 365
        
        # Long call (lower strike, ATM)
        long_call = OptionsGreeks.black_scholes(
            spot, long_strike, time_to_expiry, risk_free_rate, volatility, OptionType.CALL
        )
        
        # Short call (higher strike, OTM)
        short_call = OptionsGreeks.black_scholes(
            spot, short_strike, time_to_expiry, risk_free_rate, volatility, OptionType.CALL
        )
        
        net_cost = long_call.price - short_call.price
        max_profit = (short_strike - long_strike) - net_cost
        max_loss = net_cost
        
        return {
            'strategy': 'Bull Call Spread',
            'long_strike': long_strike,
            'short_strike': short_strike,
            'net_cost': float(net_cost),
            'max_profit': float(max_profit),
            'max_loss': float(max_loss),
            'breakeven': float(long_strike + net_cost),
            'net_delta': float(long_call.delta - short_call.delta),
            'net_theta': float(long_call.theta - short_call.theta),
            'net_vega': float(long_call.vega - short_call.vega),
        }
    
    @staticmethod
    def bear_put_spread(
        spot: float,
        short_strike: float,
        long_strike: float,
        expiry_days: int,
        volatility: float,
        risk_free_rate: float = 0.05,
    ) -> Dict:
        """
        Bear Put Spread: Short OTM Put + Long ATM Put
        
        Strategy for moderately bearish outlook.
        Generates credit, limits downside.
        """
        time_to_expiry = expiry_days / 365
        
        # Short put (higher strike, OTM)
        short_put = OptionsGreeks.black_scholes(
            spot, short_strike, time_to_expiry, risk_free_rate, volatility, OptionType.PUT
        )
        
        # Long put (lower strike, ATM)
        long_put = OptionsGreeks.black_scholes(
            spot, long_strike, time_to_expiry, risk_free_rate, volatility, OptionType.PUT
        )
        
        net_credit = short_put.price - long_put.price
        max_profit = net_credit
        max_loss = (short_strike - long_strike) - net_credit
        
        return {
            'strategy': 'Bear Put Spread',
            'short_strike': short_strike,
            'long_strike': long_strike,
            'net_credit': float(net_credit),
            'max_profit': float(max_profit),
            'max_loss': float(max_loss),
            'breakeven': float(short_strike - net_credit),
            'net_delta': float(-short_put.delta + long_put.delta),
            'net_theta': float(-short_put.theta + long_put.theta),
            'net_vega': float(-short_put.vega + long_put.vega),
        }
    
    @staticmethod
    def iron_condor(
        spot: float,
        put_strike_short: float,
        put_strike_long: float,
        call_strike_short: float,
        call_strike_long: float,
        expiry_days: int,
        volatility: float,
        risk_free_rate: float = 0.05,
    ) -> Dict:
        """
        Iron Condor: Bull Put Spread + Bear Call Spread
        
        Strategy for low-volatility outlook.
        Profits from time decay if price stays between strikes.
        """
        time_to_expiry = expiry_days / 365
        
        # Bull Put Spread (lower)
        short_put = OptionsGreeks.black_scholes(
            spot, put_strike_short, time_to_expiry, risk_free_rate, volatility, OptionType.PUT
        )
        long_put = OptionsGreeks.black_scholes(
            spot, put_strike_long, time_to_expiry, risk_free_rate, volatility, OptionType.PUT
        )
        
        # Bear Call Spread (upper)
        short_call = OptionsGreeks.black_scholes(
            spot, call_strike_short, time_to_expiry, risk_free_rate, volatility, OptionType.CALL
        )
        long_call = OptionsGreeks.black_scholes(
            spot, call_strike_long, time_to_expiry, risk_free_rate, volatility, OptionType.CALL
        )
        
        net_credit = (short_put.price - long_put.price) + (short_call.price - long_call.price)
        max_width = min(put_strike_short - put_strike_long, call_strike_long - call_strike_short)
        max_loss = max_width - net_credit
        
        return {
            'strategy': 'Iron Condor',
            'put_short_strike': put_strike_short,
            'put_long_strike': put_strike_long,
            'call_short_strike': call_strike_short,
            'call_long_strike': call_strike_long,
            'net_credit': float(net_credit),
            'max_profit': float(net_credit),
            'max_loss': float(max_loss),
            'breakeven_lower': float(put_strike_short - net_credit),
            'breakeven_upper': float(call_strike_short + net_credit),
            'net_delta': float(
                -short_put.delta + long_put.delta - short_call.delta + long_call.delta
            ),
            'net_theta': float(
                -short_put.theta + long_put.theta - short_call.theta + long_call.theta
            ),
            'net_vega': float(
                -short_put.vega + long_put.vega - short_call.vega + long_call.vega
            ),
        }
    
    @staticmethod
    def long_straddle(
        spot: float,
        strike: float,
        expiry_days: int,
        volatility: float,
        risk_free_rate: float = 0.05,
    ) -> Dict:
        """
        Long Straddle: Long Call + Long Put (both ATM)
        
        Strategy for high-volatility outlook.
        Profits from large moves in either direction.
        """
        time_to_expiry = expiry_days / 365
        
        call = OptionsGreeks.black_scholes(
            spot, strike, time_to_expiry, risk_free_rate, volatility, OptionType.CALL
        )
        
        put = OptionsGreeks.black_scholes(
            spot, strike, time_to_expiry, risk_free_rate, volatility, OptionType.PUT
        )
        
        net_cost = call.price + put.price
        
        return {
            'strategy': 'Long Straddle',
            'strike': strike,
            'net_cost': float(net_cost),
            'breakeven_lower': float(strike - net_cost),
            'breakeven_upper': float(strike + net_cost),
            'net_delta': float(call.delta + put.delta),
            'net_gamma': float(call.gamma + put.gamma) * 100,  # Positive gamma
            'net_vega': float(call.vega + put.vega) * 100,  # Positive vega
            'net_theta': float(call.theta + put.theta),  # Negative theta
        }
