"""Tests for services/webhooks.py."""

from unittest.mock import MagicMock, patch
import pytest


class TestWebhooks:
    """Tests for webhook dispatch and event handling."""

    def test_dispatch_webhook_importable(self, app):
        """dispatch_webhook should be importable."""
        from services.webhooks import dispatch_webhook

        assert callable(dispatch_webhook)

    def test_trigger_event_importable(self, app):
        """trigger_event should be importable."""
        from services.webhooks import trigger_event

        assert callable(trigger_event)

    def test_webhook_model_importable(self, app):
        """Webhook and WebhookEvent models should be importable."""
        from models import Webhook, WebhookEvent

        assert Webhook is not None
        assert WebhookEvent is not None

    def test_dispatch_creates_event_record(self, app, create_source):
        """dispatch_webhook should create a WebhookEvent record in the database."""
        from extensions import db
        from models import Webhook, WebhookEvent
        from services.webhooks import dispatch_webhook

        with app.app_context():
            webhook = Webhook(
                name="Test Webhook",
                url="https://example.com/webhook",
                secret="test-secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()

            webhook_id = webhook.id

            with patch("requests.post") as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = "OK"
                mock_post.return_value = mock_response

                success, error = dispatch_webhook(
                    webhook_id=webhook_id,
                    name="Test Webhook",
                    url="https://example.com/webhook",
                    secret="test-secret",
                    event_type="article.published",
                    event_data={"article_id": 42},
                )

            event = WebhookEvent.query.filter_by(webhook_id=webhook_id).first()
            assert event is not None, "WebhookEvent should be created"
            assert event.event_type == "article.published"
            assert event.webhook_id == webhook_id

    def test_trigger_event_only_calls_subscribed_webhooks(self, app):
        """trigger_event should only dispatch to webhooks subscribed to that event."""
        from extensions import db
        from models import Webhook
        from services.webhooks import trigger_event

        with app.app_context():
            webhook_a = Webhook(
                name="Webhook A",
                url="https://example.com/a",
                secret="secret-a",
                events=["article.published"],
                active=True,
            )
            webhook_b = Webhook(
                name="Webhook B",
                url="https://example.com/b",
                secret="secret-b",
                events=["article.created"],
                active=True,
            )
            db.session.add(webhook_a)
            db.session.add(webhook_b)
            db.session.commit()

            called_urls = []

            def mock_delay(**kwargs):
                called_urls.append(kwargs["url"])
                return None

            with patch("tasks.webhook.dispatch_webhook_task.delay", side_effect=mock_delay):
                trigger_event("article.published", {"article_id": 123})

            assert "https://example.com/a" in called_urls, "Webhook A should be called for article.published"
            assert "https://example.com/b" not in called_urls, "Webhook B should NOT be called for article.published"

    def test_webhook_idempotency_prevents_duplicate_events(self, app):
        """dispatch_webhook should skip delivery if idempotency_key was already delivered."""
        from extensions import db
        from models import Webhook, WebhookEvent
        from services.webhooks import dispatch_webhook

        with app.app_context():
            webhook = Webhook(
                name="Idempotency Test",
                url="https://example.com/webhook",
                secret="test-secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()

            idempotency_key = "article.published:123:unique-key-001"

            existing_event = WebhookEvent(
                webhook_id=webhook.id,
                event_type="article.published",
                status_code=200,
                idempotency_key=idempotency_key,
            )
            db.session.add(existing_event)
            db.session.commit()

            with patch("requests.post") as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = "OK"
                mock_post.return_value = mock_response

                dispatch_webhook(
                    webhook_id=webhook.id,
                    name="Idempotency Test",
                    url="https://example.com/webhook",
                    secret="test-secret",
                    event_type="article.published",
                    event_data={"article_id": 123},
                    idempotency_key=idempotency_key,
                )

            events = WebhookEvent.query.filter_by(
                webhook_id=webhook.id,
                idempotency_key=idempotency_key,
            ).all()
            assert len(events) == 1, "Should not create duplicate event for same idempotency_key"

    def test_webhook_retry_on_failure(self, app):
        """_send_webhook_with_retry should retry on 5xx errors with exponential backoff."""
        from services.webhooks import _send_webhook_with_retry

        with patch("requests.post") as mock_post, patch("time.sleep"):
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.text = "Service Unavailable"
            mock_post.return_value = mock_response

            success, error, status_code, response_body, attempts = _send_webhook_with_retry(
                url="https://example.com/webhook",
                payload={"event": "test"},
                secret="test-secret",
                event_type="test",
            )

            assert success is False
            assert attempts == 5, "Should retry all 5 attempts for 5xx error"
            assert "Max retries exceeded" in error

    def test_webhook_no_retry_on_4xx(self, app):
        """_send_webhook_with_retry should not retry on 4xx client errors."""
        from services.webhooks import _send_webhook_with_retry

        with patch("requests.post") as mock_post, patch("time.sleep"):
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_post.return_value = mock_response

            success, error, status_code, response_body, attempts = _send_webhook_with_retry(
                url="https://example.com/webhook",
                payload={"event": "test"},
                secret="test-secret",
                event_type="test",
            )

            assert success is False
            assert attempts == 1, "Should NOT retry on 4xx errors"
            assert "HTTP 400" in error

    def test_sign_payload_includes_timestamp(self, app):
        """_sign_payload should include timestamp in signature when provided."""
        from services.webhooks import _sign_payload

        payload = '{"event":"test"}'
        secret = "my-secret"
        timestamp = 1234567890

        signature_with_ts = _sign_payload(payload, secret, timestamp)
        signature_without_ts = _sign_payload(payload, secret, None)

        assert signature_with_ts != signature_without_ts, "Timestamp should affect signature"

        import hashlib
        import hmac
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}:{payload}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature_with_ts == expected

    def test_dispatch_webhook_returns_false_on_db_error(self, app):
        """dispatch_webhook should return False when database commit fails."""
        from sqlalchemy.exc import SQLAlchemyError

        from extensions import db
        from models import Webhook
        from services.webhooks import dispatch_webhook

        with app.app_context():
            webhook = Webhook(
                name="Test Webhook",
                url="https://example.com/webhook",
                secret="test-secret",
                events=["article.published"],
                active=True,
            )
            db.session.add(webhook)
            db.session.commit()

            webhook_id = webhook.id

            with patch("requests.post") as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = "OK"
                mock_post.return_value = mock_response

                with patch.object(db.session, "commit", side_effect=SQLAlchemyError("Test DB error")):
                    success, error = dispatch_webhook(
                        webhook_id=webhook_id,
                        name="Test Webhook",
                        url="https://example.com/webhook",
                        secret="test-secret",
                        event_type="article.published",
                        event_data={"article_id": 42},
                    )

            assert success is False
            assert "Database error:" in error

    def test_decryption_failure_raises_error(self, app):
        """Failed decryption of webhook secret should raise WebhookSecretDecryptionError."""
        from services.webhooks import _get_webhook_secret_from_db, WebhookSecretDecryptionError

        with app.app_context():
            with pytest.raises(WebhookSecretDecryptionError):
                _get_webhook_secret_from_db("v2:enc:invalidencryptedvalue", webhook_id=1)