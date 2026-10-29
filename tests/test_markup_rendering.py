"""Tests for the article markup rendering and sanitization.

The condensed article is authored by a language model as Markdown (or as
HTML, depending on the model). It has to reach the reader as structured,
safe HTML:

* Markdown that is emitted as plain text shows the reader literal ``**bold**``
  and ``### heading`` markers.
* An HTML body sanitized with a tag allowlist that omits block level
  elements loses its paragraph structure, and every paragraph is welded into
  one unreadable wall of text.
"""

from __future__ import annotations

import json


from services.markup import (
    looks_like_html,
    paragraphize,
    render_body,
    render_inline,
    render_markdown,
    sanitize_html,
)


class TestRenderMarkdown:
    def test_markdown_heading_becomes_heading(self):
        html = render_markdown("### The news\n\nSome text.")
        assert "<h3>The news</h3>" in html
        assert "<p>Some text.</p>" in html

    def test_emphasis_becomes_markup(self):
        html = render_markdown("A **bold** claim and an *italic* one.")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_markdown_markers_do_not_survive(self):
        html = render_markdown("A **bold** claim.")
        assert "**" not in html

    def test_empty_input(self):
        assert render_markdown("") == ""
        assert render_markdown(None) == ""


class TestRenderInline:
    def test_no_wrapping_paragraph(self):
        html = render_inline("A **bold** claim.")
        assert not html.startswith("<p>")
        assert "<strong>bold</strong>" in html

    def test_empty_input(self):
        assert render_inline("") == ""


class TestRenderBody:
    def test_markdown_body_is_rendered(self):
        html = render_body("### The news\n\n**Bold** paragraph.\n\nSecond paragraph.")
        assert "<h3>The news</h3>" in html
        assert "<strong>Bold</strong>" in html
        assert html.count("<p>") == 2

    def test_html_body_keeps_its_paragraphs(self):
        """An HTML body must not lose its paragraph structure."""
        html = render_body("<p>First.</p><p>Second.</p>")
        assert "<p>First.</p>" in html
        assert "<p>Second.</p>" in html

    def test_script_content_is_removed(self):
        html = render_body("<p>Safe.</p><script>alert('xss')</script>")
        assert "alert" not in html
        assert "<p>Safe.</p>" in html

    def test_event_handlers_are_dropped(self):
        html = render_body('<p onclick="alert(1)">Text</p>')
        assert "onclick" not in html

    def test_javascript_urls_are_dropped(self):
        html = render_body('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in html

    def test_wall_of_text_is_split_into_paragraphs(self):
        """A single unbroken run has to become readable paragraphs."""
        blob = (
            "The AI boom has led to a surge in energy demand across the country. "
            "Critics say this is a stress test on the grid. "
            "Worries abound about rising electrical bills. "
            "Industry insiders tempered the criticism with optimism. "
            "Grid modernization could follow from the flood of connections. "
            "The opportunity is enormous according to the founders."
        )
        html = render_body(blob)
        assert html.count("<p>") >= 2
        assert "**" not in html

    def test_empty_input(self):
        assert render_body("") == ""
        assert render_body(None) == ""


class TestParagraphize:
    def test_existing_paragraphs_are_kept(self):
        text = "One.\n\nTwo.\n\nThree."
        assert paragraphize(text) == text

    def test_hard_wrapped_text_is_split(self):
        text = "One.\nTwo.\nThree."
        assert paragraphize(text) == "One.\n\nTwo.\n\nThree."

    def test_blob_is_split(self):
        blob = (
            "One sentence. Another sentence. A third one. And a fourth. "
            "A fifth one follows. A sixth one too. A seventh one here. "
            "An eighth one closes it."
        )
        result = paragraphize(blob)
        assert "\n\n" in result
        assert result.count("\n\n") >= 1

    def test_empty_input(self):
        assert paragraphize("") == ""
        assert paragraphize(None) == ""


class TestLooksLikeHtml:
    def test_block_tags_detected(self):
        assert looks_like_html("<p>text</p>")
        assert looks_like_html("<h3>text</h3>")

    def test_plain_text_is_not_html(self):
        assert not looks_like_html("Just some text.")
        assert not looks_like_html("### A heading\n\nText.")


class TestSanitizeFinalArticle:
    """The stored body must keep its block structure.

    The previous allowlist (a, b, i, ul, li) dropped ``<p>``, so an HTML
    body was flattened into one wall of text before it was ever stored.
    """

    def test_paragraphs_survive_sanitization(self):
        from services.article import sanitize_final_article

        payload = json.dumps({"body": "<p>First.</p><p>Second.</p>"})
        stored = json.loads(sanitize_final_article(payload))
        assert "<p>First.</p>" in stored["body"]
        assert "<p>Second.</p>" in stored["body"]

    def test_scripts_are_stripped(self):
        from services.article import sanitize_final_article

        payload = json.dumps({"body": "<p>Safe.</p><script>alert(1)</script>"})
        stored = json.loads(sanitize_final_article(payload))
        assert "alert(1)" not in stored["body"]
        assert "<p>Safe.</p>" in stored["body"]

    def test_markdown_is_untouched(self):
        from services.article import sanitize_final_article

        payload = json.dumps({"body": "### The news\n\n**Bold** text."})
        stored = json.loads(sanitize_final_article(payload))
        assert "### The news" in stored["body"]
        assert "**Bold**" in stored["body"]


class TestFallbackArticle:
    """A degraded article has no model structure, so the body is built.

    The raw extracted text is used as the body, and it is paragraphised
    first: scraped text often arrives as one uninterrupted run.
    """

    def test_body_is_paragraphised(self):
        from services.article_fallback import build_fallback_article_json

        class FakeArticle:
            original_title = "Title"
            extracted_text = (
                "First sentence of the scraped text. "
                "Second sentence of the scraped text. "
                "Third sentence of the scraped text. "
                "Fourth sentence of the scraped text. "
                "Fifth sentence of the scraped text."
            )
            original_url = "https://example.com/a"
            original_author = "Author"

        payload = json.loads(build_fallback_article_json(FakeArticle()))
        assert "\n\n" in payload["body"]
        assert payload["headline"] == "Title"

    def test_body_falls_back_to_the_title(self):
        from services.article_fallback import build_fallback_article_json

        class FakeArticle:
            original_title = "Only a title"
            extracted_text = ""
            original_url = ""
            original_author = ""

        payload = json.loads(build_fallback_article_json(FakeArticle()))
        assert payload["body"] == "Only a title"


class TestSanitizeHtml:
    def test_dangerous_blocks_are_removed_with_their_content(self):
        html = sanitize_html("<p>ok</p><iframe src='http://evil'></iframe>")
        assert "iframe" not in html
        assert "<p>ok</p>" in html

    def test_images_are_not_allowed(self):
        html = sanitize_html('<p><img src="http://tracker/pixel.gif"></p>')
        assert "<img" not in html

    def test_empty_input(self):
        assert sanitize_html("") == ""
