"""Comprehensive URL map inventory verifying auth classification on every registered route.

Complements test_admin_route_auth.py by:
- Discovering routes dynamically via url_map (not hardcoded endpoint names)
- Testing all HTTP methods on key endpoints
- Verifying redirect vs JSON denial behavior
- Checking blueprint prefix consistency
"""

import pytest


class TestRouteSecurityInventory:
    """Verify every admin/API route requires auth when unauthenticated."""

    def test_all_admin_html_routes_require_auth(self, app, client):
        """Every /admin route (except login/logout/2fa) must deny unauthenticated GET."""
        from tests.test_admin_route_auth import PUBLIC_AUTH_ROUTES

        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            if endpoint.startswith("static") or endpoint.startswith("errors"):
                continue
            if not rule.rule.startswith("/admin"):
                continue
            if endpoint in PUBLIC_AUTH_ROUTES:
                continue
            if "GET" not in rule.methods:
                continue

            resp = client.get(rule.rule)
            assert resp.status_code in (302, 401, 403, 404, 405), (
                f"GET {rule.rule} ({endpoint}) returned {resp.status_code}, "
                f"expected auth denial (302/401/403)"
            )
            if resp.status_code == 302:
                assert "/admin/login" in resp.headers.get("Location", ""), (
                    f"GET {rule.rule} ({endpoint}) redirects to "
                    f"{resp.headers.get('Location')} instead of login"
                )

    def test_all_admin_api_routes_require_auth(self, app, client):
        """Every /api/v1 route must return 401 when unauthenticated."""
        public_api_exceptions = {"public.track_share_click", "themes.theme_metadata"}
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            if endpoint.startswith("static") or endpoint.startswith("errors"):
                continue
            if not rule.rule.startswith("/api/v1"):
                continue
            if endpoint in public_api_exceptions:
                continue
            if "GET" not in rule.methods:
                continue

            resp = client.get(rule.rule)
            assert resp.status_code in (401, 404, 405), (
                f"GET {rule.rule} ({endpoint}) returned {resp.status_code}, "
                f"expected 401"
            )

    def test_all_token_routes_require_auth(self, app, client):
        """Every /api-tokens route must return 401 when unauthenticated."""
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            if endpoint.startswith("static") or endpoint.startswith("errors"):
                continue
            if not rule.rule.startswith("/api-tokens"):
                continue
            if "GET" not in rule.methods:
                continue

            resp = client.get(rule.rule)
            assert resp.status_code == 401, (
                f"GET {rule.rule} ({endpoint}) returned {resp.status_code}, "
                f"expected 401"
            )

    def test_all_admin_routes_are_discoverable(self, app):
        """Every admin/API endpoint in url_map is accounted for in classification sets."""
        from tests.test_admin_route_auth import (
            ADMIN_API_ROUTES,
            ADMIN_API_TOKEN_ROUTES,
            ADMIN_ROUTES,
            PUBLIC_AUTH_ROUTES,
            PUBLIC_ROUTES,
        )

        all_classified = (
            PUBLIC_ROUTES | PUBLIC_AUTH_ROUTES | ADMIN_ROUTES | ADMIN_API_ROUTES | ADMIN_API_TOKEN_ROUTES
        )
        unclassified = []
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            if endpoint.startswith("static") or endpoint.startswith("errors"):
                continue
            if endpoint not in all_classified:
                unclassified.append(f"{endpoint} ({rule.rule})")

        assert not unclassified, (
            "Unclassified routes found:\n" + "\n".join(f"  - {r}" for r in sorted(unclassified))
        )


class TestRouteMethodAuthMatrix:
    """Test that ALL HTTP methods on protected endpoints require auth."""

    def test_sources_get_requires_auth(self, client):
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_sources_post_requires_auth(self, client):
        resp = client.post("/api/v1/sources", json={})
        assert resp.status_code == 401

    def test_source_by_id_get_requires_auth(self, client):
        resp = client.get("/api/v1/sources/1")
        assert resp.status_code == 401

    def test_source_by_id_put_requires_auth(self, client):
        resp = client.put("/api/v1/sources/1", json={})
        assert resp.status_code == 401

    def test_source_by_id_patch_requires_auth(self, client):
        resp = client.patch("/api/v1/sources/1", json={})
        assert resp.status_code == 401

    def test_source_by_id_delete_requires_auth(self, client):
        resp = client.delete("/api/v1/sources/1")
        assert resp.status_code == 401

    def test_article_by_id_get_requires_auth(self, client):
        resp = client.get("/api/v1/articles/1")
        assert resp.status_code == 401

    def test_article_by_id_put_requires_auth(self, client):
        resp = client.put("/api/v1/articles/1", json={})
        assert resp.status_code == 401

    def test_article_by_id_delete_requires_auth(self, client):
        resp = client.delete("/api/v1/articles/1")
        assert resp.status_code == 401

    def test_webhooks_get_requires_auth(self, client):
        resp = client.get("/api/v1/webhooks")
        assert resp.status_code == 401

    def test_webhooks_post_requires_auth(self, client):
        resp = client.post("/api/v1/webhooks", json={})
        assert resp.status_code == 401

    def test_webhook_by_id_get_requires_auth(self, client):
        resp = client.get("/api/v1/webhooks/1")
        assert resp.status_code == 401

    def test_webhook_by_id_put_requires_auth(self, client):
        resp = client.put("/api/v1/webhooks/1", json={})
        assert resp.status_code == 401

    def test_webhook_by_id_patch_requires_auth(self, client):
        resp = client.patch("/api/v1/webhooks/1", json={})
        assert resp.status_code == 401

    def test_webhook_by_id_delete_requires_auth(self, client):
        resp = client.delete("/api/v1/webhooks/1")
        assert resp.status_code == 401

    def test_api_tokens_get_requires_auth(self, client):
        resp = client.get("/api-tokens")
        assert resp.status_code == 401

    def test_api_tokens_post_requires_auth(self, client):
        resp = client.post("/api-tokens", json={"name": "x"})
        assert resp.status_code == 401

    def test_api_token_by_id_delete_requires_auth(self, client):
        resp = client.delete("/api-tokens/1")
        assert resp.status_code == 401

    def test_config_reload_post_requires_auth(self, client):
        resp = client.post("/api/v1/config/reload")
        assert resp.status_code == 401

    def test_pipeline_trigger_post_requires_auth(self, client):
        resp = client.post("/api/v1/articles/1/pipeline", json={})
        assert resp.status_code == 401

    def test_source_refresh_post_requires_auth(self, client):
        resp = client.post("/api/v1/sources/1/refresh")
        assert resp.status_code == 401

    def test_article_bulk_post_requires_auth(self, client):
        resp = client.post("/api/v1/articles/bulk", json={"article_ids": [1], "action": "delete"})
        assert resp.status_code == 401

    def test_webhook_test_post_requires_auth(self, client):
        resp = client.post("/api/v1/webhooks/1/test")
        assert resp.status_code == 401

    def test_webhook_events_get_requires_auth(self, client):
        resp = client.get("/api/v1/webhooks/1/events")
        assert resp.status_code == 401

    def test_webhook_event_resend_post_requires_auth(self, client):
        resp = client.post("/api/v1/webhooks/events/1/resend")
        assert resp.status_code == 401


class TestPublicRouteAuthBypass:
    """Verify public routes are accessible without authentication."""

    def test_health_returns_success(self, client):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)

    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_admin_login_returns_200(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200

    def test_subscribe_action_accepts_post(self, client):
        resp = client.post("/subscribe", data={"email": "test@example.com"})
        assert resp.status_code in (200, 302, 400)

    def test_health_json_has_status_field(self, client):
        resp = client.get("/health")
        if resp.status_code == 200:
            data = resp.get_json()
            assert "status" in data


class TestAdminRouteRedirectBehavior:
    """Verify HTML routes redirect to login, API routes return JSON 401."""

    def test_admin_dashboard_redirects_to_login(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_articles_redirects_to_login(self, client):
        resp = client.get("/admin/articles")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_sources_redirects_to_login(self, client):
        resp = client.get("/admin/sources")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_webhooks_redirects_to_login(self, client):
        resp = client.get("/admin/webhooks")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_newsletters_redirects_to_login(self, client):
        resp = client.get("/admin/newsletters")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_pipelines_redirects_to_login(self, client):
        resp = client.get("/admin/pipelines")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_metrics_redirects_to_login(self, client):
        resp = client.get("/admin/metrics")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_trend_memory_redirects_to_login(self, client):
        resp = client.get("/admin/trend-memory")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_subscribers_redirects_to_login(self, client):
        resp = client.get("/admin/subscribers")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_admin_review_queue_redirects_to_login(self, client):
        resp = client.get("/admin/review")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_api_v1_health_returns_json_401(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data is not None
        assert "error" in data

    def test_api_v1_sources_returns_json_401(self, client):
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data is not None
        assert "error" in data

    def test_api_v1_webhooks_returns_json_401(self, client):
        resp = client.get("/api/v1/webhooks")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data is not None
        assert "error" in data

    def test_api_v1_articles_returns_json_401(self, client):
        resp = client.get("/api/v1/articles/ids")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data is not None
        assert "error" in data

    def test_api_tokens_returns_json_401(self, client):
        resp = client.get("/api-tokens")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data is not None
        assert "error" in data

    def test_admin_html_routes_do_not_return_json(self, client):
        """HTML admin routes should redirect (302), not return JSON 401."""
        for path in ["/admin/", "/admin/articles", "/admin/sources"]:
            resp = client.get(path)
            assert resp.status_code == 302, (
                f"GET {path} returned {resp.status_code} instead of 302 redirect"
            )
            assert resp.content_type != "application/json", (
                f"GET {path} returned JSON content-type; should redirect to login"
            )

    def test_admin_api_routes_return_json_not_redirect(self, client):
        """API routes should return JSON 401, not HTML redirect."""
        for path in ["/api/v1/health", "/api/v1/sources", "/api/v1/webhooks"]:
            resp = client.get(path)
            assert resp.status_code == 401, (
                f"GET {path} returned {resp.status_code} instead of 401"
            )
            data = resp.get_json()
            assert data is not None, f"GET {path} did not return JSON body"


class TestRouteBlueprintPrefixConsistency:
    """Verify blueprint registration: routes match expected prefixes."""

    def test_all_admin_routes_use_admin_bp(self, app):
        """All /admin/* routes must be registered under the 'admin' blueprint."""
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/admin"):
                continue
            blueprint = rule.endpoint.split(".")[0]
            assert blueprint == "admin", (
                f"Route {rule.rule} ({rule.endpoint}) is on blueprint '{blueprint}', "
                f"expected 'admin'"
            )

    def test_all_api_v1_routes_use_admin_api_bp(self, app):
        """All /api/v1/* routes must be registered under the 'admin_api' blueprint,
        except public tracking endpoints that intentionally live under /api/v1."""
        public_api_exceptions = {"public.track_share_click", "themes.theme_metadata"}
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/v1"):
                continue
            if rule.endpoint in public_api_exceptions:
                continue
            blueprint = rule.endpoint.split(".")[0]
            assert blueprint == "admin_api", (
                f"Route {rule.rule} ({rule.endpoint}) is on blueprint '{blueprint}', "
                f"expected 'admin_api'"
            )

    def test_all_api_tokens_routes_use_api_tokens_bp(self, app):
        """All /api-tokens/* routes must be registered under the 'api_tokens' blueprint."""
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api-tokens"):
                continue
            blueprint = rule.endpoint.split(".")[0]
            assert blueprint == "api_tokens", (
                f"Route {rule.rule} ({rule.endpoint}) is on blueprint '{blueprint}', "
                f"expected 'api_tokens'"
            )

    def test_no_admin_routes_on_wrong_blueprints(self, app):
        """No /admin/* route should exist on blueprints other than 'admin'."""
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/admin"):
                continue
            blueprint = rule.endpoint.split(".")[0]
            assert blueprint == "admin", (
                f"Route {rule.rule} ({rule.endpoint}) leaked to blueprint '{blueprint}'"
            )

    def test_no_api_v1_routes_on_wrong_blueprints(self, app):
        """No /api/v1/* route should exist on blueprints other than 'admin_api',
        except public tracking endpoints that intentionally live under /api/v1."""
        public_api_exceptions = {"public.track_share_click", "themes.theme_metadata"}
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/v1"):
                continue
            if rule.endpoint in public_api_exceptions:
                continue
            blueprint = rule.endpoint.split(".")[0]
            assert blueprint == "admin_api", (
                f"Route {rule.rule} ({rule.endpoint}) leaked to blueprint '{blueprint}'"
            )

    def test_admin_bp_has_url_prefix(self, app):
        """admin_bp must be registered with url_prefix=/admin."""
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith("admin."):
                assert rule.rule.startswith("/admin"), (
                    f"admin.* endpoint {rule.endpoint} has path {rule.rule} "
                    f"that doesn't start with /admin"
                )
                break

    def test_admin_api_bp_has_url_prefix(self, app):
        """admin_api_bp must be registered with url_prefix=/api/v1."""
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith("admin_api."):
                assert rule.rule.startswith("/api/v1"), (
                    f"admin_api.* endpoint {rule.endpoint} has path {rule.rule} "
                    f"that doesn't start with /api/v1"
                )
                break

    def test_api_tokens_bp_has_no_prefix(self, app):
        """api_tokens_bp must be registered without url_prefix (routes include /api-tokens)."""
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith("api_tokens."):
                assert rule.rule.startswith("/api-tokens"), (
                    f"api_tokens.* endpoint {rule.endpoint} has path {rule.rule} "
                    f"that doesn't start with /api-tokens"
                )
                break

    def test_public_bp_routes_have_no_prefix(self, app):
        """public_bp must be registered without url_prefix."""
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith("public."):
                assert not rule.rule.startswith("/admin"), (
                    f"public.* endpoint {rule.endpoint} has path {rule.rule} "
                    f"under /admin — possible blueprint conflict"
                )

    def test_no_endpoint_name_collisions(self, app):
        """No two blueprints should register the same endpoint name.

        Flask may register both /path and /path/ for the same view function
        (trailing slash redirect). We only check that different view functions
        don't share an endpoint name.
        """
        seen = {}
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            if endpoint.startswith("static") or endpoint.startswith("errors"):
                continue
            if endpoint in seen:
                prev_rule = seen[endpoint]
                if rule.rule.rstrip("/") == prev_rule.rule.rstrip("/"):
                    continue
                pytest.fail(
                    f"Endpoint name collision: '{endpoint}' registered at "
                    f"{rule.rule} and {prev_rule.rule}"
                )
            seen[endpoint] = rule
