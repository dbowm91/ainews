from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def write_article(self, article_id: int, run_id=None):
    from models import Article
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.llm import get_provider_for_role
    from services.limiter import get_limiter
    from services.writer import (
        CondensedArticle,
        get_writer_system_prompt,
        build_writer_prompt,
    )
    from tasks.pipeline import _log_pipeline, _handle_stage_failure, _finalize

    rc = get_role_config("writer")
    if not rc.enabled:
        _finalize(article_id)
        return {"article_id": article_id, "decision": "skip_writer"}

    article = Article.query.get(article_id)
    if not article:
        return {"article_id": article_id, "error": "not found"}

    provider, model, max_tokens = get_provider_for_role("writer")
    limiter = get_limiter()
    acquired = False

    if not limiter.acquire(rc.provider, model, rc.concurrency, rc.timeout_seconds):
        raise self.retry(countdown=30, max_retries=15)
    acquired = True

    try:
        prompt = build_writer_prompt(
            title=article.original_title or "",
            topics=article.topics or [],
            research_brief=article.research_brief or "",
            max_key_points=rc.max_key_points or 5,
        )

        result = provider.chat_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=CondensedArticle,
            model=model,
            system=get_writer_system_prompt(),
            temperature=rc.temperature,
            max_tokens=max_tokens,
        )

        from services.llm import record_provider_success

        record_provider_success(rc.provider, model)

        article.draft_article = result.model_dump_json()
        article.writer_model = model
        article.retry_count = 0
        article.last_error = None
        article.pipeline_status = "editing"
        db.session.commit()

        if run_id:
            _log_pipeline(
                run_id,
                "write",
                "info",
                f"Drafted: {article.original_title[:50]}",
                article_id=article.id,
            )

        logger.info(f"Drafted: {article.original_title[:50]}")
    except Exception as e:
        db.session.rollback()
        from services.llm import record_provider_failure

        record_provider_failure(rc.provider, model)
        article = Article.query.get(article_id)
        if article:
            if _handle_stage_failure(article, "write", e, run_id=run_id):
                return {"article_id": article_id, "result": "degraded"}
        if run_id:
            _log_pipeline(
                run_id,
                "write",
                "error",
                f"Article {article_id}: {e}",
                article_id=article_id,
            )
        logger.error(f"Writer failed for article {article_id}: {e}")
        raise
    finally:
        if acquired:
            limiter.release(rc.provider, model)

    from tasks.edit import edit_article

    edit_article.delay(article_id, run_id=run_id)
    return {"article_id": article_id}
