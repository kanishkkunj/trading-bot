"""Ingestion of news, filings, and social feeds for sentiment analysis."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import feedparser
import httpx

# Note: Twitter/X API calls are stubbed; plug in credentials and real endpoints when available.


@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    published: datetime
    link: str
    symbols: List[str]
    sector: Optional[str] = None
    raw: Optional[dict] = None


class NewsIngestion:
    """Fetches news from RSS, social, filings, and policy statements."""

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self.default_feeds = [
            "https://www.moneycontrol.com/rss/latestnews.xml",
            "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
            "https://www.bloombergquint.com/feed",
        ]

    async def fetch_rss(self, feeds: Optional[Iterable[str]] = None) -> List[NewsItem]:
        feeds = list(feeds) if feeds else self.default_feeds
        items: List[NewsItem] = []
        for url in feeds:
            parsed = feedparser.parse(url)
            for entry in parsed.entries:
                published = datetime(*entry.published_parsed[:6]) if getattr(entry, "published_parsed", None) else datetime.utcnow()
                items.append(
                    NewsItem(
                        source=url,
                        title=entry.get("title", ""),
                        summary=entry.get("summary", ""),
                        published=published,
                        link=entry.get("link", ""),
                        symbols=[],
                        raw=entry,
                    )
                )
        return items

    async def fetch_twitter(self, query: str, max_results: int = 50) -> List[NewsItem]:
        """Stub for Twitter/X ingestion; plug in API call if creds are available."""
        # Placeholder to keep latency low when API is unavailable.
        _ = query, max_results
        return []

    async def fetch_transcripts(self, urls: List[str]) -> List[NewsItem]:
        items: List[NewsItem] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for url in urls:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    items.append(
                        NewsItem(
                            source="earnings_call",
                            title=url,
                            summary=resp.text[:2000],
                            published=datetime.utcnow(),
                            link=url,
                            symbols=[],
                        )
                    )
                except Exception:
                    continue
        return items

    async def fetch_filings(self, urls: List[str]) -> List[NewsItem]:
        # SEC/NSE filings text ingestion; simple HTTP fetch
        return await self.fetch_transcripts(urls)

    async def fetch_rbi_statements(self, urls: List[str]) -> List[NewsItem]:
        return await self.fetch_transcripts(urls)

    async def gather_all(self, transcript_urls: List[str] = None, filing_urls: List[str] = None, rbi_urls: List[str] = None) -> List[NewsItem]:
        transcript_urls = transcript_urls or []
        filing_urls = filing_urls or []
        rbi_urls = rbi_urls or []
        rss_task = asyncio.create_task(self.fetch_rss())
        tx_task = asyncio.create_task(self.fetch_transcripts(transcript_urls))
        fil_task = asyncio.create_task(self.fetch_filings(filing_urls))
        rbi_task = asyncio.create_task(self.fetch_rbi_statements(rbi_urls))
        rss, tx, fil, rbi = await asyncio.gather(rss_task, tx_task, fil_task, rbi_task)
        return [*rss, *tx, *fil, *rbi]
