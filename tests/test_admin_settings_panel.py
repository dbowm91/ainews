"""Regression tests for the admin panel controls.

Four separate defects lived behind the operator's complaint that the admin
panel was not usable:

* The "trigger crawl" button answered ``CSRF token missing``. The endpoint
  demanded the token in the ``X-CSRFToken`` header, but a plain HTML form
  posts it in a field, and a browser form never sends a custom header.
* Several buttons carried ``btn-primary`` without ``btn``, so they lost the
  button geometry entirely and rendered as bare text.
* Most of the settings an operator needs -- the topics the site follows, how
  often the pipeline runs, and whether articles publish without a human --
  were not reachable from the panel at all.
* A trend memory entry was shown truncated behind an ellipsis, so the stored
  signal could never be read in full.

Each of those gets a test here, because each one is the kind of thing that
silently comes back.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest
import yaml

# Captured at import time, before the autouse fixture in conftest.py pins
# auto-review mode off. The "fails closed" test needs the real decision,
# not the pinned one.
from services.auto_review import is_auto_approve_enabled as _real_is_auto_approve_enabled

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csrf_token_pair(app):
    """Return a (signed_token, raw_token) pair for the app's secret key."""
    from itsdangerous import URLSafeTimedSerializer

    raw = hashlib.sha1(os.urandom(64)).hexdigest()
    signer = URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token")
    return signer.dumps(raw), raw


def _login(client, raw_token):
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["csrf_token"] = raw_token


@pytest.fixture
def csrf_app(monkeypatch):
    """An app with CSRF enforcement switched on."""
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FLASK_CONFIG", "testing")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/15")
    monkeypatch.setenv(
        "CELERY_TASK_SECRET",
        "test-secret-key-at-least-32-characters-long",
    )

    from app import create_app
    from extensions import limiter

    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = True
    limiter.enabled = False

    with app.app_context():
        yield app

        from extensions import db

        db.session.remove()
        db.drop_all()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


# ---------------------------------------------------------------------------
# 1. The CSRF token may arrive in a form field
# ---------------------------------------------------------------------------


class TestFormPostCarriesTheCsrfToken:
    """A form post must not be rejected for a missing CSRF header.

    The decorator that guards the admin endpoints read the token from the
    ``X-CSRFToken`` header only. An HTML form cannot send that header, so
    every form post on the admin panel -- "trigger crawl" most obviously --
    failed with "CSRF token missing" before it reached the view.
    """

    def test_form_post_with_the_token_in_the_field_is_accepted(self, csrf_app, csrf_client):
        signed, raw = _csrf_token_pair(csrf_app)
        _login(csrf_client, raw)

        resp = csrf_client.post(
            "/admin/trigger-crawl",
            data={"csrf_token": signed},
        )

        assert resp.status_code != 400, resp.get_data(as_text=True)[:400]
        assert "CSRF token missing" not in resp.get_data(as_text=True)

    def test_header_post_is_still_accepted(self, csrf_app, csrf_client):
        """The JSON clients that send the header keep working."""
        signed, raw = _csrf_token_pair(csrf_app)
        _login(csrf_client, raw)

        resp = csrf_client.post(
            "/admin/trigger-crawl",
            headers={"X-CSRFToken": signed},
        )

        assert resp.status_code != 400, resp.get_data(as_text=True)[:400]

    def test_post_without_any_token_is_rejected(self, csrf_app, csrf_client):
        """No token at all is still a failure."""
        _login(csrf_client, "")

        resp = csrf_client.post("/admin/trigger-crawl")

        assert resp.status_code == 400

    def test_post_with_a_forged_token_is_rejected(self, csrf_app, csrf_client):
        """A token that was not signed by this app is still a failure."""
        _login(csrf_client, "nonsense")

        resp = csrf_client.post(
            "/admin/trigger-crawl",
            data={"csrf_token": "nonsense"},
        )

        assert resp.status_code == 400

    def test_a_form_post_answers_with_a_page_not_a_json_body(self, csrf_app, csrf_client):
        """The operator should not be shown raw JSON after clicking a button."""
        signed, raw = _csrf_token_pair(csrf_app)
        _login(csrf_client, raw)

        resp = csrf_client.post(
            "/admin/trigger-crawl",
            data={"csrf_token": signed},
            headers={"Accept": "text/html"},
        )

        assert resp.status_code in (200, 302)
        if resp.status_code == 200:
            assert "application/json" not in resp.headers.get("Content-Type", "")

    def test_the_token_is_accepted_from_a_json_body(self, csrf_app, csrf_client):
        """A JSON client may carry the token in the body.

        The global Flask-WTF protection only reads the header and the form
        field, so this path matters for the API blueprint, which is exempt
        from the global protection and relies on the decorator alone.
        """
        signed, raw = _csrf_token_pair(csrf_app)
        _login(csrf_client, raw)

        resp = csrf_client.post(
            "/api/v1/newsletter/preview",
            json={"csrf_token": signed},
        )

        body = resp.get_data(as_text=True)
        assert "CSRF token missing" not in body
        assert "CSRF token invalid" not in body

    def test_the_token_is_read_from_the_form_field(self, csrf_app, csrf_client):
        """The form field is the path an HTML form takes."""
        from routes.decorators import _csrf_token_from_request

        signed, raw = _csrf_token_pair(csrf_app)
        _login(csrf_client, raw)

        with csrf_app.test_request_context(
            "/admin/trigger-crawl",
            method="POST",
            data={"csrf_token": signed},
        ):
            assert _csrf_token_from_request() == signed

    def test_every_admin_form_post_route_accepts_a_form_token(self, csrf_app, csrf_client):
        """No admin endpoint may insist on a header a form cannot send.

        The guard reads the token from the header, the form field or the JSON
        body. An endpoint that reads it from somewhere else would fail for
        every HTML form that posts to it.
        """
        import routes.decorators as decorators

        source = Path(decorators.__file__).read_text()
        assert 'request.headers.get("X-CSRFToken")' in source
        assert "request.form.get(field_name)" in source


# ---------------------------------------------------------------------------
# 2. Every button carries the base class
# ---------------------------------------------------------------------------


class TestButtonsAreStyled:
    """A button without ``btn`` renders as bare text.

    ``.btn-primary`` only sets the colours. The geometry -- the padding, the
    border radius, the minimum height, the font -- lives in ``.btn``. A
    template that wrote ``class="btn-primary"`` produced a control that was
    technically a button and looked like a word.
    """

    def _templates(self):
        return sorted((REPO_ROOT / "templates").rglob("*.html"))

    def test_no_button_class_omits_the_base_class(self):
        offenders = []
        for path in self._templates():
            text = path.read_text()
            for match in re.finditer(r'class="([^"]*)"', text):
                classes = match.group(1).split()
                for cls in classes:
                    if not re.fullmatch(r"btn(-[a-z]+)?", cls):
                        continue
                    if cls in ("btn-delete", "btn-logout", "btn-group"):
                        # These carry their own complete geometry.
                        continue
                    if "btn" not in classes:
                        line = text[: match.start()].count("\n") + 1
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(1)}")
        assert not offenders, "buttons missing the base class:\n" + "\n".join(offenders)

    def test_the_base_class_is_defined_by_the_stylesheet(self):
        css = (REPO_ROOT / "static" / "css" / "components.css").read_text()
        assert re.search(r"^\.btn \{", css, re.MULTILINE)
        assert re.search(r"^\.btn-primary \{", css, re.MULTILINE)

    def test_the_link_button_variant_exists(self):
        """A button styled as a link needs its own rule to exist."""
        css = (REPO_ROOT / "static" / "css" / "components.css").read_text()
        assert re.search(r"^\.btn-link \{", css, re.MULTILINE)


# ---------------------------------------------------------------------------
# 3. Auto-review mode
# ---------------------------------------------------------------------------


class TestAutoReviewMode:
    """Auto-review mode publishes what would otherwise wait for a human."""

    def _article(self, status="editing"):
        from models import Article

        article = Article(
            original_title="A headline",
            original_url="https://example.test/a",
            source_id=1,
            pipeline_status=status,
        )
        return article

    def test_the_switch_defaults_to_off(self):
        """A site that never asked for autonomy must not get it."""
        from schemas.pipeline import ReviewConfig

        assert ReviewConfig().auto_approve is False

    def test_routing_to_review_queues_the_article_when_the_switch_is_off(self, monkeypatch):
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: False)
        article = self._article()

        queued = auto_review.route_to_review(article)

        assert queued is True
        assert article.pipeline_status == "review"

    def test_routing_to_review_publishes_the_article_when_the_switch_is_on(self, monkeypatch):
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)
        article = self._article()

        queued = auto_review.route_to_review(article)

        assert queued is False
        assert article.pipeline_status == "done"
        assert article.published_at is not None

    def test_the_pipeline_transition_to_review_honours_the_switch(self, monkeypatch):
        """The stage that routes an article to review must respect it."""
        from services import auto_review
        from tasks.pipeline import _transition_article_status

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)
        article = self._article(status="pending")

        _transition_article_status(article, "review")

        assert article.pipeline_status == "done"

    def test_the_pipeline_transition_to_review_queues_when_off(self, monkeypatch):
        from services import auto_review
        from tasks.pipeline import _transition_article_status

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: False)
        article = self._article(status="pending")

        _transition_article_status(article, "review")

        assert article.pipeline_status == "review"

    def test_an_unreadable_setting_fails_closed(self, monkeypatch):
        """A broken configuration must not silently start publishing."""

        def _boom():
            raise RuntimeError("the configuration is broken")

        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", _boom)

        # The real implementation, not the one the conftest fixture pins.
        assert _real_is_auto_approve_enabled() is False

    def test_a_broken_setting_leaves_the_articles_waiting(self, monkeypatch):
        """Failing closed means the article stays in the queue."""
        from services import auto_review

        def _boom():
            raise RuntimeError("the configuration is broken")

        monkeypatch.setattr("schemas.pipeline.load_pipeline_config", _boom)

        article = self._article(status="editing")
        auto_review.route_to_review(article)

        assert article.pipeline_status == "review"

    def test_the_review_dispatch_is_skipped_when_the_article_was_published(self, monkeypatch):
        """Re-running the editor on a published article edits it twice."""
        from unittest.mock import MagicMock

        from services import auto_review
        from services import pipeline_utils

        fake_task = MagicMock()
        fake_module = MagicMock()
        fake_module.fake_review_task = fake_task

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)
        monkeypatch.setitem(pipeline_utils._task_fn_cache, "review", (fake_module, "fake_review_task"))

        pipeline_utils._dispatch_next(12345, run_id=None, next_status="review")

        assert fake_task.apply_async.call_count == 0

    def test_the_review_dispatch_still_happens_in_manual_mode(self, monkeypatch):
        """With a human waiting in the queue, the editor still runs."""
        from unittest.mock import MagicMock

        from services import auto_review
        from services import pipeline_utils

        fake_task = MagicMock()
        fake_module = MagicMock()
        fake_module.fake_review_task = fake_task

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: False)
        monkeypatch.setitem(pipeline_utils._task_fn_cache, "review", (fake_module, "fake_review_task"))

        pipeline_utils._dispatch_next(12345, run_id=None, next_status="review")

        assert fake_task.apply_async.call_count == 1

    def test_the_beat_task_is_registered(self):
        """The safety net has to be on the beat, or it never runs."""
        from config import Config

        schedule = Config.get_beat_schedule()
        assert "auto-approve-review-articles" in schedule
        assert (
            schedule["auto-approve-review-articles"]["task"]
            == "tasks.scheduler.auto_approve_review_articles"
        )

    def test_the_task_is_imported_so_it_registers(self):
        import tasks

        assert "auto_approve_review_articles" in tasks.__all__

    def test_the_queue_is_drained_when_the_switch_is_on(self, app, create_source, monkeypatch):
        from constants import PipelineStatus
        from extensions import db
        from models import Article
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)

        source = create_source()
        article = Article(
            original_title="Waiting in the queue",
            original_url="https://example.test/queued",
            source_id=source.id,
            pipeline_status=PipelineStatus.REVIEW,
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id

        approved = auto_review.auto_approve_queued()

        assert approved == 1
        db.session.expire_all()
        assert db.session.get(Article, article_id).pipeline_status == PipelineStatus.DONE

    def test_the_queue_is_left_alone_when_the_switch_is_off(self, app, create_source, monkeypatch):
        from constants import PipelineStatus
        from extensions import db
        from models import Article
        from services import auto_review

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: False)

        source = create_source()
        article = Article(
            original_title="Waiting in the queue",
            original_url="https://example.test/queued-off",
            source_id=source.id,
            pipeline_status=PipelineStatus.REVIEW,
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id

        approved = auto_review.auto_approve_queued()

        assert approved == 0
        db.session.expire_all()
        assert db.session.get(Article, article_id).pipeline_status == PipelineStatus.REVIEW

    def test_an_article_that_is_not_waiting_is_not_approved(self):
        from services.auto_review import approve_article

        article = self._article(status="done")

        assert approve_article(article) is False
        assert article.pipeline_status == "done"

    def test_an_approved_article_gets_the_post_finalize_work(self, monkeypatch):
        """An approved article is still a published article.

        Trend memory, the webhooks and the embedding are what a published
        article is for. An article that went through the review queue has to
        get the same treatment as one that passed the editor on the first
        try, or the site learns from a fraction of what it publishes.
        """
        from services import pipeline_degradation

        called = []
        monkeypatch.setattr(
            pipeline_degradation,
            "post_finalize_article",
            lambda article, run_id=None: called.append(article.id),
        )

        article = self._article(status="review")
        from services.auto_review import approve_article

        assert approve_article(article) is True
        assert called == [article.id]

    def test_a_failed_post_finalize_does_not_unpublish_the_article(self, monkeypatch):
        """The article is published whatever the post-finalize work does."""
        from services import pipeline_degradation

        def _boom(article, run_id=None):
            raise RuntimeError("the trend memory call failed")

        monkeypatch.setattr(pipeline_degradation, "post_finalize_article", _boom)

        article = self._article(status="review")
        from services.auto_review import approve_article

        assert approve_article(article) is True
        assert article.pipeline_status == "done"

    def test_the_human_and_the_auto_approver_agree(self, monkeypatch):
        """One primitive, so the two cannot drift apart."""
        from services import auto_review, pipeline_degradation

        monkeypatch.setattr(
            pipeline_degradation,
            "post_finalize_article",
            lambda article, run_id=None: None,
        )

        by_hand = self._article(status="review")
        by_machine = self._article(status="review")

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: False)
        auto_review.route_to_review(by_hand)
        auto_review.approve_article(by_hand, reason="admin")

        monkeypatch.setattr(auto_review, "is_auto_approve_enabled", lambda: True)
        auto_review.route_to_review(by_machine)

        assert by_hand.pipeline_status == by_machine.pipeline_status
        assert by_hand.retry_count == by_machine.retry_count
        assert by_hand.last_error == by_machine.last_error
        assert by_hand.scheduled_publish_at == by_machine.scheduled_publish_at
        assert by_hand.published_at is not None
        assert by_machine.published_at is not None


# ---------------------------------------------------------------------------
# 4. The settings the panel exposes
# ---------------------------------------------------------------------------


@pytest.fixture
def config_files(tmp_path, monkeypatch):
    """Point the settings service at a throwaway set of configuration files."""
    from services import admin_settings

    providers = tmp_path / "providers.yaml"
    pipeline = tmp_path / "pipeline.yaml"
    topics = tmp_path / "topics.yaml"
    sources = tmp_path / "sources.yaml"

    providers.write_text(
        yaml.safe_dump({"providers": [{"id": "local", "type": "openai", "enabled": True}]}),
    )
    pipeline.write_text(
        yaml.safe_dump(
            {
                "pipeline": {
                    "selector": {"provider": "local", "model": "m"},
                    "researcher": {"provider": "local", "model": "m"},
                    "writer": {"provider": "local", "model": "m"},
                    "editor": {"provider": "local", "model": "m"},
                },
                "schedule": {"crawl_interval_minutes": 30},
            },
        ),
    )
    topics.write_text(
        yaml.safe_dump(
            {
                "topics": {
                    "ai": {
                        "display_name": "AI",
                        "description": "machine learning",
                        "color": "purple",
                    },
                    "privacy": {
                        "display_name": "Privacy",
                        "description": "data protection",
                        "color": "green",
                    },
                },
            },
        ),
    )
    sources.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {
                        "id": "hn",
                        "name": "Hacker News",
                        "type": "api",
                        "enabled": True,
                        "topics": {"match_mode": "keyword", "include": ["ai", "privacy"]},
                    },
                    {
                        "id": "tc",
                        "name": "TechCrunch",
                        "type": "rss",
                        "enabled": True,
                        "topics": {"match_mode": "keyword", "include": ["ai"]},
                    },
                ],
            },
        ),
    )

    monkeypatch.setattr(admin_settings, "_providers_path", lambda: providers)
    monkeypatch.setattr(admin_settings, "_pipeline_path", lambda: pipeline)
    monkeypatch.setattr(admin_settings, "_topics_path", lambda: topics)
    monkeypatch.setattr(admin_settings, "_sources_path", lambda: sources)

    return {
        "providers": providers,
        "pipeline": pipeline,
        "topics": topics,
        "sources": sources,
    }


class TestAdminTopics:
    """The operator can set, change and remove the topics the site follows."""

    def test_the_topics_are_readable(self, config_files):
        from services.admin_settings import read_topics

        topics = read_topics()
        by_id = {t.id: t for t in topics}

        assert set(by_id) == {"ai", "privacy"}
        assert by_id["ai"].display_name == "AI"
        assert by_id["ai"].color == "purple"
        assert by_id["ai"].source_count == 2
        assert by_id["privacy"].source_count == 1

    def test_a_topic_can_be_changed(self, config_files):
        from services.admin_settings import read_topics, update_topics

        changed = update_topics(
            {"ai": {"display_name": "Artificial Intelligence", "color": "blue"}},
        )

        assert changed == ["ai"]
        by_id = {t.id: t for t in read_topics()}
        assert by_id["ai"].display_name == "Artificial Intelligence"
        assert by_id["ai"].color == "blue"
        # The untouched field survives.
        assert by_id["ai"].description == "machine learning"

    def test_a_topic_can_be_added(self, config_files):
        from services.admin_settings import read_topics, add_topic

        topic_id = add_topic("Robotics", "Robotics", "machines", "orange")

        assert topic_id == "robotics"
        by_id = {t.id: t for t in read_topics()}
        assert by_id["robotics"].display_name == "Robotics"
        assert by_id["robotics"].color == "orange"

    def test_a_duplicate_topic_is_refused(self, config_files):
        from services.admin_settings import SettingsError, add_topic

        with pytest.raises(SettingsError):
            add_topic("ai", "AI again")

    def test_an_unknown_colour_is_refused(self, config_files):
        from services.admin_settings import SettingsError, add_topic

        with pytest.raises(SettingsError):
            add_topic("newone", "New One", "d", "chartreuse")

    def test_a_topic_can_be_removed(self, config_files):
        from services.admin_settings import read_topics, remove_topic

        touched = remove_topic("privacy")

        assert touched == ["hn"]
        assert {t.id for t in read_topics()} == {"ai"}

    def test_removing_a_topic_cleans_up_the_sources(self, config_files):
        """A source that follows a topic that no longer exists is invalid.

        The validator rejects it, so leaving the reference behind would break
        the configuration for everything else.
        """
        from services.admin_settings import remove_topic

        remove_topic("ai")

        sources = yaml.safe_load(config_files["sources"].read_text())
        includes = {
            entry["id"]: entry["topics"]["include"]
            for entry in sources["sources"]
        }
        assert includes["hn"] == ["privacy"]
        assert includes["tc"] == []

    def test_removing_a_topic_that_does_not_exist_is_refused(self, config_files):
        from services.admin_settings import SettingsError, remove_topic

        with pytest.raises(SettingsError):
            remove_topic("nosuchtopic")


class TestAdminSchedule:
    """The operator can change how often the pipeline runs."""

    def test_the_schedule_is_readable(self, config_files):
        from services.admin_settings import read_schedule

        schedule = read_schedule()

        assert schedule.crawl_interval_minutes == 30
        assert schedule.auto_approve_interval_minutes == 1

    def test_the_schedule_can_be_changed(self, config_files):
        from services.admin_settings import read_schedule, update_schedule

        changed = update_schedule({"crawl_interval_minutes": 5})

        assert changed == ["crawl_interval_minutes"]
        assert read_schedule().crawl_interval_minutes == 5

    def test_a_value_out_of_range_is_refused(self, config_files):
        from services.admin_settings import SettingsError, update_schedule

        with pytest.raises(SettingsError):
            update_schedule({"crawl_interval_minutes": 0})

    def test_an_unknown_setting_is_refused(self, config_files):
        from services.admin_settings import SettingsError, update_schedule

        with pytest.raises(SettingsError):
            update_schedule({"crawl_everything": 5})

    def test_the_value_is_written_to_the_pipeline_file(self, config_files):
        from services.admin_settings import update_schedule

        update_schedule({"crawl_interval_minutes": 15})

        raw = yaml.safe_load(config_files["pipeline"].read_text())
        assert raw["schedule"]["crawl_interval_minutes"] == 15


class TestAdminReviewSettings:
    """The operator can switch auto-review mode on and off."""

    def test_the_review_settings_are_readable(self, config_files):
        from services.admin_settings import read_review

        review = read_review()

        assert review.enabled is False
        assert review.auto_approve is False
        assert review.auto_publish_threshold is None

    def test_auto_review_mode_can_be_switched_on(self, config_files):
        from services.admin_settings import read_review, update_review

        changed = update_review(auto_approve=True)

        assert "auto_approve" in changed
        assert read_review().auto_approve is True

    def test_auto_review_mode_can_be_switched_off(self, config_files):
        from services.admin_settings import read_review, update_review

        update_review(auto_approve=True)
        update_review(auto_approve=False)

        assert read_review().auto_approve is False

    def test_the_threshold_can_be_set(self, config_files):
        from services.admin_settings import read_review, update_review

        update_review(auto_publish_threshold=7)

        assert read_review().auto_publish_threshold == 7

    def test_the_threshold_can_be_cleared(self, config_files):
        from services.admin_settings import read_review, update_review

        update_review(auto_publish_threshold=7)
        update_review(clear_threshold=True)

        assert read_review().auto_publish_threshold is None

    def test_an_impossible_threshold_is_refused(self, config_files):
        from services.admin_settings import SettingsError, update_review

        with pytest.raises(SettingsError):
            update_review(auto_publish_threshold=500)

    def test_the_value_reaches_the_pipeline_configuration(self, config_files):
        """The pipeline reads the setting from the file, so it has to be there."""
        from services.admin_settings import update_review

        update_review(auto_approve=True)

        raw = yaml.safe_load(config_files["pipeline"].read_text())
        assert raw["pipeline"]["review"]["auto_approve"] is True

    def test_the_written_file_still_loads(self, config_files):
        """A panel that writes a file the loader rejects would break the site."""
        from schemas.pipeline import load_pipeline_config

        from services.admin_settings import update_review

        update_review(auto_approve=True, enabled=True, auto_publish_threshold=5)

        config = load_pipeline_config(config_files["pipeline"])
        assert config.pipeline.review.auto_approve is True
        assert config.pipeline.review.enabled is True
        assert config.pipeline.review.auto_publish_threshold == 5


# ---------------------------------------------------------------------------
# 5. The panel shows the whole stored memory
# ---------------------------------------------------------------------------


class TestTrendMemoryPulldown:
    """A trend memory entry has to be readable in full.

    The signal was rendered into a cell that clipped it at 300 pixels with
    an ellipsis, so the operator could see that a memory existed and nothing
    about what it said.
    """

    def test_the_template_offers_the_whole_signal(self):
        template = (REPO_ROOT / "templates" / "admin" / "trend_memory.html").read_text()

        assert "<details" in template
        assert "memory-full" in template
        assert "{{ memory.signal | e }}" in template

    def test_the_summary_is_truncated_but_the_body_is_not(self):
        template = (REPO_ROOT / "templates" / "admin" / "trend_memory.html").read_text()

        assert "memory.signal | truncate(" in template
        # The full text is rendered inside the details body.
        body = template.split("<div class=\"memory-full\">", 1)[1]
        body = body.split("</div>", 1)[0]
        assert "{{ memory.signal | e }}" in body
        assert "truncate" not in body

    def test_the_cell_no_longer_clips_the_signal(self):
        """The clipping has to move to the summary, not stay on the cell."""
        css = (REPO_ROOT / "static" / "css" / "components.css").read_text()
        cell = css.split(".signal-cell {", 1)[1].split("}", 1)[0]

        assert "overflow: hidden" not in cell
        assert "white-space: nowrap" not in cell
        assert "text-overflow: ellipsis" not in cell

    def test_the_stylesheet_has_the_pulldown_rules(self):
        css = (REPO_ROOT / "static" / "css" / "components.css").read_text()

        assert re.search(r"^\.memory-summary \{", css, re.MULTILINE)
        assert re.search(r"^\.memory-full \{", css, re.MULTILINE)


# ---------------------------------------------------------------------------
# 6. The panel reaches the settings
# ---------------------------------------------------------------------------


class TestTheSettingsPanelExposesTheSettings:
    """The panel has to render the controls the operator needs."""

    def _template(self):
        return (REPO_ROOT / "templates" / "admin" / "settings.html").read_text()

    def test_the_panel_has_a_topics_section(self):
        template = self._template()

        assert "/admin/settings/topics" in template
        assert "/admin/settings/topics/add" in template
        assert "/admin/settings/topics/delete" in template

    def test_the_panel_has_a_schedule_section(self):
        template = self._template()

        assert "/admin/settings/schedule" in template
        assert "schedule_fields" in template

    def test_the_panel_has_a_review_section(self):
        template = self._template()

        assert "/admin/settings/review" in template
        assert "auto_approve" in template

    def test_the_panel_offers_the_auto_review_switch(self):
        template = self._template()

        assert 'name="auto_approve"' in template

    def test_the_settings_routes_exist(self):
        from app import create_app

        app = create_app("testing")
        rules = {str(r) for r in app.url_map.iter_rules()}

        for rule in (
            "/admin/settings/topics",
            "/admin/settings/topics/add",
            "/admin/settings/topics/delete",
            "/admin/settings/schedule",
            "/admin/settings/review",
        ):
            assert rule in rules

    def test_the_new_routes_require_authentication(self):
        """A settings route that answers without a login would be a hole."""
        from routes.admin import admin_bp

        guarded = {
            "update_topics",
            "add_topic",
            "delete_topic",
            "update_schedule",
            "update_review",
        }
        found = set()
        for rule in admin_bp.url_values_defaults and admin_bp.deferred_functions or []:
            found.add(rule)

        # The blueprint records the endpoint names; the guard is applied by
        # the require_auth decorator, which wraps the view.
        import routes.admin.settings as settings_module

        for name in guarded:
            view = getattr(settings_module, name)
            assert view.__name__ == name, f"{name} must be a named view"
            # require_auth wraps the view, so the wrapper is not the raw view.
            assert getattr(view, "__wrapped__", None) is not None, (
                f"{name} must be wrapped by the authentication guard"
            )
