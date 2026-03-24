from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def run_all_sources(self, run_id=None):
    from schemas.source import load_sources
    from adapters.base import get_adapter_class
    from models import Source, PipelineRun
    from extensions import db
    from services.crawling import (
        create_pipeline_run, should_skip_source, get_existing_external_ids,
        filter_new_items, filter_non_other_topics, update_source_crawl_time,
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
        _log_pipeline(run_id, "crawl", "error", f"Failed to load sources: {exc}")
        run = PipelineRun.query.get(run_id)
        if run:
            run.status = "failed"
            db.session.commit()
        raise self.retry(exc=exc)

    total_fetched = 0
    total_new = 0
    results = []

    for cfg in configs:
        try:
            adapter_class = get_adapter_class(cfg.type)
            adapter = adapter_class(cfg)

            source = Source.query.filter_by(source_key=cfg.id).first()

            if should_skip_source(source, cfg.schedule_minutes):
                results.append({"source_id": cfg.id, "skipped": True})
                continue

            # Ensure Source record exists before dispatching process_item tasks
            if not source:
                from services.crawling import get_or_create_source
                source = get_or_create_source(
                    source_key=cfg.id,
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
            min_content = getattr(adapter.adapter_config, "min_content_length", MIN_CONTENT_LENGTH) if adapter.adapter_config else MIN_CONTENT_LENGTH

            from tasks.extract import process_item
            for item in new_items:
                process_item.delay(
                    source_key=cfg.id,
                    source_name=cfg.name,
                    source_type=cfg.type,
                    external_id=item.external_id,
                    title=item.title,
                    url=item.url,
                    author=item.author,
                    published_at=item.published_at.isoformat() if item.published_at else None,
                    text_content=item.text_content,
                    raw_score=item.raw_score,
                    raw_metadata=item.raw_metadata,
                    topics=item.topics,
                    min_content_length=min_content,
                    run_id=run_id,
                )

            update_source_crawl_time(source, cfg)

            total_fetched += len(items)
            total_new += len(new_items)
            _log_pipeline(run_id, "crawl", "info",
                          f"{cfg.id}: fetched {len(items)}, {len(new_items)} new")
            results.append({"source_id": cfg.id, "fetched": len(items), "new": len(new_items)})
        except Exception as e:
            db.session.rollback()
            _log_pipeline(run_id, "crawl", "error", f"{cfg.id}: {e}")
            logger.error(f"Pipeline failed for {cfg.id}: {e}", exc_info=True)
            results.append({"source_id": cfg.id, "error": str(e)})

    # Update run stats
    run = PipelineRun.query.get(run_id)
    if run:
        update_pipeline_run_stats(run, total_fetched, total_new)

    logger.info(f"All sources complete: {results}")
    return results
