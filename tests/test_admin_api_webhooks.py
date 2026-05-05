"""Tests for routes/admin/api/webhooks.py - Webhook management API."""




class TestListWebhooks:
    """Tests for list_webhooks endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.get("/api/v1/webhooks")
        assert resp.status_code in (302, 401)

    def test_returns_webhooks_list(self, auth_client, app):
        """Returns list of webhooks for authenticated user."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Test Webhook",
                url="https://example.com/webhook",
                secret="secret123",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()

            resp = auth_client.get("/api/v1/webhooks")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "data" in data
            assert "webhooks" in data["data"]
            assert len(data["data"]["webhooks"]) == 1
            assert data["data"]["webhooks"][0]["name"] == "Test Webhook"


class TestCreateWebhook:
    """Tests for create_webhook endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.post("/api/v1/webhooks", json={"name": "Test"})
        assert resp.status_code in (302, 401)

    def test_returns_error_for_invalid_json(self, auth_client, app):
        """Returns 400 for invalid JSON body."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            data="not json",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_returns_error_for_missing_name(self, auth_client, app):
        """Returns 400 when name is missing."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/webhook", "events": ["article.published"]},
        )
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    def test_returns_error_for_missing_url(self, auth_client, app):
        """Returns 400 when URL is missing."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={"name": "Test", "events": ["article.published"]},
        )
        assert resp.status_code == 400
        assert "url" in resp.get_json()["error"]

    def test_returns_error_for_invalid_url(self, auth_client, app):
        """Returns 400 for invalid URL."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={"name": "Test", "url": "not-a-url", "events": ["article.published"]},
        )
        assert resp.status_code == 400
        assert "Invalid URL" in resp.get_json()["error"]

    def test_returns_error_for_invalid_events(self, auth_client, app):
        """Returns 400 for invalid event types."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={"name": "Test", "url": "https://example.com/webhook", "events": ["invalid.event"]},
        )
        assert resp.status_code == 400
        assert "unknown event" in resp.get_json()["error"]

    def test_returns_error_for_empty_events_list(self, auth_client, app):
        """Returns 400 when events list is empty."""
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={"name": "Test", "url": "https://example.com/webhook", "events": []},
        )
        assert resp.status_code == 400

    def test_creates_webhook_successfully(self, auth_client, app, monkeypatch):
        """Creates webhook and returns 201."""
        import base64
        key = base64.urlsafe_b64encode(b"0" * 32).decode()
        monkeypatch.setenv("WEBHOOK_SECRET_KEY", key)
        resp = auth_client.post(
            "/api/v1/webhooks",
            json={
                "name": "New Webhook",
                "url": "https://example.com/webhook",
                "events": ["article.published", "newsletter.sent"],
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "data" in data
        assert "webhook" in data["data"]
        assert data["data"]["webhook"]["name"] == "New Webhook"
        assert "secret" in data["data"]["webhook"]
        assert "..." in data["data"]["webhook"]["secret"]


class TestGetWebhook:
    """Tests for get_webhook endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.get("/api/v1/webhooks/1")
        assert resp.status_code in (302, 401)

    def test_returns_404_for_nonexistent_webhook(self, auth_client, app):
        """Returns 404 for non-existent webhook ID."""
        resp = auth_client.get("/api/v1/webhooks/99999")
        assert resp.status_code == 404

    def test_returns_webhook_details(self, auth_client, app):
        """Returns webhook details for valid ID."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Test Webhook",
                url="https://example.com/webhook",
                secret="secret123",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id

            resp = auth_client.get(f"/api/v1/webhooks/{webhook_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "data" in data
            assert "webhook" in data["data"]
            assert data["data"]["webhook"]["name"] == "Test Webhook"
            assert data["data"]["webhook"]["url"] == "https://example.com/webhook"


class TestUpdateWebhook:
    """Tests for update_webhook endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.put("/api/v1/webhooks/1", json={})
        assert resp.status_code in (302, 401)

    def test_returns_404_for_nonexistent_webhook(self, auth_client, app):
        """Returns 404 for non-existent webhook ID."""
        resp = auth_client.put("/api/v1/webhooks/99999", json={})
        assert resp.status_code == 404

    def test_returns_error_for_invalid_json(self, auth_client, app):
        """Returns 400 for invalid JSON body."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Test",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id

            resp = auth_client.put(
                f"/api/v1/webhooks/{webhook_id}",
                data="not json",
                content_type="application/json",
            )
            assert resp.status_code == 400

    def test_updates_webhook_name(self, auth_client, app):
        """Updates webhook name successfully."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Original",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id

            resp = auth_client.put(
                f"/api/v1/webhooks/{webhook_id}",
                json={"name": "Updated Name"},
            )
            assert resp.status_code == 200

    def test_returns_error_for_invalid_url_update(self, auth_client, app):
        """Returns 400 for invalid URL in update."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Test",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id

            resp = auth_client.put(
                f"/api/v1/webhooks/{webhook_id}",
                json={"url": "invalid-url"},
            )
            assert resp.status_code == 400

    def test_returns_error_for_invalid_events_update(self, auth_client, app):
        """Returns 400 for invalid event types in update."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Test",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id

            resp = auth_client.put(
                f"/api/v1/webhooks/{webhook_id}",
                json={"events": ["invalid.event"]},
            )
            assert resp.status_code == 400

    def test_regenerates_secret_when_requested(self, auth_client, app, monkeypatch):
        """Regenerates secret when regenerate_secret is true."""
        import base64
        key = base64.urlsafe_b64encode(b"0" * 32).decode()
        monkeypatch.setenv("WEBHOOK_SECRET_KEY", key)
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Test",
                url="https://example.com/webhook",
                secret="old-secret-value",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id
            old_secret = webhook.secret

            resp = auth_client.put(
                f"/api/v1/webhooks/{webhook_id}",
                json={"regenerate_secret": True},
            )
            assert resp.status_code == 200

            db.session.refresh(webhook)
            assert webhook.secret != old_secret


class TestDeleteWebhook:
    """Tests for delete_webhook endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.delete("/api/v1/webhooks/1")
        assert resp.status_code in (302, 401)

    def test_returns_404_for_nonexistent_webhook(self, auth_client, app):
        """Returns 404 for non-existent webhook ID."""
        resp = auth_client.delete("/api/v1/webhooks/99999")
        assert resp.status_code == 404

    def test_deletes_webhook_successfully(self, auth_client, app):
        """Deletes webhook and returns 200."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="To Delete",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id

            resp = auth_client.delete(f"/api/v1/webhooks/{webhook_id}")
            assert resp.status_code == 200

            assert db.session.get(Webhook, webhook_id) is None


class TestTestWebhook:
    """Tests for test_webhook endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.post("/api/v1/webhooks/1/test")
        assert resp.status_code in (302, 401)

    def test_returns_404_for_nonexistent_webhook(self, auth_client, app):
        """Returns 404 for non-existent webhook ID."""
        resp = auth_client.post("/api/v1/webhooks/99999/test")
        assert resp.status_code == 404

    def test_queues_test_webhook(self, auth_client, app, mock_celery_tasks):
        """Returns 202 and queues test webhook task."""
        with app.app_context():
            from extensions import db
            from models import Webhook

            webhook = Webhook(
                name="Test",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()
            webhook_id = webhook.id

            resp = auth_client.post(f"/api/v1/webhooks/{webhook_id}/test")
            assert resp.status_code == 202


class TestListWebhookEvents:
    """Tests for list_webhook_events endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.get("/api/v1/webhooks/1/events")
        assert resp.status_code in (302, 401)

    def test_returns_404_for_nonexistent_webhook(self, auth_client, app):
        """Returns 404 for non-existent webhook ID."""
        resp = auth_client.get("/api/v1/webhooks/99999/events")
        assert resp.status_code == 404

    def test_returns_webhook_events(self, auth_client, app):
        """Returns list of webhook events for valid webhook."""
        with app.app_context():
            from extensions import db
            from models import Webhook, WebhookEvent

            webhook = Webhook(
                name="Test",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.flush()

            event = WebhookEvent(
                webhook_id=webhook.id,
                event_type="article.published",
                status_code=200,
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id

            resp = auth_client.get(f"/api/v1/webhooks/{webhook.id}/events")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "data" in data
            assert "events" in data["data"]
            assert len(data["data"]["events"]) == 1
            assert data["data"]["events"][0]["event_type"] == "article.published"


class TestResendWebhookEvent:
    """Tests for resend_webhook_event endpoint."""

    def test_requires_auth(self, client):
        """Returns 302 for unauthenticated requests."""
        resp = client.post("/api/v1/webhooks/events/1/resend")
        assert resp.status_code in (302, 401)

    def test_returns_404_for_nonexistent_event(self, auth_client, app):
        """Returns 404 for non-existent event ID."""
        resp = auth_client.post("/api/v1/webhooks/events/99999/resend")
        assert resp.status_code == 404

    def test_returns_error_for_inactive_webhook(self, auth_client, app):
        """Returns 400 when webhook is inactive."""
        with app.app_context():
            from extensions import db
            from models import Webhook, WebhookEvent

            webhook = Webhook(
                name="Inactive",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=False,
            )
            db.session.add(webhook)
            db.session.flush()

            event = WebhookEvent(
                webhook_id=webhook.id,
                event_type="article.published",
                status_code=500,
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id

            resp = auth_client.post(f"/api/v1/webhooks/events/{event_id}/resend")
            assert resp.status_code == 400
            assert "inactive" in resp.get_json()["error"].lower()

    def test_resends_event_successfully(self, auth_client, app, mock_celery_tasks):
        """Returns 202 and queues resend task."""
        with app.app_context():
            from extensions import db
            from models import Webhook, WebhookEvent

            webhook = Webhook(
                name="Test",
                url="https://example.com/webhook",
                secret="secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.flush()

            event = WebhookEvent(
                webhook_id=webhook.id,
                event_type="article.published",
                status_code=500,
                payload='{"data": {"test": true}}',
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id

            resp = auth_client.post(f"/api/v1/webhooks/events/{event_id}/resend")
            assert resp.status_code == 202


class TestMaskSecret:
    """Tests for _mask_secret helper function."""

    def test_masks_short_secrets(self):
        """Masks secrets 8 chars or less."""
        from routes.admin.api.webhooks import _mask_secret

        assert _mask_secret("short") == "***"
        assert _mask_secret("12345678") == "***"

    def test_masks_long_secrets(self):
        """Shows first 4 and last 4 chars of long secrets."""
        from routes.admin.api.webhooks import _mask_secret

        result = _mask_secret("1234567890abcdef")
        assert result == "1234...cdef"