from celery import shared_task
from celery.utils.log import get_task_logger
from constants import truncate_for_log
from services.logging_utils import get_pipeline_logger

logger = get_task_logger(__name__)
plog = get_pipeline_logger("research")


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def research_article(self, article_id: int, run_id=None):
    from extensions import db
    from schemas.pipeline import get_role_config
    from services.researcher import (
        ResearchBrief,
        get_researcher_system_prompt,
        build_research_prompt,
    )
    from services.related import find_related_articles_dicts
    from services.search import search_web, get_search_provider
    from tasks.pipeline import run_stage, _log_pipeline, _dispatch_next

    def work(article, provider, model, max_tokens):
        rc = get_role_config("researcher")
        article.pipeline_status = "researching"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

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

        from services.metrics import time_histogram

        with time_histogram(
            "pipeline.stage_duration_seconds", labels={"stage": "research"}
        ):
            brief = provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=ResearchBrief,
                model=model,
                system=get_researcher_system_prompt(),
                temperature=rc.temperature,
                max_tokens=max_tokens,
            )

        article.research_brief = brief.model_dump_json()
        article.impact_score = brief.impact_score
        article.pipeline_status = "writing"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        if run_id:
            _log_pipeline(
                run_id,
                "research",
                "info",
                f"Researched: {truncate_for_log(article.original_title)} (score: {brief.impact_score})",
                article_id=article.id,
            )

        plog.info(
            "Article researched",
            article_id=article.id,
            impact_score=brief.impact_score,
            sources=len(web_results),
            related=len(related),
            title=truncate_for_log(article.original_title),
        )

        _dispatch_next(article_id, run_id=run_id, next_status="writing")
        return {"article_id": article_id}

    return run_stage(
        "researcher",
        article_id,
        work,
        task_self=self,
        run_id=run_id,
        skip_next="writing",
    )
