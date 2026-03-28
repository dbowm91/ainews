from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, soft_time_limit=300, time_limit=360)
def select_article(self, article_id: int, run_id=None):
    from models import PipelineRun
    from extensions import db
    from pydantic import BaseModel, Field
    from schemas.pipeline import get_role_config
    from services.prompts import get_system_prompt
    from tasks.pipeline import run_stage, _log_pipeline, _dispatch_next

    class SelectionResult(BaseModel):
        selected: bool
        score: int = Field(ge=1, le=10)
        reason: str

    def work(article, provider, model, max_tokens):
        rc = get_role_config("selector")
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
            system=get_system_prompt("selector", rc.system_prompt),
            temperature=rc.temperature,
            max_tokens=max_tokens,
        )

        article.selector_result = result.model_dump()

        if result.selected and result.score >= (rc.min_score or 6):
            article.pipeline_status = "researching"
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            if run_id:
                run = db.session.get(PipelineRun, run_id)
                if run:
                    run.articles_selected = (run.articles_selected or 0) + 1
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        raise
                _log_pipeline(
                    run_id,
                    "select",
                    "info",
                    f"Selected [{result.score}/10]: {article.original_title[:50]}",
                    article_id=article.id,
                )

            logger.info(f"Selected [{result.score}/10]: {article.original_title[:50]}")
            _dispatch_next(article_id, run_id=run_id, next_status="researching")
        else:
            article.pipeline_status = "skipped"
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            if run_id:
                _log_pipeline(
                    run_id,
                    "select",
                    "info",
                    f"Skipped [{result.score}/10]: {article.original_title[:50]}",
                    article_id=article.id,
                )

            logger.info(f"Skipped [{result.score}/10]: {article.original_title[:50]}")

        return {"article_id": article_id, "result": article.selector_result}

    return run_stage(
        "selector",
        article_id,
        work,
        task_self=self,
        run_id=run_id,
        skip_next="researching",
        retry_countdown=15,
        retry_max=20,
    )
