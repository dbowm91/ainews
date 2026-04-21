from datetime import datetime, timezone, timedelta
import smtplib

from celery import shared_task, group
from sqlalchemy.exc import SQLAlchemyError
from celery.utils.log import get_task_logger
from billiard.exceptions import SoftTimeLimitExceeded

logger = get_task_logger(__name__)

# Error response convention:
# - Leaf tasks (e.g., send_single_email): re-raise for Celery retry
# - Pipeline stages: re-raise for Celery retry
# - Orchestration tasks (generate_daily_newsletters): return error dict


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

    Emails are sent in batches of 500 to reduce Celery task overhead.
    Uses non-blocking apply_async - does not wait for results.
    """
    if not subscribers:
        return 0

    BATCH_SIZE = 500

    for i in range(0, len(subscribers), BATCH_SIZE):
        batch = subscribers[i : i + BATCH_SIZE]
        email_tasks = []
        for sub in batch:
            unsub_url = f"{site_url}/unsubscribe/{sub.unsubscribe_token}"
            email_tasks.append(
                send_single_email.s(
                    email=sub.email,
                    subject=subject,
                    html=html,
                    unsub_url=unsub_url,
                )
            )

        job = group(email_tasks)
        job.apply_async()

    return 0


def _fetch_articles_for_newsletter(
    topic_key: str,
    cutoff: datetime,
    max_articles: int,
) -> list:
    from models import Article
    from constants import PipelineStatus

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
    from services.newsletter import generate_main_newsletter, generate_topic_newsletter
    from services.newsletter_pipeline import generate_executive_summary
    from services.email import send_newsletter_email
    from models import Newsletter, Subscriber
    from extensions import db

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
        subscriber_query = (
            Subscriber.query.filter(Subscriber.deleted_at.is_(None))
            .filter(Subscriber.confirmed_at.isnot(None))
            .filter_by(newsletter_type=topic_key, active=True)
        )
        subscriber_list = list(subscriber_query.yield_per(500))
        subscriber_count = len(subscriber_list)
        sent = _send_emails_parallel(subscriber_list, subject, html, site_url)
        if sent < subscriber_count and subscriber_count > 0:
            email_error = f"Only {sent} of {subscriber_count} emails sent"

    if email_error:
        db.session.rollback()
        logger.error(
            "%s newsletter failed email delivery: %s",
            topic_key,
            email_error,
        )
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
    return result_dict


def _generate_newsletters_impl(task_self, dry_run_email, run_id):
    """Implementation of newsletter generation logic.

    Newsletter generation is parallelized using Celery group for each
    topic (main + per-topic newsletters). Article fetching happens upfront
    before dispatching parallel tasks.
    """
    from celery import group

    from schemas.pipeline import load_pipeline_config
    from schemas.topic import load_topics
    from models import PipelineRun
    from extensions import db

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
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
)
def generate_daily_newsletters(self, dry_run_email=None, run_id=None):
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
        lock_status = 2

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
