import html
import logging
import re
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import deque

logger = logging.getLogger(__name__)


class SMTPConnectionPool:
    """Pool of reusable SMTP connections."""

    def __init__(self, pool_size: int = 5):
        self._pool_size = pool_size
        self._pool: deque[smtplib.SMTP] = deque()
        self._lock = threading.Lock()
        self._closed = False
        self._cfg_hash = None

    def _get_config(self) -> dict:
        """Get current SMTP config."""
        return get_smtp_config()

    def _compute_cfg_hash(self, cfg: dict) -> str:
        """Compute a simple hash of config to detect changes."""
        import hashlib
        import json

        cfg_str = json.dumps(
            {
                "host": cfg.get("host"),
                "port": cfg.get("port"),
                "user": cfg.get("user"),
                "password": cfg.get("password"),
                "from_addr": cfg.get("from_addr"),
                "use_tls": cfg.get("use_tls"),
            },
            sort_keys=True,
        )
        return hashlib.md5(cfg_str.encode()).hexdigest()

    def _create_connection(self, cfg: dict) -> smtplib.SMTP:
        """Create and authenticate a new SMTP connection."""
        server = smtplib.SMTP(
            cfg["host"], cfg["port"], timeout=30,
        )
        if cfg["use_tls"]:
            server.starttls()
        if cfg["user"] and cfg["password"]:
            server.login(cfg["user"], cfg["password"])
        return server

    def _is_healthy(self, server: smtplib.SMTP) -> bool:
        """Check if connection is still alive."""
        try:
            server.noop()
            return True
        except Exception:
            return False

    def get_connection(self) -> smtplib.SMTP:
        """Get a connection from the pool, creating one if needed."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Connection pool is closed")

            cfg = self._get_config()
            cfg_hash = self._compute_cfg_hash(cfg)

            # Reset pool if config changed
            if self._cfg_hash is not None and self._cfg_hash != cfg_hash:
                self._close_all_unsafe()
                self._pool = deque()

            self._cfg_hash = cfg_hash

            while self._pool:
                server = self._pool.popleft()
                if self._is_healthy(server):
                    return server
                try:
                    server.quit()
                except Exception:
                    pass

            return self._create_connection(cfg)

    def return_connection(self, server: smtplib.SMTP):
        """Return a connection to the pool."""
        with self._lock:
            if self._closed:
                try:
                    server.quit()
                except Exception:
                    pass
                return
            if self._is_healthy(server):
                self._pool.append(server)
            else:
                try:
                    server.quit()
                except Exception:
                    pass

    def _close_all_unsafe(self):
        """Close all connections without lock (caller must hold lock)."""
        while self._pool:
            server = self._pool.popleft()
            try:
                server.quit()
            except Exception:
                pass

    def close_all(self):
        """Close all connections in the pool."""
        with self._lock:
            self._close_all_unsafe()


# Global pool instance
_pool_lock = threading.Lock()
_smtp_pool: SMTPConnectionPool | None = None


def _get_smtp_pool() -> SMTPConnectionPool:
    """Get or create the global SMTP connection pool."""
    global _smtp_pool
    with _pool_lock:
        if _smtp_pool is None:
            pool_size = 5
            try:
                from flask import current_app
                pool_size = current_app.config.get("SMTP_POOL_SIZE", 5)
            except Exception:
                import os
                pool_size = int(os.environ.get("SMTP_POOL_SIZE", "5"))
            _smtp_pool = SMTPConnectionPool(pool_size)
        return _smtp_pool


def _reset_smtp_pool():
    """Reset the global SMTP pool. For testing purposes."""
    global _smtp_pool
    with _pool_lock:
        if _smtp_pool is not None:
            _smtp_pool.close_all()
            _smtp_pool = None

_FOOTER_WITH_AGENTS_RE = re.compile(
    r"<tr>\s*<td[^>]*>.*?condensed by agents.*?</td>\s*</tr>\s*</table>\s*</td></tr>\s*</table>",
    flags=re.DOTALL,
)
_CLOSING_TABLE_RE = re.compile(r"(</table>\s*</td></tr>\s*</table>)", flags=re.DOTALL)


def get_smtp_config():
    """Get SMTP settings from Flask app config or env."""
    try:
        from flask import current_app

        return {
            "host": current_app.config.get("SMTP_HOST", "localhost"),
            "port": current_app.config.get("SMTP_PORT", 587),
            "user": current_app.config.get("SMTP_USER", ""),
            "password": current_app.config.get("SMTP_PASSWORD", ""),
            "from_addr": current_app.config.get("SMTP_FROM", "noreply@ainews.dev"),
            "use_tls": current_app.config.get("SMTP_USE_TLS", True),
        }
    except Exception:
        import os

        return {
            "host": os.environ.get("SMTP_HOST", "localhost"),
            "port": int(os.environ.get("SMTP_PORT", "587")),
            "user": os.environ.get("SMTP_USER", ""),
            "password": os.environ.get("SMTP_PASSWORD", ""),
            "from_addr": os.environ.get("SMTP_FROM", "noreply@ainews.dev"),
            "use_tls": True,
        }


def send_verification_email(
    email: str,
    newsletter_type: str,
    verification_url: str,
    unsubscribe_url: str,
    site_name: str = "ainews//",
):
    """Send email verification link to a new subscriber."""
    newsletter_label = newsletter_type if newsletter_type != "main" else "all topics"
    safe_label = html.escape(newsletter_label)
    safe_site = html.escape(site_name)
    safe_verification_url = html.escape(verification_url, quote=True)
    safe_unsubscribe_url = html.escape(unsubscribe_url, quote=True)
    subject = f"Confirm your subscription to {html.escape(site_name)} — {html.escape(newsletter_label)}"
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;">
      <tr><td style="padding:24px 32px;background:#0d1117;color:#fff;">
        <span style="font-family:monospace;font-size:20px;font-weight:700;">ainews<span style="color:#58a6ff;">//</span></span>
      </td></tr>
      <tr><td style="padding:24px 32px;">
        <h1 style="font-size:18px;font-weight:700;color:#111;margin:0 0 12px 0;">Confirm your subscription</h1>
        <p style="color:#555;font-size:14px;line-height:1.6;margin:0 0 16px 0;">
          Click the button below to confirm your subscription to the
          <strong>{safe_label}</strong> newsletter on {safe_site}.
          This link will expire in 1 hour.
        </p>
        <p style="text-align:center;margin:24px 0;">
          <a href="{safe_verification_url}" style="display:inline-block;padding:12px 32px;background:#0d1117;color:#fff;text-decoration:none;border-radius:6px;font-weight:700;font-size:14px;">
            Confirm subscription
          </a>
        </p>
        <p style="color:#888;font-size:12px;line-height:1.6;margin:0;">
          If you didn't request this, you can ignore this email or
          <a href="{safe_unsubscribe_url}" style="color:#58a6ff;">unsubscribe</a>.
        </p>
      </td></tr>
      <tr><td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eaeaea;">
        <p style="font-family:monospace;font-size:11px;color:#888;margin:0;text-align:center;">
          condensed by agents &middot;
          <a href="{safe_unsubscribe_url}" style="color:#58a6ff;text-decoration:none;">unsubscribe</a>
        </p>
      </td></tr>
    </table>
  </td></tr></table>
</body>
</html>"""

    _send_smtp(email, subject, html_body)
    logger.info("Verification email sent to %s for %s", email, newsletter_type)


def send_welcome_email(
    email: str,
    newsletter_type: str,
    unsubscribe_url: str,
    site_name: str = "ainews//",
):
    """Send welcome email after verification is complete."""
    newsletter_label = newsletter_type if newsletter_type != "main" else "all topics"
    safe_label = html.escape(newsletter_label)
    safe_site = html.escape(site_name)
    safe_unsubscribe_url = html.escape(unsubscribe_url, quote=True)
    subject = f"Subscribed to {html.escape(site_name)} — {html.escape(newsletter_label)}"
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;">
      <tr><td style="padding:24px 32px;background:#0d1117;color:#fff;">
        <span style="font-family:monospace;font-size:20px;font-weight:700;">ainews<span style="color:#58a6ff;">//</span></span>
      </td></tr>
      <tr><td style="padding:24px 32px;">
        <h1 style="font-size:18px;font-weight:700;color:#111;margin:0 0 12px 0;">You're subscribed!</h1>
        <p style="color:#555;font-size:14px;line-height:1.6;margin:0 0 16px 0;">
          You've subscribed to the <strong>{safe_label}</strong> newsletter on {safe_site}.
          You'll receive condensed news summaries when new articles are published.
        </p>
        <p style="color:#555;font-size:14px;line-height:1.6;margin:0;">
          If you ever want to unsubscribe, click here:
          <a href="{safe_unsubscribe_url}" style="color:#58a6ff;">unsubscribe</a>
        </p>
      </td></tr>
      <tr><td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eaeaea;">
        <p style="font-family:monospace;font-size:11px;color:#888;margin:0;text-align:center;">
          condensed by agents
        </p>
      </td></tr>
    </table>
  </td></tr></table>
</body>
</html>"""

    _send_smtp(email, subject, html_body)
    logger.info("Welcome email sent to %s for %s", email, newsletter_type)


def send_newsletter_email(
    email: str,
    subject: str,
    html_content: str,
    unsubscribe_url: str,
):
    """Send newsletter email with unsubscribe link injected into footer."""
    safe_unsubscribe_url = html.escape(unsubscribe_url, quote=True)
    footer_html = f"""
        <tr>
          <td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eaeaea;">
            <p style="font-family:monospace;font-size:11px;color:#888;margin:0;text-align:center;">
              condensed by agents &middot;
              <a href="{safe_unsubscribe_url}" style="color:#58a6ff;text-decoration:none;">unsubscribe</a>
            </p>
          </td>
        </tr>"""

    if "condensed by agents" in html_content:
        html_content = _FOOTER_WITH_AGENTS_RE.sub(
            footer_html + "</table></td></tr></table>",
            html_content,
        )
    else:
        html_content = _CLOSING_TABLE_RE.sub(
            footer_html + r"\1",
            html_content,
            count=1,
        )

    list_unsubscribe_url = f"<{unsubscribe_url}>"
    _send_smtp(
        email,
        subject,
        html_content,
        extra_headers={
            "List-Unsubscribe": list_unsubscribe_url,
            "List-Unsubscribe-Post": "One-Click",
        },
    )


def html_to_plain_text(html_body: str) -> str:
    """Convert HTML to plain text for email fallback."""
    text = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<ul\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</ul\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li\s*>", "• ", text, flags=re.IGNORECASE)
    text = re.sub(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>([^<]*)</a>", r"\2: \1", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _send_smtp(to_email: str, subject: str, html_body: str, extra_headers: dict | None = None):
    """Low-level SMTP send using connection pool."""
    cfg = get_smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    if extra_headers:
        for key, value in extra_headers.items():
            msg[key] = value
    plain_text = html_to_plain_text(html_body)
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    pool = _get_smtp_pool()
    server = None
    try:
        server = pool.get_connection()
        server.sendmail(cfg["from_addr"], to_email, msg.as_string())
        logger.info("Email sent to %s: %s", to_email, subject)
        pool.return_connection(server)
        server = None
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
        raise
