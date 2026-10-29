"""Regression tests for the pipeline state machine.

``constants.py::VALID_TRANSITIONS`` is the table that says which pipeline
status may follow which. Every edge in it has to match a transition the
pipeline actually performs.

A missing edge does not merely refuse a transition. ``_transition_article_status``
raises ``InvalidStateTransitionError`` in the middle of a stage, and the
article is left exactly where it was. It then sits there until the retry task
dead-letters it an hour later as "stuck in 'pending' beyond 60 minutes".

Three edges were missing, and all three of them are on the normal path of an
autonomous run:

``pending -> skipped``
    The selector rejected the article. This is the single most common
    outcome of a crawl, and it threw.

``writing -> review``
    The writer's quality gate found a degenerate draft and routed it to
    review.

``pending -> failed``
    The pipeline timed out before the first stage moved the article on.

The second half of this file covers the other half of the same story: an
article that is already published must stay published. The editor can be
re-dispatched onto an article that has already been finalized, and routing
such an article to review again would either drag a live article back out of
the queue or publish it a second time.
"""

from __future__ import annotations

import pytest

from constants import VALID_TRANSITIONS, PipelineStatus, is_valid_transition
from tasks.pipeline import InvalidStateTransitionError, _transition_article_status


class _DummyArticle:
    """The smallest thing ``_transition_article_status`` will accept."""

    def __init__(self, id=1, pipeline_status=None):
        self.id = id
        self.pipeline_status = pipeline_status

    def __repr__(self):
        return f"_DummyArticle(id={self.id}, pipeline_status={self.pipeline_status})"


class TestTheEdgesThePipelinePerforms:
    """Every transition a stage performs has to be in the table."""

    def test_pending_to_skipped_is_allowed(self):
        """The selector rejects an article. This used to throw."""
        assert is_valid_transition(PipelineStatus.PENDING, PipelineStatus.SKIPPED)

    def test_writing_to_review_is_allowed(self):
        """The writer's quality gate routes a degenerate draft to review."""
        assert is_valid_transition(PipelineStatus.WRITING, PipelineStatus.REVIEW)

    def test_pending_to_failed_is_allowed(self):
        """The pipeline timeout fires before the first stage moves the article."""
        assert is_valid_transition(PipelineStatus.PENDING, PipelineStatus.FAILED)

    def test_pending_to_skipped_does_not_raise(self, app):
        with app.app_context():
            article = _DummyArticle(pipeline_status=PipelineStatus.PENDING)
            _transition_article_status(article, PipelineStatus.SKIPPED)
            assert article.pipeline_status == PipelineStatus.SKIPPED

    def test_writing_to_review_does_not_raise(self, app):
        with app.app_context():
            article = _DummyArticle(pipeline_status=PipelineStatus.WRITING)
            _transition_article_status(article, PipelineStatus.REVIEW)
            assert article.pipeline_status == PipelineStatus.REVIEW

    def test_pending_to_failed_does_not_raise(self, app):
        with app.app_context():
            article = _DummyArticle(pipeline_status=PipelineStatus.PENDING)
            _transition_article_status(article, PipelineStatus.FAILED)
            assert article.pipeline_status == PipelineStatus.FAILED

    def test_the_edges_are_in_the_table_itself(self):
        """Guard against the table and the helper drifting apart."""
        assert PipelineStatus.SKIPPED in VALID_TRANSITIONS[PipelineStatus.PENDING]
        assert PipelineStatus.FAILED in VALID_TRANSITIONS[PipelineStatus.PENDING]
        assert PipelineStatus.REVIEW in VALID_TRANSITIONS[PipelineStatus.WRITING]

    def test_a_genuinely_invalid_edge_is_still_refused(self, app):
        """The table is a guard, not a blanket permission."""
        with app.app_context():
            article = _DummyArticle(pipeline_status=PipelineStatus.PENDING)
            with pytest.raises(InvalidStateTransitionError):
                _transition_article_status(article, PipelineStatus.WRITING)


class TestTerminalStatesStayTerminal:
    """A published article must not be dragged back out of the queue."""

    def test_done_to_review_is_refused_by_the_table(self):
        assert not is_valid_transition(PipelineStatus.DONE, PipelineStatus.REVIEW)

    def test_done_to_failed_is_refused_by_the_table(self):
        assert not is_valid_transition(PipelineStatus.DONE, PipelineStatus.FAILED)

    def test_a_published_article_survives_a_transition_to_review(self, app):
        """``_transition_article_status`` hands a review transition to the
        auto-review service rather than to the table, so the guard against
        un-publishing an article lives there."""
        from services import auto_review

        with app.app_context():
            article = _DummyArticle(pipeline_status=PipelineStatus.DONE)

            auto_review.route_to_review(article)

            assert article.pipeline_status == PipelineStatus.DONE

    def test_skipped_is_terminal(self):
        assert VALID_TRANSITIONS[PipelineStatus.SKIPPED] == frozenset()
        assert VALID_TRANSITIONS[PipelineStatus.DONE] == frozenset()


class TestRouteToReviewLeavesAPublishedArticleAlone:
    """``route_to_review`` must not un-publish an article that is already live."""

    def test_a_published_article_is_not_queued(self, app, create_article, monkeypatch):
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: False)

        with app.app_context():
            article = create_article(pipeline_status="done")
            article.pipeline_status = PipelineStatus.DONE

            queued = auto_review.route_to_review(article)

            assert queued is False
            assert article.pipeline_status == PipelineStatus.DONE

    def test_a_published_article_is_not_published_a_second_time(
        self, app, create_article, monkeypatch
    ):
        """Auto-review mode must not re-publish (and re-finalize) a live article."""
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)

        published = []
        monkeypatch.setattr(
            auto_review, "publish_article", lambda article, **kw: published.append(article.id)
        )

        with app.app_context():
            article = create_article(pipeline_status="done")
            article.pipeline_status = PipelineStatus.DONE

            auto_review.route_to_review(article)

            assert published == [], "a published article was published a second time"

    def test_an_unpublished_article_is_queued_in_manual_mode(
        self, app, create_article, monkeypatch
    ):
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: False)

        with app.app_context():
            article = create_article(pipeline_status="editing")

            queued = auto_review.route_to_review(article)

            assert queued is True
            assert article.pipeline_status == PipelineStatus.REVIEW


class TestTheSelectorCanSkipAnArticle:
    """The skip path is the common case, so it has to work end to end."""

    def test_the_selector_skip_path_does_not_raise(self, app, create_article):
        """``tasks/select.py`` transitions a rejected article to skipped."""
        with app.app_context():
            article = create_article(pipeline_status="pending")
            article.pipeline_status = PipelineStatus.PENDING

            _transition_article_status(article, PipelineStatus.SKIPPED)

            assert article.pipeline_status == PipelineStatus.SKIPPED
