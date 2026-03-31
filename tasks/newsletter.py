from datetime import datetime, timezone, timedelta
import smtplib

from celery import shared_task, group
from celery.utils.log import get_task_logger
from billiard.exceptions import SoftTimeLimitExceeded

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(smtplib.SMTPException, TimeoutError, ConnectionError),
    dont_autoretry_for=(smtplib.SMTPResponseException,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_single_email(
    self, email: str, subject: str, html: str, unsub_url: str
) -> dict:
    """Send a single newsletter email. Called by generate_daily_newsletters.

    Transient SMTP errors (connection failures, timeouts) are automatically
    retried via the Celery autoretry mechanism.  Permanent 5xx SMTP errors
    are not retried.
    """
    from services.email import send_newsletter_email

    try:
        send_newsletter_email(email, subject, html, unsub_url)
        return {"email": email, "sent": True}
    except smtplib.SMTPResponseException as e:
        if e.smtp_code >= 500:
            logger.error("Permanent SMTP error sending to %s: %s", email, e)
            return {"email": email, "sent": False, "error": str(e)}
        # 4xx: re-raise so autoretry_for handles it
        raise
    except Exception as e:
        logger.error("Failed to send to %s: %s", email, e)
        return {"email": email, "sent": False, "error": str(e)}


def _send_emails_parallel(subscribers, subject, html, site_url):
    """Send emails to subscribers in parallel using Celery group.

    Returns the count of successfully sent emails.
    """
    if not subscribers:
        return 0

    # Build email tasks
    email_tasks = []
    for sub in subscribers:
        unsub_url = f"{site_url}/unsubscribe/{sub.unsubscribe_token}"
        email_tasks.append(
            send_single_email.s(
                email=sub.email,
                subject=subject,
                html=html,
                unsub_url=unsub_url,
            )
        )

    # Execute in parallel
    job = group(email_tasks)
    result = job.apply_async()

    try:
        results = result.get(timeout=120, propagate=False)
        sent = sum(1 for r in results if isinstance(r, dict) and r.get("sent"))
        return sent
    except Exception as e:
        logger.error("Error waiting for email results: %s", e)
        # Fallback: count as 0 sent
        return 0


def _generate_newsletters_impl(task_self, dry_run_email, run_id):
    """Implementation of newsletter generation logic."""
    from schemas.pipeline import load_pipeline_config
    from schemas.topic import load_topics
    from services.newsletter import generate_main_newsletter, generate_topic_newsletter
    from services.newsletter_pipeline import generate_executive_summary
    from services.email import send_newsletter_email
    from models import Newsletter, Subscriber, Article, PipelineRun
    from extensions import db
    from constants import PipelineStatus

    config = load_pipeline_config()
    nl = config.newsletter
    site_url = nl.site_url
    topics = load_topics().topics

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    results = []

    is_dry_run = bool(dry_run_email)

    # Create PipelineRun for tracking
    if run_id is None:
        run = PipelineRun(
            task_id=task_self.request.id,
            run_type="newsletter",
            status="running",
            triggered_by="manual" if is_dry_run else "scheduled",
        )
        db.session.add(run)
        db.session.commit()
        run_id = run.id

    # Main newsletter
    try:
        articles = (
            Article.query.filter(
                Article.pipeline_status == PipelineStatus.DONE,
                Article.impact_score > 0,
                Article.created_at >= cutoff,
            )
            .order_by(Article.impact_score.desc())
            .limit(nl.max_articles)
            .all()
        )

        exec_summary = ""
        pipeline_info = {"used_fallback": False, "fallback_stages": []}
        if not articles:
            logger.warning("Main newsletter has 0 articles, skipping send")
            results.append({"type": "main", "articles": 0, "sent": 0, "skipped": True})
        else:
            try:
                result = generate_executive_summary(articles, topic_key="main")
                exec_summary = result["summary"]
                pipeline_info = {
                    "used_fallback": result["used_fallback"],
                    "fallback_stages": result["fallback_stages"],
                }
                if result["used_fallback"]:
                    logger.warning(
                        "Main newsletter pipeline used fallback stages: %s",
                        result["fallback_stages"],
                    )
            except Exception as e:
                logger.error("Main exec summary failed: %s", e)

            html, subject, count = generate_main_newsletter(
                site_url=site_url,
                max_articles=nl.max_articles,
                executive_summary=exec_summary,
            )

            newsletter = Newsletter(
                newsletter_type="main",
                subject=subject,
                html_content=html,
                article_count=count,
            )
            db.session.add(newsletter)
            db.session.flush()

            sent = 0
            if is_dry_run:
                unsub_url = f"{site_url}/unsubscribe/test"
                try:
                    send_newsletter_email(dry_run_email, subject, html, unsub_url)
                    sent = 1
                    logger.info("Dry run: sent main newsletter to %s", dry_run_email)
                except Exception as e:
                    logger.error("Dry run failed for %s: %s", dry_run_email, e)
            else:
                subscribers = (
                    Subscriber.query.filter(Subscriber.deleted_at.is_(None))
                    .filter(Subscriber.confirmed_at.isnot(None))
                    .filter_by(newsletter_type="main", active=True)
                    .all()
                )
                sent = _send_emails_parallel(subscribers, subject, html, site_url)

            newsletter.recipients = sent
            newsletter.sent_at = datetime.now(timezone.utc) if sent > 0 else None
            db.session.commit()
            results.append(
                {
                    "type": "main",
                    "articles": count,
                    "sent": sent,
                    "dry_run": is_dry_run,
                    **pipeline_info,
                }
            )
            logger.info(
                "Main newsletter: %s (%d articles, %d sent, dry_run=%s)",
                subject,
                count,
                sent,
                is_dry_run,
            )
    except Exception as e:
        db.session.rollback()
        logger.error("Main newsletter failed: %s", e)
        results.append({"type": "main", "error": str(e)})

    # Per-topic newsletters (skip in dry run for main only)
    if not is_dry_run:
        for topic_key in topics:
            try:
                articles = (
                    Article.query.filter(
                        Article.pipeline_status == PipelineStatus.DONE,
                        Article.category == topic_key,
                        Article.created_at >= cutoff,
                    )
                    .order_by(Article.impact_score.desc())
                    .limit(nl.max_articles)
                    .all()
                )

                if not articles:
                    results.append({"type": topic_key, "skipped": True})
                    continue

                exec_summary = ""
                pipeline_info = {"used_fallback": False, "fallback_stages": []}
                try:
                    result = generate_executive_summary(articles, topic_key=topic_key)
                    exec_summary = result["summary"]
                    pipeline_info = {
                        "used_fallback": result["used_fallback"],
                        "fallback_stages": result["fallback_stages"],
                    }
                    if result["used_fallback"]:
                        logger.warning(
                            "%s newsletter pipeline used fallback stages: %s",
                            topic_key,
                            result["fallback_stages"],
                        )
                except Exception as e:
                    logger.error("%s exec summary failed: %s", topic_key, e)

                html, subject, count = generate_topic_newsletter(
                    topic_key=topic_key,
                    site_url=site_url,
                    max_articles=nl.max_articles,
                    executive_summary=exec_summary,
                )

                newsletter = Newsletter(
                    newsletter_type=topic_key,
                    subject=subject,
                    html_content=html,
                    article_count=count,
                )
                db.session.add(newsletter)
                db.session.flush()

                subscribers = (
                    Subscriber.query.filter(Subscriber.deleted_at.is_(None))
                    .filter(Subscriber.confirmed_at.isnot(None))
                    .filter_by(newsletter_type=topic_key, active=True)
                    .all()
                )
                sent = _send_emails_parallel(subscribers, subject, html, site_url)

                newsletter.recipients = sent
                newsletter.sent_at = datetime.now(timezone.utc) if sent > 0 else None
                db.session.commit()
                results.append(
                    {
                        "type": topic_key,
                        "articles": count,
                        "sent": sent,
                        **pipeline_info,
                    }
                )
                logger.info(
                    "%s newsletter: %s (%d articles, %d sent)",
                    topic_key,
                    subject,
                    count,
                    sent,
                )
            except Exception as e:
                db.session.rollback()
                logger.error("%s newsletter failed: %s", topic_key, e)
                results.append({"type": topic_key, "error": str(e)})

    # Update run status
    run = db.session.get(PipelineRun, run_id)
    if run:
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()

    logger.info("Newsletter generation complete: %s", results)
    return results


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
)
def generate_daily_newsletters(self, dry_run_email=None, run_id=None):
    from extensions import get_redis

    # Distributed lock to prevent duplicate newsletter generation.
    # Uses task ID so retries from the same task can re-acquire.
    task_id = self.request.id or "manual"
    lock_key = "ainews:newsletter_lock"
    redis_client = get_redis()

    existing = redis_client.get(lock_key)
    if existing and existing.decode() != task_id:
        logger.info(
            "Newsletter generation already in progress (task %s), skipping",
            existing.decode(),
        )
        return {"skipped": True, "reason": "locked"}

    redis_client.set(lock_key, task_id, ex=600)

    try:
        return _generate_newsletters_impl(self, dry_run_email, run_id)
    except SoftTimeLimitExceeded:
        from extensions import db

        db.session.rollback()
        logger.error("Newsletter generation exceeded soft time limit")
        raise
    finally:
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except Exception:
            logger.warning("Failed to release newsletter lock")
