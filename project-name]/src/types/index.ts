export interface OHLCV {
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    timestamp: string;
}

export interface MacdData {
    line: number;
    signal: number;
    histogram: number;
}

export interface MarketDataPayload {
    symbol: string;
    candles: OHLCV[];
    indicators: {
        rsi: number;
        macd: MacdData;
        ema9: number;
        ema21: number;
    };
    livePrice: number;
    timestamp: string;
}

export interface ClaudeTradeDecision {
    action: 'BUY' | 'SELL' | 'HOLD';
    symbol: string;
    entry_price: number;
    target_price: number;
    stop_loss: number;
    quantity: number;
    confidence: number;
    reason: string;
}

export interface TradeOrder {
    symbol: string;
    action: 'BUY' | 'SELL';
    quantity: number;
    price: number;
    orderType: 'MARKET' | 'LIMIT';
}

export interface LogEntry {
    timestamp: string;
    symbol: string;
    action: 'BUY' | 'SELL' | 'HOLD';
    confidence: number;
    entry_price: number;
    target_price: number;
    stop_loss: number;
    quantity: number;
    reason: string;
    executed: boolean;
    executionRejectedReason?: string;
}

/**
 * News article scraped from RSS feeds
 */
export interface NewsArticle {
    title: string;
    summary: string;
    source: string;
    publishedAt: string;
    url: string;
    sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    sentimentScore: number; // -1 to +1
}

/**
 * Reddit post from public subreddit
 */
export interface RedditPost {
    title: string;
    body: string;
    score: number;
    comments: number;
    source: string;
    sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    sentimentScore: number;
}

/**
 * Research brief combining news and sentiment analysis
 */
export interface ResearchBrief {
    symbol: string;
    timestamp: string;
    overallSentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    sentimentScore: number; // weighted average, -1 to +1
    confidence: number; // 0-100, based on number of sources found
    bullishSignals: number;
    bearishSignals: number;
    neutralSignals: number;
    topHeadlines: string[]; // max 5, sanitized titles only, no body text
    redditConsensus: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'MIXED';
    nseAnnouncementFlag: boolean; // true if any NSE announcement found in last 2 hours
    sources: {
        newsCount: number;
        redditCount: number;
        nseCount: number;
    };
    summary: string; // 2-sentence plain English summary, Claude will read this
    pastLessons?: KnowledgeBaseEntry[]; // Relevant past trade lessons from vector DB
    strategySignals?: StrategySignals;
}

export interface StrategySignals {
    symbol: string;
    timestamp: string;
    strategyMode: 'trend_following' | 'mean_reversion' | 'hybrid';
    regime: 'trending' | 'range_bound' | 'high_volatility';
    trendFollowing: {
        score: number;
        bias: 'BUY' | 'SELL' | 'HOLD';
        sma20: number;
        sma50: number;
        sma200: number;
    };
    meanReversion: {
        score: number;
        bias: 'BUY' | 'SELL' | 'HOLD';
        zScore: number;
        upperBand: number;
        lowerBand: number;
    };
    supportResistance: {
        score: number;
        bias: 'BUY' | 'SELL' | 'HOLD';
        support20: number;
        resistance20: number;
        distanceToSupport: number;
        distanceToResistance: number;
    };
    volumeContext: {
        avgVolume20: number;
        lastVolume: number;
    };
    aggregate: {
        score: number;
        bias: 'BUY' | 'SELL' | 'HOLD';
        confidenceBoost: number;
    };
}

/**
 * Full record of a single trade stored in SQLite
 */
export interface TradeRecord {
    id?: number;
    symbol: string;
    action: 'BUY' | 'SELL';
    entry_price: number;
    exit_price?: number;
    target_price: number;
    stop_loss: number;
    quantity: number;
    entry_time: string;
    exit_time?: string;
    pnl?: number;
    outcome?: 'WIN' | 'LOSS' | 'BREAKEVEN' | 'OPEN';
    confidence: number;
    risk_flag: string;
    reasoning: string;
    rsi_at_entry: number;
    ema9_at_entry: number;
    ema21_at_entry: number;
    macd_line_at_entry: number;
    sentiment_at_entry: string;
    sentiment_score_at_entry: number;
    nse_announcement_flag: boolean;
    failure_cause?: 'BAD_PREDICTION' | 'BAD_TIMING' | 'BAD_EXECUTION' | 'EXTERNAL_SHOCK' | null;
    lesson?: string;
}

/**
 * Aggregated performance metrics for a set of trades
 */
export interface PerformanceMetrics {
    totalTrades: number;
    openTrades: number;
    wins: number;
    losses: number;
    winRate: number;
    totalPnl: number;
    grossProfit: number;
    grossLoss: number;
    profitFactor: number;
    sharpeRatio: number;
    maxDrawdown: number;
    currentDrawdown: number;
    maxDrawdownBreached: boolean;
    brierScore: number;
    avgConfidence: number;
    avgWinPnl: number;
    avgLossPnl: number;
    date: string;
}

/**
 * Result of the post-mortem analysis for a losing trade
 */
export interface PostMortem {
    tradeId: number;
    symbol: string;
    failure_cause: string;
    lesson: string;
    marketConditions: string;
    embeddingText: string;
}

/**
 * Entry retrieved from the Pinecone vector knowledge base
 */
export interface KnowledgeBaseEntry {
    id: string;
    lesson: string;
    failure_cause: string;
    symbol: string;
    outcome: string;
    similarity_score?: number;
}

/**
 * Extended ExecutionResult that carries the DB trade id for compound tracking
 */
export interface ExecutionResult {
    executed: boolean;
    rejection_reason?: string;
    order?: TradeOrder;
    decision: ClaudeTradeDecision;
    tradeId?: number;
}

export interface MiroFishNormalizedAdvisory {
    scenario_bias: 'risk_on' | 'neutral' | 'risk_off';
    tail_risk_score: number;
    narrative_confidence: number;
    summary: string;
}

export interface MiroFishAdvisoryResponse {
    success: boolean;
    degraded: boolean;
    simulation_id?: string;
    symbol?: string;
    status: string;
    advisory: MiroFishNormalizedAdvisory;
    source: 'tradecraft-mirofish-bridge';
    raw?: unknown;
}