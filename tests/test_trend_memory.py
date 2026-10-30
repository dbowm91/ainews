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
                final_article='{"headline": "Test Article", "body": "Test signal about AI and ML trend signal"}',
            )
            article.topics = ["AI", "machine-learning"]
            article.summary = "Test summary for the article"
            from extensions import db
            db.session.commit()

            with patch("services.trend_memory.get_provider_for_role") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.chat_structured.return_value = MagicMock(
                    entries=[
                        MagicMock(topic="AI", importance=2, signal="Test signal about AI", candidate_source_url=None),
                        MagicMock(topic="machine-learning", importance=1, signal="ML trend signal", candidate_source_url=None),
                    ]
                )
                mock_get_provider.return_value = (mock_provider, "gpt-4", 2048, "openai")

                propose_trend_memory(article)

            entries = TrendMemory.query.filter_by(source_article_id=article.id).all()
            assert len(entries) == 2, f"Expected 2 TrendMemory entries, got {len(entries)}"

    def test_reproposal_after_article_revision_does_not_duplicate_signal(self, app, create_article):
        from extensions import db
        from models import MemoryEvidence, TrendMemory
        from services.trend_memory import propose_trend_memory

        with app.app_context():
            article = create_article(
                pipeline_status="done",
                final_article='{"headline":"Before","body":"A durable AI infrastructure observation"}',
            )
            article.topics = ["ai"]
            db.session.commit()
            with patch("services.trend_memory.get_provider_for_role") as mocked:
                provider = MagicMock()
                provider.chat_structured.return_value = MagicMock(entries=[
                    MagicMock(topic="ai", importance=2, signal="A durable AI infrastructure observation", candidate_source_url=None)
                ])
                mocked.return_value = (provider, "model", 1024, "test")
                propose_trend_memory(article)
                article.final_article = '{"headline":"After","body":"A durable AI infrastructure observation remains supported"}'
                db.session.commit()
                propose_trend_memory(article)

            assert TrendMemory.query.filter_by(source_article_id=article.id).count() == 1
            # V2 dual writes are independently gated and disabled in the default
            # test configuration; the legacy proposal remains idempotent.
            assert MemoryEvidence.query.filter_by(source_article_id=article.id).count() == 0

    def test_deterministic_reuse_separates_source_confidence_from_importance(self, app):
        from types import SimpleNamespace

        from services.trend_memory import _deterministic_candidates

        brief = SimpleNamespace(
            external_sources=[SimpleNamespace(url="https://reports.example.com/policy")],
            key_claims=[SimpleNamespace(
                claim="The policy committee published a routine weekly status update for its public dashboard.",
                confidence="high",
                source="https://reports.example.com/policy",
            )],
        )
        candidates = _deterministic_candidates(
            brief,
            {"ai": "ai"},
            "https://origin.example.com/article",
            "{\"headline\":\"Routine policy update\",\"body\":\"The policy committee published a routine weekly status update for its public dashboard.\"}",
        )

        assert len(candidates) == 1
        assert candidates[0].evidence_confidence == "high"
        assert candidates[0].importance == 2
        assert candidates[0].candidate_source_url == "https://reports.example.com/policy"
        assert "capped at MEDIUM" in candidates[0].decision_reason

    def test_deterministic_reuse_rejects_fabricated_or_invalid_source_claims(self, app):
        from types import SimpleNamespace

        from services.trend_memory import _deterministic_candidates

        brief = SimpleNamespace(
            external_sources=[SimpleNamespace(url="javascript:alert(1)")],
            key_claims=[SimpleNamespace(
                claim="The agency released a major new safety standard for the latest model generation.",
                confidence="high",
                source="javascript:alert(1)",
            )],
        )
        candidates = _deterministic_candidates(
            brief,
            {"ai": "ai"},
            "file:///private/source",
            "{\"headline\":\"Unrelated article\",\"body\":\"A different subject with no matching claim.\"}",
        )

        assert candidates == []

    def test_v2_dual_write_is_explicitly_gated(self, app, create_article):
        from unittest.mock import patch

        from extensions import db
        from models import MemoryEvidence, MemoryItem
        from schemas.pipeline import MemoryConfig, PipelineRootConfig
        from services.trend_memory import TrendMemoryEntry, _save_memory_entries

        with app.app_context():
            article = create_article(category="ai")
            db.session.commit()
            entry = TrendMemoryEntry(topic="ai", importance=2, signal="A durable AI source-backed observation")
            config = PipelineRootConfig.model_construct(memory=MemoryConfig(memory_v2_writes_enabled=True))
            with patch("schemas.pipeline.load_pipeline_config", return_value=config):
                _save_memory_entries(
                    [entry], article.id, "article-v1", owner_category="ai",
                    source_url=article.original_url,
                )

            item = MemoryItem.query.filter_by(owner_category="ai").one()
            evidence = MemoryEvidence.query.filter_by(memory_id=item.id).one()
            assert evidence.source_article_id == article.id
            assert evidence.source_url == article.original_url
            assert item.confidence == "medium"
            assert db.session.query(MemoryItem).count() == 1

    def test_corrected_claim_supersedes_prior_memory_with_lineage(self, app, create_article):
        from extensions import db
        from models import MemoryEvidence, MemoryLineage
        from services.memory.lifecycle import add_observation

        with app.app_context():
            article = create_article(category="ai")
            db.session.commit()
            prior = add_observation(
                owner_category="ai", text="The policy takes effect in June.", importance=2,
                article_id=article.id, article_version="v1", source_url=article.original_url,
                claim_id="policy-effective-date", decision_reason="source-backed policy date",
            )
            corrected = add_observation(
                owner_category="ai", text="The policy takes effect in July.", importance=2,
                article_id=article.id, article_version="v2", source_url=article.original_url,
                claim_id="policy-effective-date-v2", relation="corrects",
                supersedes_claim_id="policy-effective-date",
                decision_reason="official correction",
            )
            db.session.commit()

            assert prior is not None and corrected is not None
            db.session.refresh(prior)
            assert prior.status == "superseded"
            assert corrected.status == "active"
            correction_evidence = MemoryEvidence.query.filter_by(memory_id=corrected.id).one()
            assert correction_evidence.relation == "corrects"
            assert MemoryLineage.query.filter_by(
                source_memory_id=prior.id, target_memory_id=corrected.id, relation="supersedes",
            ).count() == 1

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
        """Empty retrieval stays empty so callers can use an explicit has-memory check."""
        from services.trend_memory import _format_memory_for_prompt

        result = _format_memory_for_prompt([])
        assert result == ""

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
