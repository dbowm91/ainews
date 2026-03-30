"""Tests for new service modules created in the improvement plan.

Covers: article_parser, pagination, config_unified, logging_utils,
health, dead_letter, validation, audit, timeout, degradation, DNS cache.
"""

import json
import time
import pytest
from unittest.mock import MagicMock, patch


# ─── article_parser ────────────────────────────────────────────


class TestArticleParser:
    def test_parse_article_json_with_valid_json(self):
        from services.article_parser import parse_article_json

        article = MagicMock()
        article.final_article = json.dumps({"headline": "Test", "tldr": "Summary"})
        article.summary = None

        parse_article_json(article)

        assert article._fa == {"headline": "Test", "tldr": "Summary"}
        assert article._summary is None

    def test_parse_article_json_with_invalid_json(self):
        from services.article_parser import parse_article_json

        article = MagicMock()
        article.final_article = "not json"
        article.summary = "also not json"

        parse_article_json(article)

        assert article._fa is None
        assert article._summary is None

    def test_parse_article_json_with_none(self):
        from services.article_parser import parse_article_json

        article = MagicMock()
        article.final_article = None
        article.summary = None

        parse_article_json(article)

        assert article._fa is None
        assert article._summary is None

    def test_parse_articles_batch(self):
        from services.article_parser import parse_articles

        articles = []
        for i in range(3):
            a = MagicMock()
            a.final_article = json.dumps({"headline": f"Article {i}"})
            a.summary = None
            articles.append(a)

        result = parse_articles(articles)

        assert len(result) == 3
        for i, a in enumerate(result):
            assert a._fa["headline"] == f"Article {i}"


# ─── pagination ────────────────────────────────────────────────


class TestPagination:
    def test_paginate_query_basic(self, app):
        from services.pagination import paginate_query
        from models import Article, Source
        from extensions import db

        source = Source(source_key="pg", name="PG", source_type="rss", feed_url="")
        db.session.add(source)
        db.session.flush()

        for i in range(5):
            db.session.add(
                Article(
                    source_id=source.id,
                    external_id=f"pg_{i}",
                    original_title=f"Article {i}",
                    pipeline_status="done",
                )
            )
        db.session.commit()

        from models import Article as A

        q = A.query.order_by(A.id)
        items, has_next, next_page = paginate_query(q, page=1, per_page=3)

        assert len(items) == 3
        assert has_next is True
        assert next_page == 2

    def test_paginate_query_last_page(self, app):
        from services.pagination import paginate_query
        from models import Article, Source
        from extensions import db

        source = Source(source_key="pg2", name="PG2", source_type="rss", feed_url="")
        db.session.add(source)
        db.session.flush()

        for i in range(3):
            db.session.add(
                Article(
                    source_id=source.id,
                    external_id=f"pg2_{i}",
                    original_title=f"Article {i}",
                    pipeline_status="done",
                )
            )
        db.session.commit()

        from models import Article as A

        q = A.query.order_by(A.id)
        items, has_next, next_page = paginate_query(q, page=1, per_page=10)

        assert len(items) == 3
        assert has_next is False
        assert next_page == 2

    def test_escape_like_pattern(self):
        from services.pagination import _escape_like_pattern

        assert _escape_like_pattern("100%") == "100\\%"
        assert _escape_like_pattern("file_name") == "file\\_name"
        assert _escape_like_pattern("normal text") == "normal text"

    def test_build_fts_query(self):
        from services.pagination import _build_fts_query

        assert _build_fts_query("python") == '"python"'
        assert _build_fts_query("python ai") == '"python" AND "ai"'
        assert _build_fts_query("") == ""
        assert _build_fts_query("   ") == ""
        assert _build_fts_query("python*") == '"python"'


# ─── config_unified ────────────────────────────────────────────


class TestConfigUnified:
    def test_from_env(self):
        from services.config_unified import AppConfig

        config = AppConfig.from_env()
        assert config.pipeline.max_stage_retries >= 1
        assert config.security.max_content_length > 0
        assert config.sources.max_consecutive_failures >= 1

    def test_from_flask(self, app):
        from services.config_unified import AppConfig

        config = AppConfig.from_flask()
        assert config.pipeline.max_stage_retries == app.config["MAX_STAGE_RETRIES"]
        assert config.security.max_content_length == app.config["MAX_CONTENT_LENGTH"]

    def test_get_config_caching(self, app):
        from services.config_unified import get_config, reset_config

        reset_config()
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2
        reset_config()


# ─── logging_utils ─────────────────────────────────────────────


class TestLoggingUtils:
    def test_log_pipeline_event(self):
        from services.logging_utils import log_pipeline_event

        with patch("services.logging_utils.logger") as mock_logger:
            log_pipeline_event("write", "started", article_id=42, run_id=1)
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args
            assert call_kwargs[1]["extra"]["stage"] == "write"
            assert call_kwargs[1]["extra"]["article_id"] == 42

    def test_log_article_event(self):
        from services.logging_utils import log_article_event

        with patch("services.logging_utils.logger") as mock_logger:
            log_article_event(42, "processed", level="info")
            mock_logger.info.assert_called_once()

    def test_log_admin_event(self):
        from services.logging_utils import log_admin_event

        with patch("services.logging_utils.logger") as mock_logger:
            log_admin_event("config_reload", user="admin")
            mock_logger.info.assert_called_once()

    def test_log_duration(self):
        from services.logging_utils import log_duration

        with patch("services.logging_utils.logger") as mock_logger:
            with log_duration("test_op"):
                time.sleep(0.01)
            mock_logger.info.assert_called_once()
            assert "duration_ms" in mock_logger.info.call_args[1]["extra"]


# ─── health ────────────────────────────────────────────────────


class TestHealth:
    def test_health_result_is_healthy(self):
        from services.health import HealthResult

        r = HealthResult(status="ok", checks={})
        assert r.is_healthy is True
        assert r.to_dict()["status"] == "ok"

    def test_health_result_degraded(self):
        from services.health import HealthResult

        r = HealthResult(status="degraded", checks={"redis": "error"})
        assert r.is_healthy is False

    def test_check_database(self, app):
        from services.health import check_database

        name, status = check_database()
        assert name == "database"
        assert status == "ok"


# ─── dead_letter ───────────────────────────────────────────────


class TestDeadLetter:
    def test_dead_letter_article(self, app, create_source, create_article):
        from services.dead_letter import dead_letter_article

        source = create_source(source_key="dl_test2")
        article = create_article(source=source, pipeline_status="writing")
        result = dead_letter_article(article, reason="test dead letter", stage="write")

        assert result is True
        assert article.pipeline_status == "failed"
        assert "Dead-lettered" in article.last_error

    def test_retry_dead_letter(self, app, create_source, create_article):
        from services.dead_letter import retry_dead_letter

        source = create_source(source_key="dl_test3")
        article = create_article(source=source, pipeline_status="failed")
        result = retry_dead_letter(article)

        assert result is True
        assert article.pipeline_status == "pending"
        assert article.retry_count == 0

    def test_get_dead_lettered_articles(self, app, create_source, create_article):
        from services.dead_letter import get_dead_lettered_articles

        source = create_source(source_key="dl_test")
        create_article(source=source, pipeline_status="failed")
        create_article(source=source, pipeline_status="done", external_id="dl_done")

        articles = get_dead_lettered_articles(limit=10)
        assert len(articles) == 1
        assert articles[0].pipeline_status == "failed"


# ─── validation ────────────────────────────────────────────────


class TestValidation:
    def test_validate_slug(self):
        from services.validation import validate_slug, ValidationError

        assert validate_slug("my-slug") == "my-slug"
        assert validate_slug("abc123") == "abc123"

        with pytest.raises(ValidationError):
            validate_slug("Invalid Slug!")

        with pytest.raises(ValidationError):
            validate_slug("")

    def test_validate_category(self):
        from services.validation import validate_category, ValidationError

        assert validate_category("ai") == "ai"
        assert validate_category("my-category") == "my-category"

        with pytest.raises(ValidationError):
            validate_category("a" * 100)  # too long

    def test_validate_token(self):
        from services.validation import validate_token, ValidationError

        assert validate_token("abc123DEF_-") == "abc123DEF_-"

        with pytest.raises(ValidationError):
            validate_token("")

    def test_validate_page(self):
        from services.validation import validate_page

        assert validate_page(1) == 1
        assert validate_page(0) == 1
        assert validate_page(-5) == 1
        assert validate_page(99999) == 10000

    def test_validate_per_page(self):
        from services.validation import validate_per_page

        assert validate_per_page(10) == 10
        assert validate_per_page(0) == 1
        assert validate_per_page(999) == 100

    def test_sanitize_search_query(self):
        from services.validation import sanitize_search_query

        assert sanitize_search_query("  hello world  ") == "hello world"
        assert sanitize_search_query("a" * 300) == "a" * 200

    def test_validate_bulk_ids(self):
        from services.validation import validate_bulk_ids, ValidationError

        assert validate_bulk_ids([1, 2, 3]) == [1, 2, 3]

        with pytest.raises(ValidationError):
            validate_bulk_ids([])

        with pytest.raises(ValidationError):
            validate_bulk_ids([1, -1, 3])

        with pytest.raises(ValidationError):
            validate_bulk_ids("not a list")


# ─── audit ─────────────────────────────────────────────────────


class TestAudit:
    def test_log_admin_action_logs(self):
        from services.audit import log_admin_action

        with patch("services.audit.logger") as mock_logger:
            log_admin_action("article_edit", target_type="article", target_id=42)
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["extra"]["audit"] is True
            assert call_kwargs["extra"]["action"] == "article_edit"


# ─── timeout ───────────────────────────────────────────────────


class TestTimeout:
    def test_timeout_decorator_success(self):
        from services.timeout import timeout

        @timeout(5, operation="fast_op")
        def fast():
            return 42

        assert fast() == 42

    def test_timeout_decorator_raises(self):
        from services.timeout import timeout, OperationTimeoutError
        import time

        @timeout(0.1, operation="slow_op")
        def slow():
            time.sleep(1)

        with pytest.raises(OperationTimeoutError):
            slow()

    def test_timeout_budget(self):
        from services.timeout import TimeoutBudget

        budget = TimeoutBudget(total=10)
        assert budget.remaining > 0
        assert budget.is_expired is False

    def test_timeout_budget_expired(self):
        from services.timeout import TimeoutBudget, OperationTimeoutError

        budget = TimeoutBudget(total=0.01)
        time.sleep(0.02)
        assert budget.is_expired is True

        with pytest.raises(OperationTimeoutError):
            budget.check("test")


# ─── degradation ───────────────────────────────────────────────


class TestDegradation:
    def test_degrade_on_failure_calls_fallback(self):
        from services.degradation import degrade_on_failure

        def primary():
            raise ValueError("fail")

        def fallback():
            return "fallback_result"

        @degrade_on_failure(fallback=fallback, exceptions=(ValueError,))
        def wrapped():
            return primary()

        assert wrapped() == "fallback_result"

    def test_degrade_on_failure_passes_through(self):
        from services.degradation import degrade_on_failure

        def fallback():
            return "fallback"

        @degrade_on_failure(fallback=fallback)
        def success():
            return "success"

        assert success() == "success"

    def test_fallback_chain_success(self):
        from services.degradation import fallback_chain

        result = fallback_chain(
            lambda: 1 / 0,
            lambda: "second",
            lambda: "third",
        )()
        assert result == "second"

    def test_fallback_chain_all_fail(self):
        from services.degradation import fallback_chain

        with pytest.raises(ZeroDivisionError):
            fallback_chain(
                lambda: 1 / 0,
                lambda: 2 / 0,
            )()

    def test_safe_default(self):
        from services.degradation import safe_default

        @safe_default(default=[], exceptions=(ValueError,))
        def failing():
            raise ValueError("oops")

        assert failing() == []

        @safe_default(default=42)
        def succeeding():
            return 100

        assert succeeding() == 100


# ─── DNS cache ─────────────────────────────────────────────────


class TestDNSCache:
    def test_cache_hit_miss_stats(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=10, ttl=60)
        cache.set("example.com", ["1.2.3.4"])

        result = cache.get("example.com")
        assert result == ["1.2.3.4"]

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 1.0

        cache.get("nonexistent.com")
        stats = cache.get_stats()
        assert stats["misses"] == 1

    def test_cache_eviction(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=2, ttl=60)
        cache.set("a.com", ["1.1.1.1"])
        cache.set("b.com", ["2.2.2.2"])
        cache.set("c.com", ["3.3.3.3"])  # should evict oldest (a.com)

        assert cache.get("a.com") is None
        assert cache.get("b.com") == ["2.2.2.2"]
        assert cache.get("c.com") == ["3.3.3.3"]

    def test_cache_ttl_expiry(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=10, ttl=0.01)
        cache.set("fast.com", ["1.1.1.1"])
        time.sleep(0.02)

        assert cache.get("fast.com") is None

    def test_cache_clear(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=10, ttl=60)
        cache.set("a.com", ["1.1.1.1"])
        cache.clear()

        stats = cache.get_stats()
        assert stats["size"] == 0


# ─── metrics expansion ─────────────────────────────────────────


class TestMetricsExpansion:
    def test_time_histogram(self):
        from services.metrics import time_histogram, get_metrics, reset_metrics

        reset_metrics()
        with time_histogram("test.duration"):
            time.sleep(0.01)

        metrics = get_metrics().get_metrics()
        assert "test.duration" in metrics["histograms"]
        assert metrics["histograms"]["test.duration"]["count"] == 1

    def test_record_request(self):
        from services.metrics import record_request, get_metrics, reset_metrics

        reset_metrics()
        record_request("GET", "/api/test", 200, 42.5)

        metrics = get_metrics().get_metrics()
        # Label format: {key1=val1,key2=val2} (no spaces after commas)
        assert "http_requests_total{method=GET,status=200}" in metrics["counters"]
