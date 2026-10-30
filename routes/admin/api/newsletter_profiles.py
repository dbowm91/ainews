"""Durable profile and multi-time schedule controls."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app, jsonify, request
from sqlalchemy import update

from extensions import db
from models import DeliveryIntent, NewsletterDeliveryConfig, NewsletterEdition, NewsletterProfile, NewsletterSchedule
from routes.admin import admin_api_bp, require_auth
from routes.decorators import csrf_for_session_auth

_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _parse_schedules(data):
    if "schedules" not in data:
        return None
    schedules = data["schedules"]
    if not isinstance(schedules, list) or len(schedules) > 8:
        raise ValueError("schedules must contain at most 8 times")
    parsed = []
    seen = set()
    for schedule in schedules:
        time = str(schedule.get("time", "")) if isinstance(schedule, dict) else ""
        weekdays = schedule.get("weekdays", list(range(7))) if isinstance(schedule, dict) else []
        enabled = schedule.get("enabled", True) if isinstance(schedule, dict) else None
        if (not _TIME.fullmatch(time) or time in seen or not isinstance(weekdays, list)
                or any(type(day) is not int or day < 0 or day > 6 for day in weekdays)
                or len(set(weekdays)) != len(weekdays) or not isinstance(enabled, bool)):
            raise ValueError("invalid or duplicate schedule time / weekday")
        seen.add(time)
        parsed.append((time, sum(1 << day for day in weekdays), enabled))
    return parsed


def _profile_timezone(data, profile):
    timezone_name = data.get("timezone", profile.timezone_name)
    if not isinstance(timezone_name, str) or not timezone_name:
        raise ValueError("timezone must be an installed IANA timezone")
    try:
        ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("timezone must be an installed IANA timezone") from exc
    return timezone_name


def _cancel_if_email_disabled(was_enabled: bool, profile_id: int) -> None:
    if was_enabled:
        from services.distribution.dispatch import cancel_email_requests
        cancel_email_requests(profile_id=profile_id)


@admin_api_bp.route("/newsletter-delivery", methods=["GET"])
@require_auth
def get_newsletter_delivery_config():
    config = db.session.get(NewsletterDeliveryConfig, 1)
    return jsonify({"email_enabled": bool(config and config.email_enabled)})


@admin_api_bp.route("/newsletter-delivery", methods=["PUT"])
@require_auth
@csrf_for_session_auth
def set_newsletter_delivery_config():
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("email_enabled"), bool):
        return jsonify({"error": "email_enabled must be a boolean"}), 400
    config = db.session.get(NewsletterDeliveryConfig, 1) or NewsletterDeliveryConfig(id=1)
    was_enabled = bool(config.email_enabled)
    config.email_enabled = data["email_enabled"]
    db.session.add(config)
    if was_enabled and not config.email_enabled:
        from services.distribution.dispatch import cancel_email_requests
        cancel_email_requests()
    db.session.commit()
    from services.audit import log_admin_action
    log_admin_action("newsletter_delivery_config", target_type="newsletter_delivery_config", target_id=1,
        details={"email_enabled": config.email_enabled}, category="pipeline")
    return jsonify({"email_enabled": config.email_enabled})


def _profile_json(profile):
    last = NewsletterEdition.query.filter_by(profile_id=profile.id, status="published").order_by(NewsletterEdition.published_at.desc()).first()
    return {"key": profile.key, "scope": profile.scope, "category": profile.category, "title": profile.title,
        "policy_revision": profile.policy_revision,
        "enabled": profile.enabled, "email_enabled": profile.email_enabled, "timezone": profile.timezone_name,
        "max_articles": profile.max_articles, "min_impact": profile.min_impact,
        "schedules": [{"time": s.local_time, "weekdays": [day for day in range(7) if s.weekdays & (1 << day)], "enabled": s.enabled} for s in profile.schedules],
        "last_edition": last.public_id if last else None,
        "next_slots": _next_slots(profile)}


def _next_slots(profile, *, count=3):
    """Return upcoming civil schedule times, respecting weekdays and DST gaps."""
    from datetime import datetime, time, timedelta, timezone
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(profile.timezone_name)
    now = datetime.now(timezone.utc)
    local_today = now.astimezone(zone).date()
    slots = []
    for day_offset in range(15):
        local_date = local_today + timedelta(days=day_offset)
        weekday = local_date.weekday()
        for schedule in profile.schedules:
            if not schedule.enabled or not schedule.weekdays & (1 << weekday):
                continue
            hour, minute = map(int, schedule.local_time.split(":"))
            candidate = datetime.combine(local_date, time(hour, minute), tzinfo=zone).replace(fold=0)
            # Round trip detects a nonexistent spring-forward civil time.
            if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != candidate.replace(tzinfo=None):
                continue
            if candidate.astimezone(timezone.utc) > now:
                slots.append(candidate.isoformat())
        if len(slots) >= count:
            break
    return sorted(slots)[:count]


@admin_api_bp.route("/newsletter-profiles", methods=["GET"])
@require_auth
def list_newsletter_profiles():
    return jsonify([_profile_json(p) for p in NewsletterProfile.query.order_by(NewsletterProfile.scope, NewsletterProfile.key).all()])


@admin_api_bp.route("/newsletter-profiles/<key>", methods=["PUT"])
@require_auth
@csrf_for_session_auth
def update_newsletter_profile(key: str):
    profile = NewsletterProfile.query.filter_by(key=key).first_or_404()
    was_email_enabled = bool(profile.email_enabled)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    revision = data.get("policy_revision")
    if type(revision) is not int or revision != profile.policy_revision:
        return jsonify({"error": "policy_revision is required and must match the current profile", "policy_revision": profile.policy_revision}), 409
    for field in ("enabled", "email_enabled"):
        if field in data and not isinstance(data[field], bool):
            return jsonify({"error": f"{field} must be a boolean"}), 400
    try:
        timezone_name = _profile_timezone(data, profile)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    max_articles = data.get("max_articles", profile.max_articles)
    min_impact = data.get("min_impact", profile.min_impact)
    if type(max_articles) is not int or not 1 <= max_articles <= 20 or type(min_impact) is not int or min_impact < 0:
        return jsonify({"error": "invalid selection limits"}), 400
    try:
        parsed = _parse_schedules(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    schedules = data.get("schedules") if "schedules" in data else None
    previous_schedules = sorted((s.local_time, s.weekdays, s.enabled) for s in profile.schedules)
    for field in ("enabled", "email_enabled"):
        if field in data and not isinstance(data[field], bool):
            return jsonify({"error": f"{field} must be a boolean"}), 400
    changed = db.session.execute(update(NewsletterProfile).where(
        NewsletterProfile.id == profile.id, NewsletterProfile.policy_revision == revision
    ).values(enabled=data.get("enabled", profile.enabled),
        email_enabled=data.get("email_enabled", profile.email_enabled), timezone_name=timezone_name,
        max_articles=max_articles, min_impact=min_impact, policy_revision=revision + 1))
    if changed.rowcount != 1:
        db.session.rollback()
        return jsonify({"error": "profile changed while this form was open; reload and retry"}), 409
    db.session.expire(profile)
    db.session.refresh(profile)
    _cancel_if_email_disabled(was_email_enabled and not profile.email_enabled, profile.id)
    if parsed is not None:
        existing = {schedule.local_time: schedule for schedule in profile.schedules}
        for time, weekdays, enabled in parsed:
            schedule = existing.pop(time, None)
            if schedule is None:
                schedule = NewsletterSchedule(profile_id=profile.id, local_time=time)
                db.session.add(schedule)
            schedule.weekdays, schedule.enabled = weekdays, enabled
        for schedule in existing.values():
            db.session.delete(schedule)
    db.session.commit()
    from services.audit import log_admin_action
    log_admin_action("newsletter_profile_update", target_type="newsletter_profile", target_id=profile.id,
        details={"key": key, "enabled": profile.enabled, "email_enabled": profile.email_enabled,
            "timezone": profile.timezone_name, "schedule_count": len(profile.schedules),
            "schedules_before": previous_schedules,
            "schedules_after": sorted((s.local_time, s.weekdays, s.enabled) for s in profile.schedules),
            "max_articles": profile.max_articles, "min_impact": profile.min_impact}, category="pipeline")
    return jsonify(_profile_json(profile))


@admin_api_bp.route("/newsletter-profiles/<key>/preview", methods=["POST"])
@require_auth
@csrf_for_session_auth
def preview_newsletter_profile(key: str):
    from services.newsletter_editions import _editorial_text, select_articles
    profile = NewsletterProfile.query.filter_by(key=key).first_or_404()
    articles = select_articles(key, limit=profile.max_articles)
    return jsonify({"profile": key, "published": False, "sent": False, "items": [
        {"article_public_id": a.public_id, "headline": _editorial_text(a)[0], "why_it_matters": _editorial_text(a)[1],
         "paragraph": _editorial_text(a)[2], "canonical_url": f"{str(current_app.config.get('SITE_URL') or 'http://localhost:5000').rstrip('/')}/article/{a.public_id}"} for a in articles]})


@admin_api_bp.route("/newsletter-profiles/<key>/publish", methods=["POST"])
@require_auth
@csrf_for_session_auth
def publish_newsletter_profile(key: str):
    from uuid import uuid4
    from services.newsletter_editions import create_edition, select_articles
    profile = NewsletterProfile.query.filter_by(key=key).first_or_404()
    data = request.get_json(silent=True) or {}
    send = data.get("send", False)
    if not isinstance(send, bool):
        return jsonify({"error": "send must be a boolean"}), 400
    if send:
        delivery = db.session.get(NewsletterDeliveryConfig, 1)
        if not profile.email_enabled or delivery is None or not delivery.email_enabled:
            return jsonify({"error": "email delivery is disabled for this profile or globally"}), 409
    edition = create_edition(key, select_articles(key, limit=profile.max_articles), occurrence_key=f"manual:{key}:{uuid4()}", send_email=send)
    if edition is None:
        return jsonify({"error": "no eligible published articles"}), 409
    queued = 0
    if send:
        from services.distribution.dispatch import plan_edition_deliveries
        from tasks.distribution import deliver_newsletter_intent
        from models import DeliveryIntent
        from sqlalchemy import select
        queued = plan_edition_deliveries(edition.id)
        for intent_id in db.session.scalars(select(DeliveryIntent.id).where(DeliveryIntent.edition_id == edition.id, DeliveryIntent.state == "pending")):
            deliver_newsletter_intent.apply_async(args=[intent_id])
    from services.audit import log_admin_action
    log_admin_action("newsletter_publish", target_type="newsletter_edition", target_id=edition.id, details={"profile": key, "send": send}, category="pipeline")
    return jsonify({"public_id": edition.public_id, "published": True, "delivery_intents": queued}), 201


@admin_api_bp.route("/newsletter-editions/<public_id>/deliveries", methods=["GET"])
@require_auth
def newsletter_edition_deliveries(public_id: str):
    from sqlalchemy import func
    edition = NewsletterEdition.query.filter_by(public_id=public_id).first_or_404()
    rows = db.session.query(DeliveryIntent.state, func.count(DeliveryIntent.id)).filter_by(edition_id=edition.id).group_by(DeliveryIntent.state).all()
    intents = DeliveryIntent.query.filter_by(edition_id=edition.id).order_by(DeliveryIntent.id.desc()).limit(500).all()
    return jsonify({"edition": public_id, "counts": dict(rows), "intents": [
        {"id": item.id, "state": item.state, "attempt_count": item.attempt_count, "error_code": item.error_code}
        for item in intents]})


@admin_api_bp.route("/newsletter-editions/<public_id>/deliveries", methods=["POST"])
@require_auth
@csrf_for_session_auth
def manage_newsletter_edition_deliveries(public_id: str):
    from datetime import datetime, timezone
    from services.audit import log_admin_action
    edition = NewsletterEdition.query.filter_by(public_id=public_id).first_or_404()
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    intent_ids = data.get("intent_ids")
    if action not in {"retry", "retry_unknown", "cancel"} or not isinstance(intent_ids, list) or not intent_ids or len(intent_ids) > 500 or any(not isinstance(i, int) for i in intent_ids):
        return jsonify({"error": "provide action and 1–500 delivery intent IDs"}), 400
    if action == "retry_unknown" and data.get("confirm_unknown_retry") is not True:
        return jsonify({"error": "confirm_unknown_retry is required because SMTP outcomes may be ambiguous"}), 400
    allowed_states = {"retry": {"failed"}, "retry_unknown": {"unknown"}, "cancel": {"pending", "failed"}}[action]
    intents = DeliveryIntent.query.filter(DeliveryIntent.edition_id == edition.id, DeliveryIntent.id.in_(intent_ids),
        DeliveryIntent.state.in_(allowed_states), DeliveryIntent.attempt_count < 5).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for intent in intents:
        if action.startswith("retry"):
            intent.state = "pending"
            intent.next_attempt_at = None
            intent.error_code = None
            intent.updated_at = now
        else:
            intent.state = "cancelled"
            intent.updated_at = now
            intent.next_attempt_at = None
    db.session.commit()
    log_admin_action("newsletter_delivery_manage", target_type="newsletter_edition", target_id=edition.id,
        details={"action": action, "count": len(intents)}, category="pipeline")
    return jsonify({"action": action, "updated": len(intents)})
