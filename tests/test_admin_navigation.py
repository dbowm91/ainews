"""Tests for the admin navigation.

The admin area lost its navigation for two reasons: a link built with the
wrong endpoint namespace raised a ``BuildError`` and answered HTTP 500, and
an anchor pointing at a POST-only route answered HTTP 405.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"


def _admin_nav_hrefs() -> list[str]:
    html = (TEMPLATES_DIR / "base_admin.html").read_text(encoding="utf-8")
    return re.findall(r'<a href="(/admin[^"]*)"', html)


class TestAdminNavLinksResolve:
    @pytest.mark.parametrize("href", _admin_nav_hrefs())
    def test_nav_link_matches_a_route(self, app, href):
        adapter = app.url_map.bind("localhost")
        assert adapter.match(href) is not None, (
            f"the admin nav links to {href}, which is not a registered route"
        )

    def test_every_admin_section_is_reachable_from_the_nav(self, app):
        """The sections that exist as routes must be navigable."""
        from app import create_app  # noqa: F401 - ensure the app is importable

        sections = {
            "/admin/",
            "/admin/pipelines",
            "/admin/review",
            "/admin/articles",
            "/admin/newsletters",
            "/admin/metrics",
            "/admin/subscribers",
            "/admin/shares",
            "/admin/trend-memory",
            "/admin/sources",
            "/admin/topic-notes",
            "/admin/webhooks",
            "/admin/dead-letters",
        }
        links = set(_admin_nav_hrefs())
        missing = sorted(sections - links)
        assert not missing, (
            "these admin sections have no navigation entry: " + ", ".join(missing)
        )


class TestAdminTemplatesUseValidEndpoints:
    def test_no_wrong_endpoint_namespace(self):
        """``admin.article_detail`` does not exist; the article detail route
        lives in the public blueprint."""
        offenders = []
        for path in sorted((TEMPLATES_DIR / "admin").rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            if "admin.article_detail" in text:
                offenders.append(path.name)
        assert not offenders, (
            "these admin templates reference the non-existent endpoint "
            "'admin.article_detail': " + ", ".join(offenders)
        )

    def test_no_anchor_to_a_post_only_route(self, app):
        """An anchor to a POST-only route answers HTTP 405."""
        post_only = {
            rule.rule
            for rule in app.url_map.iter_rules()
            if "POST" in (rule.methods or set()) and "GET" not in (rule.methods or set())
        }
        offenders = []
        for path in sorted((TEMPLATES_DIR / "admin").rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            for href in re.findall(r'<a href="(/admin[^"]*)"', text):
                if href in post_only:
                    offenders.append(f"{path.name}: {href}")
        assert not offenders, (
            "these anchors point at POST-only routes: " + ", ".join(offenders)
        )


class TestAdminPagesRender:
    @pytest.mark.parametrize(
        "path",
        [
            "/admin/",
            "/admin/pipelines",
            "/admin/review",
            "/admin/articles",
            "/admin/newsletters",
            "/admin/metrics",
            "/admin/subscribers",
            "/admin/shares",
            "/admin/trend-memory",
            "/admin/sources",
            "/admin/topic-notes",
            "/admin/webhooks",
            "/admin/dead-letters",
        ],
    )
    def test_admin_page_returns_200(self, app, auth_client, path):
        response = auth_client.get(path)
        assert response.status_code == 200, (
            f"{path} answered {response.status_code}: "
            f"{response.get_data(as_text=True)[:200]}"
        )


class TestAdminDeadLetters:
    """The stuck-articles table renders an age computed against ``now()``.

    The template only reaches that expression when there is a stuck article
    to show, so the page has to be requested with one.
    """

    def test_dead_letters_page_renders_with_a_stuck_article(
        self, app, auth_client, create_article
    ):
        from datetime import datetime, timedelta, timezone

        from extensions import db

        article = create_article(pipeline_status="researching")
        article.updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
        db.session.commit()

        response = auth_client.get("/admin/dead-letters")
        assert response.status_code == 200, (
            f"the dead letters page answered {response.status_code}: "
            f"{response.get_data(as_text=True)[:300]}"
        )

    def test_now_global_is_registered_and_naive(self, app):
        """``db.DateTime`` values come back naive, so ``now()`` must be too."""
        assert "now" in app.jinja_env.globals
        value = app.jinja_env.globals["now"]()
        assert value.tzinfo is None


class TestAdminHtmxBootstrap:
    def test_nonce_config_does_not_touch_htmx_before_it_loads(self):
        """htmx.min.js is deferred, so an inline script that runs during
        parsing raises 'htmx is not defined' on every admin page."""
        html = (TEMPLATES_DIR / "base_admin.html").read_text(encoding="utf-8")
        inline_scripts = re.findall(r"<script nonce=.*?</script>", html, re.DOTALL)
        for script in inline_scripts:
            assert "htmx.config" not in script or "window.htmx" in script, (
                "the inline script configures htmx before the deferred htmx "
                "bundle has executed, which raises 'htmx is not defined'"
            )

    def test_htmx_bundle_is_loaded_with_defer(self):
        html = (TEMPLATES_DIR / "base_admin.html").read_text(encoding="utf-8")
        match = re.search(r"<script[^>]*htmx\.min\.js[^>]*>", html)
        assert match is not None
        assert "defer" in match.group(0)


class TestAdminDashboardRecentArticles:
    """The dashboard's recent-articles table rendered empty columns.

    The route selected a different set of columns from the one the template
    rendered -- the template reads ``original_title``, ``category``,
    ``selector_result``, ``impact_score`` and ``created_at`` off the row,
    and every one of them was missing from the SELECT list. A column that is
    not selected renders as an empty cell rather than raising, so the table
    looked broken without erroring.
    """

    @staticmethod
    def _cells(html: str) -> list[str]:
        """Return the cell texts of the first row of the recent-articles table."""
        match = re.search(
            r'<table class="dash-table" aria-label="Recent articles table">'
            r".*?<tbody>(.*?)</tbody>",
            html,
            re.DOTALL,
        )
        assert match, "the recent articles table is missing"
        row = re.search(r"<tr>(.*?)</tr>", match.group(1), re.DOTALL)
        assert row, "the recent articles table has no rows"
        return [
            re.sub(r"<[^>]+>", "", cell).strip()
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row.group(1), re.DOTALL)
        ]

    def test_the_table_renders_populated_cells(self, auth_client, create_article):
        from extensions import db

        article = create_article(
            original_title="A Dashboard Article",
            pipeline_status="done",
            category="ai",
            impact_score=64,
        )
        db.session.commit()

        response = auth_client.get("/admin/")
        assert response.status_code == 200
        cells = self._cells(response.get_data(as_text=True))

        # title, topic, status, source, score, impact, created, audit
        assert len(cells) >= 7, f"unexpected column count: {cells}"
        assert cells[0] == "A Dashboard Article", (
            f"the title cell is empty; the route did not select the column "
            f"the template renders: {cells}"
        )
        assert cells[1].lower() == "ai", f"the topic cell is empty: {cells}"
        assert cells[5] == "64", f"the impact cell is empty: {cells}"
        assert cells[6], f"the created cell is empty: {cells}"

    def test_the_route_selects_every_column_the_template_renders(self):
        """A source-level guard on the SELECT list.

        The template reads the attributes off the row, so a column that is
        missing from the query renders blank instead of failing loudly.
        """
        source = (REPO_ROOT / "routes" / "admin" / "dashboard.py").read_text(
            encoding="utf-8"
        )
        query = re.search(
            r"recent\s*=\s*\(\s*db\.session\.query\((.*?)\)\s*\.outerjoin",
            source,
            re.DOTALL,
        )
        assert query, "the recent articles query was not found"
        columns = query.group(1)
        for column in (
            "Article.id",
            "Article.original_title",
            "Article.category",
            "Article.pipeline_status",
            "Article.selector_result",
            "Article.impact_score",
            "Article.created_at",
        ):
            assert column in columns, (
                f"{column} is not selected by the recent-articles query, so "
                "the dashboard renders that column empty"
            )

    def test_the_dashboard_links_to_the_article_audit_trail(self, auth_client, create_article):
        from extensions import db

        article = create_article(original_title="Auditable Article")
        db.session.commit()

        response = auth_client.get("/admin/")
        body = response.get_data(as_text=True)
        assert f"/admin/articles/{article.id}/audit" in body
