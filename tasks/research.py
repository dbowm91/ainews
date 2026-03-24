from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def research_article(self, article_id: int, run_id=None):
    from models import Article
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.llm import get_provider_for_role
    from services.limiter import get_limiter
    from services.researcher import (
        ResearchBrief,
        get_researcher_system_prompt,
        build_research_prompt,
    )
    from services.related import find_related_articles_dicts
    from services.search import search_web, get_search_provider
    from tasks.pipeline import _log_pipeline, _handle_stage_failure

    rc = get_role_config("researcher")
    if not rc.enabled:
        from tasks.write import write_article

        write_article.delay(article_id, run_id=run_id)
        return {"article_id": article_id, "decision": "skip_researcher"}

    article = Article.query.get(article_id)
    if not article:
        return {"article_id": article_id, "error": "not found"}

    provider, model, max_tokens = get_provider_for_role("researcher")
    limiter = get_limiter()
    acquired = False

    if not limiter.acquire(rc.provider, model, rc.concurrency, rc.timeout_seconds):
        raise self.retry(countdown=30, max_retries=15)
    acquired = True

    try:
        article.pipeline_status = "researching"
        db.session.commit()

        # Web search
        web_results = []
        if rc.web_search:
            search_query = f"{article.original_title} {' '.join(article.topics or [])}"
            if rc.web_search_provider:
                search_prov = get_search_provider(rc.web_search_provider)
                search_results = search_prov.search(
                    search_query, max_results=rc.web_search_max_results or 5
                )
            else:
                search_results = search_web(
                    search_query, max_results=rc.web_search_max_results or 5
                )
            web_results = [
                {"title": s.title, "url": s.url, "snippet": s.snippet}
                for s in search_results
            ]

        # DB lookup for related articles
        related = find_related_articles_dicts(
            article.topics or [], article.id, limit=rc.db_related_max or 5
        )

        # Build prompt
        prompt = build_research_prompt(
            title=article.original_title or "",
            extracted_text=article.extracted_text or "",
            original_url=article.original_url or "",
            author=article.original_author or "",
            topics=article.topics or [],
            web_results=web_results,
            related_articles=related,
            max_text_length=rc.max_article_text_length or 6000,
        )

        brief = provider.chat_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=ResearchBrief,
            model=model,
            system=get_researcher_system_prompt(),
            temperature=rc.temperature,
            max_tokens=max_tokens,
        )

        from services.llm import record_provider_success

        record_provider_success(rc.provider, model)

        article.research_brief = brief.model_dump_json()
        article.impact_score = brief.impact_score
        article.retry_count = 0
        article.last_error = None
        article.pipeline_status = "writing"
        db.session.commit()

        if run_id:
            _log_pipeline(
                run_id,
                "research",
                "info",
                f"Researched: {article.original_title[:50]} (score: {brief.impact_score})",
                article_id=article.id,
            )

        logger.info(
            f"Researched: {article.original_title[:50]} (score: {brief.impact_score}, sources: {len(web_results)}, related: {len(related)})"
        )
    except Exception as e:
        db.session.rollback()
        from services.llm import record_provider_failure

        record_provider_failure(rc.provider, model)
        article = Article.query.get(article_id)
        if article:
            if _handle_stage_failure(article, "research", e, run_id=run_id):
                return {"article_id": article_id, "result": "degraded"}
        if run_id:
            _log_pipeline(
                run_id,
                "research",
                "error",
                f"Article {article_id}: {e}",
                article_id=article_id,
            )
        logger.error(f"Researcher failed for article {article_id}: {e}")
        raise
    finally:
        if acquired:
            limiter.release(rc.provider, model)

    from tasks.write import write_article

    write_article.delay(article_id, run_id=run_id)
    return {"article_id": article_id}
