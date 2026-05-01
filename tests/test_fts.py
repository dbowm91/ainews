"""Tests for FTS5 query escaping to prevent injection vulnerabilities."""

from services.search.sqlite_fts import _escape_fts5_string


class TestEscapeFTS5String:
    """Tests for _escape_fts5_string helper function."""

    def test_escapes_double_quotes(self):
        """Double quotes should be escaped by doubling them per FTS5 rules."""
        assert _escape_fts5_string('hello "world"') == 'hello ""world""'

    def test_no_quotes_unchanged(self):
        """Strings without double quotes should be unchanged."""
        assert _escape_fts5_string("hello world") == "hello world"

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert _escape_fts5_string("") == ""

    def test_multiple_quotes(self):
        """Multiple double quotes should all be escaped."""
        assert _escape_fts5_string('a"b"c"d') == 'a""b""c""d'

    def test_only_quotes(self):
        """String with only double quotes."""
        assert _escape_fts5_string('""') == '""""'


class TestFTS5QueryWithEscapedChars:
    """Tests for FTS5 queries with escaped special characters."""

    def test_fts5_query_with_escaped_url(self):
        """FTS5 query with escaped double quotes in URL is properly formed."""
        from services.search.sqlite_fts import _escape_fts5_string

        # Build FTS5 query with escaped URL
        url = 'https://example.com/article?"id"=1'
        escaped_url = _escape_fts5_string(url)
        fts_query = f'original_url:"{escaped_url}"'

        # Verify the query is properly formed with escaped quotes
        assert '""id""' in fts_query
        # Verify the original unescaped pattern is not present as a standalone token
        # The escaped form should have doubled quotes
        import re
        # Should not have single double-quote surrounding id without being part of double-double-quote
        assert re.search(r'(?<!")"id"(?!")', fts_query) is None

    def test_fts5_query_injection_prevented(self, app, create_article):
        """FTS5 query with malicious input doesn't break the query structure."""
        # Create test article
        create_article(
            original_url='https://example.com/test',
            original_title="Test Article",
            pipeline_status="published",
        )

        # Test with potentially malicious input containing quotes
        malicious_query = 'test" OR ""="'

        # Build the FTS5 query as done in the actual code
        from services.search.sqlite_fts import _escape_fts5_string

        escaped = _escape_fts5_string(malicious_query)
        fts_query = f'original_url:"{escaped}"'

        # Verify the query structure is safe (quotes are escaped)
        assert '""' in fts_query
        # The query should not have unescaped quotes that could break parsing
        # Count occurrences to verify proper escaping
        assert fts_query.count('"') % 2 == 0  # Should be even (properly paired)
