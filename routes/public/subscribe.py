"""Subscription and verification routes: subscribe, unsubscribe, verify."""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import Response, current_app, jsonify, redirect, render_template, request
from wtforms.validators import ValidationError
from flask_wtf.csrf import validate_csrf
from werkzeug.wrappers.response import Response as WerkzeugResponse
from sqlalchemy.exc import SQLAlchemyError

from extensions import csrf, db
from models import Subscriber
from routes import limit_content_length
from routes.public import (
    _get_categories,
    public_bp,
)
from services.utils import is_valid_email

logger = logging.getLogger(__name__)

# Token format validation: secrets.token_urlsafe(32) produces 43 base64url chars
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _validate_token(token: str) -> bool:
    """Validate token format to prevent malformed token exploits."""
    return bool(token) and bool(_TOKEN_RE.match(token))


@public_bp.route("/subscribe", methods=["POST"])
@limit_content_length(1024)
def subscribe() -> str | Response | WerkzeugResponse:
    email = request.form.get("email", "").strip().lower()
    newsletter_type = request.form.get("newsletter_type", "main").strip()

    # Validate newsletter_type against known topic keys
    valid_types = set(_get_categories()) | {"main"}
    if newsletter_type not in valid_types:
        newsletter_type = "main"

    # Parse topic preferences
    preferences: dict[str, list[str]] = {"topics": []}
    topics_raw = request.form.getlist("topics")
    if topics_raw:
        valid_topic_keys = set(_get_categories())
        preferences["topics"] = [t for t in topics_raw if t in valid_topic_keys][:10]

    if not is_valid_email(email):
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_error="Please enter a valid email.",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    from services.distribution.dispatch import email_channel_enabled
    if not email_channel_enabled(newsletter_type):
        if request.headers.get("HX-Request"):
            return render_template("partials/subscribe_box.html", subscribe_info="Email delivery for this newsletter is currently disabled.", newsletter_type=newsletter_type)
        return redirect("/")

    existing = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(email=email, newsletter_type=newsletter_type)
        .first()
    )

    if existing and existing.active and existing.confirmed_at is not None:
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_success="Check your email to confirm your subscription.",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    unsub_token = secrets.token_urlsafe(32)
    verify_token = secrets.token_urlsafe(32)

    if existing and not existing.active:
        existing.active = True
        existing.unsubscribe_token = unsub_token
        existing.verification_token = verify_token
        existing.confirmed_at = None
        existing.preferences = preferences
    elif existing and existing.active and existing.confirmed_at is None:
        existing.verification_token = verify_token
        unsub_token = existing.unsubscribe_token
        existing.preferences = preferences
    else:
        subscriber = Subscriber(
            email=email,
            newsletter_type=newsletter_type,
            unsubscribe_token=unsub_token,
            verification_token=verify_token,
            preferences=preferences,
        )
        db.session.add(subscriber)

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to subscribe %s", email)
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/subscribe_box.html",
                subscribe_error="Something went wrong. Please try again.",
                newsletter_type=newsletter_type,
            )
        return redirect("/")

    site_url = str(current_app.config.get("NEWSLETTER_SITE_URL") or current_app.config.get("SITE_URL") or "").rstrip("/")
    verification_url = f"{site_url}/verify/{verify_token}"
    unsubscribe_url = f"{site_url}/unsubscribe/{unsub_token}"
    email_failed = False
    try:
        from services.email import send_verification_email

        send_verification_email(
            email, newsletter_type, verification_url, unsubscribe_url,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Verification email failed for %s: %s", email, e)
        email_failed = True

    if request.headers.get("HX-Request"):
        return render_template(
            "partials/subscribe_box.html",
            subscribe_info="Check your email to confirm your subscription."
            if not email_failed
            else None,
            subscribe_warning="Verification email could not be sent. Please try again later."
            if email_failed
            else None,
            newsletter_type=newsletter_type,
        )
    return redirect("/")


@public_bp.route("/unsubscribe/<token>")
def unsubscribe(token: str) -> str:
    """Show unsubscribe confirmation page (GET)."""
    if not _validate_token(token):
        return render_template("unsubscribe.html", token=token, found=False)
    subscriber = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(unsubscribe_token=token, active=True)
        .first()
    )

    return render_template(
        "unsubscribe.html", token=token, found=subscriber is not None,
    )


@public_bp.route("/unsubscribe/<token>", methods=["POST"])
def unsubscribe_confirm(token: str) -> str | Response:
    """Process unsubscribe request (POST with CSRF protection)."""
    one_click = request.mimetype == "application/x-www-form-urlencoded" and request.form.get("List-Unsubscribe") == "One-Click"
    if not one_click:
        try:
            validate_csrf(request.form.get("csrf_token") or request.headers.get("X-CSRFToken"))
        except (ValidationError, TypeError, ValueError):
            return "Invalid CSRF token"
    if not _validate_token(token):
        return render_template("unsubscribe.html", token=token, found=False)
    subscriber = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(unsubscribe_token=token, active=True)
        .first()
    )

    commit_failed = False
    if subscriber:
        subscriber.active = False
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("Failed to unsubscribe token %s...", token[:8] if token else "")
            commit_failed = True

    if one_click:
        return jsonify({"unsubscribed": bool(subscriber and not commit_failed)})
    return render_template(
        "unsubscribe.html",
        token=token,
        found=subscriber is not None,
        confirmed=subscriber is not None and not commit_failed,
        error=commit_failed,
    )


# The route validates browser CSRF itself and supports the RFC 8058 token POST.
csrf.exempt(unsubscribe_confirm)


@public_bp.route("/verify/<token>")
def verify(token: str) -> str:
    """Verify a subscriber's email address via token link."""
    if not _validate_token(token):
        return render_template("verify.html", found=False)
    subscriber = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter(Subscriber.confirmed_at.is_(None))
        .filter_by(verification_token=token)
        .first()
    )

    if not subscriber:
        return render_template("verify.html", found=False)

    expiry = current_app.config.get("VERIFICATION_EXPIRY_SECONDS", 3600)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=expiry)
    subscribed_at = subscriber.subscribed_at
    if subscribed_at.tzinfo is None:
        subscribed_at = subscribed_at.replace(tzinfo=timezone.utc)
    if subscribed_at < cutoff:
        return render_template("verify.html", found=False, expired=True)

    subscriber.confirmed_at = datetime.now(timezone.utc)
    subscriber.verification_token = None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to verify subscriber token %s...", token[:8] if token else "")
        return render_template("verify.html", found=False)

    # Send welcome email
    site_url = str(current_app.config.get("NEWSLETTER_SITE_URL") or current_app.config.get("SITE_URL") or "").rstrip("/")
    unsubscribe_url = f"{site_url}/unsubscribe/{subscriber.unsubscribe_token}"
    try:
        from services.email import send_welcome_email

        send_welcome_email(
            subscriber.email, subscriber.newsletter_type, unsubscribe_url,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Welcome email failed for %s: %s", subscriber.email, e)

    return render_template("verify.html", found=True, subscriber=subscriber)
