"""Tests for admin route authentication enforcement.

Verifies that:
- Unauthenticated requests to admin routes are denied
- Blueprint-level auth guard works on api_tokens_bp
- Route registration regression: every admin route is classified
"""

import pytest


# ---------------------------------------------------------------------------
# Route classification allowlists
# ---------------------------------------------------------------------------

# Routes that are intentionally public (no auth required)
PUBLIC_ROUTES = {
    "public.health",
    "public.index",
    "public.topic",
    "public.tag",
    "public.rss_feed",
    "public.rss_all_feed",
    "public.rss_topic_feed",
    "public.rss_tag_feed",
    "public.sitemap",
    "public.search",
    "public.article_detail",
    "public.short_link",
    "public.share_redirect",
    "public.track_share",
    "public.subscribe_page",
    "public.subscribe_action",
    "public.unsubscribe_page",
    "public.unsubscribe_action",
    "public.verify_subscription",
    "public.feed_all",
    "public.feed_topic",
    "public.short_url_redirect",
    "public.short_url_tracking_page",
    "public.subscribe",
    "public.tag_feed",
    "public.topic_feed",
    "public.track_newsletter_click",
    "public.track_share_click",
    "public.unsubscribe",
    "public.unsubscribe_confirm",
    "public.verify",
    "public.offline",
    "themes.serve_theme_css",
    "themes.theme_metadata",
}

# Routes that are intentionally public auth pages
PUBLIC_AUTH_ROUTES = {
    "admin.login",
    "admin.verify_2fa",
    "admin.setup_2fa",
    "admin.logout",
}

# All admin routes that must be authenticated
ADMIN_ROUTES = {
    "admin.dashboard",
    "admin.articles",
    "admin.edit_article",
    "admin.view_original_article",
    "admin.article_versions",
    "admin.rollback_article",
    "admin.delete_article",
    "admin.reprocess_article",
    "admin.sources",
    "admin.add_source",
    "admin.enable_source",
    "admin.disable_source",
    "admin.pipelines",
    "admin.pipeline_logs",
    "admin.trigger_crawl",
    "admin.newsletters",
    "admin.view_newsletter",
    "admin.trigger_newsletter",
    "admin.newsletter_dry_run",
    "admin.metrics",
    "admin.dead_letters",
    "admin.webhooks",
    "admin.trend_memory_list",
    "admin.trend_memory_delete",
    "admin.trend_memory_delete_expired",
    "admin.topic_notes_list",
    "admin.topic_notes_create",
    "admin.topic_notes_edit",
    "admin.topic_notes_delete",
    "admin.topic_notes_row",
    "admin.subscribers",
    "admin.export_subscribers",
    "admin.review_queue",
    "admin.approve_article",
    "admin.reject_article",
    "admin.shares",
    "admin.add_share",
    "admin.edit_share",
    "admin.delete_share",
    "admin.edit_share_form",
    "admin.share_row",
    "admin.toggle_share",
}

# All admin API routes that must be authenticated
ADMIN_API_ROUTES = {
    "admin_api.health",
    "admin_api.workers_health",
    "admin_api.task_status",
    "admin_api.list_sources",
    "admin_api.create_source",
    "admin_api.get_source",
    "admin_api.update_source",
    "admin_api.update_source_partial",
    "admin_api.delete_source",
    "admin_api.refresh_source",
    "admin_api.get_article_ids",
    "admin_api.get_article_counts_by_status",
    "admin_api.bulk_article_operations",
    "admin_api.trigger_article_pipeline",
    "admin_api.get_article",
    "admin_api.update_article",
    "admin_api.delete_article",
    "admin_api.reload_config",
    "admin_api.app_metrics",
    "admin_api.prometheus_metrics",
    "admin_api.pipeline_stats",
    "admin_api.dead_letter_stats",
    "admin_api.pipeline_backlog",
    "admin_api.cost_summary",
    "admin_api.sources_health",
    "admin_api.pipeline_sla",
    "admin_api.search_analytics",
    "admin_api.search_articles",
    "admin_api.list_webhooks",
    "admin_api.create_webhook",
    "admin_api.get_webhook",
    "admin_api.update_webhook",
    "admin_api.delete_webhook",
    "admin_api.test_webhook",
    "admin_api.list_webhook_events",
    "admin_api.resend_webhook_event",
    "admin_api.get_article_quality_report",
    "admin_api.get_recent_quality_reports",
    "admin_api.get_pipeline_history",
    "admin_api.replay_article_stage",
    "admin_api.restore_article_version",
    "admin_api.newsletter_performance",
    "admin_api.newsletters_stats",
    "admin_api.newsletter_preview",
    "admin_api.list_alerts",
    "admin_api.source_performance",
    "admin_api.topic_coverage",
    "admin_api.source_recommendations",
    "admin_api.trend_memory_semantic_search",
    "admin_api.topic_gap_reports",
    "admin_api.list_audit_logs",
    "admin_api.themes_diagnostics",
}

# API token routes (separate blueprint, no url_prefix)
ADMIN_API_TOKEN_ROUTES = {
    "api_tokens.list_tokens",
    "api_tokens.create_token",
    "api_tokens.delete_token",
}


# ---------------------------------------------------------------------------
# Route registration regression test
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    """Every admin route must appear in an auth classification set."""

    def test_all_admin_routes_classified(self, app):
        """Fail if a new /admin, /api/v1, or /api-tokens route is added
        without being classified in the auth allowlists above."""
        all_classified = PUBLIC_ROUTES | PUBLIC_AUTH_ROUTES | ADMIN_ROUTES | ADMIN_API_ROUTES | ADMIN_API_TOKEN_ROUTES

        unclassified = []
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            # Skip static files and error handlers
            if endpoint.startswith("static") or endpoint.startswith("errors"):
                continue
            if endpoint not in all_classified:
                unclassified.append(f"{endpoint} ({rule.rule})")

        if unclassified:
            msg = (
                "The following routes are not classified in any auth allowlist. "
                "Add them to the appropriate set in test_admin_route_auth.py:\n"
                + "\n".join(f"  - {r}" for r in sorted(unclassified))
            )
            pytest.fail(msg)

    def test_admin_api_token_routes_exist(self, app):
        """Verify the expected api_tokens endpoints are registered."""
        endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
        for expected in ADMIN_API_TOKEN_ROUTES:
            assert expected in endpoints, f"Missing endpoint: {expected}"

    def test_admin_api_token_paths_are_api_prefixed(self, app):
        """Verify /api-tokens paths start with /api for JSON 401 behavior."""
        for rule in app.url_map.iter_rules():
            if rule.endpoint in ADMIN_API_TOKEN_ROUTES:
                assert rule.rule.startswith("/api"), (
                    f"Route {rule.endpoint} at {rule.rule} does not start with /api; "
                    "require_auth will redirect instead of returning JSON 401"
                )


# ---------------------------------------------------------------------------
# Unauthenticated denial tests — /api-tokens
# ---------------------------------------------------------------------------


class TestApiTokensUnauthenticated:
    """Verify unauthenticated requests to /api-tokens are denied with JSON 401."""

    def test_list_tokens_no_auth(self, client):
        resp = client.get("/api-tokens")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "error" in data or "Unauthorized" in data.get("message", "")

    def test_create_token_no_auth(self, client):
        resp = client.post("/api-tokens", json={"name": "test"})
        assert resp.status_code == 401

    def test_delete_token_no_auth(self, client):
        resp = client.delete("/api-tokens/1")
        assert resp.status_code == 401

    def test_list_tokens_invalid_bearer(self, client):
        resp = client.get("/api-tokens", headers={"Authorization": "Bearer invalid-token"})
        assert resp.status_code == 401

    def test_create_token_invalid_bearer(self, client):
        resp = client.post(
            "/api-tokens",
            json={"name": "test"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unauthenticated denial tests — /api/v1 admin API
# ---------------------------------------------------------------------------


class TestAdminApiUnauthenticated:
    """Verify unauthenticated requests to /api/v1 are denied with JSON 401."""

    def test_health_no_auth(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 401

    def test_sources_no_auth(self, client):
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_articles_no_auth(self, client):
        resp = client.get("/api/v1/articles/ids")
        assert resp.status_code == 401

    def test_webhooks_no_auth(self, client):
        resp = client.get("/api/v1/webhooks")
        assert resp.status_code == 401

    def test_config_reload_no_auth(self, client):
        resp = client.post("/api/v1/config/reload")
        assert resp.status_code == 401

    def test_pipeline_stats_no_auth(self, client):
        resp = client.get("/api/v1/pipeline/stats")
        assert resp.status_code == 401

    def test_search_no_auth(self, client):
        resp = client.get("/api/v1/search/analytics")
        assert resp.status_code == 401

    def test_metrics_no_auth(self, client):
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unauthenticated denial tests — /admin HTML pages
# ---------------------------------------------------------------------------


class TestAdminPagesUnauthenticated:
    """Verify unauthenticated requests to /admin redirect to login."""

    def test_dashboard_redirects(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_articles_redirects(self, client):
        resp = client.get("/admin/articles")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_sources_redirects(self, client):
        resp = client.get("/admin/sources")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_webhooks_redirects(self, client):
        resp = client.get("/admin/webhooks")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_newsletters_redirects(self, client):
        resp = client.get("/admin/newsletters")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_pipelines_redirects(self, client):
        resp = client.get("/admin/pipelines")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Public routes remain accessible
# ---------------------------------------------------------------------------


class TestPublicRoutesAccessible:
    """Verify public routes are still accessible without auth."""

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)  # 503 if deps are down

    def test_index_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_login_page(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Authenticated access still works
# ---------------------------------------------------------------------------


class TestAuthenticatedAccess:
    """Verify authenticated requests succeed."""

    def test_api_tokens_with_session(self, auth_client):
        resp = auth_client.get("/api-tokens")
        assert resp.status_code == 200

    def test_admin_dashboard_with_session(self, auth_client):
        resp = auth_client.get("/admin/")
        assert resp.status_code == 200

    def test_admin_articles_with_session(self, auth_client):
        resp = auth_client.get("/admin/articles")
        assert resp.status_code == 200
