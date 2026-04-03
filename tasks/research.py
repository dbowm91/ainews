from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError
from constants import PipelineStatus, truncate_for_log
from services.logging_utils import get_pipeline_logger
from services.llm.errors import ProviderServerError

logger = get_task_logger(__name__)
plog = get_pipeline_logger("research")

# Error response convention:
# - Leaf tasks: re-raise for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks: return error dict with aggregated results


def _format_web_results(web_results: list[dict]) -> str:
    if not web_results:
        return "(no web results)"
    parts = []
    for wr in web_results:
        parts.append(f"Source: {wr.get('title', 'Unknown')}")
        parts.append(f"URL: {wr.get('url', '')}")
        parts.append(f"Snippet: {wr.get('snippet', '')[:300]}")
        parts.append("")
    return "\n".join(parts)


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
        article.pipeline_status = PipelineStatus.RESEARCHING
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        web_results = []
        web_synthesis = ""
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

            if web_results:
                from services.subagent import run_subagent, ResearchSynthesisResponse

                web_synthesis_result = run_subagent(
                    task_type="research_synthesis",
                    stage="research",
                    prompt_data={
                        "title": article.original_title or "",
                        "body": article.extracted_text or "",
                        "web_results": _format_web_results(web_results),
                    },
                    response_model=ResearchSynthesisResponse,
                )
                web_synthesis = web_synthesis_result.synthesis
                if web_synthesis_result.used_fallback:
                    plog.warning(
                        "Research web synthesis subagent failed, proceeding without synthesis",
                        article_id=article.id,
                    )

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
            web_synthesis=web_synthesis,
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
        article.pipeline_status = PipelineStatus.WRITING
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        if run_id:
            _log_pipeline(
                run_id,
                "research",
                "info",
                "Researched: %s (score: %s)",
                truncate_for_log(article.original_title),
                brief.impact_score,
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

        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.WRITING)
        return {"article_id": article_id}

    return run_stage(
        "researcher",
        article_id,
        work,
        task_self=self,
        run_id=run_id,
        skip_next=PipelineStatus.WRITING,
    )
