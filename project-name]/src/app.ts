import path from 'path';
import dotenv from 'dotenv';
import axios from 'axios';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

import express, { Request, Response } from 'express';
import { Trader } from './trader/trader';
import { DecisionLogger } from './logger/decisionLogger';
import { riskManager } from './risk/riskManager';
import { initAutoSquareOff, closeAllPositions } from './squareOff/autoSquareOff';
import { dhanClient } from './dhan/dhanClient';
import { MarketDataPayload, ClaudeTradeDecision, LogEntry, ResearchBrief, TradeRecord } from './types';
import { ResearchOrchestrator } from './research/researchOrchestrator';
import { getHistoricalContext } from './research/historicalContext';
import { deriveStrategySignalsFromPayload, getStrategySignals } from './research/strategySignals';
import { db } from './db/database';
import { performanceTracker } from './compound/performanceTracker';
import { postMortemAgent } from './compound/postMortemAgent';
import { knowledgeBase } from './compound/knowledgeBase';
import { startNightlyConsolidation, runNightlyConsolidation } from './compound/nightlyConsolidation';

const app = express();
const PORT = Number(process.env.PORT ?? 3000);

app.use(express.json());

const decisionLogger = new DecisionLogger();
const trader = new Trader(riskManager, decisionLogger, dhanClient);
const researchOrchestrator = new ResearchOrchestrator();

initAutoSquareOff();
startNightlyConsolidation();

/**
 * Cache for research briefs: Map<symbol, { brief: ResearchBrief, cachedAt: number }>
 * Expires after 10 minutes (600000 ms)
 */
const researchCache = new Map<string, { brief: ResearchBrief; cachedAt: number }>();
const RESEARCH_CACHE_TTL = 10 * 60 * 1000; // 10 minutes
const signalStore: Array<Record<string, unknown>> = [];

type AdvisoryMetricKey = 'run' | 'latest' | 'refresh';

type AdvisoryMetricBucket = {
    requests: number;
    success: number;
    degraded: number;
    errors: number;
    totalLatencyMs: number;
    lastStatus: string;
    lastError: string | null;
    lastUpdatedAt: string | null;
};

const advisoryMetrics: Record<AdvisoryMetricKey, AdvisoryMetricBucket> = {
    run: {
        requests: 0,
        success: 0,
        degraded: 0,
        errors: 0,
        totalLatencyMs: 0,
        lastStatus: 'init',
        lastError: null,
        lastUpdatedAt: null,
    },
    latest: {
        requests: 0,
        success: 0,
        degraded: 0,
        errors: 0,
        totalLatencyMs: 0,
        lastStatus: 'init',
        lastError: null,
        lastUpdatedAt: null,
    },
    refresh: {
        requests: 0,
        success: 0,
        degraded: 0,
        errors: 0,
        totalLatencyMs: 0,
        lastStatus: 'init',
        lastError: null,
        lastUpdatedAt: null,
    },
};

function isAdvisoryDegradedStatus(status: string | undefined): boolean {
    return ['degraded', 'timeout', 'disabled', 'not_found', 'error'].includes(String(status ?? '').toLowerCase());
}

function recordAdvisoryMetric(
    key: AdvisoryMetricKey,
    options: { status: string; degraded: boolean; latencyMs: number; error?: string },
): void {
    const bucket = advisoryMetrics[key];
    bucket.requests += 1;
    bucket.totalLatencyMs += Math.max(0, options.latencyMs);
    bucket.lastStatus = options.status;
    bucket.lastUpdatedAt = new Date().toISOString();

    if (options.error) {
        bucket.errors += 1;
        bucket.lastError = options.error;
        return;
    }

    bucket.lastError = null;
    if (options.degraded) {
        bucket.degraded += 1;
    } else {
        bucket.success += 1;
    }
}

function getSimulationIdForSymbol(symbol: string, fallback?: string, requestMap?: Record<string, string>): string | undefined {
    const upper = symbol.toUpperCase();
    if (requestMap?.[upper]) {
        return requestMap[upper];
    }

    const rawMap = process.env.MIROFISH_SYMBOL_SIMULATION_MAP;
    if (rawMap) {
        try {
            const parsed = JSON.parse(rawMap) as Record<string, string>;
            if (parsed && typeof parsed === 'object') {
                const entries = Object.entries(parsed).map(([k, v]) => [String(k).toUpperCase(), String(v)] as const);
                const normalizedMap = Object.fromEntries(entries);
                if (normalizedMap[upper]) {
                    return normalizedMap[upper];
                }
            }
        } catch {
            // Ignore invalid env mapping and continue with default fallback.
        }
    }

    return fallback ?? process.env.MIROFISH_SIMULATION_ID;
}

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

async function proxyBackend(
    method: 'GET' | 'POST',
    backendPath: string,
    payload?: unknown,
    params?: Record<string, unknown>,
): Promise<unknown> {
    const candidates = getBackendCandidates();
    let lastError: Error | null = null;

    for (const base of candidates) {
        try {
            const url = `${base}${backendPath}`;
            const resp = await axios.request({
                method,
                url,
                data: payload,
                params,
                timeout: 30000,
            });
            return resp.data;
        } catch (error) {
            lastError = error as Error;
        }
    }

    throw lastError ?? new Error('No reachable backend candidate');
}

/**
 * Safely parse a value that may already be an object or may be a JSON string.
 */
function parseMaybeJson<T>(value: unknown): T | undefined {
    if (!value) return undefined;
    if (typeof value === 'object') return value as T;
    if (typeof value !== 'string') return undefined;
    try {
        return JSON.parse(value) as T;
    } catch {
        return undefined;
    }
}

/**
 * Validate and normalize incoming research brief data.
 */
function normalizeResearchBrief(value: unknown): ResearchBrief | undefined {
    const parsed = parseMaybeJson<Partial<ResearchBrief>>(value);
    if (!parsed || typeof parsed !== 'object') return undefined;
    if (!parsed.overallSentiment || typeof parsed.sentimentScore !== 'number') return undefined;

    return {
        symbol: String(parsed.symbol ?? ''),
        timestamp: String(parsed.timestamp ?? new Date().toISOString()),
        overallSentiment: parsed.overallSentiment,
        sentimentScore: Number(parsed.sentimentScore ?? 0),
        confidence: Number(parsed.confidence ?? 0),
        bullishSignals: Number(parsed.bullishSignals ?? 0),
        bearishSignals: Number(parsed.bearishSignals ?? 0),
        neutralSignals: Number(parsed.neutralSignals ?? 0),
        topHeadlines: Array.isArray(parsed.topHeadlines) ? parsed.topHeadlines.map(String) : [],
        redditConsensus: (parsed.redditConsensus as ResearchBrief['redditConsensus']) ?? 'NEUTRAL',
        nseAnnouncementFlag: Boolean(parsed.nseAnnouncementFlag),
        sources: {
            newsCount: Number(parsed.sources?.newsCount ?? 0),
            redditCount: Number(parsed.sources?.redditCount ?? 0),
            nseCount: Number(parsed.sources?.nseCount ?? 0),
        },
        summary: String(parsed.summary ?? 'No research summary provided.'),
    };
}

app.post('/api/trade', async (req: Request, res: Response) => {
    try {
        const body = req.body ?? {};
        const marketData = parseMaybeJson<MarketDataPayload>(body.marketData ?? body.payload);
        const rawDecision = parseMaybeJson<Partial<ClaudeTradeDecision>>(body.decision);

        if (!marketData || !rawDecision) {
            return res.status(400).json({ error: 'marketData (or payload) and decision are required' });
        }

        const decision: ClaudeTradeDecision = {
            action: rawDecision.action ?? 'HOLD',
            symbol: rawDecision.symbol ?? marketData.symbol,
            entry_price: Number(rawDecision.entry_price ?? 0),
            target_price: Number(rawDecision.target_price ?? 0),
            stop_loss: Number(rawDecision.stop_loss ?? 0),
            quantity: Number(rawDecision.quantity ?? 0),
            confidence: Number(rawDecision.confidence ?? 0),
            reason: (rawDecision as any).reason ?? (rawDecision as any).reasoning ?? '',
        };

        // Run sentiment research before trading
        const symbol = decision.symbol.toUpperCase();
        const now = Date.now();

        // Check cache first
        let researchBrief = normalizeResearchBrief(body.researchBrief);

        if (!researchBrief) {
            const cached = researchCache.get(symbol);
            if (cached && now - cached.cachedAt < RESEARCH_CACHE_TTL) {
                // eslint-disable-next-line no-console
                console.log(`[TRADE] Using cached research for ${symbol}`);
                researchBrief = cached.brief;
            } else {
                // eslint-disable-next-line no-console
                console.log(`[TRADE] Running sentiment research for ${symbol}`);
                researchBrief = await researchOrchestrator.runResearch(symbol);
                researchCache.set(symbol, { brief: researchBrief, cachedAt: now });
            }
        }

        // Pass research brief to trading signal processor
        const execution = await trader.processTradingSignal(marketData, decision, researchBrief);
        return res.status(200).json(execution);
    } catch (error) {
        // eslint-disable-next-line no-console
        console.error('[SERVER] /api/trade failed', error);
        const message = error instanceof Error ? error.message : 'Internal server error';
        return res.status(500).json({ error: message });
    }
});

app.post('/api/square-off', async (_req: Request, res: Response) => {
    try {
        const closedPositions = await closeAllPositions();
        return res.status(200).json({ success: true, closedPositions });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Square-off failed';
        return res.status(500).json({ error: message });
    }
});

app.post('/api/risk/check', (req: Request, res: Response) => {
    try {
        const { action, entry_price, stop_loss: _stop_loss, quantity } = req.body ?? {};

        if (!action || entry_price === undefined || quantity === undefined) {
            return res.status(400).json({ error: 'action, entry_price, and quantity are required' });
        }

        const canTrade = riskManager.canTrade(action, Number(entry_price), Number(quantity));
        const response = canTrade
            ? { can_trade: true }
            : { can_trade: false, rejection_reason: 'Risk manager rejection' };

        return res.status(200).json(response);
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Risk check failed';
        return res.status(500).json({ error: message });
    }
});

/**
 * Persist signal payloads received from workflow orchestration.
 */
app.post('/api/signals', (req: Request, res: Response) => {
    try {
        const payload = req.body ?? {};
        if (!payload.symbol || !payload.action) {
            return res.status(400).json({ error: 'symbol and action are required' });
        }

        const normalizedSignal = {
            id: `${Date.now()}-${signalStore.length + 1}`,
            createdAt: new Date().toISOString(),
            ...payload,
        };

        signalStore.push(normalizedSignal);
        return res.status(200).json({ success: true, signal: normalizedSignal });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Signal creation failed';
        return res.status(500).json({ error: message });
    }
});

app.post('/api/decisions/log', async (req: Request, res: Response) => {
    try {
        const body = req.body ?? {};
        const entry: LogEntry = {
            timestamp: String(body.timestamp ?? new Date().toISOString()),
            symbol: String(body.symbol ?? ''),
            action: (body.action ?? 'HOLD') as LogEntry['action'],
            confidence: Number(body.confidence ?? 0),
            entry_price: Number(body.entry_price ?? 0),
            target_price: Number(body.target_price ?? 0),
            stop_loss: Number(body.stop_loss ?? 0),
            quantity: Number(body.quantity ?? 0),
            reason: String(body.reason ?? body.reasoning ?? ''),
            executed: Boolean(body.executed),
            executionRejectedReason: body.executionRejectedReason
                ? String(body.executionRejectedReason)
                : undefined,
        };

        if (!entry.symbol) {
            return res.status(400).json({ error: 'symbol is required' });
        }

        await decisionLogger.log(entry);
        return res.status(200).json({ success: true });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to log decision';
        return res.status(500).json({ error: message });
    }
});

/**
 * Manually trigger nightly consolidation from orchestration workflows (e.g., n8n).
 * This path returns a summary payload and does not send Telegram directly,
 * allowing workflow nodes to control messaging.
 */
app.post('/api/nightly-consolidation', async (_req: Request, res: Response) => {
    try {
        const result = await runNightlyConsolidation({ sendTelegram: false });
        return res.status(200).json({
            success: true,
            telegramSummary: result.summary,
            processedLosses: result.processedLosses,
            totalTrades: result.totalTrades,
            startedAt: result.startedAt,
            completedAt: result.completedAt,
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Nightly consolidation failed';
        return res.status(500).json({ error: message });
    }
});

/**
 * Research endpoint: Scrape news and Reddit sentiment, analyze on-demand
 * Caches results for 10 minutes per symbol
 */
app.post('/api/research', async (req: Request, res: Response) => {
    const requestedSymbol =
        typeof req.body?.symbol === 'string' && req.body.symbol.trim().length > 0
            ? req.body.symbol.toUpperCase()
            : 'NIFTY';

    try {
        const { symbol } = req.body ?? {};

        if (!symbol || typeof symbol !== 'string') {
            return res.status(400).json({ error: 'symbol is required' });
        }

        const symbolUpper = symbol.toUpperCase();
        const now = Date.now();

        // Check cache
        const cached = researchCache.get(symbolUpper);
        if (cached && now - cached.cachedAt < RESEARCH_CACHE_TTL) {
            // eslint-disable-next-line no-console
            console.log(`[RESEARCH] Cache hit for ${symbolUpper}`);

            if (!cached.brief.strategySignals) {
                let strategySignals = deriveStrategySignalsFromPayload(symbolUpper, req.body ?? {});
                if (!strategySignals) {
                    strategySignals = await getStrategySignals(symbolUpper);
                }

                if (strategySignals) {
                    cached.brief.strategySignals = strategySignals;
                    cached.brief.summary = `${cached.brief.summary} Strategy mode=${strategySignals.strategyMode}, regime=${strategySignals.regime}, aggregateBias=${strategySignals.aggregate.bias}, aggregateScore=${strategySignals.aggregate.score}.`.trim();
                    cached.brief.pastLessons = [
                        {
                            id: `strat-${symbolUpper}-${Date.now()}`,
                            symbol: symbolUpper,
                            failure_cause: 'BAD_TIMING' as const,
                            outcome: 'STRATEGY_CONTEXT',
                            lesson: `Strategy overlay suggests ${strategySignals.aggregate.bias} bias (${strategySignals.strategyMode}, regime=${strategySignals.regime}, score=${strategySignals.aggregate.score}). Respect this unless intraday signal is materially stronger.`,
                            similarity_score: 1,
                        },
                        ...(cached.brief.pastLessons ?? []),
                    ].slice(0, 8);
                }
            }

            return res.status(200).json(cached.brief);
        }

        // Run research
        const brief = await researchOrchestrator.runResearch(symbolUpper);

        // Attach a compact long-horizon context derived from the 10Y dataset.
        // This keeps workflow payloads unchanged while giving Claude structural bias.
        const historicalContext = await getHistoricalContext(symbolUpper);
        if (historicalContext) {
            brief.summary = `${brief.summary} ${historicalContext.summary}`.trim();
            brief.pastLessons = [...historicalContext.lessons, ...(brief.pastLessons ?? [])].slice(0, 8);
        }

        // Attach explicit strategy overlays (trend-following / mean-reversion / S/R)
        // so n8n can use them directly without changing endpoint contracts.
        let strategySignals = deriveStrategySignalsFromPayload(symbolUpper, req.body ?? {});
        if (!strategySignals) {
            strategySignals = await getStrategySignals(symbolUpper);
        }
        if (strategySignals) {
            brief.strategySignals = strategySignals;
            brief.summary = `${brief.summary} Strategy mode=${strategySignals.strategyMode}, regime=${strategySignals.regime}, aggregateBias=${strategySignals.aggregate.bias}, aggregateScore=${strategySignals.aggregate.score}.`.trim();

            const strategyLesson = {
                id: `strat-${symbolUpper}-${Date.now()}`,
                symbol: symbolUpper,
                failure_cause: 'BAD_TIMING' as const,
                outcome: 'STRATEGY_CONTEXT',
                lesson: `Strategy overlay suggests ${strategySignals.aggregate.bias} bias (${strategySignals.strategyMode}, regime=${strategySignals.regime}, score=${strategySignals.aggregate.score}). Respect this unless intraday signal is materially stronger.`,
                similarity_score: 1,
            };

            brief.pastLessons = [strategyLesson, ...(brief.pastLessons ?? [])].slice(0, 8);
        }

        // Cache the result
        researchCache.set(symbolUpper, { brief, cachedAt: now });

        return res.status(200).json(brief);
    } catch (error) {
        // eslint-disable-next-line no-console
        console.error('[SERVER] /api/research failed', error);

        // Never block workflow execution on research failures.
        return res.status(200).json({
            symbol: requestedSymbol,
            timestamp: new Date().toISOString(),
            overallSentiment: 'NEUTRAL',
            sentimentScore: 0,
            confidence: 0,
            bullishSignals: 0,
            bearishSignals: 0,
            neutralSignals: 0,
            topHeadlines: [],
            redditConsensus: 'NEUTRAL',
            nseAnnouncementFlag: false,
            sources: {
                newsCount: 0,
                redditCount: 0,
                nseCount: 0,
            },
            summary: 'Research temporarily unavailable. Proceeding with technical-only context.',
            pastLessons: [],
            strategySignals: null,
        });
    }
});

app.get('/api/health', (_req: Request, res: Response) => {
    const summary = riskManager.getDailySummary();
    return res.status(200).json({
        status: 'ok',
        timestamp: new Date().toISOString(),
        openPositions: summary.openPositions,
        dailyPnL: summary.dailyPnL,
    });
});

app.get('/api/risk/summary', (_req: Request, res: Response) => {
    const summary = riskManager.getDailySummary();
    return res.status(200).json(summary);
});

/**
 * Single normalized advisory endpoint for n8n.
 * Triggers MiroFish generate->poll->normalize flow through backend bridge.
 */
app.post('/api/mirofish/advisory', async (req: Request, res: Response) => {
    const startedAt = Date.now();
    try {
        const body = req.body ?? {};
        if (!body.simulation_id || typeof body.simulation_id !== 'string') {
            return res.status(400).json({ error: 'simulation_id is required' });
        }

        const data = await proxyBackend('POST', '/api/v1/mirofish/advisory/run', {
            simulation_id: body.simulation_id,
            symbol: typeof body.symbol === 'string' ? body.symbol.toUpperCase() : undefined,
            force_regenerate: Boolean(body.force_regenerate),
            wait_timeout_seconds: Number(body.wait_timeout_seconds ?? 90),
            poll_interval_seconds: Number(body.poll_interval_seconds ?? 5),
            store_result: body.store_result !== false,
        }) as Record<string, any>;

        const normalized = data.normalized ?? {
            scenario_bias: 'neutral',
            tail_risk_score: 0.5,
            narrative_confidence: 0,
            summary: 'No advisory available.',
        };

        const status = String(data.status ?? 'unknown');
        const degraded = isAdvisoryDegradedStatus(status);
        recordAdvisoryMetric('run', {
            status,
            degraded,
            latencyMs: Date.now() - startedAt,
        });

        return res.status(200).json({
            success: data.completed === true,
            degraded,
            simulation_id: data.simulation_id,
            symbol: data.symbol,
            status,
            advisory: normalized,
            source: 'tradecraft-mirofish-bridge',
            raw: data.raw_report ?? null,
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'MiroFish advisory proxy failed';
        recordAdvisoryMetric('run', {
            status: 'error',
            degraded: true,
            latencyMs: Date.now() - startedAt,
            error: message,
        });
        return res.status(500).json({ error: message });
    }
});

/**
 * Fetch latest stored normalized advisory from backend bridge.
 */
app.get('/api/mirofish/advisory', async (req: Request, res: Response) => {
    const startedAt = Date.now();
    try {
        const symbol =
            typeof req.query.symbol === 'string' && req.query.symbol.trim().length > 0
                ? req.query.symbol.toUpperCase()
                : undefined;
        const simulationId =
            typeof req.query.simulation_id === 'string' && req.query.simulation_id.trim().length > 0
                ? req.query.simulation_id
                : undefined;

        const data = await proxyBackend('GET', '/api/v1/mirofish/advisory/latest', undefined, {
            symbol,
            simulation_id: simulationId,
        }) as Record<string, any>;

        const status = String(data.status ?? 'unknown');
        const degraded = isAdvisoryDegradedStatus(status);
        recordAdvisoryMetric('latest', {
            status,
            degraded,
            latencyMs: Date.now() - startedAt,
        });

        return res.status(200).json({
            success: data.completed === true,
            degraded,
            simulation_id: data.simulation_id,
            symbol: data.symbol,
            status,
            advisory: data.normalized ?? {
                scenario_bias: 'neutral',
                tail_risk_score: 0.5,
                narrative_confidence: 0,
                summary: 'No advisory available.',
            },
            source: 'tradecraft-mirofish-bridge',
            raw: data.raw_report ?? null,
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to fetch latest advisory';
        recordAdvisoryMetric('latest', {
            status: 'error',
            degraded: true,
            latencyMs: Date.now() - startedAt,
            error: message,
        });
        return res.status(500).json({ error: message });
    }
});

/**
 * Refresh advisory snapshots for a watchlist; intended for scheduled jobs (n8n/cron).
 */
app.post('/api/mirofish/advisory/refresh-watchlist', async (req: Request, res: Response) => {
    const startedAt = Date.now();
    try {
        const body = req.body ?? {};
        const symbolsInput = Array.isArray(body.symbols) ? body.symbols : ['NIFTY'];
        const symbols = symbolsInput
            .map((s) => String(s).trim().toUpperCase())
            .filter((s) => Boolean(s));

        if (symbols.length === 0) {
            return res.status(400).json({ error: 'symbols must contain at least one symbol' });
        }

        const requestMap =
            body.simulation_map && typeof body.simulation_map === 'object'
                ? (body.simulation_map as Record<string, string>)
                : undefined;

        const defaultSimulationId =
            typeof body.default_simulation_id === 'string' && body.default_simulation_id.trim().length > 0
                ? body.default_simulation_id
                : undefined;

        const waitTimeoutSeconds = Number(body.wait_timeout_seconds ?? 45);
        const pollIntervalSeconds = Number(body.poll_interval_seconds ?? 5);
        const storeResult = body.store_result !== false;

        const results: Array<Record<string, unknown>> = [];
        for (const symbol of symbols) {
            const simulationId = getSimulationIdForSymbol(symbol, defaultSimulationId, requestMap);
            if (!simulationId) {
                results.push({
                    symbol,
                    simulation_id: null,
                    status: 'skipped',
                    degraded: true,
                    error: 'Missing simulation_id mapping for symbol',
                });
                continue;
            }

            try {
                const data = await proxyBackend('POST', '/api/v1/mirofish/advisory/run', {
                    simulation_id: simulationId,
                    symbol,
                    wait_timeout_seconds: waitTimeoutSeconds,
                    poll_interval_seconds: pollIntervalSeconds,
                    store_result: storeResult,
                }) as Record<string, any>;

                const status = String(data.status ?? 'unknown');
                const degraded = isAdvisoryDegradedStatus(status);
                results.push({
                    symbol,
                    simulation_id: simulationId,
                    status,
                    degraded,
                    advisory: data.normalized ?? null,
                });
            } catch (error) {
                const message = error instanceof Error ? error.message : 'Refresh failed';
                results.push({
                    symbol,
                    simulation_id: simulationId,
                    status: 'error',
                    degraded: true,
                    error: message,
                });
            }
        }

        const degradedCount = results.filter((item) => item.degraded === true).length;
        const status = degradedCount > 0 ? 'degraded' : 'success';
        recordAdvisoryMetric('refresh', {
            status,
            degraded: degradedCount > 0,
            latencyMs: Date.now() - startedAt,
        });

        return res.status(200).json({
            success: degradedCount === 0,
            status,
            refreshed: results.length,
            degraded_count: degradedCount,
            results,
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Watchlist advisory refresh failed';
        recordAdvisoryMetric('refresh', {
            status: 'error',
            degraded: true,
            latencyMs: Date.now() - startedAt,
            error: message,
        });
        return res.status(500).json({ error: message });
    }
});

app.get('/api/mirofish/metrics', (_req: Request, res: Response) => {
    const payload = Object.fromEntries(
        Object.entries(advisoryMetrics).map(([key, value]) => {
            const avgLatencyMs = value.requests > 0 ? Number((value.totalLatencyMs / value.requests).toFixed(2)) : 0;
            return [key, { ...value, avgLatencyMs }];
        }),
    );

    return res.status(200).json({
        status: 'ok',
        source: 'tradecraft-advisory-observability',
        backendCandidates: getBackendCandidates(),
        metrics: payload,
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Compound Learning System Endpoints
// ─────────────────────────────────────────────────────────────────────────────

/**
 * POST /api/trades/open — Log a new trade entry into SQLite.
 */
app.post('/api/trades/open', (req: Request, res: Response) => {
    try {
        const body = req.body ?? {} as Partial<TradeRecord>;
        if (!body.symbol || !body.action || body.entry_price === undefined) {
            return res.status(400).json({ error: 'symbol, action, and entry_price are required' });
        }

        const trade: Omit<TradeRecord, 'id'> = {
            symbol: String(body.symbol),
            action: body.action as 'BUY' | 'SELL',
            entry_price: Number(body.entry_price),
            exit_price: body.exit_price !== undefined ? Number(body.exit_price) : undefined,
            target_price: Number(body.target_price ?? 0),
            stop_loss: Number(body.stop_loss ?? 0),
            quantity: Number(body.quantity ?? 0),
            entry_time: String(body.entry_time ?? new Date().toISOString()),
            exit_time: body.exit_time ? String(body.exit_time) : undefined,
            pnl: body.pnl !== undefined ? Number(body.pnl) : undefined,
            outcome: (body.outcome as TradeRecord['outcome']) ?? 'OPEN',
            confidence: Number(body.confidence ?? 0),
            risk_flag: String(body.risk_flag ?? ''),
            reasoning: String(body.reasoning ?? ''),
            rsi_at_entry: Number(body.rsi_at_entry ?? 0),
            ema9_at_entry: Number(body.ema9_at_entry ?? 0),
            ema21_at_entry: Number(body.ema21_at_entry ?? 0),
            macd_line_at_entry: Number(body.macd_line_at_entry ?? 0),
            sentiment_at_entry: String(body.sentiment_at_entry ?? 'NEUTRAL'),
            sentiment_score_at_entry: Number(body.sentiment_score_at_entry ?? 0),
            nse_announcement_flag: Boolean(body.nse_announcement_flag),
            failure_cause: (body.failure_cause as TradeRecord['failure_cause']) ?? null,
            lesson: body.lesson ? String(body.lesson) : undefined,
        };

        const tradeId = db.insertTrade(trade);
        return res.status(200).json({ success: true, tradeId });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to log trade';
        return res.status(500).json({ error: message });
    }
});

/**
 * POST /api/trades/close — Close an open trade and trigger async post-mortem if loss.
 */
app.post('/api/trades/close', async (req: Request, res: Response) => {
    try {
        const { tradeId, exit_price } = req.body ?? {};
        if (!tradeId || exit_price === undefined) {
            return res.status(400).json({ error: 'tradeId and exit_price are required' });
        }

        const exitTime = new Date().toISOString();
        db.closeTrade(Number(tradeId), Number(exit_price), exitTime);

        const updated = db.getTradeById(Number(tradeId));
        if (!updated) {
            return res.status(404).json({ error: 'Trade not found after closing' });
        }

        // Trigger post-mortem asynchronously on losses — do not await
        if (updated.outcome === 'LOSS') {
            postMortemAgent.analyzeFailure(updated).catch((err) => {
                console.error('[SERVER] post-mortem error:', (err as Error).message);
            });
        }

        return res.status(200).json({
            success: true,
            pnl: updated.pnl,
            outcome: updated.outcome,
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to close trade';
        return res.status(500).json({ error: message });
    }
});

/**
 * GET /api/performance — All-time aggregated performance metrics.
 */
app.get('/api/performance', (_req: Request, res: Response) => {
    try {
        const allTrades = db.getRecentTrades(10_000);
        const metrics = performanceTracker.calculateMetrics(allTrades);
        const drawdownBreached = performanceTracker.isDrawdownBreached();
        return res.status(200).json({ ...metrics, drawdownBreached });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to compute metrics';
        return res.status(500).json({ error: message });
    }
});

/**
 * GET /api/performance/today — Metrics for today's trading session only.
 */
app.get('/api/performance/today', (_req: Request, res: Response) => {
    try {
        const todaysTrades = db.getTodaysTrades();
        const metrics = performanceTracker.calculateMetrics(todaysTrades);
        return res.status(200).json(metrics);
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to compute metrics';
        return res.status(500).json({ error: message });
    }
});

/**
 * GET /api/lessons/query — Semantic search for similar past trade lessons.
 * Query params: ?symbol=NIFTY&rsi=32&sentiment=BULLISH
 */
app.get('/api/lessons/query', async (req: Request, res: Response) => {
    try {
        const { symbol, rsi, sentiment } = req.query;
        const setupText = [
            symbol ? `${String(symbol)} setup.` : '',
            rsi ? `RSI: ${String(rsi)}.` : '',
            sentiment ? `Sentiment: ${String(sentiment)}.` : '',
        ]
            .filter(Boolean)
            .join(' ');

        if (!setupText.trim()) {
            return res.status(400).json({ error: 'At least one query parameter is required' });
        }

        const lessons = await knowledgeBase.querySimilarLessons(setupText);
        return res.status(200).json({ lessons });
    } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to query lessons';
        return res.status(500).json({ error: message });
    }
});

app.listen(PORT, () => {
    // eslint-disable-next-line no-console
    console.log(`🚀 Tradecraft TypeScript server running on port ${PORT}`);
});