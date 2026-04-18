"""Tests for newsletter HTML sanitization (nh3-based)."""

from routes.admin.newsletters import _sanitize_newsletter_html


class TestSanitizeNewsletterHtml:
    """Test that dangerous HTML is stripped while safe content is preserved."""

    def test_strips_script_tags(self):
        html = '<p>Hello</p><script>alert("xss")</script><p>World</p>'
        result = _sanitize_newsletter_html(html)
        assert "<script" not in result.lower()
        assert "Hello" in result
        assert "World" in result

    def test_strips_unclosed_script_tags(self):
        html = '<img src="x" onerror="alert(1)"><script src="evil.js">'
        result = _sanitize_newsletter_html(html)
        assert "<script" not in result.lower()
        assert "onerror" not in result.lower()

    def test_strips_event_handlers(self):
        html = '<img src="test.jpg" onerror="alert(1)" alt="test">'
        result = _sanitize_newsletter_html(html)
        assert "onerror" not in result.lower()
        assert "alert" not in result

    def test_strips_onclick_handlers(self):
        html = '<a href="https://example.com" onclick="steal()">click</a>'
        result = _sanitize_newsletter_html(html)
        assert "onclick" not in result.lower()
        assert "steal" not in result
        assert "click" in result

    def test_strips_iframe(self):
        html = '<iframe src="https://evil.com"></iframe>'
        result = _sanitize_newsletter_html(html)
        assert "<iframe" not in result.lower()

    def test_strips_object_embed(self):
        html = '<object data="evil.swf"></object><embed src="evil.swf">'
        result = _sanitize_newsletter_html(html)
        assert "<object" not in result.lower()
        assert "<embed" not in result.lower()

    def test_preserves_safe_tags(self):
        html = "<p>Text with <strong>bold</strong> and <em>italic</em></p>"
        result = _sanitize_newsletter_html(html)
        assert "<p>" in result
        assert "<strong>" in result
        assert "<em>" in result

    def test_preserves_safe_links(self):
        html = '<a href="https://example.com" title="Example">Link</a>'
        result = _sanitize_newsletter_html(html)
        assert 'href="https://example.com"' in result
        assert "Link" in result

    def test_preserves_safe_images(self):
        html = '<img src="https://example.com/photo.jpg" alt="Photo">'
        result = _sanitize_newsletter_html(html)
        assert 'src="https://example.com/photo.jpg"' in result
        assert 'alt="Photo"' in result

    def test_preserves_tables(self):
        html = "<table><thead><tr><th>Header</th></tr></thead><tbody><tr><td>Data</td></tr></tbody></table>"
        result = _sanitize_newsletter_html(html)
        assert "<table>" in result
        assert "<th>" in result
        assert "<td>" in result

    def test_empty_html(self):
        assert _sanitize_newsletter_html("") == ""
        assert _sanitize_newsletter_html(None) is None

    def test_strips_javascript_urls(self):
        html = '<a href="javascript:alert(1)">click</a>'
        result = _sanitize_newsletter_html(html)
        assert "javascript:" not in result.lower()

    def test_multiple_attack_vectors(self):
        html = """
        <p>Safe content</p>
        <script>alert(1)</script>
        <img onerror="alert(2)" src="x">
        <a href="javascript:alert(3)">link</a>
        <iframe src="evil"></iframe>
        <p onclick="steal()">More safe content</p>
        """
        result = _sanitize_newsletter_html(html)
        assert "<script" not in result.lower()
        assert "<iframe" not in result.lower()
        assert "onerror" not in result.lower()
        assert "onclick" not in result.lower()
        assert "javascript:" not in result.lower()
        assert "Safe content" in result
        assert "More safe content" in result
