import axios from 'axios';
import { KnowledgeBaseEntry } from '../types';

interface CandleLike {
    close: number;
    timestamp: string;
}

interface HistoricalContext {
    summary: string;
    lessons: KnowledgeBaseEntry[];
}

interface CachedContext {
    context: HistoricalContext;
    cachedAt: number;
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
const historicalCache = new Map<string, CachedContext>();

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

function maxDrawdownPct(closes: number[]): number {
    let peak = closes[0] ?? 0;
    let maxDd = 0;

    for (const c of closes) {
        if (c > peak) peak = c;
        if (peak > 0) {
            const dd = ((peak - c) / peak) * 100;
            if (dd > maxDd) maxDd = dd;
        }
    }

    return Number(maxDd.toFixed(2));
}

function stdDev(values: number[]): number {
    if (!values.length) return 0;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / values.length;
    return Math.sqrt(variance);
}

function sma(values: number[], period: number): number {
    if (values.length < period || period <= 0) return values[values.length - 1] ?? 0;
    const slice = values.slice(-period);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
}

async function fetchDailyCandles(symbol: string): Promise<CandleLike[] | null> {
    const candidates = getBackendCandidates();

    for (const base of candidates) {
        try {
            const url = `${base}/api/v1/market/historical/${encodeURIComponent(symbol)}?timeframe=1d&days=3650`;
            const resp = await axios.get(url, { timeout: 15000 });
            const candles = Array.isArray(resp.data?.candles) ? resp.data.candles : [];
            if (!candles.length) continue;

            return candles
                .map((c: any) => ({
                    close: Number(c.close),
                    timestamp: String(c.timestamp),
                }))
                .filter((c: CandleLike) => Number.isFinite(c.close) && c.close > 0)
                .sort((a: CandleLike, b: CandleLike) => a.timestamp.localeCompare(b.timestamp));
        } catch {
            // Try next backend candidate.
        }
    }

    return null;
}

function buildContext(symbol: string, candles: CandleLike[]): HistoricalContext {
    const closes = candles.map((c) => c.close);
    const first = closes[0];
    const last = closes[closes.length - 1];

    const totalReturnPct = first > 0 ? Number((((last / first) - 1) * 100).toFixed(2)) : 0;

    const returns: number[] = [];
    for (let i = 1; i < closes.length; i++) {
        const prev = closes[i - 1];
        if (prev > 0) returns.push((closes[i] / prev) - 1);
    }

    const annualizedVolPct = Number((stdDev(returns) * Math.sqrt(252) * 100).toFixed(2));
    const drawdownPct = maxDrawdownPct(closes);

    const sma50 = sma(closes, 50);
    const sma200 = sma(closes, 200);
    const regime = sma50 >= sma200 ? 'BULLISH' : 'BEARISH';

    const lookback20 = closes.length > 20 ? closes[closes.length - 21] : first;
    const momentum20Pct = lookback20 > 0 ? Number((((last / lookback20) - 1) * 100).toFixed(2)) : 0;

    const summary = [
        `10Y context (${symbol}): total return ${totalReturnPct}% with annualized volatility ${annualizedVolPct}%.`,
        `Observed max drawdown ${drawdownPct}% and current long-term regime ${regime} (SMA50 ${sma50.toFixed(2)} vs SMA200 ${sma200.toFixed(2)}).`,
        `Recent 20-session momentum: ${momentum20Pct}%. Use this as structural bias, while intraday decisions use latest 20 candles.`,
    ].join(' ');

    const lessons: KnowledgeBaseEntry[] = [
        {
            id: `hist-${symbol}-regime`,
            symbol,
            failure_cause: 'BAD_TIMING',
            outcome: 'HISTORICAL_CONTEXT',
            lesson: `Long-horizon regime is ${regime}. Avoid aggressively fading this regime unless intraday reversal evidence is strong.`,
            similarity_score: 1,
        },
        {
            id: `hist-${symbol}-risk`,
            symbol,
            failure_cause: 'BAD_EXECUTION',
            outcome: 'HISTORICAL_CONTEXT',
            lesson: `10Y max drawdown is ${drawdownPct}%. Keep risk tight during volatility clusters and avoid oversized positions after sharp expansions.`,
            similarity_score: 1,
        },
        {
            id: `hist-${symbol}-momentum`,
            symbol,
            failure_cause: 'BAD_PREDICTION',
            outcome: 'HISTORICAL_CONTEXT',
            lesson: `20-session momentum is ${momentum20Pct}%. Align entries with both intraday signal and this medium-term drift when confidence is marginal.`,
            similarity_score: 1,
        },
    ];

    return { summary, lessons };
}

export async function getHistoricalContext(symbol: string): Promise<HistoricalContext | null> {
    const key = symbol.toUpperCase();
    const now = Date.now();

    const cached = historicalCache.get(key);
    if (cached && now - cached.cachedAt < CACHE_TTL_MS) {
        return cached.context;
    }

    const candles = await fetchDailyCandles(key);
    if (!candles || candles.length < 200) {
        return null;
    }

    const context = buildContext(key, candles);
    historicalCache.set(key, { context, cachedAt: now });
    return context;
}
