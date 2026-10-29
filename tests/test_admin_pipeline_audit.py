"""Tests for the admin pipeline audit surfaces.

The pipeline wrote its own log, but nothing surfaced it: the operator had
the trend-memory page for what the agent remembered, and no equivalent for
what the pipeline did. These tests lock in the two surfaces that close that
gap -- the activity feed and the per-article trail -- and the service layer
they read from.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"


def _make_log(
    *,
    run_id: int | None = None,
    article_id: int | None = None,
    stage: str = "edit",
    level: str = "info",
    message: str = "something happened",
):
    """Create a PipelineLog row for a test.

    ``pipeline_logs.run_id`` is NOT NULL, so a run is created when the
    caller does not supply one.
    """
    from extensions import db
    from models import PipelineLog

    if run_id is None:
        from tests.factories import create_pipeline_run

        run_id = create_pipeline_run().id

    log = PipelineLog(
        run_id=run_id,
        article_id=article_id,
        stage=stage,
        level=level,
        message=message,
    )
    db.session.add(log)
    db.session.flush()
    return log


class TestArticleTrail:
    """``get_article_trail`` assembles the audit trail of one article."""

    def test_returns_none_for_a_missing_article(self, app):
        from services.pipeline_audit import get_article_trail

        assert get_article_trail(999999) is None

    def test_returns_the_provenance_of_an_article(self, app, create_article):
        from services.pipeline_audit import get_article_trail

        article = create_article(
            original_title="Audited article",
            pipeline_status="review",
            category="ai",
            impact_score=42,
            selector_result={"score": 8, "reason": "high signal"},
            research_brief="a brief",
            draft_article="a draft",
        )

        trail = get_article_trail(article.id)
        assert trail is not None
        provenance = trail.provenance

        assert provenance.article_id == article.id
        assert provenance.title == "Audited article"
        assert provenance.pipeline_status == "review"
        assert provenance.category == "ai"
        assert provenance.impact_score == 42
        assert provenance.selector_score == 8.0
        assert provenance.selector_reason == "high signal"
        assert provenance.has_research_brief is True
        assert provenance.has_draft is True
        assert provenance.has_final is True

    def test_selector_score_is_none_when_the_selector_never_ran(self, app, create_article):
        from services.pipeline_audit import get_article_trail

        article = create_article(selector_result=None)
        trail = get_article_trail(article.id)

        assert trail is not None
        assert trail.provenance.selector_score is None

    def test_a_malformed_selector_result_does_not_raise(self, app, create_article):
        from services.pipeline_audit import get_article_trail

        article = create_article()
        article.selector_result = {"score": "not a number"}
        from extensions import db

        db.session.flush()

        trail = get_article_trail(article.id)
        assert trail is not None
        assert trail.provenance.selector_score is None

    def test_collects_the_stage_events_of_the_article(self, app, create_article):
        from services.pipeline_audit import get_article_trail
        from tests.factories import create_source

        source = create_source()
        article = create_article(source=source)
        other = create_article(source=source)
        _make_log(article_id=article.id, stage="select", message="Selected [9/10]")
        _make_log(article_id=article.id, stage="write", level="warning", message="slow")
        _make_log(article_id=article.id, stage="edit", level="error", message="boom")
        _make_log(article_id=other.id, stage="edit", message="unrelated article")

        trail = get_article_trail(article.id)
        assert trail is not None

        assert len(trail.events) == 3
        assert {e.stage for e in trail.events} == {"select", "write", "edit"}
        assert sum(1 for e in trail.events if e.is_error) == 1
        assert sum(1 for e in trail.events if e.is_warning) == 1

    def test_summarises_the_stages_it_saw(self, app, create_article):
        from services.pipeline_audit import get_article_trail

        article = create_article()
        _make_log(article_id=article.id, stage="edit", level="warning")
        _make_log(article_id=article.id, stage="edit", level="error")

        trail = get_article_trail(article.id)
        assert trail is not None

        by_stage = {s.stage: s for s in trail.stage_summaries}
        assert by_stage["edit"].total == 2
        assert by_stage["edit"].warnings == 1
        assert by_stage["edit"].errors == 1

    def test_the_stages_are_ordered_by_the_pipeline_sequence(self, app, create_article):
        from services.pipeline_audit import get_article_trail

        article = create_article()
        _make_log(article_id=article.id, stage="edit")
        _make_log(article_id=article.id, stage="extract")
        _make_log(article_id=article.id, stage="select")

        trail = get_article_trail(article.id)
        assert trail is not None
        assert [s.stage for s in trail.stage_summaries] == ["extract", "select", "edit"]


class TestStageEventFeed:
    """``list_stage_events`` is the filtered activity feed."""

    def test_returns_the_newest_events_first(self, app, create_article):
        from services.pipeline_audit import list_stage_events

        article = create_article()
        _make_log(article_id=article.id, stage="edit", message="older")
        _make_log(article_id=article.id, stage="write", message="newer")

        result = list_stage_events()
        assert result.total >= 2
        # The two events we created are the only ones, and they are ordered
        # by creation time descending.
        assert result.events[0].message == "newer"

    def test_filters_by_stage(self, app, create_article):
        from services.pipeline_audit import list_stage_events

        article = create_article()
        _make_log(article_id=article.id, stage="edit")
        _make_log(article_id=article.id, stage="write")

        result = list_stage_events(stage="write")
        assert all(e.stage == "write" for e in result.events)

    def test_filters_by_level(self, app, create_article):
        from services.pipeline_audit import list_stage_events

        article = create_article()
        _make_log(article_id=article.id, level="error")
        _make_log(article_id=article.id, level="info")

        result = list_stage_events(level="error")
        assert all(e.level == "error" for e in result.events)

    def test_filters_by_article(self, app, create_article):
        from services.pipeline_audit import list_stage_events
        from tests.factories import create_source

        # The article factory creates a default source with a fixed key, so
        # two articles in one test have to share one source.
        source = create_source()
        first = create_article(source=source)
        second = create_article(source=source)
        _make_log(article_id=first.id, message="for first")
        _make_log(article_id=second.id, message="for second")

        result = list_stage_events(article_id=first.id)
        assert [e.message for e in result.events] == ["for first"]

    def test_paginates(self, app, create_article):
        from services.pipeline_audit import list_stage_events

        article = create_article()
        for i in range(15):
            _make_log(article_id=article.id, message=f"event {i}")

        first = list_stage_events(page=1, per_page=10)
        second = list_stage_events(page=2, per_page=10)

        assert first.total == 15
        assert first.has_next is True
        assert first.has_prev is False
        assert second.has_prev is True
        assert len(first.events) == 10
        assert len(second.events) == 5

    def test_reports_the_known_stages(self, app, create_article):
        from services.pipeline_audit import list_known_stages

        article = create_article()
        _make_log(article_id=article.id, stage="write")
        _make_log(article_id=article.id, stage="edit")

        stages = list_known_stages()
        assert "write" in stages
        assert "edit" in stages


class TestAuditRoutes:
    """The two admin pages that surface the trail."""

    def test_pipeline_audit_requires_authentication(self, client):
        response = client.get("/admin/pipeline-audit")
        assert response.status_code in (302, 401, 403)

    def test_pipeline_audit_renders(self, auth_client, create_article):
        from extensions import db

        article = create_article()
        _make_log(article_id=article.id, stage="edit", message="gate ran")
        db.session.commit()

        response = auth_client.get("/admin/pipeline-audit")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "pipeline audit" in body
        assert "gate ran" in body

    def test_pipeline_audit_honours_the_stage_filter(self, auth_client, create_article):
        from extensions import db

        article = create_article()
        _make_log(article_id=article.id, stage="write", message="drafted something")
        _make_log(article_id=article.id, stage="edit", message="edited something")
        db.session.commit()

        response = auth_client.get("/admin/pipeline-audit?stage=write")
        body = response.get_data(as_text=True)
        assert "drafted something" in body
        assert "edited something" not in body

    def test_article_audit_requires_authentication(self, client, create_article):
        article = create_article()
        response = client.get(f"/admin/articles/{article.id}/audit")
        assert response.status_code in (302, 401, 403)

    def test_article_audit_renders_the_trail(self, auth_client, create_article):
        from extensions import db

        article = create_article(original_title="Trail Article")
        _make_log(article_id=article.id, stage="select", message="Selected [9/10]")
        db.session.commit()

        response = auth_client.get(f"/admin/articles/{article.id}/audit")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Trail Article" in body
        assert "Selected [9/10]" in body

    def test_article_audit_404s_for_a_missing_article(self, auth_client):
        response = auth_client.get("/admin/articles/999999/audit")
        assert response.status_code == 404


class TestAuditSurfacesAreLinked:
    """The new pages have to be reachable, not just routable."""

    def test_pipeline_audit_is_in_the_admin_navigation(self):
        html = (TEMPLATES_DIR / "base_admin.html").read_text(encoding="utf-8")
        assert "/admin/pipeline-audit" in html

    def test_the_articles_table_links_to_the_article_trail(self):
        html = (TEMPLATES_DIR / "admin" / "partials" / "articles_table.html").read_text(
            encoding="utf-8"
        )
        assert "/audit" in html

    def test_the_dashboard_links_to_the_article_trail(self):
        html = (TEMPLATES_DIR / "admin" / "dashboard.html").read_text(encoding="utf-8")
        assert "/audit" in html

    def test_the_activity_feed_links_into_the_article_trail(self):
        html = (TEMPLATES_DIR / "admin" / "pipeline_audit.html").read_text(encoding="utf-8")
        assert "/admin/articles/" in html
        assert "/audit" in html


class TestAuditLayering:
    """The audit module is a service and stays out of the framework."""

    def test_the_service_does_not_import_flask(self):
        source = (REPO_ROOT / "services" / "pipeline_audit.py").read_text(encoding="utf-8")
        assert "import flask" not in source
        assert "from flask" not in source

    def test_the_service_does_not_import_routes(self):
        source = (REPO_ROOT / "services" / "pipeline_audit.py").read_text(encoding="utf-8")
        assert "from routes" not in source
        assert "import routes" not in source


class TestDashboardAuditPanel:
    """The dashboard carries the pipeline audit and the memory."""

    def test_the_summary_counts_the_events(self, app):
        from services.pipeline_audit import dashboard_summary

        _make_log(stage="crawl", level="info", message="fetched")
        _make_log(stage="edit", level="error", message="failed", run_id=None)

        summary = dashboard_summary()
        assert summary.total_events >= 2
        assert summary.error_count >= 1
        assert summary.recent_events
        assert summary.stage_summaries

    def test_the_summary_reports_the_articles_it_touched(self, app, create_article):
        from services.pipeline_audit import dashboard_summary

        article = create_article()
        _make_log(article_id=article.id, message="touched")

        summary = dashboard_summary()
        assert summary.articles_touched >= 1

    def test_the_summary_keeps_the_newest_event_first(self, app):
        from services.pipeline_audit import dashboard_summary

        _make_log(stage="crawl", message="older")
        _make_log(stage="write", message="newer")

        summary = dashboard_summary(recent=5)
        messages = [e.message for e in summary.recent_events]
        assert "newer" in messages
        if "older" in messages and "newer" in messages:
            assert messages.index("newer") < messages.index("older")

    def test_the_dashboard_renders_the_audit_panel(self, auth_client, app):
        _make_log(stage="crawl", message="fetched")

        response = auth_client.get("/admin/")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "pipeline audit" in body
        assert "full audit trail" in body

    def test_the_dashboard_renders_the_memory_panel(self, auth_client, app):
        response = auth_client.get("/admin/")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "full memory" in body

    def test_the_dashboard_payload_survives_json(self, auth_client, app):
        import json

        _make_log(stage="crawl", message="fetched")

        # The dashboard stats blob is stored in the response cache, which
        # serialises it with json.dumps. A datetime or a dataclass in the
        # payload would break the cache write and take the panel with it.
        from routes.admin.dashboard import _compute_dashboard_stats

        stats = _compute_dashboard_stats()
        assert "audit" in stats
        assert "memory" in stats
        json.dumps(stats)


class TestMemorySummary:
    """The trend memory, summarised for the dashboard."""

    def test_counts_the_memories_by_importance(self, app):
        from extensions import db
        from models import TrendMemory
        from services.trend_memory import memory_summary

        db.session.add(TrendMemory(topic="ai", signal="a", importance=3))
        db.session.add(TrendMemory(topic="ai", signal="b", importance=1))
        db.session.flush()

        summary = memory_summary()
        assert summary.total >= 2
        assert summary.high >= 1
        assert summary.low >= 1

    def test_counts_the_topics(self, app):
        from extensions import db
        from models import TrendMemory
        from services.trend_memory import memory_summary

        db.session.add(TrendMemory(topic="security", signal="a", importance=2))
        db.session.flush()

        summary = memory_summary()
        assert any(t.topic == "security" for t in summary.topics)

    def test_counts_the_expired_memories(self, app):
        from datetime import datetime, timedelta, timezone

        from extensions import db
        from models import TrendMemory
        from services.trend_memory import memory_summary

        past = datetime.now(timezone.utc) - timedelta(days=1)
        db.session.add(
            TrendMemory(topic="ai", signal="old", importance=2, expires_at=past)
        )
        db.session.flush()

        assert memory_summary().expired >= 1

    def test_the_service_does_not_import_flask(self):
        source = (REPO_ROOT / "services" / "trend_memory.py").read_text(encoding="utf-8")
        assert "import flask" not in source
        assert "from flask" not in source
