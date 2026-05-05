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
from extensions import db
from models import Article
from services.circuit_breaker import CircuitOpenError
from services.config_utils import get_config_with_default
from services.llm import (
    get_provider_chain,
    record_provider_failure,
)
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError, RateLimitError
from services.metrics import get_metrics
from services.pipeline_degradation import (
    finalize_article as _finalize,
)
from services.pipeline_failure import handle_stage_failure as _handle_stage_failure
from services.pipeline_monitor import record_stage_result
from services.pipeline_utils import _dispatch_next, _log_pipeline
from services.logging_utils import traced_stage

from services.tracing import TraceContext, generate_trace_id, get_current_trace_id


def _degrade_and_advance(article, failed_stage: str, run_id=None):
    """Advance article to next stage with degraded quality on persistent failure."""
    from extensions import db
    from services.pipeline_degradation import degrade_stage
    from services.pipeline_utils import _log_pipeline

    # Normalize: accept both action names ("write") and status names ("writing")
    from constants import STAGE_STATUS_MAP
    failed_stage = STAGE_STATUS_MAP.get(failed_stage, failed_stage)

    logger.warning(
        f"Degrading article {article.id} from stage '{failed_stage}' (retry_count={article.retry_count})"
    )

    if failed_stage == "select":
        article.selector_result = {
            "selected": True,
            "score": 6,
            "reason": "auto-selected after failure",
        }
        article.pipeline_status = "researching"
        article.retry_count = 0
        article.last_error = None
        db.session.commit()
        _log_pipeline(failed_stage, article.id, run_id, "degraded_to_research")
    elif failed_stage == "research":
        degrade_stage(article, "writing")
        _log_pipeline(failed_stage, article.id, run_id, "degraded_to_write")
    elif failed_stage == "write":
        degrade_stage(article, "editing")
        _log_pipeline(failed_stage, article.id, run_id, "degraded_to_edit")
    elif failed_stage == "edit":
        # Final degradation: finalize with fallback
        _finalize(article.id)
    else:
        logger.error(f"Unknown stage for degradation: {failed_stage}")

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


def _get_failure_reason(e):
    """Map exception to a failure reason string."""
    if isinstance(e, RateLimitError):
        return "rate_limit"
    elif isinstance(e, ProviderTimeoutError):
        return "timeout"
    elif isinstance(e, ProviderServerError):
        return "server_error"
    elif isinstance(e, AuthError):
        return "auth"
    return "unknown"


def _handle_stage_exception(e, stage, article_id, run_id, t0, provider_id, model, trace_id=None):
    """Handle exceptions in run_stage, return appropriate response."""
    if trace_id is None:
        trace_id = get_current_trace_id()
    db.session.rollback()
    if provider_id:
        record_provider_failure(provider_id, model, stage)
    reason = _get_failure_reason(e)
    record_stage_result(stage, success=False, run_id=run_id, reason=reason)
    get_metrics().histogram_observe(
        "pipeline.stage_duration_seconds", time.monotonic() - t0,
        labels={"stage": stage, "success": "false"},
    )
    exc_article = db.session.get(Article, article_id)
    if exc_article and _handle_stage_failure(exc_article, stage, e, run_id=run_id):
        logger.warning("TraceID=%s: %s stage degraded for article %s", trace_id, stage.title(), article_id)
        return {"article_id": article_id, "result": "degraded"}
    if run_id:
        _log_pipeline(run_id, stage, "error", "Article %s: %s", article_id, e, article_id=article_id)
    logger.error("TraceID=%s: %s failed for article %s: %s", trace_id, stage.title(), article_id, e)
    raise


def _setup_request_id(task_self):
    if task_self and hasattr(task_self, "request"):
        headers = getattr(task_self.request, "headers", None) or {}
        req_id = headers.get("request_id") if isinstance(headers, dict) else None
        if req_id:
            from services.logging_utils import set_task_request_id
            set_task_request_id(req_id)


def _handle_disabled(rc, skip_next, run_id, stage, article_id):
    if not rc.enabled:
        if skip_next == "finalize":
            _finalize(article_id)
        else:
            _dispatch_next(article_id, run_id=run_id, next_status=skip_next)
        return True
    return False


def _acquire_stage_resources(rc, task_self, retry_countdown, retry_max, lock_key, task_id):
    """Acquire limiter and stage lock. Returns (limiter, redis_client, lock_acquired)."""
    limiter = _check_stage_limiter(rc, task_self, retry_countdown, retry_max)
    from extensions import get_redis
    redis_client = get_redis()
    lock_acquired = _acquire_stage_lock(redis_client, lock_key, task_id, rc.timeout_seconds + 120)
    return limiter, redis_client, lock_acquired


def _handle_soft_timeout_module(stage, run_id, t0, article_id):
    trace_id = get_current_trace_id()
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
    logger.warning("TraceID=%s: Soft timeout in %s stage for article %s", trace_id, stage, article_id)


def _handle_circuit_open_module(ce, stage, run_id, t0, article_id):
    trace_id = get_current_trace_id()
    db.session.rollback()
    record_stage_result(stage, success=False, run_id=run_id, reason="circuit_open")
    get_metrics().histogram_observe("pipeline.stage_duration_seconds", time.monotonic() - t0, labels={"stage": stage, "success": "false"})
    exc_article = db.session.get(Article, article_id)
    if exc_article and _handle_stage_failure(exc_article, stage, ce, run_id=run_id):
        logger.warning("TraceID=%s: %s stage degraded for article %s", trace_id, stage.title(), article_id)
        return {"article_id": article_id, "result": "degraded"}
    logger.error("TraceID=%s: %s failed for article %s: no providers available", trace_id, stage.title(), article_id)
    raise


def _run_stage_core(stage, article_id, work_fn, rc, t0, run_id):
    """Execute the core stage logic. Returns (result, provider_id, model) or raises."""
    article = db.session.get(Article, article_id)
    if not article:
        logger.warning("TraceID=%s: Article %s not found", generate_trace_id(), article_id)
        return {"article_id": article_id, "error": "not found"}, None, None
    
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
            return {"article_id": article_id, "error": "pipeline_timeout"}, None, None
    
    provider, model, max_tokens, provider_id = _get_provider_for_stage(stage)
    logger.info("TraceID=%s: Starting %s stage for article %s with provider %s", generate_trace_id(), stage, article_id, provider_id)
    
    with TraceContext(generate_trace_id()):
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
    logger.info("TraceID=%s: Completed %s stage for article %s", generate_trace_id(), stage, article_id)
    return result, provider_id, model


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
    from schemas.pipeline import get_role_config
    _setup_request_id(task_self)
    trace_id = generate_trace_id()
    rc = get_role_config(stage)
    
    if _handle_disabled(rc, skip_next, run_id, stage, article_id):
        logger.info("TraceID=%s: Stage %s disabled for article %s, skipping", trace_id, stage, article_id)
        return {"article_id": article_id, "decision": f"skip_{stage}"}
    
    lock_key = f"ainews:stage_lock:{article_id}:{stage}"
    task_id = task_self.request.id or "manual"
    t0 = time.monotonic()
    
    limiter, redis_client, lock_acquired = _acquire_stage_resources(rc, task_self, retry_countdown, retry_max, lock_key, task_id)
    if not lock_acquired:
        if limiter is not None:
            limiter.release(rc.provider, None, rc.timeout_seconds)
        logger.info("TraceID=%s: Stage %s already running for article %s, skipping", trace_id, stage, article_id)
        return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}
    
    model = None
    provider_id = None
    try:
        result, provider_id, model = _run_stage_core(stage, article_id, work_fn, rc, t0, run_id)
        return result
    except SoftTimeLimitExceeded:
        _handle_soft_timeout_module(stage, run_id, t0, article_id)
        raise
    except CircuitOpenError as ce:
        return _handle_circuit_open_module(ce, stage, run_id, t0, article_id)
    except Exception as e:  # noqa: BLE001 - stage exceptions are handled by _handle_stage_exception which logs and returns error dict
        return _handle_stage_exception(e, stage, article_id, run_id, t0, provider_id, model)
    finally:
        if limiter is not None:
            limiter.release(rc.provider, model if model is not None else None, rc.timeout_seconds)
        if redis_client is not None:
            try:
                from services.redis_utils import release_lock
                release_lock(redis_client, lock_key, task_id)
            except redis.exceptions.RedisError as e:
                logger.warning("Failed to release stage lock %s: %s", lock_key, e)
