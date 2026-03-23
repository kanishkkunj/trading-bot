/**
 * SentimentAnalyzer combines the 'sentiment' npm package with custom Indian financial keywords
 * to determine sentimentPolarity and calculate sentiment scores.
 */

// eslint-disable-next-line @typescript-eslint/no-var-requires
const Sentiment = require('sentiment');

/**
 * Custom keyword weights for Indian financial market sentiment
 */
const BULLISH_KEYWORDS = [
    'rally',
    'surge',
    'breakout',
    'beat estimates',
    'strong results',
    'upgrade',
    'buy rating',
    'profit up',
    'revenue growth',
    'fii buying',
    'dii buying',
    'bullish',
    'positive outlook',
    'record high',
    'nifty up',
    'sensex up',
    'gains',
    'momentum',
    'outperform',
    'long',
];

const BEARISH_KEYWORDS = [
    'crash',
    'fall',
    'selloff',
    'missed estimates',
    'weak results',
    'downgrade',
    'sell rating',
    'profit down',
    'revenue miss',
    'fii selling',
    'dii selling',
    'bearish',
    'negative outlook',
    '52-week low',
    'nifty down',
    'sensex down',
    'losses',
    'circuit breaker',
    'ban',
    'probe',
    'fraud',
    'losses',
    'underperform',
    'short',
];

/**
 * BatchAnalysisResult contains the breakdown of sentiment analysis for multiple texts
 */
interface BatchAnalysisResult {
    overall: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    score: number;
    breakdown: {
        bullishCount: number;
        bearishCount: number;
        neutralCount: number;
        weightedAverage: number;
    };
}

/**
 * AnalysisResult contains the sentiment label and score for a single text
 */
interface AnalysisResult {
    sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    score: number;
}

/**
 * SentimentAnalyzer: uses 'sentiment' npm package + custom keywords to classify text
 */
export class SentimentAnalyzer {
    private baseSentiment: InstanceType<typeof Sentiment>;

    constructor() {
        this.baseSentiment = new Sentiment();
    }

    /**
     * Analyze a single text and return sentiment label + score
     * @param text The text to analyze
     * @returns Object with sentiment label and score (-1 to +1)
     */
    public analyzeText(text: string): AnalysisResult {
        if (!text || text.trim().length === 0) {
            return { sentiment: 'NEUTRAL', score: 0 };
        }

        const lowerText = text.toLowerCase();

        // Base sentiment score from the sentiment package
        const baseResult = this.baseSentiment.analyze(text);
        let score = baseResult.score;

        // Count custom keyword occurrences
        let bullishMatches = 0;
        let bearishMatches = 0;

        for (const keyword of BULLISH_KEYWORDS) {
            const count = (lowerText.match(new RegExp(`\\b${keyword}\\b`, 'g')) || []).length;
            bullishMatches += count;
        }

        for (const keyword of BEARISH_KEYWORDS) {
            const count = (lowerText.match(new RegExp(`\\b${keyword}\\b`, 'g')) || []).length;
            bearishMatches += count;
        }

        // Apply custom keyword weights
        score += bullishMatches * 0.2;
        score -= bearishMatches * 0.2;

        // Clamp score between -1 and +1
        score = Math.max(-1, Math.min(1, score));

        // Determine sentiment based on thresholds
        let sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
        if (score > 0.15) {
            sentiment = 'BULLISH';
        } else if (score < -0.15) {
            sentiment = 'BEARISH';
        } else {
            sentiment = 'NEUTRAL';
        }

        return { sentiment, score };
    }

    /**
     * Analyze multiple texts (optionally weighted) and return overall sentiment
     * @param texts Array of texts or objects with text and score (for Reddit weighting)
     * @returns BatchAnalysisResult with overall sentiment and stats
     */
    public classifyBatch(
        texts: (string | { text: string; weight?: number })[],
    ): BatchAnalysisResult {
        if (!texts || texts.length === 0) {
            return {
                overall: 'NEUTRAL',
                score: 0,
                breakdown: {
                    bullishCount: 0,
                    bearishCount: 0,
                    neutralCount: 0,
                    weightedAverage: 0,
                },
            };
        }

        let totalBullish = 0;
        let totalBearish = 0;
        let totalNeutral = 0;
        let weightedSum = 0;
        let totalWeight = 0;

        for (const item of texts) {
            const text = typeof item === 'string' ? item : item.text;
            const weight = typeof item === 'string' ? 1 : item.weight ?? 1;

            const result = this.analyzeText(text);

            if (result.sentiment === 'BULLISH') {
                totalBullish++;
            } else if (result.sentiment === 'BEARISH') {
                totalBearish++;
            } else {
                totalNeutral++;
            }

            weightedSum += result.score * weight;
            totalWeight += weight;
        }

        const weightedAverage = totalWeight > 0 ? weightedSum / totalWeight : 0;

        // Determine overall sentiment
        let overall: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
        if (weightedAverage > 0.15) {
            overall = 'BULLISH';
        } else if (weightedAverage < -0.15) {
            overall = 'BEARISH';
        } else {
            overall = 'NEUTRAL';
        }

        return {
            overall,
            score: weightedAverage,
            breakdown: {
                bullishCount: totalBullish,
                bearishCount: totalBearish,
                neutralCount: totalNeutral,
                weightedAverage,
            },
        };
    }
}
