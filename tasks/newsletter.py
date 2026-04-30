import smtplib
from datetime import datetime, timedelta, timezone

from billiard.exceptions import SoftTimeLimitExceeded
from celery import group, shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from services.task_security import verify_task

logger = get_task_logger(__name__)

# Error response convention:
# - Leaf tasks (e.g., send_single_email): re-raise for Celery retry
# - Pipeline stages: re-raise for Celery retry
# - Orchestration tasks (generate_daily_newsletters): return error dict


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
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
    try:
        from schemas.tasks import SendEmailTask
        validated = SendEmailTask(
            email=email, subject=subject, html=html, unsub_url=unsub_url
        )
    except Exception as e:
        logger.warning("Invalid send_single_email input: %s", e)
        raise TypeError(f"Invalid send_single_email input: {e}") from e

    from services.email import send_newsletter_email

    try:
        send_newsletter_email(validated.email, validated.subject, validated.html, validated.unsub_url)
        return {"email": validated.email, "sent": True}
    except smtplib.SMTPResponseException as e:
        if e.smtp_code >= 500:
            logger.error("Permanent SMTP error sending to %s: %s", validated.email, e)
            return {"email": validated.email, "sent": False, "error": str(e)}
        raise
    except Exception as e:
        logger.error("Failed to send to %s: %s", validated.email, e)
        return {"email": validated.email, "sent": False, "error": str(e)}


def _send_emails_parallel(subscribers_iter, subject, html, site_url):
    """Send emails to subscribers in parallel using Celery group.

    Emails are sent in batches of 500 to reduce Celery task overhead.
    Uses non-blocking apply_async - does not wait for results.

    Args:
        subscribers_iter: Iterator/generator of Subscriber objects (not a list)
        subject: Email subject
        html: Email HTML content
        site_url: Base URL for unsubscribe links

    Returns:
        Total number of subscribers dispatched (approximate, as sending is async)
    """
    BATCH_SIZE = 500

    batch = []
    dispatched = 0
    for sub in subscribers_iter:
        unsub_url = f"{site_url}/unsubscribe/{sub.unsubscribe_token}"
        batch.append(
            send_single_email.s(
                email=sub.email,
                subject=subject,
                html=html,
                unsub_url=unsub_url,
            )
        )
        if len(batch) >= BATCH_SIZE:
            job = group(batch)
            job.apply_async()
            dispatched += len(batch)
            batch = []

    if batch:
        job = group(batch)
        job.apply_async()
        dispatched += len(batch)

    return dispatched


def _fetch_articles_for_newsletter(
    topic_key: str,
    cutoff: datetime,
    max_articles: int,
) -> list:
    from constants import PipelineStatus
    from models import Article

    q = Article.query.filter(
        Article.pipeline_status == PipelineStatus.DONE,
        Article.created_at >= cutoff,
    )
    if topic_key == "main":
        q = q.filter(Article.impact_score > 0)
    else:
        q = q.filter(Article.category == topic_key)
    return q.order_by(Article.impact_score.desc()).limit(max_articles).all()


def _generate_topic_newsletter_impl(
    topic_key: str,
    articles: list,
    site_url: str,
    max_articles: int,
    dry_run_email: str | None,
    nl,
) -> dict:
    from extensions import db
    from models import Newsletter, Subscriber
    from services.email import send_newsletter_email
    from services.newsletter import generate_main_newsletter, generate_topic_newsletter
    from services.newsletter_pipeline import generate_executive_summary

    if not articles:
        return {"type": topic_key, "articles": 0, "sent": 0, "skipped": True}

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

    if topic_key == "main":
        html, subject, count = generate_main_newsletter(
            site_url=site_url,
            max_articles=max_articles,
            executive_summary=exec_summary,
        )
    else:
        html, subject, count = generate_topic_newsletter(
            topic_key=topic_key,
            site_url=site_url,
            max_articles=max_articles,
            executive_summary=exec_summary,
        )

    if not html or not html.strip():
        logger.warning(
            "%s newsletter has empty content after generation, skipping send",
            topic_key,
        )
        return {"type": topic_key, "articles": 0, "skipped": "empty_content"}

    newsletter = Newsletter(
        newsletter_type=topic_key,
        subject=subject,
        html_content=html,
        article_count=count,
    )
    db.session.add(newsletter)
    db.session.flush()

    is_dry_run = bool(dry_run_email)
    sent = 0
    email_error = None
    if is_dry_run:
        unsub_url = f"{site_url}/unsubscribe/test"
        try:
            send_newsletter_email(dry_run_email, subject, html, unsub_url)
            sent = 1
            logger.info("Dry run: sent main newsletter to %s", dry_run_email)
        except Exception as e:
            logger.error("Dry run failed for %s: %s", dry_run_email, e)
            email_error = str(e)
    else:
        base_filters = [
            Subscriber.deleted_at.is_(None),
            Subscriber.confirmed_at.isnot(None),
            Subscriber.newsletter_type == topic_key,
            Subscriber.active.is_(True),
        ]
        subscriber_count = Subscriber.query.filter(*base_filters).count()
        subscriber_query = Subscriber.query.filter(*base_filters).yield_per(500)
        sent = _send_emails_parallel(subscriber_query, subject, html, site_url)
        if sent < subscriber_count and subscriber_count > 0:
            email_error = f"Only {sent} of {subscriber_count} emails sent"

    if email_error:
        db.session.rollback()
        logger.error(
            "%s newsletter failed email delivery: %s",
            topic_key,
            email_error,
        )
        try:
            from services.webhooks import trigger_event
            trigger_event("newsletter.failed", {
                "newsletter_id": newsletter.id,
                "newsletter_type": topic_key,
                "error": str(email_error),
            })
        except Exception as wh_exc:
            logger.warning("Failed to trigger newsletter.failed webhook: %s", wh_exc)
        return {"type": topic_key, "articles": count, "sent": 0, "error": email_error}

    newsletter.recipients = sent
    newsletter.delivered_count = sent if sent > 0 else 0
    newsletter.error_message = email_error
    newsletter.sent_at = datetime.now(timezone.utc) if sent > 0 else None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    result_dict = {
        "type": topic_key,
        "articles": count,
        "sent": sent,
        "delivered": newsletter.delivered_count,
        **pipeline_info,
    }
    if is_dry_run:
        result_dict["dry_run"] = True
    logger.info(
        "%s newsletter: %s (%d articles, %d sent, dry_run=%s)",
        topic_key,
        subject,
        count,
        sent,
        is_dry_run,
    )

    try:
        from services.webhooks import trigger_event

        trigger_event(
            "newsletter.sent",
            {
                "newsletter_id": newsletter.id,
                "newsletter_type": topic_key,
                "subject": subject,
                "article_count": count,
                "sent_count": sent,
            },
            idempotency_key=f"newsletter.sent:{topic_key}:{datetime.now(timezone.utc).date().isoformat()}",
        )
    except Exception:
        logger.warning(
            "Newsletter webhook trigger failed for %s, continuing",
            topic_key,
        )

    return result_dict


def _generate_newsletters_impl(task_self, dry_run_email, run_id):
    """Implementation of newsletter generation logic.

    Newsletter generation is parallelized using Celery group for each
    topic (main + per-topic newsletters). Article fetching happens upfront
    before dispatching parallel tasks.
    """
    from celery import group

    from extensions import db
    from models import PipelineRun
    from schemas.pipeline import load_pipeline_config
    from schemas.topic import load_topics

    config = load_pipeline_config()
    nl = config.newsletter
    site_url = nl.site_url
    topics = load_topics().topics

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    is_dry_run = bool(dry_run_email)

    if run_id is None:
        run = PipelineRun(
            task_id=task_self.request.id,
            run_type="newsletter",
            status="running",
            triggered_by="manual" if is_dry_run else "scheduled",
        )
        db.session.add(run)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        run_id = run.id

    all_topic_keys = ["main"] + list(topics.keys())

    all_articles = {
        topic_key: _fetch_articles_for_newsletter(topic_key, cutoff, nl.max_articles)
        for topic_key in all_topic_keys
    }

    task_signatures = []
    for topic_key in all_topic_keys:
        dry_run = dry_run_email if topic_key == "main" and is_dry_run else None
        task_signatures.append(
            _generate_topic_newsletter_impl.s(
                topic_key,
                all_articles[topic_key],
                site_url,
                nl.max_articles,
                dry_run,
                nl,
            )
        )

    job = group(task_signatures)
    job.apply_async()

    run = db.session.get(PipelineRun, run_id)
    if run:
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

    logger.info("Newsletter generation dispatched for %d topics", len(task_signatures))
    return []


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def generate_daily_newsletters(self, dry_run_email=None, run_id=None):
    try:
        from schemas.tasks import GenerateNewsletterTask
        validated = GenerateNewsletterTask(dry_run_email=dry_run_email, run_id=run_id)
    except Exception as e:
        logger.warning("Invalid generate_daily_newsletters input: %s", e)
        raise TypeError(f"Invalid generate_daily_newsletters input: {e}") from e

    if not verify_task("generate_daily_newsletters", (), {"dry_run_email": validated.dry_run_email, "run_id": validated.run_id}):
        logger.error("Invalid signature for generate_daily_newsletters task")
        raise ValueError("Invalid task signature")

    dry_run_email = validated.dry_run_email
    run_id = validated.run_id

    import redis.exceptions

    from extensions import get_redis

    task_id = self.request.id or "manual"
    lock_key = "ainews:newsletter_lock"
    redis_client = get_redis()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    idempotency_key = f"idempotency:newsletter:{today}"
    if redis_client.exists(idempotency_key):
        logger.info("Newsletter generation already completed today, skipping")
        return {"skipped": True, "reason": "already_generated_today"}

    _NEWSLETTER_LOCK_SCRIPT = """
    local current = redis.call('GET', KEYS[1])
    if current == ARGV[1] then
        redis.call('EXPIRE', KEYS[1], ARGV[2])
        return 1
    elseif not current then
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
        return 2
    else
        return 0
    end
    """
    _newsletter_lock = redis_client.register_script(_NEWSLETTER_LOCK_SCRIPT)

    try:
        lock_status = _newsletter_lock(keys=[lock_key], args=[task_id, 600])
    except redis.exceptions.RedisError:
        logger.error("Redis error during newsletter lock acquisition, cannot proceed")
        raise

    if lock_status == 0:
        logger.info("Newsletter generation already in progress, skipping")
        return {"skipped": True, "reason": "locked"}
    elif lock_status == 1:
        logger.debug("Refreshed existing newsletter lock")
    else:
        logger.debug("Acquired new newsletter lock")

    try:
        result = _generate_newsletters_impl(self, dry_run_email, run_id)
        redis_client.setex(idempotency_key, 86400 * 2, "1")
        return result
    except SoftTimeLimitExceeded:
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
        logger.error("Newsletter generation exceeded soft time limit")
        raise
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
    finally:
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except redis.exceptions.RedisError:
            logger.warning("Failed to release newsletter lock")


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(smtplib.SMTPException, TimeoutError, ConnectionError),
    dont_autoretry_for=(smtplib.SMTPResponseException,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def retry_failed_newsletter_deliveries(self):
    """Re-attempt delivery for newsletters that previously failed.

    Queries Newsletter records with non-null error_message and re-sends
    emails to subscribers using the same delivery logic as send_single_email.

    Runs every 2 hours via Celery Beat.
    """
    if not verify_task("retry_failed_newsletter_deliveries", (), {}):
        logger.error("Invalid signature for retry_failed_newsletter_deliveries")
        raise ValueError("Invalid task signature")

    from extensions import db
    from models import Newsletter, Subscriber
    from schemas.pipeline import load_pipeline_config
    from services.email import send_newsletter_email

    config = load_pipeline_config()
    site_url = config.newsletter.site_url
    failed = (
        Newsletter.query.filter(Newsletter.error_message.isnot(None))
        .order_by(Newsletter.id.desc())
        .limit(100)
        .all()
    )
    if not failed:
        logger.debug("No failed newsletters to retry")
        return {"retried": 0, "sent": 0, "failed": 0}

    sent = 0
    failed_count = 0
    for nl in failed:
        unsub_url = f"{site_url}/unsubscribe/test"
        base_filters = [
            Subscriber.deleted_at.is_(None),
            Subscriber.confirmed_at.isnot(None),
            Subscriber.newsletter_type == nl.newsletter_type,
            Subscriber.active.is_(True),
        ]
        subscribers = Subscriber.query.filter(*base_filters).yield_per(500)
        if not subscribers:
            nl.error_message = None
            db.session.commit()
            continue
        try:
            for sub in subscribers:
                send_newsletter_email(
                    sub.email,
                    nl.subject or "AI News Newsletter",
                    nl.html_content or "",
                    unsub_url,
                )
                sent += 1
            nl.error_message = None
            nl.delivered_count = sent
            db.session.commit()
        except smtplib.SMTPResponseException as e:
            db.session.rollback()
            if e.smtp_code >= 500:
                failed_count += 1
                logger.error(
                    "Permanent SMTP error retrying newsletter %s: %s", nl.id, e
                )
            else:
                raise
        except SoftTimeLimitExceeded:
            db.session.rollback()
            logger.error(
                "retry_failed_newsletter_deliveries exceeded soft time limit"
            )
            raise
        except Exception as e:
            db.session.rollback()
            failed_count += 1
            logger.error("Failed to retry newsletter %s: %s", nl.id, e)

    logger.info(
        "Newsletter retry complete: retried=%d, sent=%d, failed=%d",
        len(failed),
        sent,
        failed_count,
    )
    return {"retried": len(failed), "sent": sent, "failed": failed_count}
