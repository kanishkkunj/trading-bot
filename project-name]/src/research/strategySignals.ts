import axios from 'axios';
import { StrategySignals } from '../types';

interface CandleLike {
    close: number;
    high: number;
    low: number;
    volume: number;
    timestamp: string;
}

interface IntradayPayload {
    candles?: Array<{ close?: number; high?: number; low?: number; volume?: number; timestamp?: string }>;
    indicators?: {
        ema9?: number;
        ema21?: number;
        ma20?: number;
        rsi?: number;
    };
    livePrice?: number;
}

interface CachedSignals {
    signals: StrategySignals;
    cachedAt: number;
}

const CACHE_TTL_MS = 5 * 60 * 1000;
const signalsCache = new Map<string, CachedSignals>();

function getBackendCandidates(): string[] {
    const envBase = process.env.BACKEND_BASE_URL?.trim();
    const candidates = [
        envBase,
        'http://localhost:8000',
        'http://host.docker.internal:8000',
        'http://backend:8000',
    ].filter((v): v is string => Boolean(v));

    return Array.from(new Set(candidates));
}

function sma(values: number[], period: number): number {
    if (values.length < period || period <= 0) return values[values.length - 1] ?? 0;
    const slice = values.slice(-period);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
}

function std(values: number[]): number {
    if (!values.length) return 0;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / values.length;
    return Math.sqrt(variance);
}

function toDecision(score: number): { bias: 'BUY' | 'SELL' | 'HOLD'; confidenceBoost: number } {
    if (score >= 0.25) {
        return { bias: 'BUY', confidenceBoost: 1 };
    }
    if (score <= -0.25) {
        return { bias: 'SELL', confidenceBoost: 1 };
    }
    return { bias: 'HOLD', confidenceBoost: 0 };
}

async function fetchDailyCandles(symbol: string): Promise<CandleLike[] | null> {
    const candidates = getBackendCandidates();

    for (const base of candidates) {
        try {
            const url = `${base}/api/v1/market/historical/${encodeURIComponent(symbol)}?timeframe=1d&days=500`;
            const resp = await axios.get(url, { timeout: 12000 });
            const candles = Array.isArray(resp.data?.candles) ? resp.data.candles : [];
            if (!candles.length) continue;

            const normalized = candles
                .map((c: any) => ({
                    close: Number(c.close),
                    high: Number(c.high),
                    low: Number(c.low),
                    volume: Number(c.volume ?? 0),
                    timestamp: String(c.timestamp ?? c.time ?? ''),
                }))
                .filter((c: CandleLike) => Number.isFinite(c.close) && c.close > 0)
                .sort((a: CandleLike, b: CandleLike) => a.timestamp.localeCompare(b.timestamp));

            if (normalized.length >= 220) return normalized;
        } catch {
            // Try next backend candidate.
        }
    }

    return null;
}

function computeSignals(symbol: string, candles: CandleLike[]): StrategySignals {
    const closes = candles.map((c) => c.close);
    const highs = candles.map((c) => c.high);
    const lows = candles.map((c) => c.low);
    const volumes = candles.map((c) => c.volume);

    const last = closes[closes.length - 1] ?? 0;
    const sma20 = sma(closes, 20);
    const sma50 = sma(closes, 50);
    const sma200 = sma(closes, 200);

    // Trend-following composite
    const trendRaw =
        (last > sma50 ? 0.5 : -0.5) +
        (sma50 > sma200 ? 0.4 : -0.4) +
        (sma20 > sma50 ? 0.3 : -0.3);
    const trendScore = Number((trendRaw / 1.2).toFixed(3));
    const trendDecision = toDecision(trendScore);

    // Mean-reversion composite
    const lookback = closes.slice(-20);
    const mean20 = sma20;
    const std20 = std(lookback);
    const z = std20 > 0 ? (last - mean20) / std20 : 0;
    const upperBand = mean20 + 2 * std20;
    const lowerBand = mean20 - 2 * std20;
    const mrRaw = Math.max(-1, Math.min(1, -z / 2));
    const meanReversionScore = Number(mrRaw.toFixed(3));
    const meanReversionDecision = toDecision(meanReversionScore);

    // Support/Resistance proximity
    const support20 = Math.min(...lows.slice(-20));
    const resistance20 = Math.max(...highs.slice(-20));
    const distSupport = last > 0 ? (last - support20) / last : 0;
    const distResistance = last > 0 ? (resistance20 - last) / last : 0;
    let srScore = 0;
    if (distSupport <= 0.01) srScore += 0.5;
    if (distResistance <= 0.01) srScore -= 0.5;
    const srDecision = toDecision(srScore);

    // Regime suggestion
    const ret20 = closes.length > 21 ? (last / closes[closes.length - 21] - 1) : 0;
    const vol20 = std(
        closes.slice(-21).slice(1).map((c, i) => {
            const prev = closes[closes.length - 21 + i] ?? c;
            return prev > 0 ? c / prev - 1 : 0;
        })
    );
    const regime = vol20 > 0.03 ? 'high_volatility' : (Math.abs(ret20) > 0.03 ? 'trending' : 'range_bound');

    let strategyMode: 'trend_following' | 'mean_reversion' | 'hybrid' = 'hybrid';
    if (regime === 'trending') strategyMode = 'trend_following';
    if (regime === 'range_bound') strategyMode = 'mean_reversion';

    const aggregateScore = Number(((trendScore * 0.5) + (meanReversionScore * 0.2) + (srScore * 0.3)).toFixed(3));
    const aggregate = toDecision(aggregateScore);

    return {
        symbol,
        timestamp: new Date().toISOString(),
        strategyMode,
        regime,
        trendFollowing: {
            score: trendScore,
            bias: trendDecision.bias,
            sma20,
            sma50,
            sma200,
        },
        meanReversion: {
            score: meanReversionScore,
            bias: meanReversionDecision.bias,
            zScore: Number(z.toFixed(3)),
            upperBand: Number(upperBand.toFixed(2)),
            lowerBand: Number(lowerBand.toFixed(2)),
        },
        supportResistance: {
            score: Number(srScore.toFixed(3)),
            bias: srDecision.bias,
            support20: Number(support20.toFixed(2)),
            resistance20: Number(resistance20.toFixed(2)),
            distanceToSupport: Number(distSupport.toFixed(4)),
            distanceToResistance: Number(distResistance.toFixed(4)),
        },
        volumeContext: {
            avgVolume20: Number(sma(volumes, 20).toFixed(2)),
            lastVolume: Number((volumes[volumes.length - 1] ?? 0).toFixed(2)),
        },
        aggregate: {
            score: aggregateScore,
            bias: aggregate.bias,
            confidenceBoost: aggregate.confidenceBoost,
        },
    };
}

export async function getStrategySignals(symbol: string): Promise<StrategySignals | null> {
    const key = symbol.toUpperCase();
    const now = Date.now();

    const cached = signalsCache.get(key);
    if (cached && now - cached.cachedAt < CACHE_TTL_MS) {
        return cached.signals;
    }

    const candles = await fetchDailyCandles(key);
    if (!candles || candles.length < 220) {
        return null;
    }

    const signals = computeSignals(key, candles);
    signalsCache.set(key, { signals, cachedAt: now });
    return signals;
}

export function deriveStrategySignalsFromPayload(symbol: string, payload: IntradayPayload): StrategySignals | null {
    const candles = Array.isArray(payload.candles) ? payload.candles : [];
    if (candles.length < 10) return null;

    const normalized: CandleLike[] = candles
        .map((c, idx) => ({
            close: Number(c.close),
            high: Number(c.high ?? c.close),
            low: Number(c.low ?? c.close),
            volume: Number(c.volume ?? 0),
            timestamp: String(c.timestamp ?? idx),
        }))
        .filter((c) => Number.isFinite(c.close) && c.close > 0);

    if (normalized.length < 10) return null;

    const closes = normalized.map((c) => c.close);
    const highs = normalized.map((c) => c.high);
    const lows = normalized.map((c) => c.low);
    const volumes = normalized.map((c) => c.volume);

    const last = Number(payload.livePrice ?? closes[closes.length - 1] ?? 0);
    const ema9 = Number(payload.indicators?.ema9 ?? sma(closes, 9));
    const ema21 = Number(payload.indicators?.ema21 ?? sma(closes, 21));
    const ma20 = Number(payload.indicators?.ma20 ?? sma(closes, 20));
    const rsi = Number(payload.indicators?.rsi ?? 50);

    const trendRaw = (last > ema21 ? 0.6 : -0.6) + (ema9 > ema21 ? 0.4 : -0.4);
    const trendScore = Number((trendRaw / 1.0).toFixed(3));
    const trendDecision = toDecision(trendScore);

    const std20 = std(closes);
    const z = std20 > 0 ? (last - ma20) / std20 : 0;
    const upperBand = ma20 + 2 * std20;
    const lowerBand = ma20 - 2 * std20;
    const mrRaw = Number(((-z / 2) + ((50 - rsi) / 50) * 0.4).toFixed(3));
    const meanReversionScore = Math.max(-1, Math.min(1, mrRaw));
    const meanReversionDecision = toDecision(meanReversionScore);

    const support20 = Math.min(...lows);
    const resistance20 = Math.max(...highs);
    const distSupport = last > 0 ? (last - support20) / last : 0;
    const distResistance = last > 0 ? (resistance20 - last) / last : 0;
    let srScore = 0;
    if (distSupport <= 0.01) srScore += 0.5;
    if (distResistance <= 0.01) srScore -= 0.5;
    const srDecision = toDecision(srScore);

    const regime: 'trending' | 'range_bound' | 'high_volatility' = std20 > (last * 0.02) ? 'high_volatility' : (Math.abs(ema9 - ema21) > (last * 0.003) ? 'trending' : 'range_bound');
    const strategyMode: 'trend_following' | 'mean_reversion' | 'hybrid' = regime === 'trending' ? 'trend_following' : (regime === 'range_bound' ? 'mean_reversion' : 'hybrid');

    const aggregateScore = Number(((trendScore * 0.5) + (meanReversionScore * 0.2) + (srScore * 0.3)).toFixed(3));
    const aggregate = toDecision(aggregateScore);

    return {
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
        strategyMode,
        regime,
        trendFollowing: {
            score: trendScore,
            bias: trendDecision.bias,
            sma20: ma20,
            sma50: ema21,
            sma200: ema21,
        },
        meanReversion: {
            score: meanReversionScore,
            bias: meanReversionDecision.bias,
            zScore: Number(z.toFixed(3)),
            upperBand: Number(upperBand.toFixed(2)),
            lowerBand: Number(lowerBand.toFixed(2)),
        },
        supportResistance: {
            score: Number(srScore.toFixed(3)),
            bias: srDecision.bias,
            support20: Number(support20.toFixed(2)),
            resistance20: Number(resistance20.toFixed(2)),
            distanceToSupport: Number(distSupport.toFixed(4)),
            distanceToResistance: Number(distResistance.toFixed(4)),
        },
        volumeContext: {
            avgVolume20: Number(sma(volumes, Math.max(1, volumes.length)).toFixed(2)),
            lastVolume: Number((volumes[volumes.length - 1] ?? 0).toFixed(2)),
        },
        aggregate: {
            score: aggregateScore,
            bias: aggregate.bias,
            confidenceBoost: aggregate.confidenceBoost,
        },
    };
}
