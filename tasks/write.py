from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60, soft_time_limit=300, time_limit=360)
def write_article(self, article_id: int, run_id=None):
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.writer import (
        CondensedArticle,
        get_writer_system_prompt,
        build_writer_prompt,
    )
    from tasks.pipeline import run_stage, _log_pipeline, _dispatch_next

    def work(article, provider, model, max_tokens):
        rc = get_role_config("writer")
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

        article.draft_article = result.model_dump_json()
        article.writer_model = model
        article.pipeline_status = "editing"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        if run_id:
            _log_pipeline(
                run_id,
                "write",
                "info",
                f"Drafted: {article.original_title[:50]}",
                article_id=article.id,
            )

        logger.info(f"Drafted: {article.original_title[:50]}")

        _dispatch_next(article_id, run_id=run_id, next_status="editing")
        return {"article_id": article_id}

    return run_stage(
        "writer", article_id, work, task_self=self, run_id=run_id, skip_next="editing"
    )
