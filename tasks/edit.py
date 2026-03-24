from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def edit_article(self, article_id: int, run_id=None):
    from models import Article
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.llm import get_provider_for_role
    from services.limiter import get_limiter
    from services.writer import CondensedArticle
    from services.editor import get_editor_system_prompt, build_editor_prompt
    from tasks.pipeline import (
        _log_pipeline,
        _handle_stage_failure,
        _finalize,
        _assign_tags,
    )

    rc = get_role_config("editor")
    if not rc.enabled:
        _finalize(article_id)
        return {"article_id": article_id, "decision": "skip_editor"}

    article = Article.query.get(article_id)
    if not article:
        return {"article_id": article_id, "error": "not found"}

    provider, model, max_tokens = get_provider_for_role("editor")
    limiter = get_limiter()
    acquired = False

    if not limiter.acquire(rc.provider, model, rc.concurrency, rc.timeout_seconds):
        raise self.retry(countdown=30, max_retries=15)
    acquired = True

    try:
        from models import Tag

        existing_tags = [t.name for t in Tag.query.all()]

        prompt = build_editor_prompt(
            draft_json=article.draft_article or "",
            research_brief=article.research_brief or "",
            existing_tags=existing_tags,
            max_tags=rc.max_tags or 3,
        )

        result = provider.chat_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=CondensedArticle,
            model=model,
            system=get_editor_system_prompt(),
            temperature=rc.temperature,
            max_tokens=max_tokens,
        )

        from services.llm import record_provider_success

        record_provider_success(rc.provider, model)

        article.final_article = result.model_dump_json()
        article.original_ai_article = result.model_dump_json()
        article.retry_count = 0
        article.last_error = None

        _assign_tags(article, result.tags or [], db)

        # Create version snapshot of the AI-generated article
        from services.article import create_article_version

        create_article_version(
            article, change_reason="pipeline_edit", changed_by="pipeline:editor"
        )

        # Route to review if review is enabled and article doesn't meet auto-publish threshold
        from schemas.pipeline import load_pipeline_config

        review_cfg = load_pipeline_config().pipeline.review
        if review_cfg.enabled:
            threshold = review_cfg.auto_publish_threshold
            if threshold is None or (article.impact_score or 0) < threshold:
                article.pipeline_status = "review"
                db.session.commit()
                if run_id:
                    _log_pipeline(
                        run_id,
                        "edit",
                        "info",
                        f"Queued for review: {article.original_title[:50]}",
                        article_id=article.id,
                    )
                logger.info(
                    f"Queued for review: {article.original_title[:50]} (tags: {result.tags})"
                )
                return {"article_id": article_id, "status": "review"}

        article.pipeline_status = "done"
        db.session.commit()

        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "info",
                f"Finalized: {article.original_title[:50]}",
                article_id=article.id,
            )

        logger.info(f"Finalized: {article.original_title[:50]} (tags: {result.tags})")
    except Exception as e:
        db.session.rollback()
        from services.llm import record_provider_failure

        record_provider_failure(rc.provider, model)
        article = Article.query.get(article_id)
        if article:
            if _handle_stage_failure(article, "edit", e, run_id=run_id):
                return {"article_id": article_id, "result": "degraded"}
        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "error",
                f"Article {article_id}: {e}",
                article_id=article_id,
            )
        logger.error(f"Editor failed for article {article_id}: {e}")
        raise
    finally:
        if acquired:
            limiter.release(rc.provider, model)

    return {"article_id": article_id, "status": "done"}
