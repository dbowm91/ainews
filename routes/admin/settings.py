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
import json

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from datetime import datetime, timezone
import hashlib
import secrets
import re
from sqlalchemy import func
from extensions import db
from models import NarrationJob, TTSWorkerCredential

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
    from services.tts.settings import get_settings
    tts_settings = get_settings()
    tts_counts = dict(db.session.query(NarrationJob.state, func.count(NarrationJob.id)).group_by(NarrationJob.state).all())
    worker_last_seen = db.session.query(func.max(TTSWorkerCredential.last_used_at)).filter_by(enabled=True, revoked_at=None).scalar()
    tts_credentials = TTSWorkerCredential.query.order_by(TTSWorkerCredential.created_at.desc()).all()
    tts_recent_jobs = NarrationJob.query.order_by(NarrationJob.updated_at.desc()).limit(25).all()

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
        tts_settings=tts_settings, tts_counts=tts_counts, tts_credentials=tts_credentials, tts_recent_jobs=tts_recent_jobs,
        tts_worker_online=bool(worker_last_seen and (datetime.now(timezone.utc).replace(tzinfo=None) - worker_last_seen).total_seconds() < 180),
    )


@admin_bp.route("/settings/tts", methods=["POST"])
@require_auth
def update_tts_settings():
    from services.tts.settings import save_settings
    instruction = request.form.get("instruction", "").strip()
    backend = request.form.get("backend", "mlx-breeze").strip()
    try:
        cfg_scale = float(request.form.get("cfg_scale", "4"))
        bitrate = int(request.form.get("opus_bitrate", "40"))
        max_minutes = int(request.form.get("max_minutes", "30"))
        max_chars = int(request.form.get("max_chars", "16000"))
        max_pending = int(request.form.get("max_pending_jobs", "500"))
        retries = int(request.form.get("retry_budget", "5"))
        retention = int(request.form.get("retention_days", "30"))
        if backend != "mlx-breeze" or not 0 <= cfg_scale <= 20 or not 24 <= bitrate <= 96 or not 1 <= max_minutes <= 30:
            raise ValueError("Unsupported backend or out-of-range speech settings.")
        model_id = request.form.get("model", "").strip()
        if model_id != "mlx-community/Breeze-TTS-2-mlx-4bit":
            raise ValueError("Only the operator-approved Breeze 4-bit checkpoint is currently supported.")
        accepted = bool(request.form.get("license_accepted"))
        if request.form.get("enabled") and not accepted:
            raise ValueError("Confirm the Breeze research/non-commercial license before enabling TTS.")
        checkpoint_revision = request.form.get("checkpoint_revision", "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", checkpoint_revision):
            raise ValueError("Checkpoint revision must be a full 40-character commit hash.")
        if not 500 <= max_chars <= 16000 or not 1 <= max_pending <= 10000 or not 1 <= retries <= 10 or not 1 <= retention <= 365:
            raise ValueError("One or more TTS limits are outside the allowed range.")
        if not instruction or len(instruction) > 1000 or any(ord(c) < 32 and c not in "\t" for c in instruction):
            raise ValueError("Voice instruction must be plain text up to 1000 characters.")
        aliases_raw = request.form.get("pronunciation_aliases", "")
        aliases = json.loads(aliases_raw) if aliases_raw.strip() else {"AI": "A I", "LLM": "L L M", "GPU": "G P U", "API": "A P I"}
        if not isinstance(aliases, dict) or len(aliases) > 50:
            raise ValueError("Pronunciation aliases must be a JSON object with at most 50 entries.")
        for source, spoken in aliases.items():
            if not isinstance(source, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,31}", source):
                raise ValueError("Pronunciation alias keys must be short alphanumeric tokens.")
            if not isinstance(spoken, str) or not re.fullmatch(r"[A-Za-z0-9 .,'-]{1,64}", spoken):
                raise ValueError("Pronunciation alias values must contain plain spoken text only.")
        saved = save_settings({"enabled": bool(request.form.get("enabled")), "articles_enabled": bool(request.form.get("articles_enabled")),
            "editions_enabled": bool(request.form.get("editions_enabled")), "backfill_enabled": bool(request.form.get("backfill_enabled")),
            "backend": backend, "model": model_id,
            "checkpoint_revision": checkpoint_revision, "instruction": instruction,
            "pronunciation_aliases": aliases,
            "cfg_scale": cfg_scale, "opus_bitrate": bitrate, "max_minutes": max_minutes, "max_chars": max_chars,
            "max_pending_jobs": max_pending, "retry_budget": retries, "retention_days": retention, "license_accepted": accepted})
        try:
            from services.audit import log_admin_action
            log_admin_action("tts_settings_update", target_type="tts_settings", target_id=1,
                details={"enabled": saved.enabled, "articles_enabled": saved.articles_enabled,
                         "editions_enabled": saved.editions_enabled, "profile_revision": saved.profile_revision}, category="config")
        except Exception:  # noqa: BLE001 - audit write failures must not undo operator changes
            logger.warning("Failed to audit TTS settings update", exc_info=True)
        flash("TTS settings saved. Existing jobs retain their recipe snapshot.", "success")
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.settings", _anchor="tts"))


@admin_bp.route("/settings/tts/worker-token", methods=["POST"])
@require_auth
def issue_tts_worker_token():
    secret = secrets.token_urlsafe(40)
    db.session.add(TTSWorkerCredential(label=(request.form.get("label") or "native worker")[:120],
        secret_hash=hashlib.sha256(secret.encode()).hexdigest()))
    db.session.commit()
    try:
        from services.audit import log_admin_action
        log_admin_action("tts_worker_credential_issue", target_type="tts_worker", target_id=None, category="config")
    except Exception:  # noqa: BLE001 - audit write failures must not undo credential issuance
        logger.warning("Failed to audit TTS credential issuance", exc_info=True)
    flash("Worker credential created. Copy it now; its value will not be shown again.", "success")
    return render_template("admin/tts_token.html", secret=secret)


@admin_bp.route("/settings/tts/worker-token/<int:credential_id>/revoke", methods=["POST"])
@require_auth
def revoke_tts_worker_token(credential_id: int):
    credential = db.session.get(TTSWorkerCredential, credential_id)
    if credential:
        credential.enabled = False
        credential.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        try:
            from services.audit import log_admin_action
            log_admin_action("tts_worker_credential_revoke", target_type="tts_worker", target_id=credential_id, category="config")
        except Exception:  # noqa: BLE001 - audit write failures must not undo revocation
            logger.warning("Failed to audit TTS credential revocation", exc_info=True)
    return redirect(url_for("admin.settings", _anchor="tts"))


@admin_bp.route("/settings/tts/jobs/<int:job_id>/action", methods=["POST"])
@require_auth
def tts_job_action(job_id: int):
    from services.tts.worker_protocol import recipe_still_current, target_still_current
    job = db.session.get(NarrationJob, job_id)
    action = request.form.get("action", "")
    if job is None:
        flash("Narration job not found.", "error")
    elif action == "cancel" and job.state in {"pending", "claimed", "encoding"}:
        job.state = "cancelled"; job.claim_token_hash = None; job.claim_deadline = None
        db.session.commit(); _audit_tts_action("tts_job_cancel", job.id); flash("Narration job cancelled.", "success")
    elif action == "retry" and job.state in {"failed", "cancelled"}:
        job.state = "pending"; job.error_code = None; job.claim_token_hash = None; job.claim_deadline = None; job.attempt_count = 0
        db.session.commit(); _audit_tts_action("tts_job_retry", job.id); flash("Narration job queued for retry.", "success")
    elif action == "regenerate" and job.state == "ready" and recipe_still_current(job) and target_still_current(job):
        old_key = job.storage_key
        job.state = "pending"; job.claim_token_hash = None; job.claim_deadline = None; job.error_code = None
        job.storage_key = None; job.audio_sha256 = None; job.duration_seconds = None; job.channels = None
        job.sample_rate = None; job.codec = None; job.byte_size = None; job.ready_at = None
        db.session.commit()
        if old_key:
            from services.tts.storage import get_audio_path
            old_path = get_audio_path(old_key)
            if old_path:
                old_path.unlink(missing_ok=True)
        _audit_tts_action("tts_job_regenerate", job.id)
        try:
            from services.publication import invalidate_publication_cache
            invalidate_publication_cache()
        except Exception:  # noqa: BLE001 - public player caches expire if Redis is unavailable
            logger.warning("Could not invalidate public cache after narration regeneration", exc_info=True)
        flash("Narration regeneration queued.", "success")
    else:
        flash("That action is not valid for the job's current state.", "error")
    return redirect(url_for("admin.settings", _anchor="tts"))


def _audit_tts_action(action: str, target_id: int) -> None:
    try:
        from services.audit import log_admin_action
        log_admin_action(action, target_type="narration_job", target_id=target_id, category="config")
    except Exception:  # noqa: BLE001 - audit failures must not block admin actions
        logger.warning("Failed to audit narration job action", exc_info=True)


@admin_bp.route("/settings/tts/backfill", methods=["POST"])
@require_auth
def tts_backfill():
    from services.tts.settings import value
    from services.tts.jobs import ensure_narration_job_for_published
    from models import Article, NewsletterEdition
    from sqlalchemy import select
    kind = request.form.get("kind", "article")
    limit = request.form.get("limit", type=int) or 0
    offset = request.form.get("offset", type=int) or 0
    cap = int(value("max_pending_jobs", 500))
    if not value("backfill_enabled", False) or kind not in {"article", "edition"} or not 1 <= limit <= min(cap, 100) or not 0 <= offset <= 1_000_000:
        flash("Backfill is disabled or the requested batch exceeds the allowed limit.", "error")
        return redirect(url_for("admin.settings", _anchor="tts"))
    model = Article if kind == "article" else NewsletterEdition
    if kind == "article":
        q = select(model).where(model.publicly_visible.is_(True), model.pipeline_status == "done", model.final_article.is_not(None))
    else:
        q = select(model).where(model.status == "published", model.published_at.is_not(None))
    rows = db.session.scalars(q.order_by(model.id.asc()).offset(offset).limit(limit)).all()
    created = 0
    for target in rows:
        try:
            job = ensure_narration_job_for_published(target, kind=kind)
            created += int(job is not None)
        except Exception:  # noqa: BLE001 - backfill proceeds for later bounded rows
            db.session.rollback(); logger.warning("TTS backfill failed for target %s", target.id, exc_info=True)
    _audit_tts_action("tts_backfill", 0)
    flash(f"Processed a bounded {kind} batch; {created} eligible narration jobs exist.", "success")
    return redirect(url_for("admin.settings", _anchor="tts"))


@admin_bp.route("/settings/tts/preview", methods=["POST"])
@require_auth
def queue_tts_preview():
    from models import Article
    from services.tts.jobs import queue_voice_preview
    article = Article.query.filter(Article.publicly_visible.is_(True), Article.pipeline_status == "done",
        Article.final_article.is_not(None)).order_by(Article.published_at.desc()).first()
    job = queue_voice_preview(article) if article is not None else None
    if job is None:
        flash("Enable article narration and select a published article before requesting a voice preview.", "error")
    else:
        _audit_tts_action("tts_voice_preview", job.id)
        flash(f"Private voice preview queued as job #{job.id}.", "success")
    return redirect(url_for("admin.settings", _anchor="tts"))


@admin_bp.route("/settings/tts/preview/<int:job_id>")
@require_auth
def tts_preview_audio(job_id: int):
    from services.tts.storage import verify_stored_asset
    from services.tts.worker_protocol import recipe_still_current, target_still_current
    job = db.session.get(NarrationJob, job_id)
    if (job is None or not job.recipe.get("admin_preview") or job.state != "ready" or
            not recipe_still_current(job) or not target_still_current(job)):
        abort(404)
    path = verify_stored_asset(job)
    if path is None:
        abort(404)
    response = send_file(path, mimetype="audio/ogg", conditional=True, etag=job.audio_sha256,
        max_age=0, download_name="ainews-voice-preview.ogg")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = 'inline; filename="ainews-voice-preview.ogg"'
    return response


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
