"""The admin settings panel.

Three things an operator needs to be able to change without opening a text
editor:

* which provider and model each pipeline stage uses,
* which providers exist, which are enabled, which is the default, and
  whether each one actually works,
* the name the site attributes its summaries to.

The first two are written to the same configuration files the operator CLI
edits. The third lives in ``topics.yaml`` next to the topic definitions.

The credential a provider uses is never shown, never rendered and never
carried through this module. The panel shows whether one is configured, and
the test button uses it without revealing it.
"""

from __future__ import annotations

import logging

from flask import flash, jsonify, redirect, render_template, request, url_for

from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)


def _services():
    """Return the settings service, imported late to keep import time down."""
    from services import admin_settings

    return admin_settings


@admin_bp.route("/settings")
@require_auth
def settings() -> str:
    admin_settings = _services()
    providers = admin_settings.read_providers()
    roles = admin_settings.read_roles()
    identity = admin_settings.read_identity()
    topics = admin_settings.read_topics()
    schedule = admin_settings.read_schedule()
    review = admin_settings.read_review()

    return render_template(
        "admin/settings.html",
        providers=providers,
        roles=roles,
        identity=identity,
        topics=topics,
        schedule=schedule,
        review=review,
        schedule_fields=admin_settings.SCHEDULE_FIELDS,
        topic_colors=admin_settings.TOPIC_COLORS,
        provider_ids=[p.id for p in providers],
    )


@admin_bp.route("/settings/roles", methods=["POST"])
@require_auth
def update_roles():
    admin_settings = _services()
    updates: dict[str, dict] = {}
    for role in admin_settings.PIPELINE_ROLES:
        provider = request.form.get(f"role_{role}_provider", "").strip()
        model = request.form.get(f"role_{role}_model", "").strip()
        if not provider and not model:
            continue
        updates[role] = {
            "provider": provider,
            "model": model,
            "enabled": bool(request.form.get(f"role_{role}_enabled")),
        }

    if not updates:
        flash("Nothing to save.", "warning")
        return redirect(url_for("admin.settings"))

    try:
        changed = admin_settings.update_roles(updates)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update the pipeline roles: %s", e)
        flash(f"Could not update the pipeline roles: {e}", "error")
        return redirect(url_for("admin.settings"))

    flash(f"Updated {', '.join(changed)}.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/providers", methods=["POST"])
@require_auth
def update_providers():
    admin_settings = _services()
    providers = admin_settings.read_providers()

    # Only the rows the form actually submitted are touched. A checkbox
    # that is off sends nothing, so the rows themselves say which fields
    # were part of this submission.
    submitted = set(request.form.getlist("provider_row"))
    default_id = request.form.get("default_provider", "").strip()

    changes: dict[str, dict] = {}
    for provider in providers:
        if provider.id not in submitted:
            continue
        fields: dict = {
            "enabled": bool(request.form.get(f"enabled_{provider.id}")),
            "model": request.form.get(f"model_{provider.id}", "").strip(),
        }
        endpoint = request.form.get(f"endpoint_{provider.id}", "").strip()
        if endpoint:
            fields["endpoint"] = endpoint
        if request.form.get(f"local_{provider.id}") is not None:
            fields["local"] = bool(request.form.get(f"local_{provider.id}"))
        if default_id == provider.id:
            fields["make_default"] = True
        changes[provider.id] = fields

    if not changes:
        flash("Nothing to save.", "warning")
        return redirect(url_for("admin.settings"))

    try:
        changed = admin_settings.update_providers(changes)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update the providers: %s", e)
        flash(f"Could not update the providers: {e}", "error")
        return redirect(url_for("admin.settings"))

    flash(f"Updated {len(changed)} providers.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/providers/<provider_id>/test", methods=["POST"])
@require_auth
def test_provider(provider_id: str):
    admin_settings = _services()
    result = admin_settings.probe_provider(provider_id)
    return jsonify(
        {
            "provider_id": result.provider_id,
            "ok": result.ok,
            "detail": result.detail,
            "models": list(result.models),
            "latency_ms": result.latency_ms,
        }
    )


@admin_bp.route("/settings/identity", methods=["POST"])
@require_auth
def update_identity():
    admin_settings = _services()
    global_name = request.form.get("agent_name", "")

    topic_names: dict[str, str] = {}
    for key, _display, _current in admin_settings.read_identity().topics:
        topic_names[key] = request.form.get(f"topic_agent_name_{key}", "")

    try:
        admin_settings.update_identity(global_name, topic_names)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update the agent name: %s", e)
        flash(f"Could not update the agent name: {e}", "error")
        return redirect(url_for("admin.settings"))

    flash("Updated the agent name.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/topics", methods=["POST"])
@require_auth
def update_topics():
    """Change the topics that already exist."""
    admin_settings = _services()

    submitted = set(request.form.getlist("topic_row"))
    updates: dict[str, dict] = {}
    for topic_id in submitted:
        fields = {
            "display_name": request.form.get(f"display_name_{topic_id}", ""),
            "description": request.form.get(f"description_{topic_id}", ""),
            "color": request.form.get(f"color_{topic_id}", ""),
            "query": request.form.get(f"query_{topic_id}", ""),
        }
        if not fields["display_name"].strip():
            continue
        updates[topic_id] = fields

    if not updates:
        flash("Nothing to save.", "warning")
        return redirect(url_for("admin.settings"))

    try:
        changed = admin_settings.update_topics(updates)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update the topics: %s", e)
        flash(f"Could not update the topics: {e}", "error")
        return redirect(url_for("admin.settings"))

    flash(f"Updated {len(changed)} topics.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/topics/add", methods=["POST"])
@require_auth
def add_topic():
    """Add a topic the site follows."""
    admin_settings = _services()
    try:
        topic_id = admin_settings.add_topic(
            request.form.get("topic_id", ""),
            request.form.get("display_name", ""),
            request.form.get("description", ""),
            request.form.get("color", "blue"),
            request.form.get("query", ""),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not add the topic: %s", e)
        flash(f"Could not add the topic: {e}", "error")
        return redirect(url_for("admin.settings"))

    flash(f"Added the topic {topic_id}.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/topics/delete", methods=["POST"])
@require_auth
def delete_topic():
    """Remove a topic, and the source references that pointed at it."""
    admin_settings = _services()
    topic_id = request.form.get("topic_id", "").strip()
    if not topic_id:
        flash("No topic was named.", "error")
        return redirect(url_for("admin.settings"))

    try:
        touched = admin_settings.remove_topic(topic_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not remove the topic: %s", e)
        flash(f"Could not remove the topic: {e}", "error")
        return redirect(url_for("admin.settings"))

    if touched:
        flash(
            f"Removed the topic {topic_id}, and took it off {len(touched)} source(s): "
            f"{', '.join(touched)}.",
            "success",
        )
    else:
        flash(f"Removed the topic {topic_id}.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/schedule", methods=["POST"])
@require_auth
def update_schedule():
    """Change how often the pipeline runs."""
    admin_settings = _services()
    values: dict[str, int] = {}
    for name, _label, _low, _high in admin_settings.SCHEDULE_FIELDS:
        raw = request.form.get(name)
        if raw is None or not raw.strip():
            continue
        values[name] = raw.strip()

    if not values:
        flash("Nothing to save.", "warning")
        return redirect(url_for("admin.settings"))

    try:
        changed = admin_settings.update_schedule(values)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update the schedule: %s", e)
        flash(f"Could not update the schedule: {e}", "error")
        return redirect(url_for("admin.settings"))

    flash(f"Updated the schedule: {', '.join(changed)}.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/review", methods=["POST"])
@require_auth
def update_review():
    """Change the review behaviour, including auto-review mode."""
    admin_settings = _services()

    threshold_raw = request.form.get("auto_publish_threshold", "").strip()
    clear_threshold = not threshold_raw
    threshold: int | None = None
    if threshold_raw:
        try:
            threshold = int(threshold_raw)
        except ValueError:
            flash("The auto-publish threshold must be a whole number.", "error")
            return redirect(url_for("admin.settings"))

    try:
        changed = admin_settings.update_review(
            enabled=bool(request.form.get("review_enabled")),
            auto_approve=bool(request.form.get("auto_approve")),
            auto_publish_threshold=threshold,
            clear_threshold=clear_threshold,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update the review settings: %s", e)
        flash(f"Could not update the review settings: {e}", "error")
        return redirect(url_for("admin.settings"))

    flash(f"Updated the review settings: {', '.join(changed)}.", "success")
    return redirect(url_for("admin.settings"))
