import redis.exceptions
from billiard.exceptions import SoftTimeLimitExceeded
from celery import chord, group, shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from services.task_security import verify_invocation
from constants import CELERY_TASK_MAX_RETRIES

logger = get_task_logger(__name__)

# Error response convention:
# - Leaf tasks (e.g., crawl_source): re-raise exceptions for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks (run_all_sources, generate_daily_newsletters): return
#   error dict with aggregated results


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def crawl_source(self, source_config: dict, run_id: int, _signature: str | None = None, task_name: str | None = None) -> dict:  # noqa: C901
    """Crawl a single source. Called by run_all_sources for parallel execution."""
    from adapters.base import get_adapter_class
    from extensions import db, get_redis
    from models import Source
    from schemas.source import SourceConfig
    from services.crawling import (
        filter_new_items,
        filter_non_other_topics,
        get_existing_external_ids,
        should_skip_source,
        update_source_crawl_time,
    )
    from tasks.pipeline import _log_pipeline
    from services.pipeline_cancellation import is_pipeline_run_cancelled

    if is_pipeline_run_cancelled(run_id):
        return {"source_id": source_config.get("id"), "cancelled": True}

    cfg = SourceConfig(**source_config)
    source_id = cfg.id

    # Distributed lock to prevent duplicate processing across workers.
    # Uses task ID so retries from the same task can re-acquire.
    lock_key = f"ainews:crawl_lock:{source_id}"
    redis_client = get_redis()
    task_id = self.request.id or "manual"

    _CRAWL_LOCK_SCRIPT = """
    local current = redis.call('GET', KEYS[1])
    if current == ARGV[1] then
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
        return 1
    elseif not current then
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
        return 2
    else
        return 0
    end
    """
    _crawl_lock = redis_client.register_script(_CRAWL_LOCK_SCRIPT)

    try:
        lock_status = _crawl_lock(keys=[lock_key], args=[task_id, 30])
    except redis.exceptions.RedisError:
        logger.error("Redis unavailable for crawl lock, refusing to proceed")
        raise

    if lock_status == 0:
        logger.info("Source %s already being crawled, skipping", source_id)
        return {"source_id": source_id, "skipped": True, "reason": "locked"}
    elif lock_status == 1:
        logger.debug("Refreshed existing crawl lock for source %s", source_id)
    else:
        logger.debug("Acquired new crawl lock for source %s", source_id)

    try:
        source = Source.query.filter_by(source_key=source_id).first()

        adapter_class = get_adapter_class(cfg.type)
        adapter = adapter_class(cfg)

        if should_skip_source(source, cfg.schedule_minutes):
            return {"source_id": source_id, "skipped": True}

        # Ensure Source record exists before dispatching process_item tasks
        if not source:
            from services.crawling import get_or_create_source

            source = get_or_create_source(
                source_key=source_id,
                name=cfg.name,
                source_type=cfg.type,
                feed_url=cfg.config.get("feed_url", ""),
            )

        items = adapter.fetch_and_parse()
        for item in items:
            adapter.match_topics(item)

        filtered = filter_non_other_topics(items)
        existing_ids = get_existing_external_ids(source) if source else set()
        new_items = filter_new_items(filtered, existing_ids)

        if is_pipeline_run_cancelled(run_id):
            return {"source_id": source_id, "cancelled": True}

        from services.config_unified import MIN_CONTENT_LENGTH

        min_content = (
            getattr(adapter.adapter_config, "min_content_length", MIN_CONTENT_LENGTH)
            if adapter.adapter_config
            else MIN_CONTENT_LENGTH
        )

        # Filter out near-duplicate titles from other sources
        from services.article import find_duplicate_titles

        deduplicated_items = []
        for item in new_items:
            dupes = find_duplicate_titles(item.title, source.id)
            if dupes:
                logger.info(
                    "Skipping item '%s' — similar to article %s from source %s",
                    item.title[:80],
                    dupes[0].id,
                    dupes[0].source_id,
                )
            else:
                deduplicated_items.append(item)

        from tasks.extract import process_item

        for item in deduplicated_items:
            if is_pipeline_run_cancelled(run_id):
                break
            process_item.s(
                source_key=source_id,
                source_name=cfg.name,
                source_type=cfg.type,
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                author=item.author,
                published_at=item.published_at.isoformat()
                if item.published_at
                else None,
                text_content=item.text_content,
                raw_score=item.raw_score,
                raw_metadata=item.raw_metadata,
                topics=item.topics,
                min_content_length=min_content,
                run_id=run_id,
            ).apply_async()

        update_source_crawl_time(source, cfg)

        _log_pipeline(
            run_id,
            "crawl",
            "info",
            "%s: fetched %s, %s new",
            source_id,
            len(items),
            len(new_items),
        )

        from services.pipeline_monitor import record_stage_result, record_throughput

        record_stage_result("crawl", success=True, run_id=run_id)
        record_throughput("crawl", len(new_items))

        return {
            "source_id": source_id,
            "fetched": len(items),
            "new": len(new_items),
        }
    except SoftTimeLimitExceeded:
        db.session.rollback()
        _log_pipeline(
            run_id, "crawl", "error", "%s: soft time limit exceeded", source_id,
        )
        logger.error("Task exceeded soft time limit for source %s", source_id)
        from services.pipeline_monitor import record_stage_result

        record_stage_result("crawl", success=False, run_id=run_id, reason="timeout")
        raise
    except Exception as e:
        db.session.rollback()
        _log_pipeline(run_id, "crawl", "error", "%s: %s", source_id, e)
        logger.error("Pipeline failed for %s: %s", source_id, e, exc_info=True)
        from services.crawling import record_crawl_failure
        from services.pipeline_monitor import record_stage_result

        if source:
            record_crawl_failure(source, str(e))
        record_stage_result("crawl", success=False, run_id=run_id, reason="error")
        # Return a structured per-source failure so the chord callback always
        # runs and marks the parent PipelineRun completed/failed. A raised
        # non-retryable leaf error would prevent the callback and strand the run
        # in "running" indefinitely.
        return {"source_id": source_id, "error": str(e)}
    finally:
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except redis.exceptions.RedisError:
            logger.warning("Failed to release crawl lock for %s", source_id)


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True, max_retries=CELERY_TASK_MAX_RETRIES, default_retry_delay=30, soft_time_limit=120, time_limit=180,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def aggregate_crawl_results(self, results: list, run_id: int) -> dict:
    """Aggregate crawl results and update pipeline run stats.

    Called as a Celery chord callback after all crawl_source tasks complete.
    """
    from extensions import db
    from models import PipelineRun
    from services.crawling import update_pipeline_run_stats
    from services.pipeline_cancellation import is_pipeline_run_cancelled

    if is_pipeline_run_cancelled(run_id):
        return {"cancelled": True, "run_id": run_id}

    total_fetched = 0
    total_new = 0
    errors = 0
    for res in results:
        if isinstance(res, dict):
            if "error" in res:
                errors += 1
            total_fetched += res.get("fetched", 0)
            total_new += res.get("new", 0)

    run = db.session.get(PipelineRun, run_id)
    if run:
        update_pipeline_run_stats(run, total_fetched, total_new)
        try:
            if errors > 0 and total_new == 0:
                run.status = "failed"
            else:
                run.status = "completed"
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

    logger.info("All sources complete: %s", results)
    return {
        "total_fetched": total_fetched,
        "total_new": total_new,
        "errors": errors,
        "results": results,
    }


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def run_all_sources(self, run_id=None, _signature=None, task_name=None):
    """Orchestrate crawling of all sources using parallel task execution."""
    # The signature covers the arguments this task was called with, so it
    # is verified against the invocation rather than against a rebuilt
    # dict of the task's own defaults.
    if not verify_invocation("run_all_sources", self.request):
        logger.error("Invalid signature for run_all_sources task")
        raise ValueError("Invalid task signature")

    from extensions import db
    from models import PipelineRun
    from schemas.source import load_sources
    from services.crawling import (
        create_pipeline_run,
        update_pipeline_run_stats,
    )
    from tasks.pipeline import _log_pipeline
    from services.pipeline_cancellation import is_pipeline_run_cancelled

    if run_id is None:
        run = create_pipeline_run(self.request.id, triggered_by="scheduled")
        run_id = run.id

    if is_pipeline_run_cancelled(run_id):
        return {"cancelled": True, "run_id": run_id}

    try:
        configs = load_sources()
    except Exception as exc:
        _log_pipeline(run_id, "crawl", "error", "Failed to load sources: %s", exc)
        run = db.session.get(PipelineRun, run_id)
        if run:
            run.status = "failed"
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                raise
        raise self.retry(exc=exc) from exc

    if not configs:
        logger.info("No sources configured")
        run = db.session.get(PipelineRun, run_id)
        if run:
            update_pipeline_run_stats(run, 0, 0)
        return []

    source_configs = [cfg.model_dump() for cfg in configs]
    if is_pipeline_run_cancelled(run_id):
        return {"cancelled": True, "run_id": run_id}
    crawl_group = group(
        crawl_source.s(source_config=cfg, run_id=run_id) for cfg in source_configs
    )
    chord_task = chord(crawl_group, aggregate_crawl_results.s(run_id=run_id))
    chord_task.apply_async()

    return {"message": f"Dispatched {len(source_configs)} sources for crawling"}
