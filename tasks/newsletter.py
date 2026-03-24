from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def generate_daily_newsletters(self, dry_run_email=None, run_id=None):
    from schemas.pipeline import load_pipeline_config
    from schemas.topic import load_topics
    from services.newsletter import generate_main_newsletter, generate_topic_newsletter
    from services.newsletter_pipeline import generate_executive_summary
    from services.email import send_newsletter_email
    from models import Newsletter, Subscriber, Article, PipelineRun
    from extensions import db

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
            task_id=self.request.id,
            run_type="newsletter",
            status="running",
            triggered_by="manual" if is_dry_run else "scheduled",
        )
        db.session.add(run)
        db.session.commit()
        run_id = run.id

    # Main newsletter
    try:
        articles = Article.query.filter(
            Article.pipeline_status == "done",
            Article.impact_score > 0,
            Article.created_at >= cutoff,
        ).order_by(Article.impact_score.desc()).limit(nl.max_articles).all()

        exec_summary = ""
        if articles:
            try:
                exec_summary = generate_executive_summary(articles, topic_key="main")
            except Exception as e:
                logger.error(f"Main exec summary failed: {e}")

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
                logger.info(f"Dry run: sent main newsletter to {dry_run_email}")
            except Exception as e:
                logger.error(f"Dry run failed for {dry_run_email}: {e}")
        else:
            subscribers = Subscriber.query.filter_by(
                newsletter_type="main", active=True
            ).all()
            for sub in subscribers:
                unsub_url = f"{site_url}/unsubscribe/{sub.unsubscribe_token}"
                try:
                    send_newsletter_email(sub.email, subject, html, unsub_url)
                    sent += 1
                except Exception as e:
                    logger.error(f"Failed to send to {sub.email}: {e}")

        newsletter.recipients = sent
        newsletter.sent_at = datetime.now(timezone.utc) if sent > 0 else None
        db.session.commit()
        results.append({"type": "main", "articles": count, "sent": sent, "dry_run": is_dry_run})
        logger.info(f"Main newsletter: {subject} ({count} articles, {sent} sent, dry_run={is_dry_run})")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Main newsletter failed: {e}")
        results.append({"type": "main", "error": str(e)})

    # Per-topic newsletters (skip in dry run for main only)
    if not is_dry_run:
        for topic_key in topics:
            try:
                articles = Article.query.filter(
                    Article.pipeline_status == "done",
                    Article.category == topic_key,
                    Article.created_at >= cutoff,
                ).order_by(Article.impact_score.desc()).limit(nl.max_articles).all()

                if not articles:
                    results.append({"type": topic_key, "skipped": True})
                    continue

                exec_summary = ""
                try:
                    exec_summary = generate_executive_summary(articles, topic_key=topic_key)
                except Exception as e:
                    logger.error(f"{topic_key} exec summary failed: {e}")

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

                subscribers = Subscriber.query.filter_by(
                    newsletter_type=topic_key, active=True
                ).all()
                sent = 0
                for sub in subscribers:
                    unsub_url = f"{site_url}/unsubscribe/{sub.unsubscribe_token}"
                    try:
                        send_newsletter_email(sub.email, subject, html, unsub_url)
                        sent += 1
                    except Exception as e:
                        logger.error(f"Failed to send to {sub.email}: {e}")

                newsletter.recipients = sent
                newsletter.sent_at = datetime.now(timezone.utc) if sent > 0 else None
                db.session.commit()
                results.append({"type": topic_key, "articles": count, "sent": sent})
                logger.info(f"{topic_key} newsletter: {subject} ({count} articles, {sent} sent)")
            except Exception as e:
                db.session.rollback()
                logger.error(f"{topic_key} newsletter failed: {e}")
                results.append({"type": topic_key, "error": str(e)})

    # Update run status
    run = PipelineRun.query.get(run_id)
    if run:
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()

    logger.info(f"Newsletter generation complete: {results}")
    return results
