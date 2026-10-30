"""Bounded narration reconciliation; inference is always done by the native worker."""
from datetime import datetime, timedelta, timezone

from celery import shared_task


@shared_task(name="tasks.tts.reconcile_narration_jobs", acks_late=True, soft_time_limit=60, time_limit=90)
def reconcile_narration_jobs(limit: int = 100):
    from sqlalchemy import select
    from extensions import db
    from models import Article, NewsletterEdition, NarrationJob
    from services.tts.jobs import ensure_narration_job_for_published, target_tts_enabled
    from services.tts.worker_protocol import recover_expired_claims

    recovered = recover_expired_claims()
    created = 0
    if target_tts_enabled("article"):
        article_query = select(Article).where(Article.publicly_visible.is_(True), Article.pipeline_status == "done",
            Article.final_article.is_not(None))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
        article_query = article_query.where(Article.published_at >= cutoff)
        rows = db.session.scalars(article_query.order_by(Article.published_at.desc()).limit(max(1, min(limit, 500)))).all()
        for article in rows:
            try:
                before = NarrationJob.query.filter_by(target_kind="article", target_id=article.id).count()
                ensure_narration_job_for_published(article, kind="article")
                created += int(NarrationJob.query.filter_by(target_kind="article", target_id=article.id).count() > before)
            except Exception:  # noqa: BLE001 - one bad target must not stop bounded recovery
                db.session.rollback()
    if target_tts_enabled("edition"):
        edition_query = select(NewsletterEdition).where(NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
        edition_query = edition_query.where(NewsletterEdition.published_at >= cutoff)
        rows = db.session.scalars(edition_query.order_by(NewsletterEdition.published_at.desc()).limit(max(1, min(limit, 500)))).all()
        for edition in rows:
            try:
                before = NarrationJob.query.filter_by(target_kind="edition", target_id=edition.id).count()
                ensure_narration_job_for_published(edition, kind="edition")
                created += int(NarrationJob.query.filter_by(target_kind="edition", target_id=edition.id).count() > before)
            except Exception:  # noqa: BLE001 - one bad target must not stop bounded recovery
                db.session.rollback()
    return {"created": created, "recovered": recovered}


@shared_task(name="tasks.tts.cleanup_tts_storage", acks_late=True, soft_time_limit=120, time_limit=180)
def cleanup_tts_storage():
    from extensions import db
    from models import NarrationJob
    from services.tts.settings import value
    from services.tts.storage import get_audio_path, storage_root
    from services.tts.worker_protocol import recipe_still_current, target_still_current

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    retention_days = max(1, min(int(value("retention_days", 30)), 365))
    cutoff = now - timedelta(days=retention_days)
    jobs = NarrationJob.query.filter(NarrationJob.state == "ready", NarrationJob.storage_key.is_not(None)).all()
    protected: set[str] = set()
    removed = 0
    for job in jobs:
        current = not job.recipe.get("admin_preview") and target_still_current(job) and recipe_still_current(job)
        if current:
            protected.add(job.storage_key)
        elif job.ready_at and job.ready_at < cutoff:
            path = get_audio_path(job.storage_key)
            if path:
                path.unlink(missing_ok=True); removed += 1
            job.state = "cancelled"; job.error_code = "retention_expired"; job.storage_key = None
            job.audio_sha256 = None; job.byte_size = None; job.duration_seconds = None
            job.channels = None; job.sample_rate = None; job.codec = None
            job.updated_at = now
    root = storage_root()
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        age = now.timestamp() - path.stat().st_mtime
        if path.suffix == ".ogg" and path.stem not in protected and age > retention_days * 86400:
            path.unlink(missing_ok=True); removed += 1
        elif path.suffix == ".part" and age > 86400:
            path.unlink(missing_ok=True); removed += 1
    db.session.commit()
    return {"removed_files": removed, "protected_current_assets": len(protected)}
