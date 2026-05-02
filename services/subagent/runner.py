from __future__ import annotations

import logging
import time
from concurrent.futures import TimeoutError
from typing import Any, Type

import json  # noqa: F401 - needed for JSON operations in tools

from pydantic import BaseModel, ValidationError

from schemas.llm_responses import SubagentResponse
from schemas.pipeline import BASE_DIR, SubagentStageConfig
from services.llm.base import ToolDefinition
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError
from services.prompts import esc_xml_text

from .config import _subagent_executor

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

<trend_memory>
{trend_memory}
</trend_memory>

Review the draft in light of the research brief, topic notes, related articles, and trend memory.
Identify gaps in context, missing attribution, or claims that need additional support.
Return a concise contextualization that addresses what the editor should know.""",
}


def _load_prompt_template(path: str) -> str | None:
    p = BASE_DIR / path
    if p.exists():
        return p.read_text()
    return None


def _escape_prompt_data(data: dict[str, Any]) -> dict[str, Any]:
    """Escape all string values in prompt_data for safe XML embedding."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = esc_xml_text(value)
        elif isinstance(value, dict):
            result[key] = _escape_prompt_data(value)
        elif isinstance(value, list):
            result[key] = [
                esc_xml_text(str(v)) if isinstance(v, str) else v for v in value
            ]
        else:
            result[key] = value
    return result


def _get_task_template(task_type: str, stage_config: SubagentStageConfig) -> str:
    if stage_config.task_template:
        loaded = _load_prompt_template(stage_config.task_template)
        if loaded:
            return loaded
    return _SUBAGENT_TASK_TEMPLATES.get(task_type, "")


def run_subagent(
    task_type: str,
    stage: str,
    prompt_data: dict,
    response_model: Type[BaseModel],
    article_id: int | None = None,
) -> SubagentResponse:
    from . import resolve_subagent_config, log_pipeline_event

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
        prompt_data_escaped = _escape_prompt_data(prompt_data)
        prompt = template.format(**prompt_data_escaped)
    except KeyError as e:
        logger.warning(
            "Subagent %s/%s template missing key: %s",
            stage,
            task_type,
            e,
        )
        from . import get_metrics

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

    from .config import _get_subagent_provider_and_config

    provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
        stage_config, default_role=default_role,
    )

    def _call_with_timeout():
        from . import traced_llm_call

        with traced_llm_call(provider=provider.provider_id, model=model, stage=stage):
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
            from . import time_histogram

            with time_histogram(
                "subagent.duration_seconds",
                labels={"stage": stage, "task_type": task_type},
            ):
                if attempt > 0:
                    import random

                    delay = min(
                        1.0 * (2 ** attempt) + random.uniform(0, 0.5),  # noqa: S311
                        stage_config.retry_delay,
                    )
                    time.sleep(delay)
                future = _subagent_executor.submit(_call_with_timeout)
                try:
                    result = future.result(timeout=stage_config.timeout_seconds)
                except TimeoutError as e:
                    future.cancel()
                    logger.warning(
                        "Subagent %s/%s timed out after %ss",
                        stage,
                        task_type,
                        stage_config.timeout_seconds,
                    )
                    raise ProviderTimeoutError(
                        f"Subagent timed out after {stage_config.timeout_seconds}s",
                    ) from e
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
        except Exception as e:  # noqa: BLE001
            last_exc = e
            logger.error(
                "Subagent %s/%s unexpected error: %s — using fallback",
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
        from . import get_metrics, log_pipeline_event

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
        from . import get_metrics, log_pipeline_event

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

    from . import get_metrics

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
    from . import resolve_subagent_config, log_pipeline_event

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
        prompt_data_escaped = _escape_prompt_data(prompt_data)
        prompt = template.format(**prompt_data_escaped)
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
    from .config import _get_subagent_provider_and_config

    provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
        stage_config, default_role=default_role,
    )

    messages = [{"role": "user", "content": prompt}]

    def _call_with_timeout():
        from . import traced_llm_call

        with traced_llm_call(provider=provider.provider_id, model=model, stage=stage):
            return provider.chat_with_tools(
                messages=messages,
                tools=tools,
                tool_choice=None,
                model=model,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                max_iterations=stage_config.max_iterations,
            )

    result = None
    used_fallback = False
    fallback_stages = []
    last_exc = None
    self_corrected = False

    for attempt in range(stage_config.max_retries + 1):
        try:
            from . import time_histogram

            with time_histogram(
                "subagent.duration_seconds",
                labels={"stage": stage, "task_type": task_type},
            ):
                if attempt > 0:
                    import random

                    delay = min(
                        1.0 * (2 ** attempt) + random.uniform(0, 0.5),  # noqa: S311
                        stage_config.retry_delay,
                    )
                    time.sleep(delay)
                future = _subagent_executor.submit(_call_with_timeout)
                try:
                    tc_resp = future.result(timeout=stage_config.timeout_seconds)
                    try:
                        result = response_model.model_validate(
                            {"synthesis": tc_resp.text},
                        )
                    except (json.JSONDecodeError, ValidationError) as validation_err:
                        if self_corrected:
                            raise validation_err
                        error_msg = (
                            f"Your previous response was not valid JSON or did not match "
                            f"the expected schema: {validation_err}. Please correct and "
                            f"return valid JSON in the same format."
                        )
                        logger.info(
                            "Subagent %s/%s self-correcting after validation error: %s",
                            stage,
                            task_type,
                            validation_err,
                        )
                        messages.append({"role": "user", "content": error_msg})
                        self_corrected = True
                        continue
                except TimeoutError as e:
                    future.cancel()
                    logger.warning(
                        "Subagent %s/%s timed out after %ss",
                        stage,
                        task_type,
                        stage_config.timeout_seconds,
                    )
                    raise ProviderTimeoutError(
                        f"Subagent timed out after {stage_config.timeout_seconds}s",
                    ) from e
            break
        except (ProviderTimeoutError, TimeoutError, ConnectionError) as e:
            last_exc = e
            if attempt < stage_config.max_retries:
                import random

                delay = min(
                    1.0 * (2 ** attempt) + random.uniform(0, 0.5),
                    stage_config.retry_delay,
                )
                logger.info(
                    "Subagent %s/%s attempt %d failed, retrying in %ss: %s",
                    stage,
                    task_type,
                    attempt + 1,
                    delay,
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
        except Exception as e:  # noqa: BLE001
            last_exc = e
            logger.error(
                "Subagent %s/%s unexpected error: %s — using fallback",
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
        from . import get_metrics, log_pipeline_event

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
        from . import get_metrics, log_pipeline_event

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

    from . import get_metrics

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
