"""Private worker authentication and lease operations."""
from __future__ import annotations

import hashlib
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from typing import cast

from flask import current_app, request
from sqlalchemy import update

from extensions import db
from models import NarrationJob, TTSWorkerCredential
from .jobs import target_tts_enabled


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _retry_budget() -> int:
    from services.tts.settings import value
    return max(1, min(int(value("retry_budget", 5)), 10))


def authenticate_worker() -> bool:
    if not (target_tts_enabled("article") or target_tts_enabled("edition")):
        return False
    try:
        address = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    from urllib.parse import urlsplit
    host = urlsplit(f"//{request.host}").hostname
    loopback_host = host in {"localhost", "127.0.0.1", "::1"}
    loopback_http = bool(current_app.config.get("TTS_ALLOW_LOOPBACK_HTTP", True) and
        (address.is_loopback or (address.is_private and loopback_host)))
    if not request.is_secure and not loopback_http:
        return False
    allowed_cidrs = [part.strip() for part in str(current_app.config.get("TTS_ALLOWED_WORKER_CIDRS", "")).split(",") if part.strip()]
    cidr_allowed = False
    for cidr in allowed_cidrs:
        try:
            cidr_allowed = cidr_allowed or address in ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
    if not (address.is_private or address.is_loopback or address.is_link_local or cidr_allowed):
        return False
    supplied = request.headers.get("Authorization", "")
    if not supplied.startswith("Bearer "):
        return False
    secret = supplied[7:].strip()
    if len(secret) < 32 or len(secret) > 256:
        return False
    hashed = hashlib.sha256(secret.encode()).hexdigest()
    credential = TTSWorkerCredential.query.filter_by(secret_hash=hashed, enabled=True, revoked_at=None).first()
    if credential is not None:
        credential.last_used_at = _now()
        db.session.commit()
    return credential is not None


def claim_next() -> dict | None:
    enabled_kinds = [kind for kind in ("article", "edition") if target_tts_enabled(kind)]
    if not enabled_kinds:
        return None
    now = _now()
    import json
    from services.tts.jobs import _recipe
    normal_recipe = _recipe()
    preview_recipe = {**normal_recipe, "admin_preview": True}
    recipe_hashes = [hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                     for recipe in (normal_recipe, preview_recipe)]
    NarrationJob.query.filter(NarrationJob.state == "pending", NarrationJob.recipe_sha256.notin_(recipe_hashes)).update(
        {"state": "cancelled", "error_code": "recipe_changed", "updated_at": now}, synchronize_session=False)
    db.session.commit()
    candidate = NarrationJob.query.filter(NarrationJob.state == "pending", NarrationJob.target_kind.in_(enabled_kinds),
        NarrationJob.recipe_sha256.in_(recipe_hashes),
        NarrationJob.eligible_at <= now).order_by(
        NarrationJob.eligible_at, NarrationJob.id).first()
    if candidate is None:
        return None
    token = secrets.token_urlsafe(32)
    result = db.session.execute(update(NarrationJob).where(NarrationJob.id == candidate.id,
        NarrationJob.state == "pending").values(state="claimed", claim_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        claim_deadline=now + timedelta(minutes=10), heartbeat_at=now, attempt_count=NarrationJob.attempt_count + 1,
        updated_at=now))
    db.session.commit()
    if not int(getattr(result, "rowcount", 0) or 0):
        return None
    return {"job_id": candidate.id, "claim_token": token, "target_kind": candidate.target_kind,
            "script": candidate.script, "script_sha256": candidate.script_sha256,
            "recipe": candidate.recipe, "source_revision": candidate.source_revision}


def owns_claim(job: NarrationJob, token: str) -> bool:
    hashed = hashlib.sha256(token.encode()).hexdigest()
    return bool(job.state in {"claimed", "encoding"} and job.claim_token_hash and
                secrets.compare_digest(job.claim_token_hash, hashed) and job.claim_deadline and job.claim_deadline >= _now())


def target_still_current(job: NarrationJob) -> bool:
    from models import Article, NewsletterEdition
    from services.tts.jobs import _target
    model = Article if job.target_kind == "article" else NewsletterEdition
    target = cast(Article | NewsletterEdition | None, db.session.get(model, job.target_id))
    identity = _target(job.target_kind, target) if target else None
    return bool(identity and identity == (job.target_public_id, job.source_revision))


def recipe_still_current(job: NarrationJob) -> bool:
    import json
    from services.tts.jobs import _recipe
    recipe = _recipe()
    if job.recipe.get("admin_preview"):
        recipe["admin_preview"] = True
    expected = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return secrets.compare_digest(job.recipe_sha256, expected)


def recover_expired_claims() -> int:
    now = _now()
    retry_budget = _retry_budget()
    result = db.session.execute(update(NarrationJob).where(NarrationJob.state.in_(["claimed", "encoding"]),
        NarrationJob.claim_deadline < now, NarrationJob.attempt_count < retry_budget).values(state="pending", claim_token_hash=None,
        claim_deadline=None, eligible_at=now, error_code="lease_expired", updated_at=now))
    count = int(getattr(result, "rowcount", 0) or 0)
    exhausted = db.session.execute(update(NarrationJob).where(NarrationJob.state.in_(["claimed", "encoding"]),
        NarrationJob.claim_deadline < now, NarrationJob.attempt_count >= retry_budget).values(state="failed", claim_token_hash=None,
        claim_deadline=None, error_code="retry_limit", updated_at=now))
    db.session.commit()
    return count + int(getattr(exhausted, "rowcount", 0) or 0)
