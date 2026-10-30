"""Personalized email rendering over immutable edition snapshots."""
from __future__ import annotations

import smtplib
from html import escape

from sqlalchemy import select

from extensions import db
from models import DeliveryIntent, NewsletterEditionItem, Subscriber
from services.distribution.base import DeliveryOutcome


class EmailChannel:
    key = "email"

    def send(self, intent_id: int) -> DeliveryOutcome:
        intent = db.session.get(DeliveryIntent, intent_id)
        if intent is None or intent.state != "claimed":
            return DeliveryOutcome("suppressed", "intent_not_claimed")
        subscriber = db.session.get(Subscriber, intent.subscriber_id) if intent.subscriber_id else None
        if subscriber is None or subscriber.deleted_at is not None or not subscriber.active or subscriber.confirmed_at is None:
            return DeliveryOutcome("suppressed", "recipient_inactive")
        items = db.session.scalars(select(NewsletterEditionItem).where(NewsletterEditionItem.edition_id == intent.edition_id).order_by(NewsletterEditionItem.position)).all()
        edition = intent.edition
        if edition is None or edition.status != "published":
            return DeliveryOutcome("suppressed", "edition_not_published")
        from flask import current_app
        try:
            site_url = current_app.config.get("NEWSLETTER_SITE_URL") or current_app.config.get("SITE_URL") or "http://localhost"
            content = [f"<h1>{escape(edition.subject)}</h1>"]
            for item in items:
                content.append(f'<article><h2><a href="{escape(item.canonical_url, quote=True)}">{escape(item.headline)}</a></h2>')
                if item.why_it_matters:
                    content.append(f"<p><strong>Why it matters:</strong> {escape(item.why_it_matters)}</p>")
                if item.paragraph:
                    content.append(f"<p>{escape(item.paragraph)}</p>")
                content.append("</article>")
            unsubscribe = f"{site_url.rstrip('/')}/unsubscribe/{subscriber.unsubscribe_token}"
            content.append(f'<p><a href="{escape(unsubscribe, quote=True)}">Unsubscribe</a></p>')
            from services.email import send_newsletter_email
            send_newsletter_email(subscriber.email, edition.subject, "".join(content), unsubscribe)
            return DeliveryOutcome("accepted")
        except smtplib.SMTPResponseException as exc:
            if exc.smtp_code >= 500:
                return DeliveryOutcome("permanent_failure", f"smtp_{exc.smtp_code}")
            return DeliveryOutcome("temporary_failure", f"smtp_{exc.smtp_code}")
        except (TimeoutError, ConnectionError, smtplib.SMTPServerDisconnected):
            # The transport may have accepted before disconnect. Treat as ambiguous.
            return DeliveryOutcome("unknown", "smtp_outcome_unknown")
        except smtplib.SMTPException:
            return DeliveryOutcome("temporary_failure", "smtp_temporary")
        except Exception:  # noqa: BLE001 - an unexpected failure after transport entry is ambiguous
            return DeliveryOutcome("unknown", "transport_error")
