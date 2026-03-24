from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def select_article(self, article_id: int, run_id=None):
    from models import Article, PipelineRun
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.llm import get_provider_for_role
    from services.limiter import get_limiter
    from tasks.pipeline import _log_pipeline, _handle_stage_failure
    from pydantic import BaseModel, Field

    rc = get_role_config("selector")
    if not rc.enabled:
        from tasks.research import research_article

        research_article.delay(article_id, run_id=run_id)
        return {"article_id": article_id, "decision": "skip_selector"}

    article = Article.query.get(article_id)
    if not article:
        return {"article_id": article_id, "error": "not found"}

    provider, model, max_tokens = get_provider_for_role("selector")
    limiter = get_limiter()
    acquired = False

    if not limiter.acquire(rc.provider, model, rc.concurrency, rc.timeout_seconds):
        raise self.retry(countdown=15, max_retries=20)
    acquired = True

    try:

        class SelectionResult(BaseModel):
            selected: bool
            score: int = Field(ge=1, le=10)
            reason: str

        text_preview = (article.extracted_text or article.original_title or "")[:500]
        prompt = (
            f"ARTICLE: {article.original_title}\n"
            f"TOPICS: {', '.join(article.topics or [])}\n"
            f"PREVIEW: {text_preview}\n\n"
            "Should we write a condensed news article about this? "
            "Score 1-10 for newsworthiness to a tech audience. "
            "Return JSON with selected (bool), score (1-10), reason (string)."
        )

        result = provider.chat_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=SelectionResult,
            model=model,
            system=rc.system_prompt
            or "You are a news editor deciding which stories to cover.",
            temperature=rc.temperature,
            max_tokens=max_tokens,
        )

        from services.llm import record_provider_success

        record_provider_success(rc.provider, model)

        article.selector_result = result.model_dump()
        article.retry_count = 0
        article.last_error = None

        if result.selected and result.score >= (rc.min_score or 6):
            article.pipeline_status = "researching"
            db.session.commit()

            if run_id:
                run = PipelineRun.query.get(run_id)
                if run:
                    run.articles_selected = (run.articles_selected or 0) + 1
                    db.session.commit()
                _log_pipeline(
                    run_id,
                    "select",
                    "info",
                    f"Selected [{result.score}/10]: {article.original_title[:50]}",
                    article_id=article.id,
                )

            logger.info(f"Selected [{result.score}/10]: {article.original_title[:50]}")
            from tasks.research import research_article

            research_article.delay(article_id, run_id=run_id)
        else:
            article.pipeline_status = "skipped"
            db.session.commit()

            if run_id:
                _log_pipeline(
                    run_id,
                    "select",
                    "info",
                    f"Skipped [{result.score}/10]: {article.original_title[:50]}",
                    article_id=article.id,
                )

            logger.info(f"Skipped [{result.score}/10]: {article.original_title[:50]}")
    except Exception as e:
        db.session.rollback()
        from services.llm import record_provider_failure

        record_provider_failure(rc.provider, model)
        article = Article.query.get(article_id)
        if article:
            if _handle_stage_failure(article, "select", e, run_id=run_id):
                return {"article_id": article_id, "result": "degraded"}
        if run_id:
            _log_pipeline(
                run_id,
                "select",
                "error",
                f"Article {article_id}: {e}",
                article_id=article_id,
            )
        logger.error(f"Selector failed for article {article_id}: {e}")
        raise
    finally:
        if acquired:
            limiter.release(rc.provider, model)

    return {"article_id": article_id, "result": article.selector_result}
