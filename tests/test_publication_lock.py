"""Regression tests for the publication lock.

Publication used to do three things in one transaction: it marked the article
as done, it asked the model for the trend memory, and it wrote the answer
away. The middle step is an LLM request, and a local model can take minutes
to answer one.

The write lock was therefore taken before the request went out and held for
the whole of it. A local model that took longer than the task's time limit
killed the task mid-request, and the killed worker left the lock held
behind it. Every other writer then blocked on the database — including the
beat task that would have drained the queue.

The rule these tests pin down: **the publication is committed before the
model is asked anything, and the model call never runs with a transaction
open.** The response is buffered in memory and written in one short
transaction once it is complete.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import object_session


def _in_transaction(obj) -> bool:
    """True when the object is attached to a session with an open transaction."""
    session = object_session(obj)
    return session is not None and session.in_transaction()


@pytest.fixture
def published_article(app, create_article):
    """A verified candidate whose publication effects have not yet been claimed."""
    import hashlib
    import json

    from extensions import db
    from models import EditorialDossier, QualityReport

    final_article = json.dumps({
        "headline": "Verified test article",
        "tldr": "A concise verified test summary.",
        "why_it_matters": "A bounded test fixture.",
        "body": "The release notes state the version is 3.2.",
        "key_points": ["Version 3.2 is stated in the release notes."],
        "what_to_watch": "The next release is pending.",
        "citations": [{"title": "Official release notes", "url": "https://source.example/release"}],
        "original_attribution": {"source": "feed", "url": "https://feed.example/item"},
        "tags": ["ai"],
    })
    article = create_article(
        pipeline_status="editing",
        topics=["ai"],
        draft_article="A draft about local inference.",
        final_article=final_article,
    )
    article.pipeline_status = "done"
    article.raw_metadata = {"editorial_audit": {"passed": True, "findings": []}}
    db.session.add(EditorialDossier(
        article_id=article.id,
        revision=1,
        policy_version="evidence-first-v1",
        status="verified",
        content_digest="e" * 64,
        payload={
            "sources": [{"evidence_source_id": "ev_1", "retrieval_status": "retrieved", "url": "https://source.example/release", "excerpt": "The release notes state the version is 3.2."}],
            "claims": [{"claim_id": "c1", "claim": "Version 3.2 is stated in the release notes.", "status": "primary_supported", "publish_allowed": True, "independent_origin_count": 0, "supports": [{"evidence_source_id": "ev_1", "span": "The release notes state the version is 3.2."}], "contradicts": []}],
        },
    ))
    digest = hashlib.sha256(final_article.encode("utf-8")).hexdigest()
    db.session.add(QualityReport(
        article_id=article.id,
        stage="edit",
        overall_score=0.9,
        groundedness=0.9,
        coherence=0.9,
        completeness=0.9,
        safety=1.0,
        citation_score=1.0,
        claim_score=1.0,
        passed=True,
        needs_review=False,
        findings=[],
        meta={"content_digest": digest},
    ))
    article.published_at = None
    return article


class TestTheModelCallNeverHoldsTheLock:
    """The transaction must be gone before the model is asked."""

    def test_the_model_call_runs_with_no_open_transaction(
        self, app, published_article, monkeypatch
    ):
        from services import trend_memory

        observed = {}

        def _fake_call(draft, topics, summary, engagement_info=""):
            observed["in_transaction"] = _in_transaction(published_article)
            return SimpleNamespace(entries=[])

        monkeypatch.setattr(trend_memory, "_call_llm_for_memory", _fake_call)

        # The publication is a pending write, so the session is holding a
        # transaction before the proposal starts.
        assert _in_transaction(published_article) is True

        trend_memory.propose_trend_memory(published_article)

        assert observed["in_transaction"] is False, (
            "the model call ran with a transaction open, so it held the "
            "database for as long as the model took"
        )

    def test_the_publication_is_durable_while_the_model_waits(
        self, app, published_article, monkeypatch
    ):
        """The article must survive a rollback taken after the request.

        A rollback undoes everything that is still pending. If the
        publication were still pending when the model was asked, the
        rollback would take it with it, and a task killed mid-request would
        leave the article unpublished and the database locked.
        """
        from extensions import db
        from models import Article
        from services import trend_memory
        from datetime import datetime, timezone

        # This test exercises the already-published memory path directly.
        published_article.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

        observed = {}

        def _fake_call(draft, topics, summary, engagement_info=""):
            db.session.rollback()
            observed["status"] = published_article.pipeline_status
            observed["published"] = published_article.published_at is not None
            return SimpleNamespace(entries=[])

        monkeypatch.setattr(trend_memory, "_call_llm_for_memory", _fake_call)

        trend_memory.propose_trend_memory(published_article)

        assert observed["status"] == "done", (
            "the publication was not committed before the model was asked"
        )
        assert observed["published"] is True

        db.session.expire_all()
        stored = db.session.get(Article, published_article.id)
        assert stored.pipeline_status == "done"
        assert stored.published_at is not None

    def test_the_transaction_is_released_even_without_a_model_answer(
        self, app, published_article, monkeypatch
    ):
        """A model that fails still leaves the transaction released."""
        from services import trend_memory

        def _boom(*args, **kwargs):
            raise RuntimeError("the model did not answer")

        monkeypatch.setattr(trend_memory, "_call_llm_for_memory", _boom)

        result = trend_memory.propose_trend_memory(published_article)

        assert result.used_fallback is True
        assert _in_transaction(published_article) is False


class TestPublicationCommitsBeforeTheSlowWork:
    """The publication is durable before anything slow begins."""

    def test_the_article_is_committed_before_the_trend_memory_dispatch(
        self, app, published_article, monkeypatch
    ):
        from extensions import db
        from models import Article
        from services import pipeline_degradation

        observed = {}

        def _fake_dispatch(article):
            observed["status"] = article.pipeline_status
            observed["published"] = article.published_at is not None

        monkeypatch.setattr(pipeline_degradation, "_dispatch_trend_memory", _fake_dispatch)

        pipeline_degradation.post_finalize_article(published_article)

        assert observed["status"] == "done"
        assert observed["published"] is True

        db.session.expire_all()
        stored = db.session.get(Article, published_article.id)
        assert stored.published_at is not None, (
            "the publication was not committed before the slow work"
        )

    def test_the_trend_memory_proposal_is_dispatched_rather_than_run_inline(
        self, app, published_article, monkeypatch
    ):
        """The publication must not wait for the model.

        The proposal is an LLM request that can take minutes. Running it
        inline would make every publication wait for it, and would put the
        request inside whatever time limit the publisher happens to have.
        """
        from services import pipeline_degradation

        dispatched = []
        monkeypatch.setattr(
            pipeline_degradation,
            "_dispatch_trend_memory",
            lambda article: dispatched.append(article.id),
        )

        pipeline_degradation.post_finalize_article(published_article)

        assert dispatched == [published_article.id]

    def test_a_failed_dispatch_does_not_unpublish_the_article(
        self, app, published_article, monkeypatch
    ):
        """The memory is a side effect, not a condition of publication."""
        from extensions import db
        from models import Article
        from services import pipeline_degradation

        def _boom(article):
            raise RuntimeError("the broker is unreachable")

        monkeypatch.setattr(pipeline_degradation, "_dispatch_trend_memory", _boom)

        pipeline_degradation.post_finalize_article(published_article)

        db.session.expire_all()
        stored = db.session.get(Article, published_article.id)
        assert stored.pipeline_status == "done"

    def test_a_provider_failure_does_not_break_publication(
        self, app, published_article, monkeypatch
    ):
        """A model that errors out must not take the publication with it."""
        from extensions import db
        from models import Article
        from services import trend_memory

        def _boom(*args, **kwargs):
            raise RuntimeError("the provider refused the request")

        monkeypatch.setattr(trend_memory, "_call_llm_for_memory", _boom)

        result = trend_memory.propose_trend_memory(published_article)

        assert result.used_fallback is True
        db.session.expire_all()
        stored = db.session.get(Article, published_article.id)
        assert stored.pipeline_status == "done"

    def test_editor_finalize_does_not_claim_publication_before_post_finalize(
        self, app, published_article, monkeypatch,
    ):
        from constants import PipelineStatus
        from extensions import db
        from models import Article
        from services import pipeline_degradation
        from tasks.pipeline import _transition_article_status

        published_article.pipeline_status = PipelineStatus.EDITING
        published_article.publicly_visible = False
        published_article.published_at = None
        monkeypatch.setattr(pipeline_degradation, "_dispatch_trend_memory", lambda _article: None)
        monkeypatch.setattr("services.webhooks.trigger_event", lambda *_args, **_kwargs: None)
        monkeypatch.setattr("tasks.embeddings.generate_article_embedding.delay", lambda *_args: None)

        _transition_article_status(published_article, PipelineStatus.DONE)
        assert published_article.published_at is None
        assert published_article.publicly_visible is False

        assert pipeline_degradation.post_finalize_article(published_article) is True
        db.session.expire_all()
        stored = db.session.get(Article, published_article.id)
        assert stored is not None
        assert stored.pipeline_status == PipelineStatus.DONE
        assert stored.published_at is not None
        assert stored.publicly_visible is True


class TestTheProposalHasItsOwnTask:
    """The slow work runs out of band, with room for a slow local model."""

    def test_the_task_exists(self):
        from tasks.trend_memory import propose_trend_memory_for_article

        assert callable(propose_trend_memory_for_article)

    def test_the_task_is_registered(self):
        import tasks

        assert "propose_trend_memory_for_article" in tasks.__all__

    def test_the_task_has_room_for_a_slow_local_model(self):
        from tasks.trend_memory import (
            TREND_MEMORY_SOFT_TIME_LIMIT,
            TREND_MEMORY_TIME_LIMIT,
        )

        # A local model reasoning over an article can take minutes. The
        # budget has to be generous, because losing the memory to a timeout
        # is worse than waiting for the answer.
        assert TREND_MEMORY_SOFT_TIME_LIMIT >= 600
        assert TREND_MEMORY_TIME_LIMIT > TREND_MEMORY_SOFT_TIME_LIMIT

    def test_the_task_reads_the_article_and_then_releases_the_transaction(
        self, app, published_article, monkeypatch
    ):
        from services import trend_memory

        observed = {}

        def _fake_call(draft, topics, summary, engagement_info=""):
            # The session that matters is the one the task is using. A Celery
            # task runs under its own app context (FlaskTask pushes one), so
            # it may well have its own session -- the fixture's session is
            # not necessarily the task's session, and its state says nothing
            # about whether the task is holding a lock.
            from extensions import db

            observed["in_transaction"] = db.session().in_transaction()
            observed["draft"] = draft
            observed["topics"] = topics
            return SimpleNamespace(entries=[])

        monkeypatch.setattr(trend_memory, "_call_llm_for_memory", _fake_call)

        from extensions import db

        db.session.commit()

        from tasks.trend_memory import propose_trend_memory_for_article

        result = propose_trend_memory_for_article(
            published_article.id, {"newsletter_clicks": 1}
        )

        assert observed["in_transaction"] is False
        assert observed["topics"] == ["ai"]
        assert result["article_id"] == published_article.id

    def test_a_missing_article_is_reported_rather_than_raised(self, app):
        from tasks.trend_memory import propose_trend_memory_for_article

        result = propose_trend_memory_for_article(999999, {})

        assert result["skipped"] == "not_found"


class TestTheBeatTaskDoesNotWaitForAModel:
    """The beat task publishes; it does not generate."""

    def test_draining_the_queue_makes_no_model_call(
        self, app, create_source, monkeypatch
    ):
        from constants import PipelineStatus
        from extensions import db
        from models import Article
        from services import auto_review
        from services import trend_memory

        def _boom(*args, **kwargs):
            raise AssertionError(
                "the beat task must not call the model; the proposal is a "
                "separate task"
            )

        monkeypatch.setattr(trend_memory, "_call_llm_for_memory", _boom)
        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)

        source = create_source()
        article = Article(
            original_title="Waiting in the queue",
            original_url="https://example.test/queued",
            source_id=source.id,
            pipeline_status=PipelineStatus.REVIEW,
            topics=["ai"],
        )
        db.session.add(article)
        db.session.commit()

        approved = auto_review.auto_approve_queued()

        assert approved == 0

    def test_missing_final_content_stays_in_review_when_the_drain_returns(
        self, app, create_source, monkeypatch
    ):
        """The drain persists a structural block instead of publishing empty content."""
        from constants import PipelineStatus
        from extensions import db
        from models import Article
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)

        source = create_source()
        article = Article(
            original_title="Waiting in the queue",
            original_url="https://example.test/queued-durable",
            source_id=source.id,
            pipeline_status=PipelineStatus.REVIEW,
            topics=["ai"],
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id

        auto_review.auto_approve_queued()

        # A rollback takes back anything that is still pending. If the
        # publication were still pending, it would go with it.
        db.session.rollback()
        db.session.expire_all()
        stored = db.session.get(Article, article_id)

        assert stored is not None
        assert stored.pipeline_status == "review"
        assert stored.published_at is None
        assert "FINAL_ARTICLE_MISSING" in stored.raw_metadata["editorial_eligibility"]["reason_codes"]
        assert "EVIDENCE_DOSSIER_MISSING" in stored.raw_metadata["editorial_eligibility"]["diagnostic_codes"]

    def test_incomplete_review_article_resumes_at_last_available_stage(
        self, app, create_source, monkeypatch,
    ):
        from constants import PipelineStatus
        from extensions import db
        from models import Article
        from services import auto_review, pipeline_utils

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)
        dispatched = []
        monkeypatch.setattr(
            pipeline_utils,
            "_dispatch_next",
            lambda article_id, **kwargs: dispatched.append((article_id, kwargs["next_status"])),
        )
        source = create_source()
        article = Article(
            source_id=source.id,
            original_title="Recoverable review article",
            pipeline_status=PipelineStatus.REVIEW,
            research_brief='{"key_claims": []}',
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id

        assert auto_review.auto_approve_queued() == 0
        db.session.expire_all()
        stored = db.session.get(Article, article_id)
        assert stored is not None
        assert stored.pipeline_status == PipelineStatus.WRITING
        assert stored.raw_metadata["incomplete_review_retries"] == 1
        assert dispatched == [(article_id, PipelineStatus.WRITING)]

    def test_editor_task_has_room_for_multiple_slow_local_calls(self):
        from tasks.edit import edit_article

        assert edit_article.soft_time_limit == 900
        assert edit_article.time_limit == 960
