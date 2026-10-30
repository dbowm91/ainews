"""Private native-worker protocol and ready-only public audio delivery."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, jsonify, request, send_file
from sqlalchemy import select

from extensions import db, csrf
from models import Article, NewsletterEdition, NarrationJob
from services.tts.jobs import _recipe, target_tts_enabled
from services.tts.storage import store_upload, verify_stored_asset
from services.tts.worker_protocol import authenticate_worker, claim_next, owns_claim, recipe_still_current, target_still_current

logger = logging.getLogger(__name__)
tts_bp = Blueprint("tts", __name__)


def _private_auth():
    if not authenticate_worker():
        abort(401)


def _current_ready(public_id: str) -> NarrationJob | None:
    for kind, model in (("article", Article), ("edition", NewsletterEdition)):
        if not target_tts_enabled(kind):
            continue
        target = db.session.scalar(select(model).where(model.public_id == public_id))
        if target is None:
            continue
        from services.tts.jobs import _target
        identity = _target(kind, target)
        if identity is None:
            continue
        recipe = _recipe()
        recipe_hash = hashlib.sha256(__import__("json").dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        job = db.session.scalar(select(NarrationJob).where(NarrationJob.target_kind == kind,
            NarrationJob.target_id == target.id, NarrationJob.source_revision == identity[1],
            NarrationJob.recipe_sha256 == recipe_hash, NarrationJob.state == "ready"))
        if job and job.target_public_id == public_id and verify_stored_asset(job):
            return job
    return None


@tts_bp.post("/internal/tts/claim")
def claim():
    _private_auth()
    job = claim_next()
    return (jsonify(job), 200) if job else ("", 204)


@tts_bp.post("/internal/tts/<int:job_id>/heartbeat")
def heartbeat(job_id: int):
    _private_auth()
    payload = request.get_json(silent=True) or {}
    job = db.session.get(NarrationJob, job_id)
    if not job or not owns_claim(job, str(payload.get("claim_token", ""))):
        abort(409)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    from datetime import timedelta
    job.state = "encoding"; job.heartbeat_at = now; job.claim_deadline = now + timedelta(minutes=10); job.updated_at = now
    db.session.commit()
    return jsonify({"ok": True})


@tts_bp.post("/internal/tts/<int:job_id>/fail")
def fail(job_id: int):
    _private_auth()
    payload = request.get_json(silent=True) or {}
    job = db.session.get(NarrationJob, job_id)
    if not job or not owns_claim(job, str(payload.get("claim_token", ""))):
        abort(409)
    from services.tts.settings import value
    retry_budget = max(1, min(int(value("retry_budget", 5)), 10))
    job.state = "failed" if job.attempt_count >= retry_budget else "pending"
    job.error_code = str(payload.get("error_code", "worker_failed"))[:64]
    job.claim_token_hash = None; job.claim_deadline = None
    db.session.commit()
    return jsonify({"ok": True})


@tts_bp.post("/internal/tts/<int:job_id>/result")
def result(job_id: int):
    _private_auth()
    request.max_content_length = int(current_app.config.get("TTS_MAX_UPLOAD_BYTES", 24 * 1024 * 1024)) + 4096
    job = db.session.get(NarrationJob, job_id)
    token = request.headers.get("X-TTS-Claim-Token", "")
    if not job or not owns_claim(job, token) or not target_tts_enabled(job.target_kind) or not target_still_current(job) or not recipe_still_current(job):
        abort(409)
    if request.headers.get("X-TTS-Script-SHA256") != job.script_sha256 or request.mimetype != "audio/ogg":
        abort(400)
    try:
        key, path, metadata = store_upload(request.stream)
    except (ValueError, OSError, RuntimeError) as exc:
        return jsonify({"error": str(exc)[:64]}), 400
    if not target_still_current(job) or not recipe_still_current(job) or not owns_claim(job, token):
        path.unlink(missing_ok=True)
        abort(409)
    job.state = "ready"; job.storage_key = key; job.audio_sha256 = metadata["sha256"]
    job.duration_seconds = metadata["duration_seconds"]; job.channels = metadata["channels"]
    job.sample_rate = metadata["sample_rate"]; job.codec = metadata["codec"]; job.byte_size = metadata["byte_size"]
    job.ready_at = datetime.now(timezone.utc).replace(tzinfo=None); job.updated_at = job.ready_at
    job.claim_token_hash = None; job.claim_deadline = None
    try:
        db.session.commit()
    except Exception:
        db.session.rollback(); path.unlink(missing_ok=True); raise
    try:
        from services.publication import invalidate_publication_cache
        invalidate_publication_cache()
    except Exception:
        logger.exception("TTS cache invalidation failed")
    return jsonify({"ready": True, "duration_seconds": metadata["duration_seconds"]})


@tts_bp.route("/audio/<public_id>/<audio_sha256>.ogg", methods=["GET", "HEAD"])
def audio(public_id: str, audio_sha256: str):
    job = _current_ready(public_id)
    if job is None or job.audio_sha256 != audio_sha256:
        abort(404)
    path = verify_stored_asset(job)
    if path is None:
        abort(404)
    response = send_file(path, mimetype="audio/ogg", conditional=True, etag=job.audio_sha256,
        max_age=0, download_name="ainews-narration.ogg")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    response.headers["Content-Disposition"] = 'inline; filename="ainews-narration.ogg"'
    response.headers["Accept-Ranges"] = "bytes"
    return response


csrf.exempt(tts_bp)
