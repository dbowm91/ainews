import logging
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


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
    subject = f"Confirm your subscription to {site_name} — {newsletter_label}"
    html = f"""<!DOCTYPE html>
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
          <strong>{newsletter_label}</strong> newsletter on {site_name}.
          This link will expire in 1 hour.
        </p>
        <p style="text-align:center;margin:24px 0;">
          <a href="{verification_url}" style="display:inline-block;padding:12px 32px;background:#0d1117;color:#fff;text-decoration:none;border-radius:6px;font-weight:700;font-size:14px;">
            Confirm subscription
          </a>
        </p>
        <p style="color:#888;font-size:12px;line-height:1.6;margin:0;">
          If you didn't request this, you can ignore this email or
          <a href="{unsubscribe_url}" style="color:#58a6ff;">unsubscribe</a>.
        </p>
      </td></tr>
      <tr><td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eaeaea;">
        <p style="font-family:monospace;font-size:11px;color:#888;margin:0;text-align:center;">
          condensed by agents &middot;
          <a href="{unsubscribe_url}" style="color:#58a6ff;text-decoration:none;">unsubscribe</a>
        </p>
      </td></tr>
    </table>
  </td></tr></table>
</body>
</html>"""

    _send_smtp(email, subject, html)
    logger.info(f"Verification email sent to {email} for {newsletter_type}")


def send_welcome_email(
    email: str,
    newsletter_type: str,
    unsubscribe_url: str,
    site_name: str = "ainews//",
):
    """Send welcome email after verification is complete."""
    newsletter_label = newsletter_type if newsletter_type != "main" else "all topics"
    subject = f"Subscribed to {site_name} — {newsletter_label}"
    html = f"""<!DOCTYPE html>
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
          You've subscribed to the <strong>{newsletter_label}</strong> newsletter on {site_name}.
          You'll receive condensed news summaries when new articles are published.
        </p>
        <p style="color:#555;font-size:14px;line-height:1.6;margin:0;">
          If you ever want to unsubscribe, click here:
          <a href="{unsubscribe_url}" style="color:#58a6ff;">unsubscribe</a>
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

    _send_smtp(email, subject, html)
    logger.info(f"Welcome email sent to {email} for {newsletter_type}")


def send_newsletter_email(
    email: str,
    subject: str,
    html_content: str,
    unsubscribe_url: str,
):
    """Send newsletter email with unsubscribe link injected into footer."""
    # Inject unsubscribe link into the footer
    footer_html = f"""
        <tr>
          <td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eaeaea;">
            <p style="font-family:monospace;font-size:11px;color:#888;margin:0;text-align:center;">
              condensed by agents &middot;
              <a href="{unsubscribe_url}" style="color:#58a6ff;text-decoration:none;">unsubscribe</a>
            </p>
          </td>
        </tr>"""

    # Replace existing footer or inject before closing table tags
    if "condensed by agents" in html_content:
        html_content = re.sub(
            r"<tr>\s*<td[^>]*>.*?condensed by agents.*?</td>\s*</tr>\s*</table>\s*</td></tr>\s*</table>",
            footer_html + "</table></td></tr></table>",
            html_content,
            flags=re.DOTALL,
        )
    else:
        # Find last </table> pair and inject footer before it
        html_content = re.sub(
            r"(</table>\s*</td></tr>\s*</table>)",
            footer_html + r"\1",
            html_content,
            count=1,
            flags=re.DOTALL,
        )

    _send_smtp(email, subject, html_content)


def _send_smtp(to_email: str, subject: str, html_body: str):
    """Low-level SMTP send."""
    cfg = get_smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)

        with server:
            if cfg["use_tls"]:
                server.starttls()
            if cfg["user"] and cfg["password"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_addr"], to_email, msg.as_string())
        logger.info(f"Email sent to {to_email}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        raise
