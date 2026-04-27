"""Tests for the newsletter service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock


class TestGenerateNewsletterHTML:
    """Tests for generate_newsletter_html function."""

    def test_generates_valid_html(self, app):
        """Test that generated HTML is well-formed."""
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = (
                '{"headline": "Test Article", "tldr": "Test summary"}'
            )

            html = generate_newsletter_html(
                articles=[article],
                title="Test Newsletter",
                site_url="https://example.com",
                date_str="Mar 24, 2026",
            )

            assert "<!DOCTYPE html>" in html
            assert "Test Newsletter" in html
            assert "Mar 24, 2026" in html
            assert "https://example.com/track/newsletter-click/1" in html

    def test_includes_executive_summary(self, app):
        """Test that executive summary is included when provided."""
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            html = generate_newsletter_html(
                articles=[],
                title="Test",
                site_url="https://example.com",
                executive_summary="This is a test summary.\n\nWith multiple paragraphs.",
            )

            assert "This is a test summary." in html
            assert "With multiple paragraphs." in html

    def test_empty_executive_summary_excluded(self, app):
        """Test that empty executive summary section is excluded."""
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            html = generate_newsletter_html(
                articles=[],
                title="Test",
                site_url="https://example.com",
                executive_summary="",
            )

            # Should not have the summary box
            assert "background:#f0f7ff" not in html

    def test_unsubscribe_url_substitution(self, app):
        """Test that {site_url} placeholder is replaced in unsubscribe URL."""
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            html = generate_newsletter_html(
                articles=[],
                title="Test",
                site_url="https://example.com",
                unsubscribe_url="{site_url}/unsubscribe/token123",
            )

            assert "https://example.com/unsubscribe/token123" in html

    def test_handles_articles_without_category(self, app):
        """Test that articles without category are handled gracefully."""
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            article = MagicMock()
            article.id = 1
            article.category = None
            article.final_article = '{"headline": "Test", "tldr": "Summary"}'

            html = generate_newsletter_html(
                articles=[article],
                title="Test",
                site_url="https://example.com",
            )

            assert "Test" in html
            # Should not have category span
            assert "text-transform:uppercase" not in html or "null" not in html

    def test_handles_empty_articles_list(self, app):
        """Test that empty articles list produces valid HTML."""
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            html = generate_newsletter_html(
                articles=[],
                title="Empty Newsletter",
                site_url="https://example.com",
            )

            assert "Empty Newsletter" in html
            assert "<!DOCTYPE html>" in html


class TestGenerateMainNewsletter:
    """Tests for generate_main_newsletter function."""

    def test_returns_tuple(self, app):
        """Test that function returns (html, subject, count) tuple."""
        with app.app_context():
            from extensions import db
            from models import Article, Source
            from services.newsletter import generate_main_newsletter

            # Create a source and article
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                pipeline_status="done",
                impact_score=50,
                original_title="Test Article",
                final_article='{"headline": "Test", "tldr": "Summary"}',
                created_at=datetime.now(timezone.utc),
            )
            db.session.add(article)
            db.session.commit()

            html, subject, count = generate_main_newsletter(
                site_url="https://example.com",
                max_articles=10,
            )

            assert isinstance(html, str)
            assert isinstance(subject, str)
            assert isinstance(count, int)
            assert count >= 1
            assert "ainews" in subject

    def test_respects_max_articles(self, app):
        """Test that max_articles limit is respected."""
        with app.app_context():
            from extensions import db
            from models import Article, Source
            from services.newsletter import generate_main_newsletter

            source = Source(source_key="test2", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            # Create 5 articles
            for i in range(5):
                article = Article(
                    source_id=source.id,
                    pipeline_status="done",
                    impact_score=50 - i,
                    original_title=f"Article {i}",
                    final_article=f'{{"headline": "Article {i}", "tldr": "Summary"}}',
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(article)
            db.session.commit()

            _, _, count = generate_main_newsletter(max_articles=3)
            assert count == 3


class TestGenerateTopicNewsletter:
    """Tests for generate_topic_newsletter function."""

    def test_filters_by_topic(self, app):
        """Test that only articles from the specified topic are included."""
        with app.app_context():
            from extensions import db
            from models import Article, Source
            from services.newsletter import generate_topic_newsletter

            source = Source(source_key="test3", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            # Create articles in different categories
            for category in ["ai", "security", "ai"]:
                article = Article(
                    source_id=source.id,
                    pipeline_status="done",
                    impact_score=50,
                    category=category,
                    original_title=f"{category} Article",
                    final_article='{"headline": "Test", "tldr": "Summary"}',
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(article)
            db.session.commit()

            _, _, count = generate_topic_newsletter(topic_key="ai")
            assert count == 2

    def test_returns_zero_for_empty_topic(self, app):
        """Test that empty topic returns zero articles."""
        with app.app_context():
            from services.newsletter import generate_topic_newsletter

            _, _, count = generate_topic_newsletter(topic_key="nonexistent")
            assert count == 0


class TestNewsletterHtmlEscaping:
    """Tests for HTML escaping of untrusted content in newsletter HTML."""

    def test_escapes_script_in_headline(self, app):
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = (
                '{"headline": "<script>alert(1)</script>", "tldr": "safe"}'
            )
            html = generate_newsletter_html(
                articles=[article], title="T", site_url="https://x.com"
            )
            assert "<script" not in html
            assert "&lt;script&gt;" in html

    def test_escapes_img_onerror_in_headline(self, app):
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = (
                '{"headline": "<img src=x onerror=alert(1)>", "tldr": "safe"}'
            )
            html = generate_newsletter_html(
                articles=[article], title="T", site_url="https://x.com"
            )
            # html.escape converts < to &lt; and > to &gt;,
            # preventing the tag from being interpreted by email clients
            assert "<img" not in html
            assert "&lt;img" in html

    def test_escapes_script_in_tldr(self, app):
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = (
                '{"headline": "safe", "tldr": "<script>alert(1)</script>"}'
            )
            html = generate_newsletter_html(
                articles=[article], title="T", site_url="https://x.com"
            )
            assert "<script" not in html
            assert "&lt;script&gt;" in html

    def test_escapes_script_in_category(self, app):
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            article = MagicMock()
            article.id = 1
            article.category = '<script>alert("cat")</script>'
            article.final_article = '{"headline": "safe", "tldr": "safe"}'
            html = generate_newsletter_html(
                articles=[article], title="T", site_url="https://x.com"
            )
            assert "<script" not in html
            assert "&lt;script&gt;" in html

    def test_escapes_script_in_title(self, app):
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            html = generate_newsletter_html(
                articles=[], title="<script>alert(1)</script>", site_url="https://x.com"
            )
            assert "<script" not in html
            assert "&lt;script&gt;" in html

    def test_escapes_script_in_executive_summary(self, app):
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            html = generate_newsletter_html(
                articles=[],
                title="T",
                site_url="https://x.com",
                executive_summary="<script>alert(1)</script>",
            )
            assert "<script" not in html
            assert "&lt;script&gt;" in html

    def test_escapes_html_entities_in_headline(self, app):
        with app.app_context():
            from services.newsletter import generate_newsletter_html

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "A & B < C > D", "tldr": "safe"}'
            html = generate_newsletter_html(
                articles=[article], title="T", site_url="https://x.com"
            )
            assert "A &amp; B &lt; C &gt; D" in html


class TestNewsletterHtmlWellFormed:
    """Tests for HTML well-formedness in newsletter generation."""

    def test_generated_html_is_well_formed(self, app):
        """Test that generated HTML is well-formed (no unclosed tags, proper nesting)."""
        from html.parser import HTMLParser

        from services.newsletter import generate_newsletter_html

        class WellFormednessChecker(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.errors = []

            def handle_starttag(self, tag, attrs):
                void_elements = {
                    "area", "base", "br", "col", "embed", "hr", "img", "input",
                    "link", "meta", "param", "source", "track", "wbr",
                }
                if tag not in void_elements:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if self.stack and self.stack[-1] == tag:
                    self.stack.pop()
                elif tag in self.stack:
                    self.errors.append(f"Unexpected close tag: {tag}")

            def handle_data(self, data):
                pass

        with app.app_context():
            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test Article", "tldr": "Test summary"}'

            html = generate_newsletter_html(
                articles=[article],
                title="Test Newsletter",
                site_url="https://example.com",
                date_str="Mar 24, 2026",
                executive_summary="This is a test summary.",
            )

            parser = WellFormednessChecker()
            try:
                parser.feed(html)
                assert not parser.errors, f"HTML parsing errors: {parser.errors}"
                assert not parser.stack, f"Unclosed tags: {parser.stack}"
            except Exception as e:
                assert False, f"HTML parsing failed: {e}"

    def test_newsletter_with_all_article_fields_is_well_formed(self, app):
        """Test well-formedness with a fully populated article."""
        from html.parser import HTMLParser

        from services.newsletter import generate_newsletter_html

        class WellFormednessChecker(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.errors = []

            def handle_starttag(self, tag, attrs):
                void_elements = {
                    "area", "base", "br", "col", "embed", "hr", "img", "input",
                    "link", "meta", "param", "source", "track", "wbr",
                }
                if tag not in void_elements:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if self.stack and self.stack[-1] == tag:
                    self.stack.pop()
                elif tag in self.stack:
                    self.errors.append(f"Unexpected close tag: {tag}")

        with app.app_context():
            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = (
                '{"headline": "AI Breakthrough", "tldr": "Major advance", '
                '"why_it_matters": "Significance", "body": "Paragraph 1. Paragraph 2.", '
                '"what_to_watch": "Next steps", "key_points": ["Point 1", "Point 2"], '
                '"citations": []}'
            )

            html = generate_newsletter_html(
                articles=[article],
                title="AI Newsletter",
                site_url="https://example.com",
                date_str="Mar 24, 2026",
            )

            parser = WellFormednessChecker()
            try:
                parser.feed(html)
                assert not parser.errors, f"HTML parsing errors: {parser.errors}"
                assert not parser.stack, f"Unclosed tags: {parser.stack}"
            except Exception as e:
                assert False, f"HTML parsing failed: {e}"
