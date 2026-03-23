"""NLP pipeline: sentiment (FinBERT if available), NER, topics, and event extraction."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

try:
    from transformers import pipeline
except Exception:  # pragma: no cover
    pipeline = None  # type: ignore

try:
    import spacy
except Exception:  # pragma: no cover
    spacy = None  # type: ignore


@dataclass
class SentimentResult:
    score: float  # [-1, 1]
    label: str
    raw: Optional[dict] = None


@dataclass
class EventExtraction:
    events: List[str]
    entities: List[str]
    topics: List[str]


class NLPProcessor:
    """Runs sentiment, NER, event extraction, and topic hints."""

    def __init__(self, model: str = "ProsusAI/finbert") -> None:
        self.model = model
        self._sentiment = None
        if pipeline:
            try:
                self._sentiment = pipeline("text-classification", model=model)
            except Exception:
                self._sentiment = None
        self._ner = spacy.load("en_core_web_sm") if spacy else None

    async def sentiment(self, text: str) -> SentimentResult:
        if self._sentiment is None:
            # Fallback heuristic
            positive = {"beat", "growth", "upgrade", "surge"}
            negative = {"downgrade", "miss", "loss", "probe", "default"}
            score = 0.0
            lower = text.lower()
            score += sum(1 for w in positive if w in lower)
            score -= sum(1 for w in negative if w in lower)
            score = float(np.tanh(score))
            label = "positive" if score > 0 else "negative" if score < 0 else "neutral"
            return SentimentResult(score=score, label=label)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._sentiment(text[:4000]))  # type: ignore[arg-type]
        best = result[0]
        score = float(best.get("score", 0.0))
        if best.get("label", "").upper().startswith("NEG"):
            score = -score
        return SentimentResult(score=score, label=str(best.get("label", "unknown")), raw=best)

    async def ner(self, text: str) -> List[str]:
        if not self._ner:
            return []
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(None, lambda: self._ner(text[:4000]))
        return [ent.text for ent in doc.ents if ent.label_ in {"ORG", "PRODUCT", "GPE"}]

    async def topics(self, texts: List[str], k: int = 5) -> List[str]:
        corpus = [t.lower() for t in texts]
        tokens = " ".join(corpus).split()
        if not tokens:
            return []
        # crude topic sketch: top frequent tokens minus stopwords
        stop = {"the", "and", "of", "to", "a", "in"}
        freq: Dict[str, int] = {}
        for tok in tokens:
            if tok in stop or len(tok) < 4:
                continue
            freq[tok] = freq.get(tok, 0) + 1
        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in ranked[:k]]

    async def extract_events(self, text: str) -> EventExtraction:
        markers = {
            "merger": ["merger", "acquire", "acquisition", "deal"],
            "earnings": ["earnings", "eps", "revenue", "guidance"],
            "product": ["launch", "product", "ship"],
            "regulatory": ["probe", "fine", "regulator", "approval", "license"],
        }
        found = []
        lower = text.lower()
        for name, words in markers.items():
            if any(w in lower for w in words):
                found.append(name)
        ents = await self.ner(text)
        topics = await self.topics([text])
        return EventExtraction(events=found, entities=ents, topics=topics)
