"""Contract tests for the public page rendering and navigation.

These lock in the defects that made the public site unusable:

* an HTMX article request rendering a template that did not exist (HTTP 500
  on every article click),
* a body level ``hx-boost`` that replaced the whole document with a bare
  fragment, destroying the page chrome and the ``#content`` swap target,
* a cacheable response that did not vary on the ``HX-Request`` header, so
  the browser handed a cached fragment to a later full page load,
* pipeline internals leaking onto the public index.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"

MARKDOWN_BODY = (
    "### The news\n\n"
    "**Google has released Gemini 4 Carbon**, its latest frontier model.\n\n"
    "Carbon follows Argon from early October 2026."
)


def _template_files() -> list[Path]:
    return sorted(TEMPLATES_DIR.rglob("*.html"))


def _referenced_templates() -> set[str]:
    """Return every template name referenced by render_template() in the app."""
    import re as _re

    pattern = _re.compile(r"render_template\(\s*[\"']([^\"']+)[\"']")
    found: set[str] = set()
    for path in sorted((REPO_ROOT / "routes").rglob("*.py")):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            found.add(match.group(1))
    return found


class TestTemplateReferences:
    """Every template a route renders has to exist."""

    def test_all_referenced_templates_exist(self):
        missing = []
        for name in sorted(_referenced_templates()):
            candidate = TEMPLATES_DIR / name
            if not candidate.exists():
                missing.append(name)
        assert not missing, (
            "routes render templates that do not exist: "
            + ", ".join(missing)
            + ". The article detail route used to render "
            "'partials/article_detail.html', which did not exist, so every "
            "article click answered HTTP 500."
        )

    def test_article_detail_partial_exists(self):
        assert (TEMPLATES_DIR / "partials" / "article_detail.html").exists()

    def test_article_detail_partial_is_a_fragment(self):
        """The HTMX swap target must not be a whole document."""
        html = (TEMPLATES_DIR / "partials" / "article_detail.html").read_text(encoding="utf-8")
        # Jinja comments may mention markup, so strip them before checking.
        markup = re.sub(r"\{#.*?#\}", "", html, flags=re.DOTALL)
        assert "<html" not in markup.lower()
        assert "<body" not in markup.lower()

    def test_full_article_page_reuses_the_fragment(self):
        """The full page and the HTMX fragment cannot drift apart."""
        page = (TEMPLATES_DIR / "article.html").read_text(encoding="utf-8")
        assert 'partials/article_detail.html' in page


class TestNoBodyLevelBoost:
    """``hx-boost`` on ``<body>`` destroys the page chrome.

    An HTMX request for a feed URL is answered with a bare fragment. htmx
    replaces the whole ``<body>`` with it, which strips the header, the
    footer and the ``#content`` wrapper -- and ``#content`` is the swap
    target every article link depends on.
    """

    @pytest.mark.parametrize("template", ["base.html", "base_admin.html"])
    def test_body_has_no_hx_boost(self, template):
        html = (TEMPLATES_DIR / template).read_text(encoding="utf-8")
        body_tag = re.search(r"<body[^>]*>", html)
        assert body_tag is not None, f"{template} has no <body> tag"
        assert "hx-boost" not in body_tag.group(0), (
            f"{template} sets hx-boost on <body>. Page level navigation must be "
            "a normal full page load; in-page updates declare their own "
            "hx-get with an explicit target."
        )


class TestFragmentAndPageAreDistinct:
    """The article route answers two different documents for one URL."""

    def test_htmx_request_returns_a_fragment(self, app, client, create_article):
        from extensions import db

        article = create_article(final_article=json.dumps({
            "headline": "Headline",
            "tldr": "A short summary.",
            "why_it_matters": "It matters.",
            "body": MARKDOWN_BODY,
            "key_points": ["A point."],
            "what_to_watch": "Watch this.",
            "citations": [],
        }))
        db.session.commit()

        response = client.get(f"/article/{article.id}", headers={"HX-Request": "true"})
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<html" not in body.lower()
        assert "article-full" in body

    def test_plain_request_returns_a_full_page(self, app, client, create_article):
        from extensions import db

        article = create_article(final_article=json.dumps({
            "headline": "Headline",
            "tldr": "A short summary.",
            "why_it_matters": "It matters.",
            "body": MARKDOWN_BODY,
            "key_points": ["A point."],
            "what_to_watch": "Watch this.",
            "citations": [],
        }))
        db.session.commit()

        response = client.get(f"/article/{article.id}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<html" in body.lower()
        assert 'class="site-header"' in body
        assert 'id="content"' in body

    def test_response_varies_on_htmx_request(self, app, client, create_article):
        """Without this the browser cache serves the fragment to a page load."""
        from extensions import db

        article = create_article(final_article=json.dumps({
            "headline": "Headline",
            "tldr": "A short summary.",
            "why_it_matters": "It matters.",
            "body": MARKDOWN_BODY,
            "key_points": ["A point."],
            "what_to_watch": "Watch this.",
            "citations": [],
        }))
        db.session.commit()

        response = client.get(f"/article/{article.id}")
        vary = response.headers.get("Vary", "")
        assert "HX-Request" in vary, (
            "the article response must vary on HX-Request, otherwise the "
            "browser HTTP cache hands the HTMX fragment to a full page load"
        )


class TestMarkdownIsRendered:
    """The condensed article is Markdown and has to be rendered as HTML."""

    def test_markdown_becomes_html(self, app, client, create_article):
        from extensions import db

        article = create_article(final_article=json.dumps({
            "headline": "Headline",
            "tldr": "A short summary.",
            "why_it_matters": "It matters.",
            "body": MARKDOWN_BODY,
            "key_points": ["**A** point."],
            "what_to_watch": "Watch this.",
            "citations": [],
        }))
        db.session.commit()

        body = client.get(f"/article/{article.id}").get_data(as_text=True)
        assert "<h3>The news</h3>" in body
        assert "<strong>Google has released Gemini 4 Carbon</strong>" in body
        # The raw markdown markers must not survive into the page.
        assert "**Google has released" not in body

    def test_body_has_paragraph_elements(self, app, client, create_article):
        from extensions import db

        article = create_article(final_article=json.dumps({
            "headline": "Headline",
            "tldr": "A short summary.",
            "why_it_matters": "It matters.",
            "body": MARKDOWN_BODY,
            "key_points": ["A point."],
            "what_to_watch": "Watch this.",
            "citations": [],
        }))
        db.session.commit()

        body = client.get(f"/article/{article.id}").get_data(as_text=True)
        assert "<p>" in body


class TestInfiniteScrollFragment:
    """The scroll sentinel swaps itself with ``hx-swap="outerHTML"``.

    The fragment it is replaced with therefore has to contain the new cards
    and the next sentinel, and nothing else. A wrapper element in the
    fragment nests a duplicate id inside the existing one.
    """

    def test_cards_fragment_does_not_nest_a_second_feed(self):
        html = (TEMPLATES_DIR / "partials" / "cards.html").read_text(encoding="utf-8")
        markup = re.sub(r"\{#.*?#\}", "", html, flags=re.DOTALL)
        assert 'id="feed"' not in markup, (
            "the scroll fragment must not wrap the cards in a second #feed "
            "element; the sentinel lives inside the existing one"
        )

    def test_cards_fragment_carries_the_next_sentinel(self):
        html = (TEMPLATES_DIR / "partials" / "cards.html").read_text(encoding="utf-8")
        assert 'id="scroll-sentinel"' in html

    def test_cards_fragment_keeps_the_sort_order(self):
        html = (TEMPLATES_DIR / "partials" / "cards.html").read_text(encoding="utf-8")
        assert "sort=sort" in html, (
            "the next page must keep the active sort order, otherwise the "
            "feed silently switches back to the default ordering"
        )


class TestPublicIndexHasNoPipelineInternals:
    """Pipeline state belongs in the admin area, not on the public index."""

    def test_feed_rail_has_no_pipeline_section(self):
        rail = (TEMPLATES_DIR / "partials" / "feed_rail.html").read_text(encoding="utf-8")
        assert "rail-section--pipeline" not in rail
        assert "produced_count" not in rail
        assert "in_progress_count" not in rail

    def test_article_card_has_no_pipeline_badge(self):
        card = (TEMPLATES_DIR / "partials" / "article_card.html").read_text(encoding="utf-8")
        assert "pipeline_badge" not in card
        assert "pipeline-badge" not in card

    def test_article_card_has_no_quality_or_degradation(self):
        card = (TEMPLATES_DIR / "partials" / "article_card.html").read_text(encoding="utf-8")
        assert "agent-quality" not in card
        assert "agent-degraded" not in card

    def test_admin_still_shows_pipeline_status(self):
        """The information has to be relocated, not deleted."""
        dashboard = (TEMPLATES_DIR / "admin" / "dashboard.html").read_text(encoding="utf-8")
        assert "pipeline status" in dashboard
        assert "pipeline_badge" in dashboard

    def test_admin_articles_table_shows_quality(self):
        table = (
            TEMPLATES_DIR / "admin" / "partials" / "articles_table.html"
        ).read_text(encoding="utf-8")
        assert "agent-quality" in table
