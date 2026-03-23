/**
 * NewsScraper fetches and analyzes news articles from Indian financial RSS feeds
 * SECURITY: Only uses title + RSS description, never scrapes full article body
 */

import axios, { AxiosError } from 'axios';
// eslint-disable-next-line @typescript-eslint/no-var-requires
const Parser = require('rss-parser');
import { NewsArticle } from '../types';
import { SentimentAnalyzer } from './sentimentAnalyzer';

/**
 * RSS feed configuration
 */
interface FeedConfig {
    name: string;
    url: string;
}

const RSS_FEEDS: FeedConfig[] = [
    {
        name: 'Economic Times Markets',
        url: 'https://economictimes.indiatimes.com/markets/rss.cms',
    },
    {
        name: 'Moneycontrol',
        url: 'https://www.moneycontrol.com/rss/business.xml',
    },
    {
        name: 'Livemint Markets',
        url: 'https://www.livemint.com/rss/markets',
    },
    {
        name: 'Business Standard',
        url: 'https://www.business-standard.com/rss/markets-106.rss',
    },
];

const MARKET_KEYWORDS = ['nifty', 'sensex', 'market', 'stocks', 'equity', 'nse', 'bse'];

export class NewsScraper {
    private rssParser: InstanceType<typeof Parser>;
    private sentimentAnalyzer: SentimentAnalyzer;

    constructor() {
        this.rssParser = new Parser({
            timeout: 8000,
        });
        this.sentimentAnalyzer = new SentimentAnalyzer();
    }

    /**
     * Sanitize text: remove HTML tags and limit length
     * @param text The text to sanitize
     * @param maxLength Maximum length of sanitized text
     * @returns Sanitized text
     */
    private sanitizeText(text: string, maxLength = 200): string {
        if (!text) return '';
        // Remove HTML tags
        let sanitized = text.replace(/<[^>]*>/g, '');
        // Decode HTML entities
        sanitized = sanitized
            .replace(/&quot;/g, '"')
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&nbsp;/g, ' ');
        // Limit length
        sanitized = sanitized.substring(0, maxLength).trim();
        return sanitized;
    }

    /**
     * Check if text contains symbol or general market keywords
     * @param text Text to search
     * @param symbol Stock symbol to search for
     * @returns True if relevant
     */
    private isRelevantArticle(text: string, symbol: string): boolean {
        const lowerText = text.toLowerCase();
        const lowerSymbol = symbol.toLowerCase();

        if (lowerText.includes(lowerSymbol)) {
            return true;
        }

        return MARKET_KEYWORDS.some((keyword) => lowerText.includes(keyword));
    }

    /**
     * Check if article was published within last 2 hours
     * @param pubDate Publication date string
     * @returns True if within 2 hours
     */
    private isWithinLastTwoHours(pubDate: string | Date | undefined): boolean {
        if (!pubDate) return false;

        const date = new Date(pubDate);
        const now = new Date();
        const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000);

        return date >= twoHoursAgo && date <= now;
    }

    /**
     * Fetch relevant articles from all RSS feeds
     * SECURITY: Only uses title + description, never scrapes full article
     * @param symbol Stock symbol to search for
     * @returns Array of NewsArticle objects, max 10
     */
    public async fetchRelevantArticles(symbol: string): Promise<NewsArticle[]> {
        try {
            const feedPromises = RSS_FEEDS.map((feed) =>
                this.fetchFromFeed(feed, symbol).catch((error) => {
                    // eslint-disable-next-line no-console
                    console.error(`[NewsScraper] Feed ${feed.name} failed:`, error);
                    return [];
                }),
            );

            const results = await Promise.allSettled(feedPromises);
            const articles: NewsArticle[] = [];

            for (const result of results) {
                if (result.status === 'fulfilled') {
                    articles.push(...result.value);
                }
            }

            // Sort by published date and return max 10
            articles.sort(
                (a, b) =>
                    new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime(),
            );

            return articles.slice(0, 10);
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error('[NewsScraper] fetchRelevantArticles error:', error);
            return [];
        }
    }

    /**
     * Fetch articles from a single RSS feed
     * @param feed Feed configuration
     * @param symbol Stock symbol to search for
     * @returns Array of NewsArticle objects
     */
    private async fetchFromFeed(feed: FeedConfig, symbol: string): Promise<NewsArticle[]> {
        try {
            const parsedFeed = await this.rssParser.parseURL(feed.url);
            const articles: NewsArticle[] = [];

            if (!parsedFeed.items) {
                return articles;
            }

            for (const item of parsedFeed.items) {
                // Extract title and description
                const title = item.title || '';
                const description = item.content || item.summary || '';

                // Check if relevant to symbol or market
                if (!this.isRelevantArticle(title + ' ' + description, symbol)) {
                    continue;
                }

                // Check publication date (last 2 hours)
                if (!this.isWithinLastTwoHours(item.pubDate)) {
                    continue;
                }

                // Sanitize text - NEVER include full article body
                const sanitizedTitle = this.sanitizeText(title, 150);
                const sanitizedDescription = this.sanitizeText(description, 200);
                const combinedText = `${sanitizedTitle} ${sanitizedDescription}`;

                // Analyze sentiment
                const analysis = this.sentimentAnalyzer.analyzeText(combinedText);

                articles.push({
                    title: sanitizedTitle,
                    summary: sanitizedDescription,
                    source: feed.name,
                    publishedAt: new Date(item.pubDate || new Date()).toISOString(),
                    url: item.link || '',
                    sentiment: analysis.sentiment,
                    sentimentScore: analysis.score,
                });
            }

            return articles;
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(`[NewsScraper] Error fetching from ${feed.name}:`, error);
            return [];
        }
    }
}
