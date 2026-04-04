from __future__ import annotations
import logging
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as ConcurrentTimeoutError,
)
from typing import Any, Type

from pydantic import BaseModel

from schemas.pipeline import resolve_subagent_config, SubagentStageConfig, BASE_DIR
from schemas.llm_responses import SubagentResponse
from services.llm import get_provider_for_role
from services.llm.base import ToolDefinition
from services.metrics import time_histogram, get_metrics
from services.logging_utils import log_pipeline_event
from services.llm.errors import ProviderTimeoutError, AuthError, ProviderServerError

# Backward-compat re-exports (canonical definitions in schemas.llm_responses)
from schemas.llm_responses import (  # noqa: F401
    ResearchSynthesisResponse,
    EditContextualizationResponse,
)


_TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(definition: ToolDefinition) -> None:
    """Register a tool definition in the global tool registry."""
    _TOOL_REGISTRY[definition.name] = definition


def get_registered_tools() -> list[ToolDefinition]:
    """Get all registered tool definitions."""
    return list(_TOOL_REGISTRY.values())


def _build_context_tools() -> list[ToolDefinition]:
    """Build tool definitions from context_service functions."""
    tools = []

    def _get_topic_note(topic: str, source: str | None = None) -> str:
        from services.context_service import get_topic_note

        note = get_topic_note(topic, source)
        return note.note if note else "No note found for this topic."

    def _get_topic_notes_for_topics(topics: list[str]) -> str:
        from services.context_service import get_topic_notes_for_topics

        result = get_topic_notes_for_topics(topics)
        if not result:
            return "No topic notes found."
        return "\n".join(
            f"Topic: {k}\nNotes: {'; '.join(v)}" for k, v in result.items()
        )

    def _get_related_articles(
        topics: list[str], exclude_id: int, limit: int = 5
    ) -> str:
        from services.context_service import get_related_articles_for_edit

        articles = get_related_articles_for_edit(topics, exclude_id, limit=limit)
        if not articles:
            return "No related articles found."
        return "\n".join(
            f"- {a['title']}: {a.get('summary_snippet', '')[:100]}" for a in articles
        )

    tools.append(
        ToolDefinition(
            name="get_topic_note",
            description="Get a topic note for a given topic name. Returns the note content.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic name"},
                    "source": {
                        "type": "string",
                        "description": "Optional source filter",
                    },
                },
                "required": ["topic"],
            },
            fn=_get_topic_note,
        )
    )

    tools.append(
        ToolDefinition(
            name="get_topic_notes_for_topics",
            description="Get topic notes for multiple topics at once.",
            parameters={
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of topic names",
                    },
                },
                "required": ["topics"],
            },
            fn=_get_topic_notes_for_topics,
        )
    )

    tools.append(
        ToolDefinition(
            name="get_related_articles",
            description="Get related articles for editing context.",
            parameters={
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of topics",
                    },
                    "exclude_id": {
                        "type": "integer",
                        "description": "Article ID to exclude",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max articles to return",
                    },
                },
                "required": ["topics", "exclude_id"],
            },
            fn=_get_related_articles,
        )
    )

    return tools


def _build_search_tools() -> list[ToolDefinition]:
    """Build tool definitions from search service."""
    tools = []

    def _search_web(query: str, max_results: int = 5) -> str:
        from services.search import search_web

        results = search_web(query, max_results)
        if not results:
            return "No search results found."
        return "\n".join(f"- {r.title}: {r.snippet[:150]}..." for r in results)

    def _get_search_provider(provider_id: str | None = None) -> str:
        from services.search import get_search_provider

        prov = get_search_provider(provider_id)
        return f"Using search provider: {prov.provider_id}"

    tools.append(
        ToolDefinition(
            name="search_web",
            description="Search the web for information on a topic.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
            fn=_search_web,
        )
    )

    tools.append(
        ToolDefinition(
            name="get_search_provider",
            description="Get the configured search provider.",
            parameters={
                "type": "object",
                "properties": {
                    "provider_id": {
                        "type": "string",
                        "description": "Optional specific provider ID",
                    },
                },
            },
            fn=_get_search_provider,
        )
    )

    return tools


def initialize_tool_registry() -> None:
    """Initialize the tool registry with built-in tools."""
    for tool in _build_context_tools():
        register_tool(tool)
    for tool in _build_search_tools():
        register_tool(tool)


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


def _load_prompt_template(path: str) -> str | None:
    p = BASE_DIR / path
    if p.exists():
        return p.read_text()
    return None


def _get_task_template(task_type: str, stage_config: SubagentStageConfig) -> str:
    if stage_config.task_template:
        loaded = _load_prompt_template(stage_config.task_template)
        if loaded:
            return loaded
    return _SUBAGENT_TASK_TEMPLATES.get(task_type, "")


def _get_subagent_provider_and_config(
    stage_config: SubagentStageConfig,
    default_role: str = "editor",
) -> tuple:
    if stage_config.provider and stage_config.model:
        from services.llm import get_provider_by_id

        provider = get_provider_by_id(stage_config.provider)
        model = stage_config.model
        max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    else:
        provider, model, max_tokens, _ = get_provider_for_role(default_role)
        if stage_config.max_tokens:
            max_tokens = stage_config.max_tokens
        temperature = stage_config.temperature
    return provider, model, max_tokens, temperature


def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:
    default_role = "researcher" if stage == "research" else "editor"
    stage_config = resolve_subagent_config(stage, default_role=default_role)
    if not stage_config.enabled:
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    log_pipeline_event(
        stage="subagent",
        event="subagent.start",
        article_id=article_id,
        task_type=task_type,
        stage_name=stage,
    )

    template = _get_task_template(task_type, stage_config)
    try:
        prompt = template.format(**prompt_data)
    except KeyError as e:
        logger.warning(
            "Subagent %s/%s template missing key: %s",
            stage,
            task_type,
            e,
        )
        get_metrics().counter_inc(
            "subagent.failure",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.failure",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
            error=f"template missing key: {e}",
        )
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    system_prompt = stage_config.system_prompt or ""

    provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
        stage_config, default_role=default_role
    )

    def _call_with_timeout():
        return provider.chat_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
            model=model,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    result = None
    used_fallback = False
    fallback_stages = []
    last_exc = None

    for attempt in range(stage_config.max_retries + 1):
        try:
            with time_histogram(
                "subagent.duration_seconds",
                labels={"stage": stage, "task_type": task_type},
            ):
                if attempt > 0:
                    time.sleep(stage_config.retry_delay)
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_call_with_timeout)
                    try:
                        result = future.result(timeout=stage_config.timeout_seconds)
                    except ConcurrentTimeoutError:
                        executor.shutdown(wait=False, cancel_futures=True)
                        logger.warning(
                            "Subagent %s/%s timed out after %ss",
                            stage,
                            task_type,
                            stage_config.timeout_seconds,
                        )
                        raise ProviderTimeoutError(
                            f"Subagent timed out after {stage_config.timeout_seconds}s"
                        )
            break
        except (ProviderTimeoutError, TimeoutError, ConnectionError) as e:
            last_exc = e
            if attempt < stage_config.max_retries:
                logger.info(
                    "Subagent %s/%s attempt %d failed, retrying in %ss: %s",
                    stage,
                    task_type,
                    attempt + 1,
                    stage_config.retry_delay,
                    e,
                )
            continue
        except (AuthError, ProviderServerError) as e:
            last_exc = e
            logger.warning(
                "Subagent %s/%s failed with non-retryable error: %s",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break
        except Exception as e:
            last_exc = e
            logger.warning(
                "Subagent %s/%s failed: %s — using fallback",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break

    if result is None:
        used_fallback = True
        fallback_stages = [stage]
        get_metrics().counter_inc(
            "subagent.failure",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.failure",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
            error=str(last_exc) if last_exc else None,
        )
    else:
        get_metrics().counter_inc(
            "subagent.success",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.complete",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
        )

    get_metrics().counter_inc(
        "subagent.calls",
        labels={
            "stage": stage,
            "task_type": task_type,
            "status": "failure" if used_fallback else "success",
        },
    )

    return SubagentResponse(
        synthesis=result.synthesis if result else "",
        used_fallback=used_fallback,
        fallback_stages=fallback_stages,
    )


def run_subagent_with_tools(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    tools: list[ToolDefinition],
    article_id: int | None = None,
) -> SubagentResponse:
    """Run subagent with tool calling support."""
    default_role = "researcher" if stage == "research" else "editor"
    stage_config = resolve_subagent_config(stage, default_role=default_role)
    if not stage_config.enabled:
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    log_pipeline_event(
        stage="subagent",
        event="subagent.start",
        article_id=article_id,
        task_type=task_type,
        stage_name=stage,
    )

    template = _get_task_template(task_type, stage_config)
    try:
        prompt = template.format(**prompt_data)
    except KeyError as e:
        logger.warning(
            "Subagent %s/%s template missing key: %s",
            stage,
            task_type,
            e,
        )
        return SubagentResponse(
            synthesis="",
            used_fallback=True,
            fallback_stages=[stage],
        )

    system_prompt = stage_config.system_prompt or ""
    provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
        stage_config, default_role=default_role
    )

    messages = [{"role": "user", "content": prompt}]

    def _call_with_timeout():
        return provider.chat_with_tools(
            messages=messages,
            tools=tools,
            tool_choice=None,
            model=model,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            max_iterations=5,
        )

    result = None
    used_fallback = False
    fallback_stages = []
    last_exc = None

    for attempt in range(stage_config.max_retries + 1):
        try:
            with time_histogram(
                "subagent.duration_seconds",
                labels={"stage": stage, "task_type": task_type},
            ):
                if attempt > 0:
                    time.sleep(stage_config.retry_delay)
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_call_with_timeout)
                    try:
                        tc_resp = future.result(timeout=stage_config.timeout_seconds)
                        result = response_model.model_validate(
                            {"synthesis": tc_resp.text}
                        )
                    except ConcurrentTimeoutError:
                        executor.shutdown(wait=False, cancel_futures=True)
                        logger.warning(
                            "Subagent %s/%s timed out after %ss",
                            stage,
                            task_type,
                            stage_config.timeout_seconds,
                        )
                        raise ProviderTimeoutError(
                            f"Subagent timed out after {stage_config.timeout_seconds}s"
                        )
            break
        except (ProviderTimeoutError, TimeoutError, ConnectionError) as e:
            last_exc = e
            if attempt < stage_config.max_retries:
                logger.info(
                    "Subagent %s/%s attempt %d failed, retrying in %ss: %s",
                    stage,
                    task_type,
                    attempt + 1,
                    stage_config.retry_delay,
                    e,
                )
            continue
        except (AuthError, ProviderServerError) as e:
            last_exc = e
            logger.warning(
                "Subagent %s/%s failed with non-retryable error: %s",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break
        except Exception as e:
            last_exc = e
            logger.warning(
                "Subagent %s/%s failed: %s — using fallback",
                stage,
                task_type,
                e,
            )
            used_fallback = True
            fallback_stages = [stage]
            break

    if result is None:
        used_fallback = True
        fallback_stages = [stage]
        get_metrics().counter_inc(
            "subagent.failure",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.failure",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
            error=str(last_exc) if last_exc else None,
        )
    else:
        get_metrics().counter_inc(
            "subagent.success",
            labels={"stage": stage, "task_type": task_type},
        )
        log_pipeline_event(
            stage="subagent",
            event="subagent.complete",
            article_id=article_id,
            task_type=task_type,
            stage_name=stage,
        )

    get_metrics().counter_inc(
        "subagent.calls",
        labels={
            "stage": stage,
            "task_type": task_type,
            "status": "failure" if used_fallback else "success",
        },
    )

    return SubagentResponse(
        synthesis=result.synthesis if result else "",
        used_fallback=used_fallback,
        fallback_stages=fallback_stages,
    )


def run_subagent_chain(
    chain_name: str,
    steps: list[dict],
    initial_prompt_data: dict,
    article_id: int | None = None,
) -> dict[str, Any]:
    """Run a multi-step subagent chain.

    Each step: {task_type, prompt_data_template, response_model, condition}
    Steps can reference outputs of previous steps via template variables.
    Returns dict with step results and any fallback markers.
    """
    from schemas.pipeline import load_pipeline_config

    config = load_pipeline_config()
    chain_config = config.subagent.chains.get(chain_name)
    if not chain_config or not chain_config.enabled:
        return {
            "results": {},
            "used_fallback": True,
            "fallback_stages": ["chain"],
        }

    max_length = chain_config.max_length
    results: dict[str, Any] = {}

    for i, step_config in enumerate(chain_config.steps[:max_length]):
        step_name = f"{chain_name}_step_{i}"
        task_type = step_config.task_type

        if step_config.condition:
            try:
                condition_result = _evaluate_condition(step_config.condition, results)
                if not condition_result:
                    logger.info(
                        "Chain %s step %d (%s) skipped due to condition",
                        chain_name,
                        i,
                        task_type,
                    )
                    results[step_name] = {"synthesis": "", "skipped": True}
                    continue
            except Exception as e:
                logger.warning(
                    "Chain %s step %d condition evaluation failed: %s",
                    chain_name,
                    i,
                    e,
                )
                results[step_name] = {"synthesis": "", "skipped": True}
                continue

        stage = "research" if "research" in task_type else "edit"
        stage_config = resolve_subagent_config(stage)
        if not stage_config.enabled:
            results[step_name] = {"synthesis": "", "used_fallback": True}
            continue

        try:
            template = step_config.prompt_data_template
            prompt_data = _resolve_template_variables(
                template, initial_prompt_data, results
            )
            prompt = template.format(**prompt_data)
        except Exception as e:
            logger.warning(
                "Chain %s step %d template error: %s",
                chain_name,
                i,
                e,
            )
            results[step_name] = {"synthesis": "", "used_fallback": True}
            continue

        system_prompt = stage_config.system_prompt or ""
        provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
            stage_config, default_role="editor"
        )

        try:
            resp = provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            results[step_name] = {"synthesis": resp.text, "used_fallback": False}
        except Exception as e:
            logger.warning(
                "Chain %s step %d failed: %s",
                chain_name,
                i,
                e,
            )
            results[step_name] = {
                "synthesis": f"[Fallback: {e}]",
                "used_fallback": True,
            }

    all_fallback = all(r.get("used_fallback", False) for r in results.values())

    return {
        "results": results,
        "used_fallback": all_fallback,
        "fallback_stages": list(results.keys()) if all_fallback else [],
    }


def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Evaluate a condition expression against the context."""
    try:
        local_vars = {"results": context}
        for key, value in context.items():
            local_vars[key] = value
        return bool(eval(condition, {"__builtins__": {}}, local_vars))
    except Exception:
        return False


def _resolve_template_variables(
    template: str, initial_data: dict, results: dict[str, Any]
) -> dict:
    """Resolve template variables, including references to previous step results."""
    resolved = dict(initial_data)
    for key, value in resolved.items():
        if isinstance(value, str) and "{{" in value:
            try:
                resolved[key] = value.format(**results)
            except Exception:
                pass
    return resolved
