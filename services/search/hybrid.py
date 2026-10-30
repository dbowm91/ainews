"""Hybrid search combining SQLite FTS5 with vector similarity search."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import text

from extensions import db
from services.circuit_breaker import circuit_protected
from services.embeddings import (
    SENTENCE_TRANSFORMERS_AVAILABLE,
    deserialize_embedding,
    generate_embedding,
)
from services.publication import published_sql_predicate
from services.search.base import SearchProvider, get_db_search_provider, register_db_search_provider
from services.search.sqlite_fts import (
    SQLiteFTSProvider,
    _build_fts_query,
)

logger = logging.getLogger(__name__)


@dataclass
class SearchResultItem:
    id: int
    fts_rank: float
    vector_score: float
    combined_score: float


class SearchPage(BaseModel):
    items: list[SearchResultItem]
    total: int
    page: int
    per_page: int
    vector_available: bool = True


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        vec1: First vector.
        vec2: Second vector.

    Returns:
        Cosine similarity score between -1 and 1.
    """
    if not vec1 or not vec2:
        return 0.0

    # Compute dot product
    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))

    # Compute norms
    norm_a = sum(a * a for a in vec1) ** 0.5
    norm_b = sum(b * b for b in vec2) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def reciprocal_rank_fusion(
    results_lists: list[list[dict]], k: int = 60
) -> list[dict]:
    """Combine multiple result lists using Reciprocal Rank Fusion (RRF).

    Args:
        results_lists: List of result lists, each containing dicts with 'id'.
        k: RRF constant for smoothing (default 60).

    Returns:
        Combined and re-ranked list of dicts with 'id' and 'rrf_score'.
    """
    scores = {}

    for results in results_lists:
        for rank, item in enumerate(results, start=1):
            doc_id = item["id"]
            if doc_id not in scores:
                scores[doc_id] = {"id": doc_id, "rrf_score": 0.0, "sources": []}
            scores[doc_id]["rrf_score"] += 1.0 / (k + rank)
            scores[doc_id]["sources"].append(item.get("source", "unknown"))

    combined = list(scores.values())
    combined.sort(key=lambda x: x["rrf_score"], reverse=True)

    return combined


@register_db_search_provider("hybrid")
class HybridSearchProvider(SearchProvider):
    """Hybrid search provider combining FTS5 and vector similarity."""

    def __init__(self):
        self._fts_provider = SQLiteFTSProvider()

    def search(self, query: str, limit: int = 10, **kwargs) -> list[dict]:
        """Search using FTS5 only (for compatibility with base class).

        For true hybrid search, use hybrid_search() method.
        """
        return list(self._fts_provider.search(query, limit=limit, **kwargs))

    @circuit_protected("search_hybrid")
    def hybrid_search(
        self, query: str, limit: int = 10, vector_weight: float = 0.5, **kwargs
    ) -> list[dict]:
        """Search articles using hybrid FTS + vector similarity.

        Args:
            query: Search query string.
            limit: Maximum number of results.
            vector_weight: Weight for vector similarity (0-1). Higher values
                          prioritize vector search over FTS.
            **kwargs: Additional arguments including 'category', 'page', 'per_page'.

        Returns:
            List of dicts with 'id', 'fts_rank', 'vector_score', 'combined_score'.
        """
        if not 0 <= vector_weight <= 1:
            raise ValueError("vector_weight must be between 0 and 1")

        page = kwargs.get("page", 1)
        per_page = kwargs.get("per_page", limit)
        category = kwargs.get("category")

        # Fetch more candidates than needed for re-ranking
        candidate_limit = max(limit * 3, 50)

        # Get FTS results
        fts_results = self._get_fts_results(
            query, limit=candidate_limit, category=category
        )

        # Get vector similarity results
        vector_results = self._get_vector_results(
            query, limit=candidate_limit, category=category
        )

        # Combine results
        combined = self._combine_results(
            fts_results, vector_results, vector_weight=vector_weight
        )

        # Apply pagination
        offset = (page - 1) * per_page
        return combined[offset : offset + per_page]

    def _get_fts_results(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> list[dict]:
        """Get FTS5 search results."""
        fts_query = _build_fts_query(query)
        if not fts_query:
            return []

        if category:
            sql = text(f"""
                SELECT a.id, rank
                FROM articles_fts fts
                JOIN articles a ON a.id = fts.rowid
                WHERE articles_fts MATCH :query
                  AND {published_sql_predicate('a')}
                  AND a.category = :category
                ORDER BY rank
                LIMIT :limit
            """)
            params = {"query": fts_query, "category": category, "limit": limit}
        else:
            sql = text(f"""
                SELECT a.id, rank
                FROM articles_fts fts
                JOIN articles a ON a.id = fts.rowid
                WHERE articles_fts MATCH :query
                  AND {published_sql_predicate('a')}
                ORDER BY rank
                LIMIT :limit
            """)
            params = {"query": fts_query, "limit": limit}

        result = db.session.execute(sql, params)
        return [
            {"id": r[0], "fts_rank": r[1], "source": "fts"} for r in result.fetchall()
        ]

    def _get_vector_results(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> list[dict]:
        """Get vector similarity search results."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.debug("sentence-transformers not available, skipping vector search")
            return []

        query_embedding = generate_embedding(query)
        if not query_embedding:
            return []

        max_candidates = int(os.environ.get("HYBRID_SEARCH_MAX_CANDIDATES", "500"))

        # Fetch articles with embeddings
        if category:
            sql = text(f"""
                SELECT id, embedding, category
                FROM articles
                WHERE {published_sql_predicate('articles')}
                  AND category = :category
                  AND embedding IS NOT NULL
                  AND embedding != ''
                ORDER BY id DESC
                LIMIT :limit
            """)
            params = {"category": category, "limit": max_candidates}
        else:
            sql = text(f"""
                SELECT id, embedding, category
                FROM articles
                WHERE {published_sql_predicate('articles')}
                  AND embedding IS NOT NULL
                  AND embedding != ''
                ORDER BY id DESC
                LIMIT :limit
            """)
            params = {"limit": max_candidates}

        result = db.session.execute(sql, params)
        articles = result.fetchall()

        # Compute similarities
        scored = []
        for row in articles:
            article_id = row[0]
            embedding_str = row[1]
            article_embedding = deserialize_embedding(embedding_str)

            if article_embedding:
                similarity = cosine_similarity(query_embedding, article_embedding)
                scored.append(
                    {
                        "id": article_id,
                        "vector_score": similarity,
                        "source": "vector",
                    }
                )

        # Sort by similarity (highest first)
        scored.sort(key=lambda x: x["vector_score"], reverse=True)
        return scored[:limit]

    def _combine_results(
        self,
        fts_results: list[dict],
        vector_results: list[dict],
        vector_weight: float = 0.5,
    ) -> list[dict]:
        """Combine FTS and vector results with weighted scoring.

        Args:
            fts_results: Results from FTS search.
            vector_results: Results from vector search.
            vector_weight: Weight for vector scores (0-1).

        Returns:
            Combined and re-ranked results.
        """
        fts_weight = 1.0 - vector_weight

        # Build score maps
        fts_scores = {}
        for rank, item in enumerate(fts_results, start=1):
            doc_id = item["id"]
            # Convert FTS rank (lower is better) to a 0-1 score (higher is better)
            fts_scores[doc_id] = {"fts_rank": item.get("fts_rank", rank), "fts_rank_pos": rank}

        vector_scores = {}
        for rank, item in enumerate(vector_results, start=1):
            doc_id = item["id"]
            vector_scores[doc_id] = {
                "vector_score": item.get("vector_score", 0.0),
                "vector_rank": rank,
            }

        # Combine all document IDs
        all_ids = set(fts_scores.keys()) | set(vector_scores.keys())

        combined = []
        for doc_id in all_ids:
            fts_data = fts_scores.get(doc_id, {"fts_rank": 0, "fts_rank_pos": len(fts_results) + 1})
            vec_data = vector_scores.get(doc_id, {"vector_score": 0.0, "vector_rank": len(vector_results) + 1})

            # Normalize FTS rank (lower rank value is better, convert to 0-1 score)
            fts_rank_pos = fts_data["fts_rank_pos"]
            fts_score_normalized = 1.0 / fts_rank_pos if fts_rank_pos > 0 else 0.0

            # Vector score is already cosine similarity (-1 to 1), normalize to 0-1
            vector_score = vec_data["vector_score"]
            vector_score_normalized = (vector_score + 1.0) / 2.0

            # Weighted combination
            combined_score = (
                fts_weight * fts_score_normalized + vector_weight * vector_score_normalized
            )

            combined.append(
                {
                    "id": doc_id,
                    "fts_rank": fts_data.get("fts_rank", 0),
                    "vector_score": vector_score,
                    "combined_score": combined_score,
                }
            )

        # Sort by combined score (highest first)
        combined.sort(key=lambda x: x["combined_score"], reverse=True)
        return combined

    def index_article(self, article) -> None:
        """Index or update an article in both FTS and vector index."""
        self._fts_provider.index_article(article)

    def delete_article(self, article_id: int) -> None:
        """Remove an article from both FTS and vector index."""
        self._fts_provider.delete_article(article_id)

    def search_admin(
        self, query: str, limit: int = 1000, **kwargs
    ) -> list[int]:
        """Delegate to FTS provider for admin search."""
        return list(self._fts_provider.search_admin(query, limit=limit, **kwargs))


def search_articles(
    query: str,
    *,
    mode: str = "fts",
    category: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> SearchPage:
    """Search articles with mode=fts (FTS-only) or mode=hybrid (FTS+vector).

    Args:
        query: Search query string.
        mode: Search mode - "fts" for FTS-only, "hybrid" for FTS+vector similarity.
        category: Optional category filter.
        page: Page number (1-indexed).
        per_page: Results per page.

    Returns:
        SearchPage with items, total, page, per_page, and vector_available flag.
    """
    provider = get_db_search_provider("hybrid")
    per_page = min(per_page, 100)

    if mode == "hybrid":
        vector_available = SENTENCE_TRANSFORMERS_AVAILABLE
        results = provider.hybrid_search(
            query,
            limit=per_page * 3,
            category=category,
            page=page,
            per_page=per_page,
        )
        if not vector_available:
            logger.debug("Hybrid mode requested but sentence-transformers unavailable, using FTS fallback")
        items = [
            SearchResultItem(
                id=r["id"],
                fts_rank=r.get("fts_rank", 0.0),
                vector_score=r.get("vector_score", 0.0),
                combined_score=r.get("combined_score", 0.0),
            )
            for r in results
        ]
        return SearchPage(
            items=items,
            total=len(items),
            page=page,
            per_page=per_page,
            vector_available=vector_available,
        )
    else:
        fts_results = provider.search(query, limit=per_page, category=category, page=page, per_page=per_page)
        items = [
            SearchResultItem(
                id=r["id"],
                fts_rank=r.get("rank", 0.0),
                vector_score=0.0,
                combined_score=0.0,
            )
            for r in fts_results
        ]
        return SearchPage(
            items=items,
            total=len(items),
            page=page,
            per_page=per_page,
            vector_available=False,
        )
