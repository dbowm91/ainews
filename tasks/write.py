from celery import shared_task
from celery.utils.log import get_task_logger
from constants import PipelineStatus, truncate_for_log
from services.logging_utils import get_pipeline_logger
from services.llm.errors import ProviderServerError

logger = get_task_logger(__name__)
plog = get_pipeline_logger("write")

# Error response convention:
# - Leaf tasks: re-raise for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks: return error dict with aggregated results


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=30,
    retry_backoff_max=300,
    retry_jitter=True,
)
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

        from services.metrics import time_histogram

        with time_histogram(
            "pipeline.stage_duration_seconds", labels={"stage": "write"}
        ):
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
        article.pipeline_status = PipelineStatus.EDITING
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
                "Drafted: %s",
                truncate_for_log(article.original_title),
                article_id=article.id,
            )

        plog.info(
            "Article drafted",
            article_id=article.id,
            title=truncate_for_log(article.original_title),
        )

        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.EDITING)
        return {"article_id": article_id}

    return run_stage(
        "writer",
        article_id,
        work,
        task_self=self,
        run_id=run_id,
        skip_next=PipelineStatus.EDITING,
    )
