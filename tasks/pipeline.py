"""Shared pipeline helpers used across stage modules."""

import threading
import time

import redis.exceptions
from billiard.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError
from constants import (
    PIPELINE_TIMEOUT_SECONDS,
)

from services.pipeline_degradation import (  # noqa: F401
    degrade_stage as _degrade_and_advance,
    finalize_article as _finalize,
    apply_fallback as _apply_fallback,
    should_route_to_review as _should_route_to_review,
)
from services.pipeline_failure import handle_stage_failure as _handle_stage_failure  # noqa: F401
from services.pipeline_failure import _get_max_total_retries, _get_max_stage_retries  # noqa: F401

logger = get_task_logger(__name__)


def _get_pipeline_timeout_seconds() -> int:
    """Get pipeline hard timeout from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get(
            "PIPELINE_TIMEOUT_SECONDS", PIPELINE_TIMEOUT_SECONDS
        )
    except RuntimeError:
        return PIPELINE_TIMEOUT_SECONDS


_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "selecting": ("tasks.select", "select_article"),
    "selected": ("tasks.research", "research_article"),
    "researching": ("tasks.research", "research_article"),
    "writing": ("tasks.write", "write_article"),
    "written": ("tasks.edit", "edit_article"),
    "editing": ("tasks.edit", "edit_article"),
}

_task_fn_cache: dict[str, tuple] = {}
_task_fn_cache_lock = threading.Lock()


def clear_task_fn_cache() -> None:
    """Clear the task function cache.

    Called after config reload to ensure stale task references are refreshed.
    """
    global _task_fn_cache
    _task_fn_cache = {}


def _dispatch_next(
    article_id: int,
    run_id: int | None = None,
    next_status: str | None = None,
    article=None,
) -> None:
    """Dispatch the next pipeline stage based on article status.

    Looks up the Celery task corresponding to the article's current (or
    provided) pipeline status and calls ``.delay()`` to enqueue it.

    Args:
        article_id: ID of the article to process.
        run_id: Optional pipeline-run ID for log correlation.
        next_status: Override status; if ``None``, uses ``article.pipeline_status``.
        article: Article model instance (used only when *next_status* is ``None``).
    """
    status = next_status or (article.pipeline_status if article else None)
    if not status:
        return
    with _task_fn_cache_lock:
        if status not in _task_fn_cache:
            module_path, task_name = _STAGE_TASKS.get(status, (None, None))
            if module_path:
                import importlib

                module = importlib.import_module(module_path)
                _task_fn_cache[status] = (module, task_name)
            else:
                return
        module, task_name = _task_fn_cache[status]
    task_fn = getattr(module, task_name)
    task_fn.delay(article_id, run_id=run_id)


def _dispatch_for_status(article) -> None:
    """Re-dispatch the task matching the article's current pipeline status.

    Convenience wrapper around :func:`_dispatch_next` that reads the status
    from the article object directly.

    Args:
        article: Article model instance with a populated ``pipeline_status``.
    """
    _dispatch_next(article.id, article=article)


def _log_pipeline(run_id, stage, level, message, *args, article_id=None):
    """Create a PipelineLog entry without committing outer transactions.

    Uses a nested transaction (savepoint) so that a log-write failure does not
    roll back the caller's work.  Fatal-level (``"error"``) log failures are
    re-raised after the failed savepoint is rolled back.

    Args:
        run_id: Pipeline-run ID.
        stage: Pipeline stage name (e.g. ``"select"``, ``"write"``).
        level: Log level — ``"info"``, ``"warning"``, or ``"error"``.
        message: Human-readable log message, optionally with %-format placeholders.
        *args: Positional args for message formatting.
        article_id: Optional article ID for correlation.

    Raises:
        No exceptions are re-raised. Errors are logged and a metric is
        incremented.
    """
    from models import PipelineLog
    from extensions import db
    from services.metrics import get_metrics

    if args:
        message = message % args

    metrics = get_metrics()
    savepoint = db.session.begin_nested()
    try:
        log = PipelineLog(
            run_id=run_id,
            article_id=article_id,
            stage=stage,
            level=level,
            message=message,
        )
        db.session.add(log)
        savepoint.commit()
    except Exception as e:
        savepoint.rollback()
        logger.error("Failed to write pipeline log: %s", e)
        metrics.counter_inc(
            "pipeline.log_write_failed", labels={"stage": stage, "level": level}
        )


def _assign_tags(articles, tag_names: list[str], db):
    """Find or create tags and link them to articles.

    Batches queries to avoid N+1: one SELECT for existing tags, one flush
    for new tags, one SELECT for existing links per article, one INSERT for
    new links per article.

    Args:
        articles: Article instance or list of Article instances to tag.
        tag_names: List of tag name strings (max 10 used, max 64 chars each).
        db: SQLAlchemy database session instance.
    """
    from models import Tag, slugify, article_tags

    if not tag_names:
        return

    if not isinstance(articles, list):
        articles = [articles]

    name_by_slug: dict[str, str] = {}
    for raw in tag_names[:10]:
        name = raw.strip().lower()
        if not name or len(name) > 64:
            continue
        slug = slugify(name)
        name_by_slug.setdefault(slug, name)

    if not name_by_slug:
        return

    slugs = list(name_by_slug.keys())

    existing_tags = Tag.query.filter(Tag.slug.in_(slugs)).all()
    tag_by_slug = {t.slug: t for t in existing_tags}

    for slug, name in name_by_slug.items():
        if slug not in tag_by_slug:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
            tag_by_slug[slug] = tag
    db.session.flush()

    tag_ids = [t.id for t in tag_by_slug.values()]
    article_ids = [a.id for a in articles]

    existing_links = set(
        r[0]
        for r in db.session.execute(
            article_tags.select()
            .where(
                (article_tags.c.article_id.in_(article_ids))
                & (article_tags.c.tag_id.in_(tag_ids))
            )
            .with_only_columns(article_tags.c.tag_id)
        ).all()
    )

    for article in articles:
        for tag in tag_by_slug.values():
            link_key = (article.id, tag.id)
            if link_key not in existing_links:
                db.session.execute(
                    article_tags.insert().values(article_id=article.id, tag_id=tag.id)
                )
                existing_links.add(link_key)


def _acquire_stage_lock(redis_client, lock_key, task_id, timeout_seconds):
    """Acquire a Redis lock, returning (acquired, redis_client)."""
    import redis.exceptions

    try:
        acquired = redis_client.set(lock_key, task_id, nx=True, ex=timeout_seconds)
        return acquired
    except redis.exceptions.RedisError:
        logger.warning("Could not acquire stage lock, proceeding without")
        return True


def _check_stage_limiter(rc, task_self, retry_countdown, retry_max):
    """Acquire limiter slot or raise a retry."""
    from services.limiter import get_limiter

    limiter = get_limiter()
    if not limiter.acquire(rc.provider, rc.model, rc.concurrency, rc.timeout_seconds):
        raise task_self.retry(countdown=retry_countdown, max_retries=retry_max)
    return limiter


def run_stage(
    stage: str,
    article_id: int,
    work_fn,
    task_self,
    run_id=None,
    skip_next: str = "finalize",
    retry_countdown: int = 30,
    retry_max: int = 15,
):
    """Execute a pipeline stage with standard lifecycle management.

    Args:
        stage: Stage name (selector, researcher, writer, editor)
        article_id: Article ID
        work_fn: Callable(article, provider, model, max_tokens) -> dict
                 Returns result dict with stage-specific data
        task_self: The Celery task instance (self) for retry support
        run_id: Optional pipeline run ID
        skip_next: Where to skip to if stage disabled ("finalize" or next status)
        retry_countdown: Seconds between limiter retries
        retry_max: Max limiter retries
    """
    from models import Article
    from extensions import db, get_redis
    from schemas.pipeline import get_role_config
    from services.llm import (
        get_provider_for_role,
        record_provider_success,
        record_provider_failure,
    )
    from services.pipeline_monitor import record_stage_result
    from services.metrics import get_metrics

    rc = get_role_config(stage)
    if not rc.enabled:
        if skip_next == "finalize":
            _finalize(article_id)
        else:
            _dispatch_next(article_id, run_id=run_id, next_status=skip_next)
        return {"article_id": article_id, "decision": f"skip_{stage}"}

    limiter = None
    redis_client = None
    lock_key = f"ainews:stage_lock:{article_id}:{stage}"
    task_id = task_self.request.id or "manual"
    model = None
    provider_id = None
    t0 = time.monotonic()
    try:
        limiter = _check_stage_limiter(rc, task_self, retry_countdown, retry_max)
        redis_client = get_redis()
        lock_acquired = _acquire_stage_lock(
            redis_client, lock_key, task_id, rc.timeout_seconds + 120
        )
        if not lock_acquired:
            logger.info(
                "Stage %s already running for article %s, skipping", stage, article_id
            )
            return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}

        article = db.session.get(Article, article_id)
        if not article:
            return {"article_id": article_id, "error": "not found"}

        provider, model, max_tokens, provider_id = get_provider_for_role(stage)

        result = work_fn(article, provider, model, max_tokens)

        record_provider_success(provider_id, model, tokens_used=max_tokens)
        article.retry_count = 0
        article.last_error = None
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
        record_stage_result(stage, success=True, run_id=run_id)
        get_metrics().histogram_observe(
            "pipeline.stage_duration_seconds",
            time.monotonic() - t0,
            labels={"stage": stage, "success": "true"},
        )

        return result
    except SoftTimeLimitExceeded:
        db.session.rollback()
        record_stage_result(stage, success=False, run_id=run_id)
        get_metrics().histogram_observe(
            "pipeline.stage_duration_seconds",
            time.monotonic() - t0,
            labels={"stage": stage, "success": "false"},
        )
        exc_article = db.session.get(Article, article_id)
        if exc_article:
            exc_article.last_error = "%s: soft time limit exceeded" % stage
        raise
    except Exception as e:
        db.session.rollback()
        record_provider_failure(provider_id or rc.provider, model)
        record_stage_result(stage, success=False, run_id=run_id)
        get_metrics().histogram_observe(
            "pipeline.stage_duration_seconds",
            time.monotonic() - t0,
            labels={"stage": stage, "success": "false"},
        )
        exc_article = db.session.get(Article, article_id)
        if exc_article and _handle_stage_failure(exc_article, stage, e, run_id=run_id):
            return {"article_id": article_id, "result": "degraded"}
        if run_id:
            _log_pipeline(
                run_id,
                stage,
                "error",
                "Article %s: %s",
                article_id,
                e,
                article_id=article_id,
            )
        logger.error("%s failed for article %s: %s", stage.title(), article_id, e)
        raise
    finally:
        if limiter is not None:
            limiter.release(
                rc.provider, model if model is not None else None, rc.timeout_seconds
            )
        if redis_client is not None:
            try:
                from services.redis_utils import release_lock

                release_lock(redis_client, lock_key, task_id)
            except redis.exceptions.RedisError as e:
                logger.warning("Failed to release stage lock %s: %s", lock_key, e)
