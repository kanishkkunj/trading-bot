/**
 * PostMortemAgent uses Claude via OpenRouter to classify the root cause
 * of a losing trade and derive a concrete lesson for future trades.
 */
import axios from 'axios';
import { TradeRecord, PostMortem } from '../types';
import { db } from '../db/database';
import { knowledgeBase } from './knowledgeBase';
import { embeddingClient } from './embeddingClient';

const OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions';
const CLAUDE_MODEL = 'anthropic/claude-sonnet-4-5';

const SYSTEM_PROMPT = `You are a trading post-mortem analyst. Analyze this losing trade and \
classify the failure cause and write a concrete lesson for future trades.
Respond ONLY in this exact JSON format, no extra text:
{
  "failure_cause": "BAD_PREDICTION" | "BAD_TIMING" | "BAD_EXECUTION" | "EXTERNAL_SHOCK",
  "lesson": "One clear sentence describing what to avoid next time",
  "marketConditions": "Brief description of market state at time of trade"
}

Failure cause definitions:
- BAD_PREDICTION: Technical/sentiment signals were wrong
- BAD_TIMING: Signal was right but entry/exit timing was poor
- BAD_EXECUTION: Risk sizing or order execution was the issue
- EXTERNAL_SHOCK: Unforeseeable external event caused the loss`;

/**
 * Analyses losing trades via Claude and stores lessons in SQLite + Pinecone.
 */
export class PostMortemAgent {
    private readonly apiKey: string;

    constructor() {
        const key = process.env.OPENROUTER_API_KEY;
        if (!key) {
            console.warn('[PostMortemAgent] OPENROUTER_API_KEY not set');
        }
        this.apiKey = key ?? '';
    }

    /**
     * Analyse a losing trade, classify the failure, save the lesson, and return
     * a PostMortem object. Returns null on any error — never crashes the caller.
     * @param trade Closed trade record with outcome === 'LOSS'
     */
    public async analyzeFailure(trade: TradeRecord): Promise<PostMortem | null> {
        if (!trade.id) {
            console.warn('[PostMortemAgent] analyzeFailure called with trade missing id');
            return null;
        }
        if (trade.outcome !== 'LOSS') return null;

        try {
            const userPrompt = this.buildPrompt(trade);
            const raw = await this.callClaude(userPrompt);
            const parsed = this.parseResponse(raw);

            if (!parsed) {
                console.error('[PostMortemAgent] Could not parse Claude response');
                return null;
            }

            // Persist lesson in SQLite
            db.updateTradeLesson(trade.id, parsed.failure_cause, parsed.lesson);

            // Attach lesson to trade object for embedding
            const enrichedTrade: TradeRecord = {
                ...trade,
                failure_cause: parsed.failure_cause as TradeRecord['failure_cause'],
                lesson: parsed.lesson,
            };

            // Persist embedding in Pinecone (non-blocking)
            const embeddingText = embeddingClient.buildEmbeddingText(enrichedTrade);
            knowledgeBase.saveLesson(enrichedTrade).catch((err) => {
                console.error('[PostMortemAgent] saveLesson error:', (err as Error).message);
            });

            const postMortem: PostMortem = {
                tradeId: trade.id,
                symbol: trade.symbol,
                failure_cause: parsed.failure_cause,
                lesson: parsed.lesson,
                marketConditions: parsed.marketConditions,
                embeddingText,
            };

            console.log(
                `[PostMortemAgent] Post-mortem complete for trade ${trade.id}: ${parsed.failure_cause}`,
            );
            return postMortem;
        } catch (err) {
            console.error(
                '[PostMortemAgent] analyzeFailure error:',
                (err as Error).message,
            );
            return null;
        }
    }

    // ──────────────────────────────────────────────────────────────────────────
    // Private helpers
    // ──────────────────────────────────────────────────────────────────────────

    /** Build the user-facing prompt for Claude */
    private buildPrompt(trade: TradeRecord): string {
        return [
            `Trade: ${trade.symbol} ${trade.action}`,
            `Entry: ${trade.entry_price} | Exit: ${trade.exit_price} | PnL: ${trade.pnl}`,
            `Target: ${trade.target_price} | Stop: ${trade.stop_loss} | Qty: ${trade.quantity}`,
            `RSI at entry: ${trade.rsi_at_entry}`,
            `EMA9: ${trade.ema9_at_entry} | EMA21: ${trade.ema21_at_entry} | MACD: ${trade.macd_line_at_entry}`,
            `Sentiment: ${trade.sentiment_at_entry} (score: ${trade.sentiment_score_at_entry})`,
            `NSE announcement: ${trade.nse_announcement_flag}`,
            `Confidence: ${trade.confidence}/10`,
            `Claude reasoning: ${trade.reasoning}`,
            `Entry time: ${trade.entry_time} | Exit time: ${trade.exit_time}`,
        ].join('\n');
    }

    /** Call OpenRouter / Claude and return the raw content string */
    private async callClaude(userPrompt: string): Promise<string> {
        if (!this.apiKey) throw new Error('OPENROUTER_API_KEY is not configured');

        const response = await axios.post<{
            choices: Array<{ message: { content: string } }>;
        }>(
            OPENROUTER_API_URL,
            {
                model: CLAUDE_MODEL,
                messages: [
                    { role: 'system', content: SYSTEM_PROMPT },
                    { role: 'user', content: userPrompt },
                ],
                max_tokens: 300,
                temperature: 0.1,
            },
            {
                headers: {
                    Authorization: `Bearer ${this.apiKey}`,
                    'Content-Type': 'application/json',
                    'HTTP-Referer': 'https://tradecraft.app',
                    'X-Title': 'Tradecraft PostMortem',
                },
                timeout: 30_000,
            },
        );

        return response.data?.choices?.[0]?.message?.content ?? '';
    }

    /** Extract and validate JSON from Claude's response */
    private parseResponse(
        raw: string,
    ): { failure_cause: string; lesson: string; marketConditions: string } | null {
        try {
            // Extract JSON block from the response (handles markdown fences)
            const match = raw.match(/\{[\s\S]*\}/);
            if (!match) return null;
            const parsed = JSON.parse(match[0]);
            if (!parsed.failure_cause || !parsed.lesson) return null;
            return {
                failure_cause: String(parsed.failure_cause),
                lesson: String(parsed.lesson),
                marketConditions: String(parsed.marketConditions ?? ''),
            };
        } catch {
            return null;
        }
    }
}

/** Singleton post-mortem agent instance */
export const postMortemAgent = new PostMortemAgent();
