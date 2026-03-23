/**
 * Pinecone vector knowledge base for storing and querying trade lessons.
 * Index must be created manually in the Pinecone dashboard:
 *   - Dimensions: 1024 (voyage-finance-2)
 *   - Metric: cosine
 */
import { Pinecone } from '@pinecone-database/pinecone';
import { TradeRecord, KnowledgeBaseEntry, MarketDataPayload, ResearchBrief } from '../types';
import { embeddingClient } from './embeddingClient';

const SIMILARITY_THRESHOLD = 0.75;

/**
 * Knowledge base backed by Pinecone for semantic similarity search over past trade lessons.
 */
export class KnowledgeBase {
    private client: Pinecone | null = null;
    private indexName: string;
    private ready = false;

    constructor() {
        this.indexName = process.env.PINECONE_INDEX_NAME ?? 'tradecraft-lessons';
        this.init().catch((err) => {
            console.error('[KnowledgeBase] Initialisation failed:', err.message);
        });
    }

    /** Initialise Pinecone client and verify index is reachable */
    private async init(): Promise<void> {
        const apiKey = process.env.PINECONE_API_KEY;
        if (!apiKey) {
            console.warn('[KnowledgeBase] PINECONE_API_KEY not set — knowledge base disabled');
            return;
        }
        this.client = new Pinecone({ apiKey });
        // Probe the index to confirm it exists
        await this.client.index(this.indexName).describeIndexStats();
        this.ready = true;
        console.log(`[KnowledgeBase] Connected to Pinecone index "${this.indexName}"`);
    }

    /**
     * Save a loss trade's lesson as a vector in Pinecone.
     * Only stores entries for LOSS trades or trades with an explicit lesson.
     * @param trade Completed trade with lesson field populated
     */
    public async saveLesson(trade: TradeRecord): Promise<void> {
        if (!this.ready || !this.client) return;
        if (!trade.id) return;
        if (trade.outcome !== 'LOSS' && !trade.lesson) return;

        try {
            const text = embeddingClient.buildEmbeddingText(trade);
            const vector = await embeddingClient.generateEmbedding(text);

            const index = this.client.index(this.indexName);
            await index.upsert({
                records: [
                    {
                        id: `trade_${trade.id}`,
                        values: vector,
                        metadata: {
                            symbol: trade.symbol,
                            outcome: trade.outcome ?? 'UNKNOWN',
                            failure_cause: trade.failure_cause ?? '',
                            lesson: trade.lesson ?? '',
                            rsi: trade.rsi_at_entry,
                            sentiment: trade.sentiment_at_entry,
                            confidence: trade.confidence,
                            pnl: trade.pnl ?? 0,
                            entry_time: trade.entry_time,
                        },
                    },
                ],
            });

            console.log(`[KnowledgeBase] Lesson saved to knowledge base: trade_${trade.id}`);
        } catch (err) {
            // Never block a trade on knowledge base errors
            console.error('[KnowledgeBase] saveLesson error:', (err as Error).message);
        }
    }

    /**
     * Query Pinecone for the most similar past lessons to the current market setup.
     * Returns empty array on any error — never blocks a trade.
     * @param currentSetup Plain-English description of the current trade setup
     * @param topK Number of candidates to retrieve (default 3)
     */
    public async querySimilarLessons(
        currentSetup: string,
        topK = 3,
    ): Promise<KnowledgeBaseEntry[]> {
        if (!this.ready || !this.client) return [];

        try {
            const vector = await embeddingClient.generateEmbedding(currentSetup);
            const index = this.client.index(this.indexName);

            const result = await index.query({
                vector,
                topK,
                includeMetadata: true,
            });

            const matches = result.matches ?? [];
            return matches
                .filter((m) => (m.score ?? 0) >= SIMILARITY_THRESHOLD)
                .map((m) => ({
                    id: m.id,
                    lesson: String(m.metadata?.lesson ?? ''),
                    failure_cause: String(m.metadata?.failure_cause ?? ''),
                    symbol: String(m.metadata?.symbol ?? ''),
                    outcome: String(m.metadata?.outcome ?? ''),
                    similarity_score: m.score,
                }));
        } catch (err) {
            console.error('[KnowledgeBase] querySimilarLessons error:', (err as Error).message);
            return [];
        }
    }

    /**
     * Build a plain-English description of the CURRENT market setup (no outcome).
     * Used as the query vector for retrieving similar past lessons.
     * @param payload Current market data snapshot
     * @param research Current research brief
     */
    public buildCurrentSetupText(
        payload: MarketDataPayload,
        research: ResearchBrief,
    ): string {
        const { indicators } = payload;
        const trend = indicators.ema9 > indicators.ema21 ? 'BULLISH' : 'BEARISH';
        return [
            `${payload.symbol} setup.`,
            `RSI: ${indicators.rsi}, EMA9: ${indicators.ema9}, EMA21: ${indicators.ema21}, MACD: ${indicators.macd.line}.`,
            `Trend: ${trend}. Sentiment: ${research.overallSentiment} (score: ${research.sentimentScore}).`,
            `NSE announcement: ${research.nseAnnouncementFlag}.`,
        ].join(' ');
    }
}

/** Singleton knowledge base instance */
export const knowledgeBase = new KnowledgeBase();
