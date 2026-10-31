"""Idempotent durable narration job creation and public target eligibility."""
from __future__ import annotations

import json
import logging
from typing import Any, cast

from flask import current_app
from sqlalchemy import func, select

from extensions import db
from models import Article, NewsletterEdition, NewsletterEditionItem, NarrationJob
from services.publication import is_publicly_visible
from .text import RENDERER_VERSION, digest, render_article_script, render_edition_script

DEFAULT_ALIASES = {"AI": "A I", "LLM": "L L M", "GPU": "G P U", "API": "A P I"}
logger = logging.getLogger(__name__)


def tts_enabled() -> bool:
    return bool(current_app.config.get("TTS_ENABLED", False))


def target_tts_enabled(kind: str) -> bool:
    from .settings import value
    archive_enabled = kind != "edition" or bool(current_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False))
    return bool(archive_enabled and value("enabled", tts_enabled()) and value("license_accepted", current_app.config.get("TTS_LICENSE_ACCEPTED", False)) and
        value("articles_enabled" if kind == "article" else "editions_enabled",
        current_app.config.get("TTS_ARTICLES_ENABLED" if kind == "article" else "TTS_EDITIONS_ENABLED", False)))


def _recipe() -> dict[str, Any]:
    from .settings import value
    return {"backend": value("backend", current_app.config.get("TTS_BACKEND", "mlx-breeze")),
            "model": value("model", current_app.config.get("TTS_MODEL", "mlx-community/Breeze-TTS-2-mlx-4bit")),
            "checkpoint_revision": value("checkpoint_revision", current_app.config.get("TTS_CHECKPOINT_REVISION", "3a06d26b172ea4ae1da2f42d708383e9c79d5526")),
            "instruction": value("instruction", current_app.config.get("TTS_INSTRUCTION", "Speak clearly and naturally.")),
            "pronunciation_aliases": value("pronunciation_aliases", DEFAULT_ALIASES) or DEFAULT_ALIASES,
            "cfg_scale": float(value("cfg_scale", current_app.config.get("TTS_CFG_SCALE", 4.0))),
            "opus_bitrate": int(value("opus_bitrate", 40)), "max_minutes": int(value("max_minutes", 30)),
            "max_chars": int(value("max_chars", 16000)),
            "profile_revision": int(value("profile_revision", 1)), "renderer": RENDERER_VERSION}


def _target(kind: str, target: Article | NewsletterEdition) -> tuple[str, str] | None:
    if kind == "article":
        article = target
        if not isinstance(article, Article) or not is_publicly_visible(article) or not article.public_id:
            return None
        source = json.dumps({"final_article": article.final_article or "", "summary": article.summary or ""}, sort_keys=True)
        return article.public_id, digest(source)
    edition = cast(NewsletterEdition, target)
    if not isinstance(edition, NewsletterEdition) or edition.status != "published" or not edition.published_at:
        return None
    frozen = {"subject": edition.subject, "summary": edition.summary or "", "revision": edition.content_revision,
              "items": [{"position": i.position, "headline": i.headline, "why_it_matters": i.why_it_matters,
                         "paragraph": i.paragraph} for i in cast(list[NewsletterEditionItem], edition.items)]}
    return edition.public_id, digest(json.dumps(frozen, ensure_ascii=False, sort_keys=True))


def ensure_narration_job_for_published(target: Article | NewsletterEdition, *, kind: str | None = None) -> NarrationJob | None:
    """Create a job only for an eligible target; callers may safely retry."""
    from .settings import value
    kind = kind or ("article" if isinstance(target, Article) else "edition")
    if not target_tts_enabled(kind):
        return None
    identity = _target(kind, target)
    if identity is None:
        return None
    public_id, revision = identity
    if kind == "article":
        script = render_article_script(target.final_article or "", summary=target.summary or "", max_chars=int(value("max_chars", 16000)), aliases=_recipe()["pronunciation_aliases"])  # type: ignore[union-attr]
        target_id = target.id
    else:
        edition = cast(NewsletterEdition, target)
        script = render_edition_script(edition.subject, edition.summary or "", [
            {"position": i.position, "headline": i.headline, "why_it_matters": i.why_it_matters, "paragraph": i.paragraph}
            for i in cast(list[NewsletterEditionItem], edition.items)], max_chars=int(value("max_chars", 16000)), aliases=_recipe()["pronunciation_aliases"])
        target_id = edition.id
    recipe = _recipe()
    recipe_hash = digest(json.dumps(recipe, sort_keys=True, separators=(",", ":")))
    stmt = select(NarrationJob).where(NarrationJob.target_kind == kind, NarrationJob.target_id == target_id,
        NarrationJob.source_revision == revision, NarrationJob.recipe_sha256 == recipe_hash)
    existing = db.session.scalar(stmt)
    if existing:
        return existing
    pending_limit = int(value("max_pending_jobs", 500))
    pending_count = db.session.scalar(select(func.count(NarrationJob.id)).where(
        NarrationJob.state.in_(["pending", "claimed", "encoding"]))) or 0
    if pending_count >= pending_limit:
        return None
    job = NarrationJob(target_kind=kind, target_id=target_id, target_public_id=public_id,
        source_revision=revision, script=script, script_sha256=digest(script), renderer_version=RENDERER_VERSION,
        recipe=recipe, recipe_sha256=recipe_hash)
    db.session.add(job)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        existing = db.session.scalar(stmt)
        if existing:
            return existing
        raise
    return job


def queue_voice_preview(article: Article) -> NarrationJob | None:
    """Queue a fixed, short administrator-only voice sample on a published article anchor."""
    if not target_tts_enabled("article"):
        return None
    identity = _target("article", article)
    if identity is None:
        return None
    from .settings import value
    recipe = {**_recipe(), "admin_preview": True}
    recipe_hash = digest(json.dumps(recipe, sort_keys=True, separators=(",", ":")))
    stmt = select(NarrationJob).where(NarrationJob.target_kind == "article", NarrationJob.target_id == article.id,
        NarrationJob.source_revision == identity[1], NarrationJob.recipe_sha256 == recipe_hash)
    existing = db.session.scalar(stmt)
    if existing:
        return existing
    pending_limit = int(value("max_pending_jobs", 500))
    pending_count = db.session.scalar(select(func.count(NarrationJob.id)).where(
        NarrationJob.state.in_(["pending", "claimed", "encoding"]))) or 0
    if pending_count >= pending_limit:
        return None
    script = "This is a short AInews narration preview. The voice should sound clear and natural, with a steady pace."
    job = NarrationJob(target_kind="article", target_id=article.id, target_public_id=identity[0],
        source_revision=identity[1], script=script, script_sha256=digest(script),
        renderer_version=RENDERER_VERSION, recipe=recipe, recipe_sha256=recipe_hash)
    db.session.add(job)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        existing = db.session.scalar(stmt)
        if existing:
            return existing
        raise
    return job


def ensure_after_publication(target: Article | NewsletterEdition, *, kind: str | None = None) -> None:
    """Best-effort post-commit hook; narration failures never undo publication."""
    try:
        ensure_narration_job_for_published(target, kind=kind)
    except Exception:  # noqa: BLE001 - publication is already committed
        logger.warning("Could not persist post-publication narration work", exc_info=True)


def ready_audio_url(target: Article | NewsletterEdition, *, kind: str | None = None) -> str | None:
    """Return a public URL only for current, enabled, verified ready audio."""
    kind = kind or ("article" if isinstance(target, Article) else "edition")
    identity = _target(kind, target)
    if not identity or not target_tts_enabled(kind):
        return None
    from services.tts.storage import verify_stored_asset
    recipe_hash = digest(json.dumps(_recipe(), sort_keys=True, separators=(",", ":")))
    job = db.session.scalar(select(NarrationJob).where(NarrationJob.target_kind == kind,
        NarrationJob.target_id == target.id, NarrationJob.source_revision == identity[1],
        NarrationJob.recipe_sha256 == recipe_hash, NarrationJob.state == "ready"))
    if not job or not job.storage_key or not verify_stored_asset(job):
        return None
    from flask import url_for
    return url_for("tts.audio", public_id=identity[0], audio_sha256=job.audio_sha256, _external=True)
