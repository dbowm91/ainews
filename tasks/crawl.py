from celery import shared_task, group
from celery.utils.log import get_task_logger
from billiard.exceptions import SoftTimeLimitExceeded

import redis.exceptions

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def crawl_source(self, source_config: dict, run_id: int) -> dict:
    """Crawl a single source. Called by run_all_sources for parallel execution."""
    from adapters.base import get_adapter_class
    from models import Source
    from extensions import db, get_redis
    from services.crawling import (
        should_skip_source,
        get_existing_external_ids,
        filter_new_items,
        filter_non_other_topics,
        update_source_crawl_time,
    )
    from tasks.pipeline import _log_pipeline
    from schemas.source import SourceConfig

    cfg = SourceConfig(**source_config)
    source_id = cfg.id

    # Distributed lock to prevent duplicate processing across workers.
    # Uses task ID so retries from the same task can re-acquire.
    lock_key = f"ainews:crawl_lock:{source_id}"
    redis_client = get_redis()
    task_id = self.request.id or "manual"
    try:
        acquired = redis_client.set(lock_key, task_id, nx=True, ex=30)
    except redis.exceptions.RedisError:
        acquired = True
    if not acquired:
        try:
            existing = redis_client.get(lock_key)
            if existing and existing.decode() == task_id:
                redis_client.set(lock_key, task_id, nx=False, ex=30)
            else:
                logger.info("Source %s already being crawled, skipping", source_id)
                return {"source_id": source_id, "skipped": True, "reason": "locked"}
        except redis.exceptions.RedisError:
            logger.warning(
                "Redis unavailable for lock check on %s, proceeding", source_id
            )
            acquired = True

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

        from constants import MIN_CONTENT_LENGTH

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
            process_item.delay(
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
            )

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
        return {
            "source_id": source_id,
            "fetched": len(items),
            "new": len(new_items),
        }
    except SoftTimeLimitExceeded:
        db.session.rollback()
        _log_pipeline(
            run_id, "crawl", "error", "%s: soft time limit exceeded", source_id
        )
        logger.error("Task exceeded soft time limit for source %s", source_id)
        raise
    except Exception as e:
        db.session.rollback()
        _log_pipeline(run_id, "crawl", "error", "%s: %s", source_id, e)
        logger.error("Pipeline failed for %s: %s", source_id, e, exc_info=True)
        from services.crawling import record_crawl_failure

        if source:
            record_crawl_failure(source, str(e))
        return {"source_id": source_id, "error": str(e)}
    finally:
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except Exception:
            logger.warning("Failed to release crawl lock for %s", source_id)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def run_all_sources(self, run_id=None):
    """Orchestrate crawling of all sources using parallel task execution."""
    from schemas.source import load_sources
    from models import PipelineRun
    from extensions import db
    from services.crawling import (
        create_pipeline_run,
        update_pipeline_run_stats,
    )
    from tasks.pipeline import _log_pipeline

    # Create PipelineRun if manual trigger
    if run_id is None:
        run = create_pipeline_run(self.request.id, triggered_by="scheduled")
        run_id = run.id

    try:
        configs = load_sources()
    except Exception as exc:
        _log_pipeline(run_id, "crawl", "error", "Failed to load sources: %s", exc)
        run = db.session.get(PipelineRun, run_id)
        if run:
            run.status = "failed"
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
        raise self.retry(exc=exc)

    if not configs:
        logger.info("No sources configured")
        run = db.session.get(PipelineRun, run_id)
        if run:
            update_pipeline_run_stats(run, 0, 0)
        return []

    # Dispatch all sources as a group for parallel execution
    source_configs = [cfg.model_dump() for cfg in configs]
    job = group(
        crawl_source.s(source_config=cfg, run_id=run_id) for cfg in source_configs
    )
    result = job.apply_async()

    # Wait for all tasks to complete (with timeout)
    results = []
    timed_out = False
    try:
        results = result.get(timeout=360, propagate=False)
    except TimeoutError:
        timed_out = True
        logger.error("Source crawl timed out after 360s, aggregating partial results")
        # Try to get whatever results are available
        try:
            results = result.get(timeout=1, propagate=False) or []
        except Exception:
            results = []
    except Exception as e:
        logger.error("Error waiting for source crawl results: %s", e)
        results = []

    # Aggregate results
    total_fetched = 0
    total_new = 0
    errors = 0
    for res in results:
        if isinstance(res, dict):
            if "error" in res:
                errors += 1
                from services.crawling import record_crawl_failure
                from models import Source

                source_id = res.get("source_id")
                if source_id:
                    src = Source.query.filter_by(source_key=source_id).first()
                    if src:
                        record_crawl_failure(src, res["error"])
            total_fetched += res.get("fetched", 0)
            total_new += res.get("new", 0)

    # Update run stats
    run = db.session.get(PipelineRun, run_id)
    if run:
        update_pipeline_run_stats(run, total_fetched, total_new)
        try:
            if timed_out:
                run.status = "timeout"
            elif errors > 0 and total_new == 0:
                run.status = "failed"
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    logger.info("All sources complete: %s", results)
    return results
