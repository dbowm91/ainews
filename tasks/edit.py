from celery import shared_task
from celery.utils.log import get_task_logger
from constants import PipelineStatus, truncate_for_log
from services.logging_utils import get_pipeline_logger
import time

logger = get_task_logger(__name__)
plog = get_pipeline_logger("edit")

_TAG_CACHE: list[str] | None = None
_TAG_CACHE_TIME: float = 0
_TAG_CACHE_TTL = 300


def _get_cached_tag_names() -> list[str]:
    global _TAG_CACHE, _TAG_CACHE_TIME
    now = time.time()
    if _TAG_CACHE is not None and (now - _TAG_CACHE_TIME) < _TAG_CACHE_TTL:
        return _TAG_CACHE
    from models import Tag

    tags = Tag.query.order_by(Tag.name).limit(100).all()
    _TAG_CACHE = [t.name for t in tags]
    _TAG_CACHE_TIME = now
    return _TAG_CACHE


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=30,
    retry_backoff_max=300,
    retry_jitter=True,
)
def edit_article(self, article_id: int, run_id=None):
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.writer import CondensedArticle
    from services.editor import get_editor_system_prompt, build_editor_prompt
    from tasks.pipeline import (
        run_stage,
        _log_pipeline,
        _assign_tags,
        _should_route_to_review,
    )

    def work(article, provider, model, max_tokens):
        rc = get_role_config("editor")
        existing_tags = _get_cached_tag_names()

        prompt = build_editor_prompt(
            draft_json=article.draft_article or "",
            research_brief=article.research_brief or "",
            existing_tags=existing_tags,
            max_tags=rc.max_tags or 3,
        )

        from services.metrics import time_histogram

        with time_histogram(
            "pipeline.stage_duration_seconds", labels={"stage": "edit"}
        ):
            result = provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=CondensedArticle,
                model=model,
                system=get_editor_system_prompt(),
                temperature=rc.temperature,
                max_tokens=max_tokens,
            )

        result_json = result.model_dump_json()
        article.final_article = result_json
        article.original_ai_article = result_json

        _assign_tags(article, result.tags or [], db)

        # Create version snapshot of the AI-generated article
        from services.article import create_article_version

        create_article_version(
            article, change_reason="pipeline_edit", changed_by="pipeline:editor"
        )

        # Route to review if enabled and article doesn't meet auto-publish threshold
        if _should_route_to_review(article):
            article.pipeline_status = PipelineStatus.REVIEW
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            if run_id:
                _log_pipeline(
                    run_id,
                    "edit",
                    "info",
                    "Queued for review: %s",
                    truncate_for_log(article.original_title),
                    article_id=article.id,
                )
            plog.info(
                "Article queued for review",
                article_id=article.id,
                tags=result.tags,
                title=truncate_for_log(article.original_title),
            )
            return {"article_id": article_id, "status": "review"}

        article.pipeline_status = PipelineStatus.DONE
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "info",
                "Finalized: %s",
                truncate_for_log(article.original_title),
                article_id=article.id,
            )

        plog.info(
            "Article finalized",
            article_id=article.id,
            tags=result.tags,
            title=truncate_for_log(article.original_title),
        )
        return {"article_id": article_id, "status": "done"}

    return run_stage(
        "editor", article_id, work, task_self=self, run_id=run_id, skip_next="finalize"
    )
