"""Shared pipeline helpers used across stage modules."""

import json

from billiard.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError
from constants import PipelineStatus, truncate_for_log

logger = get_task_logger(__name__)

MAX_STAGE_RETRIES = 3
MAX_TOTAL_RETRIES = 10


def _get_max_stage_retries() -> int:
    """Get max stage retries from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get("MAX_STAGE_RETRIES", MAX_STAGE_RETRIES)
    except RuntimeError:
        return MAX_STAGE_RETRIES


def _get_max_total_retries() -> int:
    """Get max total retries from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get("MAX_TOTAL_RETRIES", MAX_TOTAL_RETRIES)
    except RuntimeError:
        return MAX_TOTAL_RETRIES


_STAGE_STATUS_MAP = {
    # Pipeline statuses → stage names
    "pending": "select",
    "researching": "research",
    "writing": "write",
    "editing": "edit",
    # Role names → stage names
    "selector": "select",
    "researcher": "research",
    "writer": "write",
    "editor": "edit",
    # Stage names → stage names (passthrough)
    "select": "select",
    "research": "research",
    "write": "write",
    "edit": "edit",
}

# Maps pipeline status to the task that handles it
_STAGE_TASKS = {
    "pending": ("tasks.select", "select_article"),
    "researching": ("tasks.research", "research_article"),
    "writing": ("tasks.write", "write_article"),
    "editing": ("tasks.edit", "edit_article"),
}

# Cache for resolved task functions to avoid repeated importlib calls
_task_fn_cache: dict[str, tuple] = {}


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


def _build_fallback_article(article) -> str:
    """Build a minimal article JSON when pipeline stages fail or are skipped.

    Constructs a best-effort article representation from raw fields so that
    downstream consumers (newsletter, editor) always receive valid JSON even
    when the LLM stages could not run.

    Args:
        article: Article model instance (may have ``original_title``,
            ``extracted_text``, ``original_url``, ``original_author``).

    Returns:
        JSON-encoded string with headline, tldr, body, and metadata fields.
    """
    return json.dumps(
        {
            "headline": article.original_title or "Untitled",
            "tldr": (article.extracted_text or "")[:200],
            "why_it_matters": "",
            "body": article.extracted_text or article.original_title or "",
            "key_points": [],
            "what_to_watch": "",
            "citations": [],
            "original_attribution": {
                "source": article.original_url or "",
                "author": article.original_author or "",
            },
            "tags": [],
        }
    )


def _log_pipeline(run_id, stage, level, message, article_id=None):
    """Create a PipelineLog entry without committing outer transactions.

    Uses a nested transaction (savepoint) so that a log-write failure does not
    roll back the caller's work.  Fatal-level (``"error"``) log failures are
    re-raised after the failed savepoint is rolled back.

    Args:
        run_id: Pipeline-run ID.
        stage: Pipeline stage name (e.g. ``"select"``, ``"write"``).
        level: Log level — ``"info"``, ``"warning"``, or ``"error"``.
        message: Human-readable log message.
        article_id: Optional article ID for correlation.

    Raises:
        Exception: Re-raised only when *level* is ``"error"`` and the
            log write itself fails.
    """
    from models import PipelineLog
    from extensions import db
    from services.metrics import get_metrics

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

        # Re-raise for fatal stages (error level) after logging failure
        if level == "error":
            raise


def _degrade_and_advance(article, failed_stage: str, run_id=None):
    """Advance article to next stage with degraded quality on persistent failure.

    When a stage exhausts its per-stage retry budget, instead of failing the
    article entirely this function synthesizes minimal content for the failed
    stage and moves the article to the next status.  Each stage has its own
    degradation strategy:

    * **select** — auto-selects the article with a default score of 6.
    * **research** — creates a minimal research brief from extracted text.
    * **write** — builds a fallback article JSON from raw fields.
    * **edit** — uses the draft as-is and marks the article done (or routes
      to review if configured).

    Args:
        article: Article model instance (will be mutated and committed).
        failed_stage: Stage name that failed (``"select"``, ``"research"``,
            ``"write"``, or ``"edit"``).
        run_id: Optional pipeline-run ID for structured logging.
    """
    from extensions import db

    # Normalize: accept both action names ("write") and status names ("writing")
    failed_stage = _STAGE_STATUS_MAP.get(failed_stage, failed_stage)

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
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "select",
                "warning",
                f"Degraded: auto-selected {truncate_for_log(article.original_title)}",
                article_id=article.id,
            )
        _dispatch_next(article.id, run_id=run_id, next_status="researching")

    elif failed_stage == "research":
        article.research_brief = json.dumps(
            {
                "source_summary": (
                    article.extracted_text or article.original_title or ""
                )[:500],
                "key_claims": [],
                "direct_quotes": [],
                "external_sources": [],
                "related_articles": [],
                "context_notes": "Research stage failed; using source text only.",
                "newsworthiness": "Auto-generated after research failure.",
                "impact_score": 30,
            }
        )
        article.impact_score = 30
        article.pipeline_status = "writing"
        article.retry_count = 0
        article.last_error = None
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "research",
                "warning",
                f"Degraded: skipped research for {truncate_for_log(article.original_title)}",
                article_id=article.id,
            )
        _dispatch_next(article.id, run_id=run_id, next_status="writing")

    elif failed_stage == "write":
        article.draft_article = _build_fallback_article(article)
        article.pipeline_status = "editing"
        article.retry_count = 0
        article.last_error = None
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "write",
                "warning",
                f"Degraded: minimal draft for {truncate_for_log(article.original_title)}",
                article_id=article.id,
            )
        _dispatch_next(article.id, run_id=run_id, next_status="editing")

    elif failed_stage == "edit":
        _apply_fallback(article)
        article.retry_count = 0
        article.last_error = None

        if _should_route_to_review(article):
            article.pipeline_status = "review"
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                raise
            if run_id:
                _log_pipeline(
                    run_id,
                    "edit",
                    "warning",
                    f"Degraded to review: {truncate_for_log(article.original_title)}",
                    article_id=article.id,
                )
            return

        article.pipeline_status = PipelineStatus.DONE
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "warning",
                f"Degraded: used draft as final for {truncate_for_log(article.original_title)}",
                article_id=article.id,
            )
        logger.warning("Article %s finalized with degraded content", article.id)

    else:
        logger.error(
            "Unknown stage '%s' for degradation of article %s",
            failed_stage,
            article.id,
        )


def _handle_stage_failure(article, stage: str, exc, run_id: int | None = None) -> bool:
    """Handle failure for a pipeline stage.

    Increments both per-stage (``retry_count``) and global (``total_retries``)
    counters, then decides the next action:

    * If the global retry budget is exceeded → mark article ``"failed"``.
    * If the per-stage retry budget is exceeded → degrade and advance.
    * Otherwise → commit the incremented counters and return for retry.

    Args:
        article: Article model instance (mutated in-place).
        stage: Stage name that failed.
        exc: The exception that caused the failure.
        run_id: Optional pipeline-run ID for structured logging.

    Returns:
        ``True`` if the article was degraded or permanently failed (caller
        should not retry).  ``False`` if the article is still eligible for
        retry.
    """
    from extensions import db

    article.retry_count = (article.retry_count or 0) + 1
    article.total_retries = (article.total_retries or 0) + 1
    article.last_error = f"{stage}: {str(exc)[:500]}"

    max_total = _get_max_total_retries()
    max_stage = _get_max_stage_retries()

    # Global retry budget: fail article permanently if exceeded
    if article.total_retries >= max_total:
        article.pipeline_status = "failed"
        try:
            db.session.commit()
        except SQLAlchemyError as commit_exc:
            db.session.rollback()
            logger.error(
                f"Failed to commit failed status for article {article.id}: {commit_exc}"
            )
        if run_id:
            _log_pipeline(
                run_id,
                stage,
                "error",
                f"Article {article.id} exceeded global retry budget ({max_total}), marked as failed",
                article_id=article.id,
            )
        logger.error(
            "Article %s exceeded global retry budget (%s)", article.id, max_total
        )
        return True

    if article.retry_count >= max_stage:
        _degrade_and_advance(article, stage, run_id=run_id)
        return True
    else:
        try:
            db.session.commit()
        except SQLAlchemyError as commit_exc:
            db.session.rollback()
            logger.error(
                f"Failed to commit retry_count for article {article.id}: {commit_exc}"
            )
        return False


def _finalize(article_id: int):
    """Mark article as done when the editor stage is skipped.

    Applies fallback content (draft or generated), creates a version
    snapshot, and either routes the article to review or marks it as
    ``PipelineStatus.DONE`` depending on the review configuration.

    Args:
        article_id: ID of the article to finalize.
    """
    from models import Article
    from extensions import db

    try:
        article = db.session.get(Article, article_id)
        if article:
            _apply_fallback(article)
            article.retry_count = 0
            article.last_error = None

            if _should_route_to_review(article):
                article.pipeline_status = PipelineStatus.REVIEW
                db.session.commit()
                logger.info("Article %s queued for review (finalize)", article_id)
                return

            article.pipeline_status = PipelineStatus.DONE

            from services.article import create_article_version

            create_article_version(
                article,
                change_reason="pipeline_finalize",
                changed_by="pipeline:finalizer",
            )

            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error("Finalize failed for article %s: %s", article_id, e)


def _assign_tags(article, tag_names: list[str], db):
    """Find or create tags and link them to the article.

    Batches queries to avoid N+1: one SELECT for existing tags, one flush
    for new tags, one SELECT for existing links, one INSERT for new links.

    Args:
        article: Article model instance to tag.
        tag_names: List of tag name strings (max 10 used, max 64 chars each).
        db: SQLAlchemy database session instance.
    """
    from models import Tag, slugify, article_tags

    if not tag_names:
        return

    # 1. Normalize names and compute slugs
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

    # 2. Batch-fetch existing tags
    existing_tags = Tag.query.filter(Tag.slug.in_(slugs)).all()
    tag_by_slug = {t.slug: t for t in existing_tags}

    # 3. Create any missing tags
    for slug, name in name_by_slug.items():
        if slug not in tag_by_slug:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
            tag_by_slug[slug] = tag
    db.session.flush()

    # 4. Batch-fetch existing article-tag links
    tag_ids = [t.id for t in tag_by_slug.values()]
    existing_links = set(
        r[0]
        for r in db.session.execute(
            article_tags.select()
            .where(
                (article_tags.c.article_id == article.id)
                & (article_tags.c.tag_id.in_(tag_ids))
            )
            .with_only_columns(article_tags.c.tag_id)
        ).all()
    )

    # 5. Insert missing links
    for tag in tag_by_slug.values():
        if tag.id not in existing_links:
            db.session.execute(
                article_tags.insert().values(article_id=article.id, tag_id=tag.id)
            )


def _should_route_to_review(article) -> bool:
    """Check if article should go to review instead of being marked done.

    Reads the review configuration from the pipeline config.  An article is
    routed to review when:

    * The review stage is enabled, **and**
    * Either ``auto_publish_threshold`` is ``None`` (always review), or the
      article's ``impact_score`` is below the threshold.

    Args:
        article: Article model instance (reads ``impact_score``).

    Returns:
        ``True`` if the article should enter the review queue.
    """
    from schemas.pipeline import load_pipeline_config

    review_cfg = load_pipeline_config().pipeline.review
    if review_cfg.enabled:
        threshold = review_cfg.auto_publish_threshold
        if threshold is None or (article.impact_score or 0) < threshold:
            return True
    return False


def _apply_fallback(article):
    """Set ``final_article`` from draft or build a minimal fallback.

    If the article has a ``draft_article`` from the writer stage, it is used
    directly.  Otherwise a minimal article is constructed from raw source
    fields via :func:`_build_fallback_article`.

    Also sets ``original_ai_article`` to the same value so that the audit
    trail always has a copy of the AI-generated (or fallback) content.

    Args:
        article: Article model instance (mutated in-place, not committed).
    """
    fallback = article.draft_article or _build_fallback_article(article)
    article.final_article = fallback
    article.original_ai_article = fallback


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
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.llm import (
        get_provider_for_role,
        record_provider_success,
        record_provider_failure,
    )
    from services.limiter import get_limiter

    rc = get_role_config(stage)
    if not rc.enabled:
        if skip_next == "finalize":
            _finalize(article_id)
        else:
            _dispatch_next(article_id, run_id=run_id, next_status=skip_next)
        return {"article_id": article_id, "decision": f"skip_{stage}"}

    # Stage lock: prevent same article/stage from running concurrently
    from extensions import get_redis

    redis_client = get_redis()
    lock_key = f"ainews:stage_lock:{article_id}:{stage}"
    task_id = task_self.request.id or "manual"
    lock_acquired = redis_client.set(
        lock_key, task_id, nx=True, ex=rc.timeout_seconds + 60
    )
    if not lock_acquired:
        logger.info(
            "Stage %s already running for article %s, skipping", stage, article_id
        )
        return {"article_id": article_id, "skipped": True, "reason": "stage_locked"}

    article = db.session.get(Article, article_id)
    if not article:
        return {"article_id": article_id, "error": "not found"}

    provider, model, max_tokens = get_provider_for_role(stage)
    limiter = get_limiter()

    if not limiter.acquire(rc.provider, model, rc.concurrency, rc.timeout_seconds):
        raise task_self.retry(countdown=retry_countdown, max_retries=retry_max)

    from services.pipeline_monitor import record_stage_result

    try:
        result = work_fn(article, provider, model, max_tokens)

        record_provider_success(rc.provider, model, tokens_used=max_tokens)
        article.retry_count = 0
        article.last_error = None
        record_stage_result(stage, success=True, run_id=run_id)

        return result
    except SoftTimeLimitExceeded:
        db.session.rollback()
        record_stage_result(stage, success=False, run_id=run_id)
        article = db.session.get(Article, article_id)
        if article:
            article.last_error = f"{stage}: soft time limit exceeded"
        raise  # Let Celery handle retry
    except Exception as e:
        db.session.rollback()
        record_provider_failure(rc.provider, model)
        record_stage_result(stage, success=False, run_id=run_id)
        article = db.session.get(Article, article_id)
        if article and _handle_stage_failure(article, stage, e, run_id=run_id):
            return {"article_id": article_id, "result": "degraded"}
        if run_id:
            _log_pipeline(
                run_id,
                stage,
                "error",
                f"Article {article_id}: {e}",
                article_id=article_id,
            )
        logger.error("%s failed for article %s: %s", stage.title(), article_id, e)
        raise
    finally:
        limiter.release(rc.provider, model)
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except Exception:
            pass
