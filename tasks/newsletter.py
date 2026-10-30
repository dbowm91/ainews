from datetime import datetime, timezone

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from services.task_security import verify_invocation, verify_task
from constants import CELERY_TASK_MAX_RETRIES

logger = get_task_logger(__name__)


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, max_retries=CELERY_TASK_MAX_RETRIES, retry_backoff=True)
def generate_edition(self, profile_key: str, occurrence_key: str) -> dict:
    """Publish a frozen edition; transport is planned separately."""
    from services.newsletter_editions import create_edition
    if not isinstance(profile_key, str) or len(profile_key) > 80 or not isinstance(occurrence_key, str) or len(occurrence_key) > 160:
        raise ValueError("Invalid edition occurrence")
    from extensions import db
    from models import NewsletterProfile, ScheduledOccurrence
    from sqlalchemy import select
    profile = db.session.scalar(select(NewsletterProfile).where(NewsletterProfile.key == profile_key))
    occurrence = db.session.scalar(select(ScheduledOccurrence).where(ScheduledOccurrence.occurrence_key == occurrence_key))
    if occurrence is not None and (profile is None or not profile.enabled):
        occurrence.state = "skipped"
        db.session.commit()
        return {"status": "skipped", "reason": "profile_disabled", "profile": profile_key}
    edition = create_edition(profile_key, occurrence_key=occurrence_key)
    if edition is None:
        if occurrence is not None:
            occurrence.state = "skipped"
            db.session.commit()
        return {"status": "skipped", "reason": "no_eligible_articles", "profile": profile_key}
    if occurrence is not None:
        occurrence.state = "completed"
        db.session.commit()
    from services.distribution.dispatch import plan_edition_deliveries
    from tasks.distribution import deliver_newsletter_intent
    from extensions import db
    from models import DeliveryIntent
    queued = plan_edition_deliveries(edition.id)
    intent_ids = db.session.scalars(select(DeliveryIntent.id).where(
        DeliveryIntent.edition_id == edition.id, DeliveryIntent.state == "pending")).all()
    for intent_id in intent_ids:
        deliver_newsletter_intent.apply_async(args=[intent_id])
    return {"status": edition.status, "public_id": edition.public_id, "profile": profile_key, "item_count": len(edition.items), "delivery_intents": queued}


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True)
def newsletter_slot_tick(self) -> dict:
    """Queue due occurrence IDs; duplicate task dispatches are edition-idempotent."""
    from services.newsletter_scheduler import plan_due_occurrences
    rows = plan_due_occurrences()
    queued = 0
    for row in rows:
        if row.state not in {"queued", "dispatched"}:
            continue
        generate_edition.apply_async(args=[row.profile.key, row.occurrence_key])
        row.state = "dispatched"
        row.dispatched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        from extensions import db
        db.session.commit()
        queued += 1
    return {"queued": queued}

# Error response convention:
# - Leaf tasks (e.g., send_single_email): re-raise for Celery retry
# - Pipeline stages: re-raise for Celery retry
# - Orchestration tasks (generate_daily_newsletters): return error dict


def _fetch_articles_for_newsletter(
    topic_key: str,
    cutoff: datetime,
    max_articles: int,
) -> list:
    from models import Article

    q = Article.query.filter(
        Article.publicly_visible.is_(True), Article.final_article.is_not(None), Article.final_article != "",
        Article.created_at >= cutoff,
    )
    if topic_key == "main":
        q = q.filter(Article.impact_score > 0)
    else:
        q = q.filter(Article.category == topic_key)
    return q.order_by(Article.impact_score.desc()).limit(max_articles).all()  # type: ignore[no-any-return]


def _generate_topic_newsletter_impl(
    topic_key: str,
    articles: list,
    site_url: str,
    max_articles: int,
    dry_run_email: str | None,
    nl,
) -> dict:
    """Compatibility wrapper that persists an edition without sending email."""
    from services.newsletter_editions import create_edition

    if dry_run_email:
        return {"type": topic_key, "articles": len(articles), "sent": 0, "preview": True}
    edition = create_edition(topic_key, articles, occurrence_key=f"manual:compat:{topic_key}:{datetime.now(timezone.utc).isoformat()}")
    if edition is None:
        return {"type": topic_key, "articles": 0, "sent": 0, "skipped": True}
    return {"type": topic_key, "articles": len(edition.items), "sent": 0, "public_id": edition.public_id}

def _generate_newsletters_impl(task_id, dry_run_email, run_id):
    """Generate independent frozen editions; never send mail from this task."""
    from extensions import db
    from models import PipelineRun
    from schemas.topic import load_topics
    from services.newsletter_editions import create_edition, ensure_profile, select_articles

    is_preview = bool(dry_run_email)
    profiles = [ensure_profile("main", title="AInews")]
    profiles.extend(ensure_profile(key, title=topic.display_name) for key, topic in load_topics().topics.items())
    results = []
    for profile in profiles:
        if not profile.enabled:
            continue
        articles = select_articles(profile.key, limit=profile.max_articles)
        if is_preview:
            results.append({"type": profile.key, "articles": len(articles), "preview": True, "sent": 0})
            continue
        edition = create_edition(profile.key, articles, occurrence_key=f"manual:{task_id}:{profile.key}")
        if edition is not None:
            results.append({"type": profile.key, "public_id": edition.public_id, "articles": len(edition.items), "sent": 0})
    if run_id is None:
        run = PipelineRun(task_id=task_id, run_type="newsletter", status="completed", triggered_by="manual" if is_preview else "scheduled",
                          finished_at=datetime.now(timezone.utc))
        db.session.add(run)
    else:
        run = db.session.get(PipelineRun, run_id)
        if run:
            run.status = "completed"
            run.finished_at = datetime.now(timezone.utc)
    db.session.commit()
    return results


def _generate_daily_newsletters_core(task_id, dry_run_email, run_id):
    """Occurrence-keyed publication supersedes the old Redis once-per-day lock."""
    try:
        return _generate_newsletters_impl(task_id, dry_run_email, run_id)
    except Exception:
        from extensions import db
        from models import PipelineRun

        db.session.rollback()
        if run_id is not None:
            run = db.session.get(PipelineRun, run_id)
            if run:
                run.status = "failed"
                run.finished_at = datetime.now(timezone.utc)
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
        raise


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    soft_time_limit=300,
    time_limit=360,
)
def generate_daily_newsletters(self, dry_run_email=None, run_id=None, _signature=None, task_name=None):
    try:
        from schemas.tasks import GenerateNewsletterTask
        validated = GenerateNewsletterTask(dry_run_email=dry_run_email, run_id=run_id)
    except Exception as e:
        logger.warning("Invalid generate_daily_newsletters input: %s", e)
        raise TypeError(f"Invalid generate_daily_newsletters input: {e}") from e

    # The signature covers the arguments this task was called with, so it
    # is verified against the invocation rather than against a rebuilt
    # dict of the task's own defaults.
    if not verify_invocation("generate_daily_newsletters", self.request):
        logger.error("Invalid signature for generate_daily_newsletters task")
        raise ValueError("Invalid task signature")

    dry_run_email = validated.dry_run_email
    run_id = validated.run_id

    task_id = self.request.id or "manual"
    return _generate_daily_newsletters_core(task_id, dry_run_email, run_id)


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
)
def retry_failed_newsletter_deliveries(self):
    """Queue only persisted due recipient intents; never replay a population."""
    if not verify_task("retry_failed_newsletter_deliveries", (), {}):
        logger.error("Invalid signature for retry_failed_newsletter_deliveries")
        raise ValueError("Invalid task signature")

    from datetime import datetime, timezone
    from sqlalchemy import select, or_
    from extensions import db
    from models import DeliveryIntent
    from tasks.distribution import deliver_newsletter_intent, reconcile_newsletter_deliveries
    reconcile_newsletter_deliveries.delay()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ids = db.session.scalars(select(DeliveryIntent.id).where(
        DeliveryIntent.state == "failed", DeliveryIntent.attempt_count < 5,
        or_(DeliveryIntent.next_attempt_at.is_(None), DeliveryIntent.next_attempt_at <= now)
    ).order_by(DeliveryIntent.id).limit(100)).all()
    for intent_id in ids:
        deliver_newsletter_intent.apply_async(args=[intent_id])
    return {"queued_intents": len(ids), "sent": 0}
