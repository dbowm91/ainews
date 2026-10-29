from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import PipelineStatus, truncate_for_log, CELERY_TASK_MAX_RETRIES
from schemas.llm_responses import ResearchBrief
from services.llm.errors import ProviderServerError
from utils.text import esc_xml_text

logger = get_task_logger(__name__)


def _is_degenerate_research(brief: ResearchBrief) -> bool:
    """Check if research brief is degenerate (fails quality gate).

    Returns True if:
    - No key claims (empty list or all with empty content)
    - Impact score is very low (< 10)
    """
    if not brief.key_claims:
        return True
    if any(claim.claim.strip() for claim in brief.key_claims):
        has_valid_claims = True
    else:
        has_valid_claims = False
    if brief.impact_score < 10:
        return True
    return not has_valid_claims

# Error response convention:
# - Leaf tasks: re-raise for Celery retry
# - Pipeline stages (select, research, write, edit): re-raise for Celery retry
# - Orchestration tasks: return error dict with aggregated results


def _format_web_results(web_results: list[dict]) -> str:
    if not web_results:
        return "(no web results)"
    parts = []
    for wr in web_results:
        parts.append(f"Source: {esc_xml_text(wr.get('title', 'Unknown'))}")
        parts.append(f"URL: {esc_xml_text(wr.get('url', ''))}")
        parts.append(f"Snippet: {esc_xml_text(wr.get('snippet', '')[:300])}")
        parts.append("")
    return "\n".join(parts)


def _perform_web_search_and_synthesis(article, rc):
    web_results = []
    web_synthesis = ""
    if not rc.web_search:
        return web_results, web_synthesis
    search_query = f"{article.original_title} {' '.join(article.topics or [])}"
    if rc.web_search_provider:
        from services.search import get_search_provider
        search_prov = get_search_provider(rc.web_search_provider)
        search_results = search_prov.search(
            search_query, max_results=rc.web_search_max_results or 5,
        )
    else:
        from services.search import search_web
        search_results = search_web(
            search_query, max_results=rc.web_search_max_results or 5,
        )
    web_results = [
        {"title": s.title, "url": s.url, "snippet": s.snippet}
        for s in search_results
    ]
    if not web_results:
        return web_results, web_synthesis
    from schemas.llm_responses import ResearchSynthesisResponse
    from schemas.pipeline import resolve_subagent_config
    from services.subagent import run_subagent, run_subagent_with_tools
    stage_config = resolve_subagent_config("research", default_role="researcher")
    if stage_config.tools:
        from services.subagent import initialize_tool_registry
        from services.tool_selection import StageAwareToolSelector
        selector = StageAwareToolSelector(stage_config.tools)
        tools = initialize_tool_registry(selector=selector)
        web_synthesis_result = run_subagent_with_tools(
            task_type="research_synthesis",
            stage="researcher",
            prompt_data={
                "title": article.original_title or "",
                "body": article.extracted_text or "",
                "web_results": _format_web_results(web_results),
            },
            response_model=ResearchSynthesisResponse,
            tools=tools,
            article_id=article.id,
        )
    else:
        web_synthesis_result = run_subagent(
            task_type="research_synthesis",
            stage="researcher",
            prompt_data={
                "title": article.original_title or "",
                "body": article.extracted_text or "",
                "web_results": _format_web_results(web_results),
            },
            response_model=ResearchSynthesisResponse,
            article_id=article.id,
        )
    web_synthesis = web_synthesis_result.synthesis
    if web_synthesis_result.used_fallback:
        logger.warning(
            "Research web synthesis subagent failed, proceeding without synthesis",
            extra={"article_id": article.id},
        )
    return web_results, web_synthesis


def _get_related_and_context(article, rc):
    from services.related import find_related_articles_dicts
    related = find_related_articles_dicts(
        article.topics or [], article.id, limit=rc.db_related_max or 5,
    )
    topic_notes = ""
    trend_memory = ""
    if article.topics:
        from services.context_service import get_topic_notes_for_topics
        from services.trend_memory import (
            _format_memory_for_prompt,
            get_memory_for_topics,
        )
        topic_notes_dict = get_topic_notes_for_topics(article.topics)
        if topic_notes_dict:
            topic_notes = "\n".join(
                f"- {note}" for notes in topic_notes_dict.values() for note in notes
            )
        trend_memory = _format_memory_for_prompt(
            get_memory_for_topics(article.topics, min_importance=1),
        )
    return related, topic_notes, trend_memory


def _generate_research_brief(
    article,
    rc,
    web_results,
    web_synthesis,
    related,
    topic_notes,
    trend_memory,
    provider,
    model,
    max_tokens,
):
    from services.researcher import build_research_prompt, get_researcher_system_prompt
    from services.logging_utils import traced_llm_call
    from services.metrics import time_histogram
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
        topic_notes=topic_notes,
        trend_memory=trend_memory,
    )
    with traced_llm_call(provider=provider.__class__.__name__, model=model, stage="researcher"):
        with time_histogram(
            "pipeline.stage_duration_seconds", labels={"stage": "researcher"},
        ):
            brief = provider.chat_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=ResearchBrief,
                model=model,
                system=get_researcher_system_prompt(),
                temperature=rc.temperature,
                max_tokens=max_tokens,
                stage="researcher",
            )
    return brief


def _perform_quality_assessment(article, brief):
    try:
        from services.quality import lightweight_quality_signals
        brief_text = " ".join(
            claim.content for claim in (brief.key_claims or []) if claim.content
        )
        if brief_text:
            quality_score = lightweight_quality_signals(brief_text)
            logger.info(
                "Research quality (shadow): article_id=%s overall=%.2f groundedness=%.2f coherence=%.2f completeness=%.2f safety=%.2f",
                article.id,
                quality_score.overall,
                quality_score.groundedness,
                quality_score.coherence,
                quality_score.completeness,
                quality_score.safety,
            )
    except Exception as e:  # noqa: BLE001 - shadow quality assessment is non-critical
        logger.warning(
            "Quality assessment failed for article %s: %s", article.id, e
        )


def _handle_quality_gate_and_transition(brief, article, run_id, article_id, db):
    from tasks.pipeline import _transition_article_status, _log_pipeline, _dispatch_next
    if _is_degenerate_research(brief):
        logger.warning(
            "Research brief failed quality gate, routing to review",
            extra={
                "article_id": article.id,
                "has_key_claims": bool(brief.key_claims),
                "impact_score": brief.impact_score,
            },
        )
        _transition_article_status(article, PipelineStatus.REVIEW)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        if run_id:
            _log_pipeline(
                run_id,
                "research",
                "warning",
                "Research failed quality gate, routed to review: %s",
                truncate_for_log(article.original_title),
                article_id=article.id,
            )
        _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)
        return {"article_id": article_id, "quality_gate": "review"}

    # Quality gate passed
    _transition_article_status(article, PipelineStatus.WRITING)
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
    _dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.WRITING)
    return {"article_id": article_id}


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=60,
    # Research includes optional multi-iteration synthesis and a structured
    # brief. Keep Celery's hard limit above the bounded provider retry budget
    # so a slow-but-progressing run is not killed and redelivered mid-call.
    soft_time_limit=1740,
    time_limit=1800,
    autoretry_for=(ConnectionError, TimeoutError, ProviderServerError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def research_article(self, article_id: int, run_id=None, _signature=None, task_name=None):
    from extensions import db
    from schemas.pipeline import get_role_config
    from tasks.pipeline import run_stage, _transition_article_status

    def work(article, provider, model, max_tokens):
        rc = get_role_config("researcher")
        _transition_article_status(article, PipelineStatus.RESEARCHING)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        # Web search + synthesis
        web_results, web_synthesis = _perform_web_search_and_synthesis(article, rc)

        # Related articles + context
        related, topic_notes, trend_memory = _get_related_and_context(article, rc)

        # Generate research brief
        brief = _generate_research_brief(
            article=article,
            rc=rc,
            web_results=web_results,
            web_synthesis=web_synthesis,
            related=related,
            topic_notes=topic_notes,
            trend_memory=trend_memory,
            provider=provider,
            model=model,
            max_tokens=max_tokens,
        )

        article.research_brief = brief.model_dump_json()
        article.impact_score = brief.impact_score

        # Quality assessment
        _perform_quality_assessment(article, brief)

        # Quality gate and transition
        return _handle_quality_gate_and_transition(
            brief=brief,
            article=article,
            run_id=run_id,
            article_id=article_id,
            db=db,
        )

    return run_stage(
        "researcher",
        article_id,
        work,
        task_self=self,
        run_id=run_id,
        skip_next=PipelineStatus.WRITING,
    )
