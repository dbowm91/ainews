"""Shared pipeline helpers used across stage modules."""

import time
from datetime import datetime, timezone

import redis.exceptions
from billiard.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import (
    PIPELINE_TIMEOUT_SECONDS,
    PipelineStatus,
)
from services.circuit_breaker import CircuitOpenError
from services.config_utils import get_config_with_default
from services.llm import (
    get_provider_chain,
    record_provider_failure,
)
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError, RateLimitError
from services.pipeline_degradation import (
    degrade_stage as _degrade_and_advance,  # noqa: F401
    finalize_article as _finalize,
)
from services.pipeline_failure import _get_max_stage_retries, _get_max_total_retries  # noqa: F401
from services.pipeline_failure import handle_stage_failure as _handle_stage_failure  # noqa: F401
from services.pipeline_utils import _dispatch_next, _log_pipeline, _task_fn_cache, clear_task_fn_cache  # noqa: F401

logger = get_task_logger(__name__)


def _get_pipeline_timeout_seconds() -> int:
    """Get pipeline hard timeout from Flask config, falling back to default."""
    return get_config_with_default("PIPELINE_TIMEOUT_SECONDS", PIPELINE_TIMEOUT_SECONDS)


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
    from models import Tag, article_tags, slugify

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
                & (article_tags.c.tag_id.in_(tag_ids)),
            )
            .with_only_columns(article_tags.c.tag_id),
        ).all()
    )

    for article in articles:
        for tag in tag_by_slug.values():
            link_key = (article.id, tag.id)
            if link_key not in existing_links:
                db.session.execute(
                    article_tags.insert().values(article_id=article.id, tag_id=tag.id),
                )
                existing_links.add(link_key)


def _acquire_stage_lock(redis_client, lock_key, task_id, timeout_seconds):
    """Acquire a Redis lock, returning (acquired, redis_client)."""
    import redis.exceptions

    try:
        acquired = redis_client.set(lock_key, task_id, nx=True, ex=timeout_seconds)
        return acquired
    except redis.exceptions.RedisError:
        logger.warning("Could not acquire stage lock, Redis unavailable")
        return False


class InvalidStateTransitionError(Exception):
    """Raised when an invalid pipeline status transition is attempted."""

    def __init__(self, article_id: int, from_status: str, to_status: str):
        self.article_id = article_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid pipeline transition for article {article_id}: "
            f"{from_status} -> {to_status}",
        )


def _transition_article_status(article, new_status: str) -> None:
    """Atomically transition an article's pipeline status.

    Validates the transition is allowed before updating. If validation fails,
    raises InvalidStateTransitionError.

    Args:
        article: The Article instance
        new_status: The target status

    Raises:
        InvalidStateTransitionError: If the transition is not valid
    """
    from constants import is_valid_transition

    current = article.pipeline_status
    if not is_valid_transition(current, new_status):
        raise InvalidStateTransitionError(article.id, current, new_status)
    article.pipeline_status = new_status


def _check_stage_limiter(rc, task_self, retry_countdown, retry_max):
    """Acquire limiter slot or raise a retry."""
    from services.limiter import get_limiter

    limiter = get_limiter()
    if not limiter.acquire(rc.provider, rc.model, rc.concurrency, rc.timeout_seconds):
        raise task_self.retry(countdown=retry_countdown, max_retries=retry_max)
    return limiter


def _get_provider_for_stage(stage: str):
    """Get provider with chain fallback."""
    providers = list(get_provider_chain(stage))
    if not providers:
        raise CircuitOpenError(f"All providers failed for stage: {stage}")
    return providers[0]


def _try_stage_work(stage: str, work_fn, article):
    """Try work function with provider chain fallback.

    Iterates through all providers in the chain, trying each one
    until success or exhausts all providers.
    Returns tuple of (result, provider_id_used).
    """
    providers = list(get_provider_chain(stage))
    if not providers:
        raise CircuitOpenError(f"All providers failed for stage: {stage}")

    last_error = None
    for provider, model, max_tokens, provider_id in providers:
        try:
            return work_fn(article, provider, model, max_tokens), provider_id
        except AuthError as auth_err:
            logger.error(
                "Provider %s non-retryable authentication error (%s), abandoning stage",
                provider_id,
                auth_err,
            )
            record_provider_failure(provider_id, model, stage)
            raise auth_err
        except (RateLimitError, ProviderServerError, ProviderTimeoutError) as transient_err:
            logger.warning(
                "Provider %s transient error (%s), trying fallback",
                provider_id,
                transient_err,
            )
            record_provider_failure(provider_id, model, stage)
            last_error = transient_err
            continue

    if last_error:
        raise last_error
    raise CircuitOpenError(f"All providers failed for stage: {stage}")


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
    """Execute a pipeline stage with standard lifecycle management."""
    from extensions import db, get_redis
    from models import Article
    from schemas.pipeline import get_role_config
    from services.logging_utils import set_task_request_id, traced_stage
    from services.metrics import get_metrics
    from services.pipeline_monitor import record_stage_result

    # Nested helpers to reduce complexity
    def _setup_request_id():
        if task_self and hasattr(task_self, "request"):
            headers = getattr(task_self.request, "headers", None) or {}
            req_id = headers.get("request_id") if isinstance(headers, dict) else None
            if req_id:
                set_task_request_id(req_id)

    def _handle_disabled():
        if not rc.enabled:
            if skip_next == "finalize":
                _finalize(article_id)
            else:
                _dispatch_next(article_id, run_id=run_id, next_status=skip_next)
            return True
        return False

    def _acquire_resources():
        nonlocal limiter, redis_client, lock_acquired
        limiter = _check_stage_limiter(rc, task_self, retry_countdown, retry_max)
        redis_client = get_redis()
        lock_acquired = _acquire_stage_lock(
            redis_client, lock_key, task_id, rc.timeout_seconds + 120,
        )
        if not lock_acquired:
            logger.info("Stage %s already running for article %s, skipping", stage, article_id)
            return False
        return True

    def _check_timeout(article):
        if article.pipeline_started_at is not None:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            elapsed = (now_utc - article.pipeline_started_at).total_seconds()
            timeout = _get_pipeline_timeout_seconds()
            if elapsed > timeout:
                logger.error("Article %s exceeded pipeline timeout (%.0fs > %ds), dead-lettering", article_id, elapsed, timeout)
                _transition_article_status(article, PipelineStatus.FAILED)
                article.last_error = "pipeline timeout exceeded (%.0fs)" % elapsed
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    raise
                record_stage_result(stage, success=False, run_id=run_id)
                get_metrics().counter_inc("pipeline.timeout_exceeded", labels={"stage": stage})
                return True
        return False

    def _handle_soft_timeout():
        db.session.rollback()
        record_stage_result(stage, success=False, run_id=run_id, reason="timeout")
        get_metrics().histogram_observe("pipeline.stage_duration_seconds", time.monotonic() - t0, labels={"stage": stage, "success": "false"})
        exc_article = db.session.get(Article, article_id)
        if exc_article:
            exc_article.last_error = f"{stage}: soft time limit exceeded"
            exc_article.retry_count = (exc_article.retry_count or 0) + 1
            exc_article.total_retries = (exc_article.total_retries or 0) + 1
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()

    def _handle_circuit_open(ce):
        db.session.rollback()
        record_stage_result(stage, success=False, run_id=run_id, reason="circuit_open")
        get_metrics().histogram_observe("pipeline.stage_duration_seconds", time.monotonic() - t0, labels={"stage": stage, "success": "false"})
        exc_article = db.session.get(Article, article_id)
        if exc_article and _handle_stage_failure(exc_article, stage, ce, run_id=run_id):
            return {"article_id": article_id, "result": "degraded"}
        logger.error("%s failed for article %s: no providers available", stage.title(), article_id)
        raise

    def _handle_generic_exception(e):
        db.session.rollback()
        if 'provider_id' in dir() and provider_id:
            record_provider_failure(provider_id, model, stage)
        reason = "unknown"
        if isinstance(e, RateLimitError):
            reason = "rate_limit"
        elif isinstance(e, ProviderTimeoutError):
            reason = "timeout"
        elif isinstance(e, ProviderServerError):
            reason = "server_error"
        elif isinstance(e, AuthError):
            reason = "auth"
        record_stage_result(stage, success=False, run_id=run_id, reason=reason)
        get_metrics().histogram_observe("pipeline.stage_duration_seconds", time.monotonic() - t0, labels={"stage": stage, "success": "false"})
        exc_article = db.session.get(Article, article_id)
        if exc_article and _handle_stage_failure(exc_article, stage, e, run_id=run_id):
            return {"article_id": article_id, "result": "degraded"}
        if run_id:
            _log_pipeline(run_id, stage, "error", "Article %s: %s", article_id, e, article_id=article_id)
        logger.error("%s failed for article %s: %s", stage.title(), article_id, e)
        raise

    # Main logic
    _setup_request_id()
    rc = get_role_config(stage)
    if _handle_disabled():
        return {"article_id": article_id, "decision": f"skip_{stage}"}

    limiter = None
    redis_client = None
    lock_key = f"ainews:stage_lock:{article_id}:{stage}"
    task_id = task_self.request.id or "manual"
    model = None
    provider_id = None
    t0 = time.monotonic()
    lock_acquired = False
    try:
        if not _acquire_resources():
            return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}

        article = db.session.get(Article, article_id)
        if not article:
            return {"article_id": article_id, "error": "not found"}

        if _check_timeout(article):
            return {"article_id": article_id, "error": "pipeline_timeout"}

        provider, model, max_tokens, provider_id = _get_provider_for_stage(stage)

        with traced_stage(stage, "work"):
            result, provider_id = _try_stage_work(stage, work_fn, article)

        article.retry_count = 0
        article.last_error = None
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        record_stage_result(stage, success=True, run_id=run_id)
        get_metrics().histogram_observe("pipeline.stage_duration_seconds", time.monotonic() - t0, labels={"stage": stage, "success": "true"})
        return result

    except SoftTimeLimitExceeded:
        _handle_soft_timeout()
        raise
    except CircuitOpenError as ce:
        return _handle_circuit_open(ce)
    except Exception as e:
        return _handle_generic_exception(e)
    finally:
        if limiter is not None:
            limiter.release(rc.provider, model if model is not None else None, rc.timeout_seconds)
        if redis_client is not None:
            try:
                from services.redis_utils import release_lock
                release_lock(redis_client, lock_key, task_id)
            except redis.exceptions.RedisError as e:
                logger.warning("Failed to release stage lock %s: %s", lock_key, e)
