"""Tests for services/webhooks.py."""


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