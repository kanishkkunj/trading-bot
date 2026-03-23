"""Multi-leg options strategy calculators (Bull Spread, Bear Spread, Iron Condor, Straddle).

Complements the existing OptionsPipeline (which already handles Greeks per-contract
and IV surface smoothing) by adding:
  - A self-contained Black-Scholes implementation using only math/numpy (no scipy)
  - Implied volatility via Newton-Raphson
  - Delta-neutral hedge ratio helper
  - Multi-leg strategy builders useful in the trading dashboard

All inputs use annualised, decimal-form volatility and risk-free rate.
Prices are in the same currency unit as spot/strike (e.g., INR for NSE).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


@dataclass
class GreeksResult:
    """Price and first-order Greeks for a single option."""

    price: float
    delta: float
    gamma: float
    theta: float   # per calendar day
    vega: float    # per 1% change in volatility
    rho: float     # per 1% change in risk-free rate


# ------------------------------------------------------------------ core BS math

def _ncdf(x: float) -> float:
    """Standard normal CDF via math.erf (no scipy needed)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    option_type: OptionType,
) -> GreeksResult:
    """Black-Scholes price + Greeks.

    Args:
        spot:          Underlying spot price.
        strike:        Option strike price.
        time_to_expiry: Time to expiry as fraction of year (e.g., 30/365).
        risk_free_rate: Annual risk-free rate as decimal (e.g., 0.06 for 6%).
        volatility:    Annual volatility as decimal (e.g., 0.20 for 20%).
        option_type:   OptionType.CALL or OptionType.PUT.

    Returns:
        GreeksResult with price and Greeks.
    """
    if spot <= 0 or strike <= 0 or time_to_expiry <= 0 or volatility <= 0:
        raise ValueError("spot, strike, time_to_expiry and volatility must all be > 0")

    sqrtT = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / (
        volatility * sqrtT
    )
    d2 = d1 - volatility * sqrtT
    Nd1 = _ncdf(d1)
    Nd2 = _ncdf(d2)
    pdf1 = _npdf(d1)
    discount = math.exp(-risk_free_rate * time_to_expiry)

    if option_type == OptionType.CALL:
        price = spot * Nd1 - strike * discount * Nd2
        delta = Nd1
        rho = strike * time_to_expiry * discount * Nd2 / 100.0
        theta = (
            -spot * pdf1 * volatility / (2.0 * sqrtT)
            - risk_free_rate * strike * discount * Nd2
        ) / 365.0
    else:
        price = strike * discount * (1.0 - Nd2) - spot * (1.0 - Nd1)
        delta = Nd1 - 1.0
        rho = -strike * time_to_expiry * discount * (1.0 - Nd2) / 100.0
        theta = (
            -spot * pdf1 * volatility / (2.0 * sqrtT)
            + risk_free_rate * strike * discount * (1.0 - Nd2)
        ) / 365.0

    gamma = pdf1 / (spot * volatility * sqrtT)
    vega = spot * pdf1 * sqrtT / 100.0

    return GreeksResult(
        price=float(price),
        delta=float(delta),
        gamma=float(gamma),
        theta=float(theta),
        vega=float(vega),
        rho=float(rho),
    )


# ------------------------------------------------------------------ IV solver

def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    option_type: OptionType,
    initial_guess: float = 0.20,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
) -> float:
    """Implied volatility via Newton-Raphson (no scipy).

    Returns initial_guess if convergence fails.
    """
    sigma = float(initial_guess)
    for _ in range(max_iterations):
        try:
            g = black_scholes(spot, strike, time_to_expiry, risk_free_rate, sigma, option_type)
            diff = g.price - market_price
            if abs(diff) < tolerance:
                break
            # vega is per 1% — convert back to raw (per unit)
            vega_raw = g.vega * 100.0
            if abs(vega_raw) < 1e-8:
                break
            sigma -= diff / vega_raw
            sigma = max(1e-6, min(sigma, 5.0))
        except ValueError:
            break
    return float(sigma)


# ------------------------------------------------------------------ hedge ratio

def delta_hedge_ratio(portfolio_delta: float, hedge_delta: float) -> float:
    """Return the number of hedge instruments needed for delta-neutrality.

    Result is negative for a short position and positive for a long position.
    """
    if hedge_delta == 0.0:
        return 0.0
    return -portfolio_delta / hedge_delta


# ------------------------------------------------------------------ multi-leg strategies

def bull_call_spread(
    spot: float,
    long_strike: float,
    short_strike: float,
    expiry_days: int,
    volatility: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, object]:
    """Bull Call Spread: long lower-strike call + short higher-strike call.

    Moderately bullish strategy with capped upside and limited downside.
    """
    T = expiry_days / 365.0
    long_call = black_scholes(spot, long_strike, T, risk_free_rate, volatility, OptionType.CALL)
    short_call = black_scholes(spot, short_strike, T, risk_free_rate, volatility, OptionType.CALL)
    net_cost = long_call.price - short_call.price
    return {
        "strategy": "Bull Call Spread",
        "long_strike": long_strike,
        "short_strike": short_strike,
        "net_cost": round(net_cost, 4),
        "max_profit": round((short_strike - long_strike) - net_cost, 4),
        "max_loss": round(net_cost, 4),
        "breakeven": round(long_strike + net_cost, 4),
        "net_delta": round(long_call.delta - short_call.delta, 4),
        "net_theta": round(long_call.theta - short_call.theta, 4),
        "net_vega": round(long_call.vega - short_call.vega, 4),
    }


def bear_put_spread(
    spot: float,
    short_strike: float,
    long_strike: float,
    expiry_days: int,
    volatility: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, object]:
    """Bear Put Spread: long lower-strike put + short higher-strike put.

    Moderately bearish strategy that generates a net credit.
    """
    T = expiry_days / 365.0
    short_put = black_scholes(spot, short_strike, T, risk_free_rate, volatility, OptionType.PUT)
    long_put = black_scholes(spot, long_strike, T, risk_free_rate, volatility, OptionType.PUT)
    net_credit = short_put.price - long_put.price
    return {
        "strategy": "Bear Put Spread",
        "short_strike": short_strike,
        "long_strike": long_strike,
        "net_credit": round(net_credit, 4),
        "max_profit": round(net_credit, 4),
        "max_loss": round((short_strike - long_strike) - net_credit, 4),
        "breakeven": round(short_strike - net_credit, 4),
        "net_delta": round(-short_put.delta + long_put.delta, 4),
        "net_theta": round(-short_put.theta + long_put.theta, 4),
        "net_vega": round(-short_put.vega + long_put.vega, 4),
    }


def iron_condor(
    spot: float,
    put_strike_short: float,
    put_strike_long: float,
    call_strike_short: float,
    call_strike_long: float,
    expiry_days: int,
    volatility: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, object]:
    """Iron Condor: Bull Put Spread + Bear Call Spread.

    Benefits from low volatility — profits when underlying stays between inner strikes.
    """
    T = expiry_days / 365.0
    sp = black_scholes(spot, put_strike_short, T, risk_free_rate, volatility, OptionType.PUT)
    lp = black_scholes(spot, put_strike_long, T, risk_free_rate, volatility, OptionType.PUT)
    sc = black_scholes(spot, call_strike_short, T, risk_free_rate, volatility, OptionType.CALL)
    lc = black_scholes(spot, call_strike_long, T, risk_free_rate, volatility, OptionType.CALL)

    net_credit = (sp.price - lp.price) + (sc.price - lc.price)
    max_width = min(put_strike_short - put_strike_long, call_strike_long - call_strike_short)
    return {
        "strategy": "Iron Condor",
        "put_short_strike": put_strike_short,
        "put_long_strike": put_strike_long,
        "call_short_strike": call_strike_short,
        "call_long_strike": call_strike_long,
        "net_credit": round(net_credit, 4),
        "max_profit": round(net_credit, 4),
        "max_loss": round(max_width - net_credit, 4),
        "breakeven_lower": round(put_strike_short - net_credit, 4),
        "breakeven_upper": round(call_strike_short + net_credit, 4),
        "net_delta": round(-sp.delta + lp.delta - sc.delta + lc.delta, 4),
        "net_theta": round(-sp.theta + lp.theta - sc.theta + lc.theta, 4),
        "net_vega": round(-sp.vega + lp.vega - sc.vega + lc.vega, 4),
    }


def long_straddle(
    spot: float,
    strike: float,
    expiry_days: int,
    volatility: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, object]:
    """Long Straddle: long ATM call + long ATM put.

    Benefits from large moves in either direction (long gamma/vega trade).
    """
    T = expiry_days / 365.0
    call = black_scholes(spot, strike, T, risk_free_rate, volatility, OptionType.CALL)
    put = black_scholes(spot, strike, T, risk_free_rate, volatility, OptionType.PUT)
    net_cost = call.price + put.price
    return {
        "strategy": "Long Straddle",
        "strike": strike,
        "net_cost": round(net_cost, 4),
        "breakeven_lower": round(strike - net_cost, 4),
        "breakeven_upper": round(strike + net_cost, 4),
        "net_delta": round(call.delta + put.delta, 4),
        # multiply by 100 for per-lot display (conventional for straddle reports)
        "net_gamma": round((call.gamma + put.gamma) * 100.0, 4),
        "net_vega": round((call.vega + put.vega) * 100.0, 4),
        "net_theta": round(call.theta + put.theta, 4),
    }


def long_strangle(
    spot: float,
    put_strike: float,
    call_strike: float,
    expiry_days: int,
    volatility: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, object]:
    """Long Strangle: long OTM put + long OTM call.

    Lower premium than straddle; requires larger move to profit.
    """
    T = expiry_days / 365.0
    put = black_scholes(spot, put_strike, T, risk_free_rate, volatility, OptionType.PUT)
    call = black_scholes(spot, call_strike, T, risk_free_rate, volatility, OptionType.CALL)
    net_cost = put.price + call.price
    return {
        "strategy": "Long Strangle",
        "put_strike": put_strike,
        "call_strike": call_strike,
        "net_cost": round(net_cost, 4),
        "breakeven_lower": round(put_strike - net_cost, 4),
        "breakeven_upper": round(call_strike + net_cost, 4),
        "net_delta": round(call.delta + put.delta, 4),
        "net_gamma": round((call.gamma + put.gamma) * 100.0, 4),
        "net_vega": round((call.vega + put.vega) * 100.0, 4),
        "net_theta": round(call.theta + put.theta, 4),
    }


def naked_call(
    spot: float,
    strike: float,
    expiry_days: int,
    volatility: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, object]:
    """Long naked call analytics (directional bullish)."""
    T = expiry_days / 365.0
    call = black_scholes(spot, strike, T, risk_free_rate, volatility, OptionType.CALL)
    return {
        "strategy": "Long Naked Call",
        "strike": strike,
        "premium": round(call.price, 4),
        "breakeven": round(strike + call.price, 4),
        "max_loss": round(call.price, 4),
        "max_profit": "unlimited",
        "delta": round(call.delta, 4),
        "gamma": round(call.gamma, 6),
        "vega": round(call.vega, 4),
        "theta": round(call.theta, 4),
    }


def naked_put(
    spot: float,
    strike: float,
    expiry_days: int,
    volatility: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, object]:
    """Long naked put analytics (directional bearish)."""
    T = expiry_days / 365.0
    put = black_scholes(spot, strike, T, risk_free_rate, volatility, OptionType.PUT)
    return {
        "strategy": "Long Naked Put",
        "strike": strike,
        "premium": round(put.price, 4),
        "breakeven": round(strike - put.price, 4),
        "max_loss": round(put.price, 4),
        "max_profit": round(strike - put.price, 4),
        "delta": round(put.delta, 4),
        "gamma": round(put.gamma, 6),
        "vega": round(put.vega, 4),
        "theta": round(put.theta, 4),
    }
