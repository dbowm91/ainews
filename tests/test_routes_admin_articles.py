"""Tests for routes/admin/articles.py - Article management routes."""

from unittest.mock import MagicMock



class TestSanitizeField:
    """Tests for _sanitize_field helper function."""

    def test_truncates_long_strings(self):
        """Truncates string to max_length."""
        from routes.admin.articles import _sanitize_field

        result = _sanitize_field("a" * 100, 50)
        assert len(result) == 50

    def test_returns_empty_for_non_string(self):
        """Returns empty string for non-string values."""
        from routes.admin.articles import _sanitize_field

        assert _sanitize_field(None, 50) == ""
        assert _sanitize_field(123, 50) == ""
        assert _sanitize_field([], 50) == ""

    def test_returns_short_strings_unchanged(self):
        """Returns string unchanged if under max_length."""
        from routes.admin.articles import _sanitize_field

        result = _sanitize_field("short", 50)
        assert result == "short"


class TestQueryLooksLikeUrl:
    """Tests for _query_looks_like_url helper function."""

    def test_returns_true_for_http_url(self):
        """Returns True for http:// URLs."""
        from routes.admin.articles import _query_looks_like_url

        assert _query_looks_like_url("http://example.com") is True

    def test_returns_true_for_https_url(self):
        """Returns True for https:// URLs."""
        from routes.admin.articles import _query_looks_like_url

        assert _query_looks_like_url("https://example.com") is True

    def test_returns_true_for_url_with_scheme_and_netloc(self):
        """Returns True for URLs with scheme and netloc."""
        from routes.admin.articles import _query_looks_like_url

        assert _query_looks_like_url("https://example.com/article/123") is True

    def test_returns_false_for_empty_string(self):
        """Returns False for empty string."""
        from routes.admin.articles import _query_looks_like_url

        assert _query_looks_like_url("") is False

    def test_returns_false_for_plain_text(self):
        """Returns False for plain text queries."""
        from routes.admin.articles import _query_looks_like_url

        assert _query_looks_like_url("machine learning") is False
        assert _query_looks_like_url("AI news") is False


class TestApplyNumericFilter:
    """Tests for _apply_numeric_filter helper function."""

    def test_returns_query_for_empty_value(self):
        """Returns original query when value_str is empty."""
        from routes.admin.articles import _apply_numeric_filter
        from models import Article
        from sqlalchemy import select

        query = select(Article)
        result = _apply_numeric_filter(query, Article.impact_score, "")
        assert result is query

    def test_applies_gte_filter(self):
        """Applies >= filter when operator is >=."""
        from routes.admin.articles import _apply_numeric_filter
        from models import Article
        from sqlalchemy import select

        query = select(Article)
        result = _apply_numeric_filter(query, Article.impact_score, "50", ">=")

        stmt = result.compile()
        assert ">=" in str(stmt) or "ge" in str(stmt).lower()

    def test_applies_lte_filter(self):
        """Applies <= filter when operator is <=."""
        from routes.admin.articles import _apply_numeric_filter
        from models import Article
        from sqlalchemy import select

        query = select(Article)
        result = _apply_numeric_filter(query, Article.impact_score, "50", "<=")

        stmt = result.compile()
        assert "<=" in str(stmt) or "le" in str(stmt).lower()

    def test_returns_query_for_invalid_value(self):
        """Returns original query for non-numeric value."""
        from routes.admin.articles import _apply_numeric_filter
        from models import Article
        from sqlalchemy import select

        query = select(Article)
        result = _apply_numeric_filter(query, Article.impact_score, "not-a-number")
        assert result is query


class TestParseDateFilter:
    """Tests for _parse_date_filter helper function."""

    def test_parses_iso_format_with_timezone(self):
        """Parses ISO format date with timezone."""
        from routes.admin.articles import _parse_date_filter

        result, error = _parse_date_filter("2026-01-15T10:30:00+00:00", "date_from")
        assert error is None
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_parses_iso_format_without_timezone(self):
        """Parses ISO format date without timezone and adds UTC."""
        from routes.admin.articles import _parse_date_filter

        result, error = _parse_date_filter("2026-01-15T10:30:00", "date_from")
        assert error is None
        assert result is not None
        assert result.tzinfo is not None

    def test_returns_error_for_invalid_date(self):
        """Returns error for invalid date string."""
        from routes.admin.articles import _parse_date_filter

        result, error = _parse_date_filter("not-a-date", "date_from")
        assert result is None
        assert error is not None
        assert "date from" in error


class TestApplyTagFilter:
    """Tests for _apply_tag_filter helper function."""

    def test_returns_query_for_empty_tag(self, app):
        """Returns original query when tag_slug is empty."""
        from routes.admin.articles import _apply_tag_filter
        from models import Article
        from sqlalchemy import select

        with app.app_context():
            query = select(Article)
            result = _apply_tag_filter(query, "")
            assert result is query

    def test_returns_query_for_nonexistent_tag(self, app, create_tag):
        """Returns original query when tag doesn't exist."""
        from routes.admin.articles import _apply_tag_filter
        from models import Article
        from sqlalchemy import select

        with app.app_context():
            tag = create_tag(name="existent_tag")
            query = select(Article)
            result = _apply_tag_filter(query, "nonexistent-tag-slug")
            assert result is query


class TestParseFinalArticle:
    """Tests for _parse_final_article helper function."""

    def test_returns_empty_for_none_article(self):
        """Returns empty dict for article with no final_article."""
        from routes.admin.articles import _parse_final_article

        article = MagicMock()
        article.final_article = None

        result, original = _parse_final_article(article)
        assert result == {}
        assert original is None

    def test_parses_valid_json(self):
        """Returns parsed JSON for valid final_article."""
        from routes.admin.articles import _parse_final_article

        article = MagicMock()
        article.final_article = '{"headline": "Test", "body": "Content"}'

        result, original = _parse_final_article(article)
        assert result["headline"] == "Test"
        assert result["body"] == "Content"

    def test_returns_empty_for_invalid_json(self):
        """Returns empty dict for invalid JSON."""
        from routes.admin.articles import _parse_final_article

        article = MagicMock()
        article.final_article = "not valid json"

        result, original = _parse_final_article(article)
        assert result == {}
        assert original is None


class TestBuildArticlesQuery:
    """Tests for _build_articles_query helper function."""

    def test_returns_query_and_empty_errors(self, app):
        """Returns query and empty date_errors for valid params."""
        from routes.admin.articles import _build_articles_query

        with app.app_context():
            query, date_errors = _build_articles_query(
                query="test",
                status="",
                category="",
                source_id="",
                date_from="",
                date_to="",
                impact_min="",
                impact_max="",
                tag_slug="",
            )
            assert query is not None
            assert date_errors == []

    def test_returns_date_error_for_invalid_from_date(self, app):
        """Returns error for invalid date_from."""
        from routes.admin.articles import _build_articles_query

        with app.app_context():
            query, date_errors = _build_articles_query(
                query="",
                status="",
                category="",
                source_id="",
                date_from="invalid-date",
                date_to="",
                impact_min="",
                impact_max="",
                tag_slug="",
            )
            assert len(date_errors) == 1
            assert "date from" in date_errors[0]


class TestAdminArticlesPage:
    """Tests for admin articles page endpoint."""

    def test_articles_page_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.get("/admin/articles")
        assert resp.status_code == 302

    def test_articles_page_renders_with_auth(self, client, app, hashed_password):
        """Renders articles page for authenticated user."""
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})
        resp = client.get("/admin/articles")
        assert resp.status_code == 200


class TestArticleEditPage:
    """Tests for article edit endpoint."""

    def test_edit_page_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.get("/admin/articles/1/edit")
        assert resp.status_code == 302

    def test_edit_page_returns_404_for_nonexistent(self, auth_client, app):
        """Returns 404 for non-existent article."""
        with app.app_context():
            resp = auth_client.get("/admin/articles/99999/edit")
            assert resp.status_code == 404

    def test_edit_page_renders_for_existent_article(self, auth_client, app, create_article):
        """Renders edit page for existing article."""
        with app.app_context():
            article = create_article()
            from extensions import db
            db.session.commit()
            article_id = article.id

            resp = auth_client.get(f"/admin/articles/{article_id}/edit")
            assert resp.status_code == 200
            assert b'name="csrf_token"' in resp.data

    def test_edit_form_post_accepts_its_hidden_csrf_field(
        self, auth_client, app, create_article
    ):
        """HTML form submissions use their hidden token, not an X-CSRFToken header."""
        import re

        from extensions import db
        from models import Article
        from routes.admin.articles import _admin_categories

        app.config["WTF_CSRF_ENABLED"] = True
        with app.app_context():
            article = create_article()
            db.session.commit()
            article_id = article.id

            edit_url = f"/admin/articles/{article_id}/edit"
            form_response = auth_client.get(edit_url)
            assert form_response.status_code == 200
            token_match = re.search(
                rb'name="csrf_token" value="([^"]+)"', form_response.data
            )
            assert token_match is not None

            response = auth_client.post(
                edit_url,
                data={
                    "csrf_token": token_match.group(1).decode(),
                    "headline": "Updated headline",
                    "tldr": "Summary",
                    "why_it_matters": "Context",
                    "body": "Article body",
                    "what_to_watch": "Next steps",
                    "key_points": "One point",
                    "tags": "test",
                    "category": _admin_categories()[0],
                    "pipeline_status": "review",
                },
            )

            assert response.status_code == 302
            updated = db.session.get(Article, article_id)
            assert updated is not None
            assert '"headline": "Updated headline"' in updated.final_article


class TestOriginalArticleView:
    """Tests for view_original_article endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.get("/admin/articles/1/original")
        assert resp.status_code == 302

    def test_returns_404_when_no_original(self, auth_client, app, create_article):
        """Returns 404 when article has no original_ai_article."""
        with app.app_context():
            article = create_article()
            article.original_ai_article = None
            from extensions import db
            db.session.commit()
            article_id = article.id

            resp = auth_client.get(f"/admin/articles/{article_id}/original")
            assert resp.status_code == 404

    def test_returns_original_article_json(self, auth_client, app, create_article):
        """Returns original_ai_article as JSON."""
        with app.app_context():
            article = create_article()
            article.original_ai_article = '{"headline": "Original"}'
            from extensions import db
            db.session.commit()
            article_id = article.id

            resp = auth_client.get(f"/admin/articles/{article_id}/original")
            assert resp.status_code == 200
            assert b"Original" in resp.data


class TestArticleVersions:
    """Tests for article_versions endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.get("/admin/articles/1/versions")
        assert resp.status_code == 302


class TestDeleteArticle:
    """Tests for delete_article endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.post("/admin/articles/1/delete")
        assert resp.status_code == 302

    def test_returns_404_for_nonexistent(self, auth_client, app):
        """Returns 404 for non-existent article."""
        resp = auth_client.post("/admin/articles/99999/delete")
        assert resp.status_code == 404


class TestReprocessArticle:
    """Tests for reprocess_article endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.post("/admin/articles/1/reprocess")
        assert resp.status_code == 302

    def test_returns_400_for_invalid_stage(self, auth_client, app, create_article):
        """Returns 400 for invalid stage."""
        with app.app_context():
            article = create_article()
            from extensions import db
            db.session.commit()
            article_id = article.id

            resp = auth_client.post(
                f"/admin/articles/{article_id}/reprocess",
                data={"from_stage": "invalid_stage"},
            )
            assert resp.status_code == 400


class TestReprocessStages:
    """Tests for _REPROCESS_STAGES configuration."""

    def test_has_required_stages(self):
        """Has stages for select, research, and write."""
        from routes.admin.articles import _REPROCESS_STAGES

        assert "select" in _REPROCESS_STAGES
        assert "research" in _REPROCESS_STAGES
        assert "write" in _REPROCESS_STAGES

    def test_select_stage_resets_correct_fields(self):
        """Select stage resets selector_result and later fields."""
        from routes.admin.articles import _REPROCESS_STAGES

        fields = _REPROCESS_STAGES["select"]["fields"]
        assert "selector_result" in fields
        assert "research_brief" in fields
        assert "draft_article" in fields
        assert "final_article" in fields