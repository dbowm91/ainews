"""Tests for hybrid search and embedding generation tasks."""

from unittest.mock import MagicMock, patch

import pytest


class TestHybridSearchProviderMethods:
    """Tests for HybridSearchProvider methods."""

    def test_search_delegates_to_fts_provider(self):
        from services.search.hybrid import HybridSearchProvider

        provider = HybridSearchProvider()
        with patch.object(provider._fts_provider, "search") as mock_search:
            mock_search.return_value = [{"id": 1, "rank": 0.5}]
            result = provider.search("test", limit=10)

            mock_search.assert_called_once_with("test", limit=10)
            assert result == [{"id": 1, "rank": 0.5}]

    def test_hybrid_search_validates_vector_weight(self):
        from services.search.hybrid import HybridSearchProvider

        provider = HybridSearchProvider()

        with pytest.raises(ValueError, match="vector_weight must be between 0 and 1"):
            provider.hybrid_search("test", vector_weight=1.5)

        with pytest.raises(ValueError, match="vector_weight must be between 0 and 1"):
            provider.hybrid_search("test", vector_weight=-0.5)


class TestSearchResultItem:
    """Tests for SearchResultItem dataclass."""

    def test_search_result_item_creation(self):
        from services.search.hybrid import SearchResultItem

        item = SearchResultItem(
            id=42,
            fts_rank=0.8,
            vector_score=0.6,
            combined_score=0.7,
        )
        assert item.id == 42
        assert item.fts_rank == 0.8
        assert item.vector_score == 0.6
        assert item.combined_score == 0.7


class TestSearchPage:
    """Tests for SearchPage model."""

    def test_search_page_default_vector_available(self):
        from services.search.hybrid import SearchPage, SearchResultItem

        page = SearchPage(
            items=[SearchResultItem(id=1, fts_rank=0.5, vector_score=0.0, combined_score=0.0)],
            total=1,
            page=1,
            per_page=20,
        )
        assert page.vector_available is True

    def test_search_page_explicit_vector_available(self):
        from services.search.hybrid import SearchPage

        page = SearchPage(
            items=[],
            total=0,
            page=1,
            per_page=20,
            vector_available=False,
        )
        assert page.vector_available is False

    def test_search_page_model_dump(self):
        from services.search.hybrid import SearchPage, SearchResultItem

        page = SearchPage(
            items=[SearchResultItem(id=1, fts_rank=0.5, vector_score=0.3, combined_score=0.4)],
            total=1,
            page=1,
            per_page=20,
        )
        data = page.model_dump()
        assert data["items"][0]["id"] == 1
        assert data["vector_available"] is True


class TestCosineSimilarity:
    """Tests for cosine_similarity utility."""

    def test_cosine_similarity_identical_vectors(self):
        from services.search.hybrid import cosine_similarity

        vec = [1.0, 0.0, 0.0]
        result = cosine_similarity(vec, vec)
        assert result == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal_vectors(self):
        from services.search.hybrid import cosine_similarity

        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(0.0)

    def test_cosine_similarity_opposite_vectors(self):
        from services.search.hybrid import cosine_similarity

        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(-1.0)

    def test_cosine_similarity_empty_vectors(self):
        from services.search.hybrid import cosine_similarity

        result = cosine_similarity([], [])
        assert result == 0.0


class TestReciprocalRankFusion:
    """Tests for reciprocal_rank_fusion utility."""

    def test_rrf_empty_lists(self):
        from services.search.hybrid import reciprocal_rank_fusion

        result = reciprocal_rank_fusion([])
        assert result == []

    def test_rrf_single_list(self):
        from services.search.hybrid import reciprocal_rank_fusion

        results = [[{"id": 1}, {"id": 2}, {"id": 3}]]
        fused = reciprocal_rank_fusion(results, k=60)
        assert len(fused) == 3
        assert fused[0]["id"] == 1
        assert fused[1]["id"] == 2

    def test_rrf_multiple_lists(self):
        from services.search.hybrid import reciprocal_rank_fusion

        results = [
            [{"id": 1}, {"id": 2}],
            [{"id": 2}, {"id": 3}],
        ]
        fused = reciprocal_rank_fusion(results, k=60)
        ids = [r["id"] for r in fused]
        assert 2 in ids
        assert 1 in ids
        assert 3 in ids


class TestSearchArticlesFunction:
    """Tests for search_articles function using mocks."""

    @patch("services.search.hybrid.SENTENCE_TRANSFORMERS_AVAILABLE", False)
    @patch("services.search.hybrid.get_db_search_provider")
    def test_fts_mode_returns_fallback(self, mock_get_provider):
        from services.search.hybrid import search_articles, SearchPage

        mock_provider = MagicMock()
        mock_provider.search.return_value = [{"id": 1, "rank": 0.9}]
        mock_get_provider.return_value = mock_provider

        result = search_articles("test", mode="fts")

        assert isinstance(result, SearchPage)
        assert result.vector_available is False

    @patch("services.search.hybrid.SENTENCE_TRANSFORMERS_AVAILABLE", True)
    @patch("services.search.hybrid.get_db_search_provider")
    @patch("services.search.hybrid.generate_embedding")
    def test_hybrid_mode_with_embeddings(self, mock_gen_emb, mock_get_provider):
        from services.search.hybrid import search_articles, SearchPage

        mock_gen_emb.return_value = [0.1] * 384

        mock_provider = MagicMock()
        mock_provider.hybrid_search.return_value = [
            {"id": 1, "fts_rank": 0.8, "vector_score": 0.7, "combined_score": 0.75},
        ]
        mock_get_provider.return_value = mock_provider

        result = search_articles("test", mode="hybrid")

        assert isinstance(result, SearchPage)
        assert result.vector_available is True

    @patch("services.search.hybrid.SENTENCE_TRANSFORMERS_AVAILABLE", False)
    @patch("services.search.hybrid.get_db_search_provider")
    def test_hybrid_mode_without_st_falls_back(self, mock_get_provider):
        from services.search.hybrid import search_articles, SearchPage

        mock_provider = MagicMock()
        mock_provider.hybrid_search.return_value = [{"id": 1, "fts_rank": 0.9, "vector_score": 0.0, "combined_score": 0.45}]
        mock_get_provider.return_value = mock_provider

        result = search_articles("test", mode="hybrid")

        assert isinstance(result, SearchPage)
        assert result.vector_available is False

    @patch("services.search.hybrid.get_db_search_provider")
    def test_per_page_limit_enforced(self, mock_get_provider):
        from services.search.hybrid import search_articles, SearchPage

        mock_provider = MagicMock()
        mock_provider.search.return_value = []
        mock_get_provider.return_value = mock_provider

        result = search_articles("test", mode="fts", per_page=500)

        assert isinstance(result, SearchPage)
        assert result.per_page <= 100