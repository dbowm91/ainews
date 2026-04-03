from __future__ import annotations
import logging
from typing import Type

from pydantic import BaseModel

from schemas.pipeline import resolve_subagent_config, SubagentStageConfig
from schemas.llm_responses import SubagentResponse
from services.llm import get_provider_for_role

# Backward-compat re-exports (canonical definitions in schemas.llm_responses)
from schemas.llm_responses import (  # noqa: F401
    ResearchSynthesisResponse,
    EditContextualizationResponse,
)


logger = logging.getLogger(__name__)


_SUBAGENT_TASK_TEMPLATES = {
    "research_synthesis": """<source_article>
  <title>{title}</title>
  <body>{body}</body>
</source_article>

<web_results>
{web_results}
</web_results>

Synthesize the external sources into a coherent summary that supplements the source article.
Focus on facts, context, and perspectives not already covered in the source article.
Return your synthesis as a concise paragraph.""",
    "edit_contextualization": """<draft_article>
{draft}
</draft_article>

<research_brief>
{brief}
</research_brief>

<topic_notes>
{topic_notes}
</topic_notes>

<related_articles>
{related_articles}
</related_articles>

Review the draft in light of the research brief, topic notes, and related articles.
Identify gaps in context, missing attribution, or claims that need additional support.
Return a concise contextualization that addresses what the editor should know.""",
}


def _get_subagent_provider_and_config(
    stage_config: SubagentStageConfig,
) -> tuple:
    if stage_config.provider and stage_config.model:
        from services.llm import get_provider_by_id

        provider = get_provider_by_id(stage_config.provider)
        model = stage_config.model
        max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    else:
        provider, model, max_tokens, _ = get_provider_for_role("editor")
        if stage_config.max_tokens:
            max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    return provider, model, max_tokens, temperature


def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
) -> SubagentResponse:
    stage_config = resolve_subagent_config(stage)
    if not stage_config.enabled:
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    template = _SUBAGENT_TASK_TEMPLATES.get(task_type, "")
    prompt = template.format(**prompt_data)

    system_prompt = stage_config.system_prompt or ""

    provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
        stage_config
    )

    try:
        result = provider.chat_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
            model=model,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return SubagentResponse(
            synthesis=result.synthesis,
            used_fallback=False,
            fallback_stages=[],
        )
    except Exception as e:
        logger.warning(
            "Subagent %s/%s failed: %s — using fallback",
            stage,
            task_type,
            e,
        )
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )
