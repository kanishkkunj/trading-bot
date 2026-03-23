/**
 * ResearchOrchestrator coordinates news scraping, Reddit analysis, and NSE checks
 * Returns a combined ResearchBrief with confidence scoring and sentiment analysis
 */

import { ResearchBrief, NewsArticle, RedditPost, KnowledgeBaseEntry, MarketDataPayload } from '../types';
import { NewsScraper } from './newsScraper';
import { RedditScraper } from './redditScraper';
import { NseChecker } from './nseChecker';
import { knowledgeBase } from '../compound/knowledgeBase';

export class ResearchOrchestrator {
    private newsScraper: NewsScraper;
    private redditScraper: RedditScraper;
    private nseChecker: NseChecker;

    constructor() {
        this.newsScraper = new NewsScraper();
        this.redditScraper = new RedditScraper();
        this.nseChecker = new NseChecker();
    }

    /**
     * Run complete research workflow for a symbol
     * Executes all scrapers in parallel with 15-second timeout
     * Always returns a ResearchBrief (never throws)
     * @param symbol Stock symbol to research
     * @returns ResearchBrief with combined sentiment analysis
     */
    public async runResearch(symbol: string): Promise<ResearchBrief> {
        try {
            // Run all three sources in parallel with timeout protection
            const researchPromise = Promise.allSettled([
                this.newsScraper.fetchRelevantArticles(symbol),
                this.redditScraper.fetchRelevantPosts(symbol),
                this.nseChecker.checkRecentAnnouncements(symbol),
            ]);

            // Set 15-second timeout
            const results = await Promise.race([
                researchPromise,
                new Promise((_, reject) =>
                    setTimeout(
                        () => reject(new Error('Research timeout after 15 seconds')),
                        15000,
                    ),
                ),
            ]);

            const [newsResult, redditResult, nseResult] = results as PromiseSettledResult<
                any
            >[];

            // Extract data from settled promises
            const articles: NewsArticle[] =
                newsResult.status === 'fulfilled' ? newsResult.value : [];
            const posts: RedditPost[] = redditResult.status === 'fulfilled' ? redditResult.value : [];
            const hasNseAnnouncement: boolean =
                nseResult.status === 'fulfilled' ? nseResult.value : false;

            // Build ResearchBrief
            const brief = this.buildResearchBrief(symbol, articles, posts, hasNseAnnouncement);

            // Attach relevant past lessons from knowledge base
            brief.pastLessons = await this.queryPastLessonsForBrief(brief);

            return brief;
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error('[ResearchOrchestrator] runResearch error:', error);
            // Return neutral brief with 0 confidence on timeout/error
            return this.buildNeutralBrief(symbol);
        }
    }

    /**
     * Build a ResearchBrief from scraped data
     * @param symbol Stock symbol
     * @param articles News articles with sentiment
     * @param posts Reddit posts with sentiment
     * @param hasNseAnnouncement Whether NSE announcement exists
     * @returns Complete ResearchBrief
     */
    private buildResearchBrief(
        symbol: string,
        articles: NewsArticle[],
        posts: RedditPost[],
        hasNseAnnouncement: boolean,
    ): ResearchBrief {
        // Calculate sentiment totals
        let bullishSignals = 0;
        let bearishSignals = 0;
        let neutralSignals = 0;

        // Process articles
        let articleScoreSum = 0;
        for (const article of articles) {
            articleScoreSum += article.sentimentScore;
            if (article.sentiment === 'BULLISH') bullishSignals++;
            else if (article.sentiment === 'BEARISH') bearishSignals++;
            else neutralSignals++;
        }

        // Process Reddit posts with weight based on score
        let postScoreSum = 0;
        let postWeightSum = 0;
        let redditBullish = 0;
        let redditBearish = 0;

        for (const post of posts) {
            const weight = Math.min(2.0, Math.max(0.5, (post.score || 0) / 100));
            postScoreSum += post.sentimentScore * weight;
            postWeightSum += weight;

            if (post.sentiment === 'BULLISH') redditBullish++;
            else if (post.sentiment === 'BEARISH') redditBearish++;
        }

        // Calculate overall sentiment score
        let totalScoreSum = articleScoreSum + postScoreSum;
        let totalWeight = articles.length + postWeightSum;
        const overallScore = totalWeight > 0 ? totalScoreSum / totalWeight : 0;

        // Determine overall sentiment
        let overallSentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
        if (overallScore > 0.15) {
            overallSentiment = 'BULLISH';
        } else if (overallScore < -0.15) {
            overallSentiment = 'BEARISH';
        } else {
            overallSentiment = 'NEUTRAL';
        }

        // Determine Reddit consensus
        const totalRedditSentiments = redditBullish + redditBearish;
        let redditConsensus: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'MIXED';
        if (totalRedditSentiments === 0) {
            redditConsensus = 'NEUTRAL';
        } else if (redditBullish > redditBearish * 1.5) {
            redditConsensus = 'BULLISH';
        } else if (redditBearish > redditBullish * 1.5) {
            redditConsensus = 'BEARISH';
        } else {
            redditConsensus = 'MIXED';
        }

        // Calculate confidence
        const totalSources = articles.length + posts.length;
        let confidence = Math.min(100, totalSources * 10);
        if (totalSources < 3) {
            confidence = Math.min(confidence, 30);
        }

        // Build headlines from articles (max 5, sanitized)
        const topHeadlines = articles
            .slice(0, 5)
            .map((article) => article.title.substring(0, 100));

        // Build summary - 2 sentences, plain English, NO raw content
        const summary = this.buildSummary(
            overallSentiment,
            overallScore,
            articles.length,
            redditConsensus,
            redditBullish,
            redditBearish,
        );

        return {
            symbol,
            timestamp: new Date().toISOString(),
            overallSentiment,
            sentimentScore: overallScore,
            confidence,
            bullishSignals,
            bearishSignals,
            neutralSignals,
            topHeadlines,
            redditConsensus,
            nseAnnouncementFlag: hasNseAnnouncement,
            sources: {
                newsCount: articles.length,
                redditCount: posts.length,
                nseCount: hasNseAnnouncement ? 1 : 0,
            },
            summary,
        };
    }

    /**
     * Build a neutral ResearchBrief with 0 confidence (for timeout/error cases)
     * @param symbol Stock symbol
     * @returns Neutral ResearchBrief
     */
    /**
     * Query the Pinecone knowledge base for past lessons relevant to the current
     * market context described in a ResearchBrief.
     * Returns empty array on any error — never blocks research.
     * @param payload Current market data (optional — used for richer query)
     * @param research Current ResearchBrief
     */
    public async queryPastLessons(
        payload: MarketDataPayload,
        research: ResearchBrief,
    ): Promise<KnowledgeBaseEntry[]> {
        try {
            const setupText = knowledgeBase.buildCurrentSetupText(payload, research);
            return await knowledgeBase.querySimilarLessons(setupText);
        } catch {
            return [];
        }
    }

    /**
     * Build a setup text from a ResearchBrief alone (no market data) and query lessons.
     * Used internally during runResearch when full market payload is not available.
     */
    private async queryPastLessonsForBrief(brief: ResearchBrief): Promise<KnowledgeBaseEntry[]> {
        try {
            const setupText = [
                `${brief.symbol} setup.`,
                `Sentiment: ${brief.overallSentiment} (score: ${brief.sentimentScore}).`,
                `NSE announcement: ${brief.nseAnnouncementFlag}.`,
            ].join(' ');
            return await knowledgeBase.querySimilarLessons(setupText);
        } catch {
            return [];
        }
    }

    private buildNeutralBrief(symbol: string): ResearchBrief {
        return {
            symbol,
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
            summary: 'No research data available. Proceed with caution and manual review.',
        };
    }

    /**
     * Build a human-readable summary of sentiment analysis
     * 2 sentences max, plain English, no raw scraped content
     * @param sentiment Overall sentiment
     * @param score Sentiment score
     * @param newsCount Number of articles analyzed
     * @param redditConsensus Reddit consensus sentiment
     * @param bullishPosts Number of bullish Reddit posts
     * @param bearishPosts Number of bearish Reddit posts
     * @returns Summary string
     */
    private buildSummary(
        sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL',
        score: number,
        newsCount: number,
        redditConsensus: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'MIXED',
        bullishPosts: number,
        bearishPosts: number,
    ): string {
        const newsDescription =
            newsCount === 0
                ? 'No recent news found. '
                : `News sentiment is ${sentiment.toLowerCase()} with ${newsCount} source${newsCount !== 1 ? 's' : ''}. `;

        const redditPercentage =
            bullishPosts + bearishPosts === 0
                ? 0
                : Math.round((bullishPosts / (bullishPosts + bearishPosts)) * 100);

        const redditDescription =
            bullishPosts + bearishPosts === 0
                ? 'No Reddit discussion found.'
                : `Reddit sentiment is ${redditConsensus.toLowerCase()} with ${redditPercentage}% of posts bullish.`;

        return `${newsDescription}${redditDescription}`;
    }
}
