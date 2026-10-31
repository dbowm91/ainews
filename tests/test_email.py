"""Tests for the email service."""

import smtplib
from unittest.mock import MagicMock, patch

import pytest


class TestGetSMTPConfig:
    """Tests for get_smtp_config function."""

    def test_get_smtp_config_from_app(self, app):
        """Test SMTP config is read from Flask app config."""
        with app.app_context():
            app.config["SMTP_HOST"] = "smtp.example.com"
            app.config["SMTP_PORT"] = 465
            app.config["SMTP_USER"] = "user@example.com"
            app.config["SMTP_PASSWORD"] = "secret"
            app.config["SMTP_FROM"] = "news@example.com"
            app.config["SMTP_USE_TLS"] = False

            from services.email import get_smtp_config

            cfg = get_smtp_config()

            assert cfg["host"] == "smtp.example.com"
            assert cfg["port"] == 465
            assert cfg["user"] == "user@example.com"
            assert cfg["password"] == "secret"
            assert cfg["from_addr"] == "news@example.com"
            assert cfg["use_tls"] is False

    def test_get_smtp_config_defaults(self, app):
        """Test SMTP config uses defaults when not configured."""
        with app.app_context():
            app.config.pop("SMTP_HOST", None)
            app.config.pop("SMTP_PORT", None)

            from services.email import get_smtp_config

            cfg = get_smtp_config()

            assert cfg["host"] == "localhost"
            assert cfg["port"] == 587


class TestSendVerificationEmail:
    """Tests for send_verification_email function."""

    @patch("services.email._send_smtp")
    def test_send_verification_email_main(self, mock_send):
        """Test verification email for main newsletter type."""
        from services.email import send_verification_email

        send_verification_email(
            email="test@example.com",
            newsletter_type="main",
            verification_url="https://example.com/verify/token123",
            unsubscribe_url="https://example.com/unsub/token123",
        )

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "test@example.com"
        assert "Confirm" in args[1]
        assert "all topics" in args[1]
        assert "verify/token123" in args[2]
        assert "unsub/token123" in args[2]

    @patch("services.email._send_smtp")
    def test_send_verification_email_topic(self, mock_send):
        """Test verification email for topic-specific newsletter."""
        from services.email import send_verification_email

        send_verification_email(
            email="test@example.com",
            newsletter_type="ai",
            verification_url="https://example.com/verify/token123",
            unsubscribe_url="https://example.com/unsub/token123",
        )

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "ai" in args[1]

    @patch("services.email._send_smtp")
    def test_send_verification_email_custom_site_name(self, mock_send):
        """Test verification email with custom site name."""
        from services.email import send_verification_email

        send_verification_email(
            email="test@example.com",
            newsletter_type="main",
            verification_url="https://example.com/verify/token123",
            unsubscribe_url="https://example.com/unsub/token123",
            site_name="MyNews",
        )

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "MyNews" in args[1]


class TestSendWelcomeEmail:
    """Tests for send_welcome_email function."""

    @patch("services.email._send_smtp")
    def test_send_welcome_email_main(self, mock_send):
        """Test welcome email for main newsletter type."""
        from services.email import send_welcome_email

        send_welcome_email(
            email="test@example.com",
            newsletter_type="main",
            unsubscribe_url="https://example.com/unsub/token123",
        )

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "test@example.com"
        assert "all topics" in args[1]
        assert "token123" in args[2]

    @patch("services.email._send_smtp")
    def test_send_welcome_email_topic(self, mock_send):
        """Test welcome email for topic-specific newsletter."""
        from services.email import send_welcome_email

        send_welcome_email(
            email="test@example.com",
            newsletter_type="ai",
            unsubscribe_url="https://example.com/unsub/token123",
        )

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "ai" in args[1]

    @patch("services.email._send_smtp")
    def test_send_welcome_email_custom_site_name(self, mock_send):
        """Test welcome email with custom site name."""
        from services.email import send_welcome_email

        send_welcome_email(
            email="test@example.com",
            newsletter_type="main",
            unsubscribe_url="https://example.com/unsub/token123",
            site_name="MyNews",
        )

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "MyNews" in args[1]


class TestSendNewsletterEmail:
    """Tests for send_newsletter_email function."""

    @patch("services.email._send_smtp")
    def test_send_newsletter_email_injects_footer(self, mock_send):
        """Test newsletter email injects unsubscribe link into footer."""
        from services.email import send_newsletter_email

        # HTML matching the format generated by generate_newsletter_html
        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0">
        <tr><td>Content</td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""

        send_newsletter_email(
            email="test@example.com",
            subject="Test Newsletter",
            html_content=html,
            unsubscribe_url="https://example.com/unsub/token123",
        )

        mock_send.assert_called_once()
        sent_html = mock_send.call_args[0][2]
        assert "token123" in sent_html
        assert "unsubscribe" in sent_html

    @patch("services.email._send_smtp")
    def test_send_newsletter_email_replaces_existing_footer(self, mock_send):
        """Test newsletter email replaces existing footer."""
        from services.email import send_newsletter_email

        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0">
        <tr><td>Content</td></tr>
        <tr><td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eaeaea;">
          <p>condensed by agents</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

        send_newsletter_email(
            email="test@example.com",
            subject="Test Newsletter",
            html_content=html,
            unsubscribe_url="https://example.com/unsub/token456",
        )

        mock_send.assert_called_once()
        sent_html = mock_send.call_args[0][2]
        assert "token456" in sent_html


class TestSendSMTP:
    """Tests for _send_smtp function."""

    @patch("services.email.smtplib.SMTP")
    @patch("services.email.get_smtp_config")
    def test_send_smtp_success(self, mock_get_config, mock_smtp_class):
        """Test successful SMTP send."""
        from services.email import _send_smtp

        mock_get_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "user": "",
            "password": "",
            "from_addr": "noreply@example.com",
            "use_tls": True,
        }

        # Make the mock work as a context manager
        # __enter__ returns the mock itself so all method calls go to it
        mock_smtp_class.return_value.__enter__ = MagicMock(
            return_value=mock_smtp_class.return_value
        )
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        _send_smtp("test@example.com", "Test Subject", "<p>Body</p>")

        mock_smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_smtp_class.return_value.starttls.assert_called_once()
        mock_smtp_class.return_value.sendmail.assert_called_once()


    @patch("services.email.smtplib.SMTP")
    @patch("services.email.get_smtp_config")
    def test_send_smtp_with_auth(self, mock_get_config, mock_smtp_class):
        """Test SMTP send with authentication."""
        from services.email import _send_smtp

        mock_get_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "user": "user@example.com",
            "password": "secret",
            "from_addr": "noreply@example.com",
            "use_tls": True,
        }

        mock_smtp_class.return_value.__enter__ = MagicMock(
            return_value=mock_smtp_class.return_value
        )
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        _send_smtp("test@example.com", "Test Subject", "<p>Body</p>")

        mock_smtp_class.return_value.login.assert_called_once_with(
            "user@example.com", "secret"
        )

    @patch("services.email.smtplib.SMTP")
    @patch("services.email.get_smtp_config")
    def test_send_smtp_without_tls(self, mock_get_config, mock_smtp_class):
        """Test SMTP send without TLS."""
        from services.email import _send_smtp

        mock_get_config.return_value = {
            "host": "smtp.example.com",
            "port": 25,
            "user": "",
            "password": "",
            "from_addr": "noreply@example.com",
            "use_tls": False,
        }

        mock_smtp_class.return_value.__enter__ = MagicMock(
            return_value=mock_smtp_class.return_value
        )
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        _send_smtp("test@example.com", "Test Subject", "<p>Body</p>")

        mock_smtp_class.return_value.starttls.assert_not_called()

    @patch("services.email.smtplib.SMTP")
    @patch("services.email.get_smtp_config")
    def test_send_smtp_connection_error(self, mock_get_config, mock_smtp_class):
        """Test SMTP send raises on connection error."""
        from services.email import _send_smtp

        mock_get_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "user": "",
            "password": "",
            "from_addr": "noreply@example.com",
            "use_tls": True,
        }

        mock_smtp_class.side_effect = ConnectionRefusedError("Connection refused")

        with pytest.raises(ConnectionRefusedError):
            _send_smtp("test@example.com", "Test Subject", "<p>Body</p>")

    @patch("services.email.smtplib.SMTP")
    @patch("services.email.get_smtp_config")
    def test_send_smtp_auth_error(self, mock_get_config, mock_smtp_class):
        """Test SMTP send raises on authentication error."""
        from services.email import _send_smtp

        mock_get_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "user": "user@example.com",
            "password": "wrong",
            "from_addr": "noreply@example.com",
            "use_tls": True,
        }

        mock_smtp_class.return_value.__enter__ = MagicMock(
            return_value=mock_smtp_class.return_value
        )
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_smtp_class.return_value.login.side_effect = (
            smtplib.SMTPAuthenticationError(535, b"Auth failed")
        )

        with pytest.raises(smtplib.SMTPAuthenticationError):
            _send_smtp("test@example.com", "Test Subject", "<p>Body</p>")


class TestEmailHtmlEscaping:
    """Tests for HTML escaping of untrusted content in email templates."""

    @patch("services.email._send_smtp")
    def test_verification_escapes_script_in_site_name(self, mock_send):
        from services.email import send_verification_email

        send_verification_email(
            email="test@example.com",
            newsletter_type="main",
            verification_url="https://example.com/verify/t",
            unsubscribe_url="https://example.com/unsub/t",
            site_name="<script>alert(1)</script>",
        )
        html = mock_send.call_args[0][2]
        assert "<script" not in html
        assert "&lt;script&gt;" in html


    @patch("services.email._send_smtp")
    def test_verification_escapes_script_in_newsletter_type(self, mock_send):
        from services.email import send_verification_email

        send_verification_email(
            email="test@example.com",
            newsletter_type="<script>alert(1)</script>",
            verification_url="https://example.com/verify/t",
            unsubscribe_url="https://example.com/unsub/t",
        )
        html = mock_send.call_args[0][2]
        assert "<script" not in html
        assert "&lt;script&gt;" in html


    @patch("services.email._send_smtp")
    def test_welcome_escapes_script_in_site_name(self, mock_send):
        from services.email import send_welcome_email

        send_welcome_email(
            email="test@example.com",
            newsletter_type="main",
            unsubscribe_url="https://example.com/unsub/t",
            site_name="<script>alert(1)</script>",
        )
        html = mock_send.call_args[0][2]
        assert "<script" not in html
        assert "&lt;script&gt;" in html


    @patch("services.email._send_smtp")
    def test_welcome_escapes_script_in_newsletter_type(self, mock_send):
        from services.email import send_welcome_email

        send_welcome_email(
            email="test@example.com",
            newsletter_type="<script>alert(1)</script>",
            unsubscribe_url="https://example.com/unsub/t",
        )
        html = mock_send.call_args[0][2]
        assert "<script" not in html
        assert "&lt;script&gt;" in html


def test_serialized_newsletter_message_has_rfc8058_headers(monkeypatch):
    from email import message_from_string
    from services.email import send_newsletter_email

    captured = {}

    class FakeSMTP:
        def sendmail(self, sender, recipient, message):
            captured.update(sender=sender, recipient=recipient, message=message)

        def noop(self):
            return 250, b"ok"

    class FakePool:
        def get_connection(self):
            return FakeSMTP()

        def return_connection(self, _server):
            return None

    monkeypatch.setattr("services.email.get_smtp_config", lambda: {
        "host": "smtp.example.test", "port": 587, "user": "", "password": "",
        "from_addr": "news@example.test", "use_tls": True,
    })
    monkeypatch.setattr("services.email._get_smtp_pool", lambda: FakePool())
    send_newsletter_email(
        "reader@example.test", "A safe edition", "<p>Edition content.</p>",
        "https://news.example.test/unsubscribe/opaque-token",
    )

    message = message_from_string(captured["message"])
    assert captured["recipient"] == "reader@example.test"
    assert message["To"] == "reader@example.test"
    assert message["Subject"] == "A safe edition"
    assert message["List-Unsubscribe"] == "<https://news.example.test/unsubscribe/opaque-token>"
    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
