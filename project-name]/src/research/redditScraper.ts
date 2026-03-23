/**
 * RedditScraper fetches and analyzes posts from Indian financial subreddits
 * SECURITY: Sanitizes all URLs, @mentions before text processing
 */

import axios from 'axios';
import { RedditPost } from '../types';
import { SentimentAnalyzer } from './sentimentAnalyzer';

/**
 * Subreddit configuration
 */
interface SubredditConfig {
    name: string;
    url: string;
}

const SUBREDDITS: SubredditConfig[] = [
    {
        name: 'IndiaInvestments',
        url: 'https://www.reddit.com/r/IndiaInvestments/hot.json?limit=25',
    },
    {
        name: 'IndianStreetBets',
        url: 'https://www.reddit.com/r/IndianStreetBets/hot.json?limit=25',
    },
];

const MARKET_KEYWORDS = ['nifty', 'market', 'sensex', 'stock', 'trading', 'buy', 'sell'];

export class RedditScraper {
    private sentimentAnalyzer: SentimentAnalyzer;

    constructor() {
        this.sentimentAnalyzer = new SentimentAnalyzer();
    }

    /**
     * Sanitize Reddit text by removing URLs, usernames, and markdown
     * @param text The text to sanitize
     * @param maxLength Maximum length of sanitized text
     * @returns Sanitized text
     */
    private sanitizeRedditText(text: string, maxLength = 300): string {
        if (!text) return '';

        let sanitized = text;

        // Remove URLs
        sanitized = sanitized.replace(/https?:\/\/[^\s]+/g, '');

        // Remove usernames (u/name or r/name)
        sanitized = sanitized.replace(/([ur]\/[a-zA-Z0-9_-]+)/g, '');

        // Remove markdown formatting
        sanitized = sanitized.replace(/[*_~`]/g, '');

        // Remove extra whitespace
        sanitized = sanitized.replace(/\s+/g, ' ').trim();

        // Limit length
        sanitized = sanitized.substring(0, maxLength).trim();

        return sanitized;
    }

    /**
     * Check if post title contains relevant keywords
     * @param title Post title to check
     * @param symbol Stock symbol
     * @returns True if relevant
     */
    private isRelevantPost(title: string, symbol: string): boolean {
        const lowerTitle = title.toLowerCase();
        const lowerSymbol = symbol.toLowerCase();

        if (lowerTitle.includes(lowerSymbol)) {
            return true;
        }

        return MARKET_KEYWORDS.some((keyword) => lowerTitle.includes(keyword));
    }

    /**
     * Fetch relevant posts from all subreddits
     * SECURITY: Strips all URLs and @mentions before processing
     * @param symbol Stock symbol to search for
     * @returns Array of RedditPost objects, max 8
     */
    public async fetchRelevantPosts(symbol: string): Promise<RedditPost[]> {
        try {
            const posts: RedditPost[] = [];

            // Fetch first subreddit
            const firstSubreddit = await this.fetchFromSubreddit(SUBREDDITS[0], symbol);
            posts.push(...firstSubreddit);

            // Wait 1.5 seconds to avoid rate limiting
            await new Promise((resolve) => setTimeout(resolve, 1500));

            // Fetch second subreddit
            const secondSubreddit = await this.fetchFromSubreddit(SUBREDDITS[1], symbol);
            posts.push(...secondSubreddit);

            // Sort by score (upvotes) and return top 8
            posts.sort((a, b) => b.score - a.score);

            return posts.slice(0, 8);
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error('[RedditScraper] fetchRelevantPosts error:', error);
            return [];
        }
    }

    /**
     * Fetch posts from a single subreddit
     * @param subreddit Subreddit configuration
     * @param symbol Stock symbol to search for
     * @returns Array of RedditPost objects
     */
    private async fetchFromSubreddit(
        subreddit: SubredditConfig,
        symbol: string,
    ): Promise<RedditPost[]> {
        try {
            const response = await axios.get(subreddit.url, {
                headers: {
                    'User-Agent': 'TradecraftBot/1.0 (automated trading research)',
                    'Accept': 'application/json',
                },
                timeout: 8000,
            });

            const posts: RedditPost[] = [];
            const data = response.data as any;

            if (!data.data || !data.data.children) {
                return posts;
            }

            for (const child of data.data.children) {
                const post = child.data;

                // Check if title is relevant
                if (!this.isRelevantPost(post.title || '', symbol)) {
                    continue;
                }

                // Sanitize title and body (limit body to first 300 chars)
                const sanitizedTitle = this.sanitizeRedditText(post.title || '', 200);
                const sanitizedBody = this.sanitizeRedditText(post.selftext || '', 300);
                const combinedText = `${sanitizedTitle} ${sanitizedBody}`;

                // Analyze sentiment
                const analysis = this.sentimentAnalyzer.analyzeText(combinedText);

                // Weight by score (upvotes)
                const weight = Math.min(2.0, Math.max(0.5, (post.score || 0) / 100));

                posts.push({
                    title: sanitizedTitle,
                    body: sanitizedBody,
                    score: post.score || 0,
                    comments: post.num_comments || 0,
                    source: subreddit.name,
                    sentiment: analysis.sentiment,
                    sentimentScore: analysis.score,
                });
            }

            return posts;
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(
                `[RedditScraper] Error fetching from ${subreddit.name}:`,
                error instanceof Error ? error.message : error,
            );
            return [];
        }
    }
}
