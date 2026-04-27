"""Tests for services/trend_memory.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


class TestTrendMemory:
    """Tests for trend memory system."""

    def test_propose_trend_memory_is_callable(self, app, create_article):
        """propose_trend_memory should be callable."""
        with app.app_context():
            from services.trend_memory import propose_trend_memory

            assert callable(propose_trend_memory)

    def test_get_memory_for_topics_is_callable(self, app, create_article, mock_redis_client):
        """get_memory_for_topics should be callable."""
        from services.trend_memory import get_memory_for_topics

        assert callable(get_memory_for_topics)

    def test_get_config_is_callable(self, app):
        """_get_config should be callable."""
        from services.trend_memory import _get_config

        config = _get_config()
        assert config is not None
        assert hasattr(config, "ttl_days_low")

    def test_propose_trend_memory_creates_entries(self, app, create_article):
        """propose_trend_memory should create TrendMemory entries in the database."""
        from models import TrendMemory
        from services.trend_memory import propose_trend_memory

        with app.app_context():
            article = create_article(
                pipeline_status="done",
                final_article='{"headline": "Test Article", "body": "Test body content"}',
            )
            article.topics = ["AI", "machine-learning"]
            article.summary = "Test summary for the article"
            from extensions import db
            db.session.commit()

            with patch("services.trend_memory.get_provider_for_role") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.chat_structured.return_value = MagicMock(
                    entries=[
                        MagicMock(topic="AI", importance=2, signal="Test signal about AI"),
                        MagicMock(topic="machine-learning", importance=1, signal="ML trend signal"),
                    ]
                )
                mock_get_provider.return_value = (mock_provider, "gpt-4", 2048, "openai")

                propose_trend_memory(article)

            entries = TrendMemory.query.filter_by(source_article_id=article.id).all()
            assert len(entries) == 2, f"Expected 2 TrendMemory entries, got {len(entries)}"

    def test_get_memory_for_topics_returns_matching_entries(self, app, create_article):
        """get_memory_for_topics should return entries matching the given topics."""
        from models import TrendMemory
        from services.trend_memory import MemoryImportance, get_memory_for_topics

        with app.app_context():
            entry = TrendMemory(
                topic="AI",
                signal="AI safety is important",
                importance=MemoryImportance.HIGH,
                expires_at=None,
            )
            from extensions import db
            db.session.add(entry)
            db.session.commit()

            results = get_memory_for_topics(["AI"])
            assert len(results) == 1
            assert results[0].topic == "AI"
            assert results[0].signal == "AI safety is important"

    def test_get_memory_for_topics_respects_min_importance(self, app, create_article):
        """get_memory_for_topics should filter by minimum importance level."""
        from extensions import db
        from models import TrendMemory
        from services.trend_memory import MemoryImportance, get_memory_for_topics

        with app.app_context():
            low_entry = TrendMemory(
                topic="tech",
                signal="low importance signal",
                importance=MemoryImportance.LOW,
                expires_at=None,
            )
            high_entry = TrendMemory(
                topic="tech",
                signal="high importance signal",
                importance=MemoryImportance.HIGH,
                expires_at=None,
            )
            db.session.add(low_entry)
            db.session.add(high_entry)
            db.session.commit()

            results = get_memory_for_topics(["tech"], min_importance=2)
            assert len(results) == 1
            assert results[0].importance == MemoryImportance.HIGH

    def test_get_memory_for_topics_filters_expired(self, app, create_article):
        """get_memory_for_topics should not return expired entries."""
        from extensions import db
        from models import TrendMemory
        from services.trend_memory import MemoryImportance, get_memory_for_topics

        with app.app_context():
            expired_entry = TrendMemory(
                topic="news",
                signal="expired signal",
                importance=MemoryImportance.MEDIUM,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            valid_entry = TrendMemory(
                topic="news",
                signal="valid signal",
                importance=MemoryImportance.MEDIUM,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.session.add(expired_entry)
            db.session.add(valid_entry)
            db.session.commit()

            results = get_memory_for_topics(["news"])
            assert len(results) == 1
            assert results[0].signal == "valid signal"

    def test_consolidate_topic_promotes_low_to_medium(self, app, create_article):
        """consolidate_topic should promote low-importance entries to medium when high exists."""
        from extensions import db
        from models import TrendMemory
        from services.trend_memory import MemoryImportance, consolidate_topic

        with app.app_context():
            high_entry = TrendMemory(
                topic="AI",
                signal="high importance AI signal",
                importance=MemoryImportance.HIGH,
                expires_at=None,
                created_at=datetime.now(timezone.utc) - timedelta(hours=12),
            )
            low_entry = TrendMemory(
                topic="AI",
                signal="low importance AI signal",
                importance=MemoryImportance.LOW,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_at=datetime.now(timezone.utc) - timedelta(hours=6),
            )
            db.session.add(high_entry)
            db.session.add(low_entry)
            db.session.commit()

            merged_count = consolidate_topic("AI")

            assert merged_count >= 1, "Should have merged at least one low entry"

            db.session.refresh(low_entry)
            assert low_entry.importance == MemoryImportance.MEDIUM, "Low entry should be promoted to medium"

    def test_purge_expired_removes_old_entries(self, app, create_article):
        """purge_expired should remove all expired TrendMemory entries."""
        from extensions import db
        from models import TrendMemory
        from services.trend_memory import MemoryImportance, purge_expired

        with app.app_context():
            expired_entry = TrendMemory(
                topic="old_topic",
                signal="expired signal",
                importance=MemoryImportance.LOW,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            valid_entry = TrendMemory(
                topic="new_topic",
                signal="valid signal",
                importance=MemoryImportance.HIGH,
                expires_at=None,
            )
            db.session.add(expired_entry)
            db.session.add(valid_entry)
            db.session.commit()

            deleted_count = purge_expired()

            assert deleted_count == 1, "Should have deleted 1 expired entry"

            remaining = TrendMemory.query.filter_by(topic="old_topic").first()
            assert remaining is None, "Expired entry should be deleted"

            valid_remaining = TrendMemory.query.filter_by(topic="new_topic").first()
            assert valid_remaining is not None, "Valid entry should remain"

    def test_format_memory_for_prompt_empty(self, app):
        """_format_memory_for_prompt should return 'No prior trend memory' for empty list."""
        from services.trend_memory import _format_memory_for_prompt

        result = _format_memory_for_prompt([])
        assert "No prior trend memory" in result

    def test_format_memory_for_prompt_groups_by_importance(self, app, create_article):
        """_format_memory_for_prompt should group entries by importance tier."""
        from extensions import db
        from models import TrendMemory
        from services.trend_memory import MemoryImportance, _format_memory_for_prompt

        with app.app_context():
            now = datetime.now(timezone.utc)
            high = TrendMemory(topic="AI", signal="high signal", importance=MemoryImportance.HIGH, expires_at=None)
            medium = TrendMemory(topic="AI", signal="medium signal", importance=MemoryImportance.MEDIUM, expires_at=None)
            low = TrendMemory(topic="AI", signal="low signal", importance=MemoryImportance.LOW, expires_at=now + timedelta(days=7))
            db.session.add_all([high, medium, low])
            db.session.commit()

            result = _format_memory_for_prompt([high, medium, low])

            assert "<high_importance_trends>" in result
            assert "<medium_importance_trends>" in result
            assert "<recent_trends>" in result
            assert "high signal" in result
            assert "medium signal" in result