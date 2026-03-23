/**
 * Voyage AI embedding client for generating trade-context vectors.
 * Uses the voyage-finance-2 model (1024-dimension output, finance-optimised).
 */
import axios from 'axios';
import { TradeRecord } from '../types';

const VOYAGE_API_URL = 'https://api.voyageai.com/v1/embeddings';
const VOYAGE_MODEL = 'voyage-finance-2';

/**
 * Client for the Voyage AI embedding API.
 * Generates 1024-dimension embeddings suitable for Pinecone cosine-similarity search.
 */
export class EmbeddingClient {
    private readonly apiKey: string;

    constructor() {
        const key = process.env.VOYAGE_API_KEY;
        if (!key) {
            console.warn('[EmbeddingClient] VOYAGE_API_KEY not set — embedding calls will fail');
        }
        this.apiKey = key ?? '';
    }

    /**
     * Generate a 1024-dimension embedding for the given text.
     * @param text Structured trade description text
     * @returns Embedding vector (number[])
     */
    public async generateEmbedding(text: string): Promise<number[]> {
        if (!this.apiKey) {
            throw new Error('VOYAGE_API_KEY is not configured');
        }

        const response = await axios.post<{
            data: Array<{ embedding: number[] }>;
        }>(
            VOYAGE_API_URL,
            { input: [text], model: VOYAGE_MODEL },
            {
                headers: {
                    Authorization: `Bearer ${this.apiKey}`,
                    'Content-Type': 'application/json',
                },
                timeout: 15_000,
            },
        );

        const embedding = response.data?.data?.[0]?.embedding;
        if (!embedding || !Array.isArray(embedding)) {
            throw new Error('Voyage AI returned unexpected response shape');
        }
        return embedding;
    }

    /**
     * Build a rich structured text representation of a trade for embedding.
     * Only structured fields are used — never raw scraped content.
     * @param trade Completed or partially completed trade record
     * @returns Plain-English trade description string
     */
    public buildEmbeddingText(trade: TradeRecord): string {
        const trend = trade.ema9_at_entry > trade.ema21_at_entry ? 'BULLISH' : 'BEARISH';
        const lines: string[] = [
            `${trade.symbol} ${trade.action} trade.`,
            `RSI: ${trade.rsi_at_entry}, EMA9: ${trade.ema9_at_entry}, EMA21: ${trade.ema21_at_entry}, MACD: ${trade.macd_line_at_entry}.`,
            `Trend: ${trend}. Sentiment: ${trade.sentiment_at_entry} (score: ${trade.sentiment_score_at_entry}).`,
            `NSE announcement: ${trade.nse_announcement_flag}. Confidence: ${trade.confidence}. Risk: ${trade.risk_flag}.`,
            `Claude reasoning: ${trade.reasoning}.`,
        ];

        if (trade.outcome && trade.outcome !== 'OPEN') {
            lines.push(`Outcome: ${trade.outcome}. Failure: ${trade.failure_cause ?? 'N/A'}. PnL: ${trade.pnl ?? 0}.`);
        }
        if (trade.lesson) {
            lines.push(`Lesson: ${trade.lesson}`);
        }

        return lines.join(' ');
    }
}

/** Singleton embedding client instance */
export const embeddingClient = new EmbeddingClient();
