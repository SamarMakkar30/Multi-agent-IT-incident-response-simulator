"""Pure-Python Okapi BM25 retrieval engine for runbooks and memory.

Transparent, deterministic, and fully explainable without external vector databases.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Generic, TypeVar

T = TypeVar("T")

STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


def tokenize(text: str) -> list[str]:
    """Tokenize string into lowercase alphanumeric words, filtering stopwords."""
    tokens = re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


class SearchResult(Generic[T]):
    """Ranked search result with explicit doc_id and BM25 score."""

    def __init__(self, doc_id: str, score: float, document: T) -> None:
        self.doc_id = doc_id
        self.score = score
        self.document = document

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "score": round(self.score, 4),
            "document": self.document,
        }

    def __repr__(self) -> str:
        return f"SearchResult(doc_id='{self.doc_id}', score={self.score:.4f})"


class BM25Index(Generic[T]):
    """Okapi BM25 ranker (k1=1.5, b=0.75)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._doc_ids: list[str] = []
        self._documents: list[T] = []
        self._doc_lengths: list[int] = []
        self._doc_freqs: list[Counter[str]] = []
        self._df: Counter[str] = Counter()  # Number of documents containing term
        self._avgdl: float = 0.0

    def add_document(self, doc_id: str, text: str, document: T) -> None:
        """Add a document to the index."""
        tokens = tokenize(text)
        freqs = Counter(tokens)
        self._doc_ids.append(doc_id)
        self._documents.append(document)
        self._doc_lengths.append(len(tokens))
        self._doc_freqs.append(freqs)
        for term in freqs:
            self._df[term] += 1
        self._avgdl = sum(self._doc_lengths) / max(len(self._doc_lengths), 1)

    def search(self, query: str, top_k: int = 3) -> list[SearchResult[T]]:
        """Search the corpus and return top_k ranked documents."""
        q_tokens = tokenize(query)
        if not q_tokens or not self._doc_ids:
            return []

        n_docs = len(self._doc_ids)
        scores: list[float] = [0.0] * n_docs

        for term in q_tokens:
            if term not in self._df:
                continue
            df_val = self._df[term]
            # Standard Okapi BM25 Robertson-Spärck Jones IDF
            idf = math.log(1.0 + (n_docs - df_val + 0.5) / (df_val + 0.5))

            for i, freqs in enumerate(self._doc_freqs):
                tf = freqs[term]
                if tf <= 0:
                    continue
                doc_len = self._doc_lengths[i]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self._avgdl))
                scores[i] += idf * (numerator / denominator)

        # Pair scores with document metadata
        ranked = [
            SearchResult(doc_id=self._doc_ids[i], score=scores[i], document=self._documents[i])
            for i in range(n_docs)
            if scores[i] > 0.0
        ]
        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[:top_k]
