from __future__ import annotations

import logging
from concurrent.futures import TimeoutError
from typing import Any, Callable, Type

import json

from pydantic import BaseModel, ValidationError

from schemas.llm_responses import SubagentResponse
from schemas.pipeline import SubagentStageConfig
from services.llm.base import ToolDefinition
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError
from utils.text import escape_prompt_data

from .config import _subagent_executor
from .middleware import (
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    TimingMiddleware,
    apply_middleware,
)
from .prompt_templates import SUBAGENT_TASK_TEMPLATES, load_prompt_template
from .utils import _retry_with_backoff, _is_task_revoked, _format_subagent_prompt

logger = logging.getLogger(__name__)


def _get_task_template(task_type: str, stage_config: SubagentStageConfig) -> str:
    if stage_config.task_template:
        loaded = load_prompt_template(stage_config.task_template)
        if loaded:
            return loaded
    return SUBAGENT_TASK_TEMPLATES.get(task_type, "")


def _run_subagent_core(
    stage_config: SubagentStageConfig,
    task_type: str,
    stage: str,
    article_id: int | None,
    call_fn: Callable[[], Any],
    response_model: Type[BaseModel],
    self_correct: bool = False,
    messages: list[dict] | None = None,
) -> SubagentResponse:
    """Core subagent execution with retry/timeout logic.

    Handles executor submission, timeout, retry with backoff, error handling,
    metrics emission, and response construction.

    Args:
        stage_config: Resolved subagent stage configuration.
        task_type: The task type identifier.
        stage: The pipeline stage name.
        article_id: Optional article ID for logging.
        call_fn: Callable that makes the LLM call (submitted to executor).
        response_model: Pydantic model for response validation.
        self_correct: Whether to attempt self-correction on validation errors.
        messages: Mutable messages list for self-correction (required if self_correct=True).
    """
    from . import get_metrics, log_pipeline_event

    result = None
    used_fallback = False
    fallback_stages: list[str] = []
    last_exc: BaseException | None = None
    corrected = False
    future = None

    def _attempt() -> Any:
        nonlocal corrected, future
        from . import time_histogram

        if _is_task_revoked():
            logger.info("Subagent %s/%s cancelled - task revoked", stage, task_type)
            raise ProviderTimeoutError("Subagent task revoked")

        with time_histogram(
            "subagent.duration_seconds",
            labels={"stage": stage, "task_type": task_type},
        ):
            future = _subagent_executor.submit(call_fn)
            try:
                resp = future.result(timeout=stage_config.timeout_seconds)

                if self_correct and messages is not None:
                    try:
                        return response_model.model_validate(
                            {"synthesis": resp.text},
                        )
                    except (json.JSONDecodeError, ValidationError) as validation_err:
                        if corrected:
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
                        corrected = True
                        raise  # Trigger retry

                return resp
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

    try:
        result = _retry_with_backoff(
            _attempt,
            max_retries=stage_config.max_retries + 1,
            base_delay=1.0,
            max_delay=stage_config.retry_delay,
            retryable_exceptions=(ProviderTimeoutError, ValidationError, TimeoutError, ConnectionError),
        )
    except (ProviderTimeoutError, ValidationError, TimeoutError, ConnectionError) as e:
        last_exc = e
        logger.error(
            "Subagent %s/%s failed after %d attempts: %s",
            stage,
            task_type,
            stage_config.max_retries + 1,
            e,
        )
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
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        last_exc = e
        logger.error(
            "Subagent %s/%s unexpected error: %s — using fallback",
            stage,
            task_type,
            e,
        )
        used_fallback = True
        fallback_stages = [stage]
    finally:
        if future:
            future.cancel()

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
        prompt_data_escaped = escape_prompt_data(prompt_data)
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

    # Initialize tool registry with stage-aware tool selection
    from services.tool_selection import StageAwareToolSelector
    from .registry import initialize_tool_registry

    tools = None
    if stage_config.tools:
        selector = StageAwareToolSelector(tool_names=stage_config.tools)
        tools = initialize_tool_registry(selector=selector, context={"stage": stage})

    def _call_with_timeout() -> Any:
        from . import traced_llm_call

        with traced_llm_call(provider=provider.provider_id, model=model, stage=stage):
            if tools:
                # Use chat_with_tools for tool-calling support
                max_iterations = getattr(stage_config, 'max_iterations', 5)
                tc_resp = provider.chat_with_tools(
                    messages=[{"role": "user", "content": prompt}],
                    tools=tools,
                    tool_choice=None,
                    model=model,
                    system=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_iterations=max_iterations,
                )
                # Validate tool-calling response against response_model
                try:
                    return response_model.model_validate(
                        {"synthesis": tc_resp.text},
                    )
                except ValidationError as e:
                    logger.warning(
                        "Subagent %s/%s validation error on tool-calling response: %s",
                        stage,
                        task_type,
                        e,
                    )
                    raise
            else:
                return provider.chat_structured(
                    messages=[{"role": "user", "content": prompt}],
                    response_model=response_model,
                    model=model,
                    system=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

    return _run_subagent_core(
        stage_config=stage_config,
        task_type=task_type,
        stage=stage,
        article_id=article_id,
        call_fn=_call_with_timeout,
        response_model=response_model,
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
    prompt = _format_subagent_prompt(template, prompt_data, stage, task_type)
    if prompt is None:
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

    # Apply token budgeting to prevent context overflow
    from services.prompts import _budget_tokens
    prompt = _budget_tokens(prompt, model, max_tokens)

    middleware_chain = [
        LoggingMiddleware(logger),
        TimingMiddleware(logger),
        ErrorHandlingMiddleware(logger),
    ]
    for i, tool in enumerate(tools):
        if tool.fn:
            wrapped_fn = apply_middleware(tool.fn, middleware_chain)
            tools[i] = ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                required=tool.required,
                fn=wrapped_fn,
            )

    messages = [{"role": "user", "content": prompt}]
    max_iterations = getattr(stage_config, 'max_iterations', 5)

    def _call_with_timeout() -> Any:
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
                max_iterations=max_iterations,
            )

    return _run_subagent_core(
        stage_config=stage_config,
        task_type=task_type,
        stage=stage,
        article_id=article_id,
        call_fn=_call_with_timeout,
        response_model=response_model,
        self_correct=True,
        messages=messages,
    )
