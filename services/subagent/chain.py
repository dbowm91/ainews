from __future__ import annotations

import json
import logging
from concurrent.futures import TimeoutError
from typing import Any

from pydantic import ValidationError

from services.llm.errors import ProviderTimeoutError

from .conditions import _evaluate_condition
from .config import _get_subagent_provider_and_config, _subagent_executor
from .utils import _retry_with_backoff

logger = logging.getLogger(__name__)


def _resolve_template_variables(
    template: str, initial_data: dict, results: dict[str, Any],
) -> dict:
    """Resolve template variables, including references to previous step results."""
    resolved = dict(initial_data)
    for key, value in resolved.items():
        if isinstance(value, str) and "{" in value:
            try:
                resolved[key] = value.format(**results)
            except (KeyError, ValueError, AttributeError) as e:
                logger.warning(
                    "Template resolution failed for key '%s': %s",
                    key, e,
                )
    return resolved


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
    from schemas.pipeline import load_pipeline_config, resolve_subagent_config

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
            except (ValueError, KeyError, AttributeError) as e:
                logger.error(
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
                template, initial_prompt_data, results,
            )
            from utils.text import escape_prompt_data

            prompt_data_escaped = escape_prompt_data(prompt_data)
            prompt = template.format(**prompt_data_escaped)
        except (KeyError, ValueError, AttributeError) as e:
            logger.error(
                "Chain %s step %d template error: %s",
                chain_name,
                i,
                e,
            )
            results[step_name] = {"synthesis": "", "used_fallback": True}
            continue

        system_prompt = stage_config.system_prompt or ""
        provider, model, max_tokens, temperature = _get_subagent_provider_and_config(
            stage_config, default_role="editor",
        )

        def _chain_call():
            return provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        step_succeeded = False
        try:
            resp = _retry_with_backoff(
                lambda: _subagent_executor.submit(_chain_call).result(
                    timeout=stage_config.timeout_seconds
                ),
                max_retries=stage_config.max_retries + 1,
                base_delay=1.0,
                max_delay=stage_config.retry_delay,
                retryable_exceptions=(ProviderTimeoutError, TimeoutError),
            )
            step_succeeded = True
        except (ProviderTimeoutError, TimeoutError) as e:
            logger.warning(
                "Chain %s step %d failed after %d attempts: %s",
                chain_name,
                i,
                stage_config.max_retries + 1,
                e,
            )
            results[step_name] = {
                "synthesis": f"[Fallback: {e}]",
                "used_fallback": True,
                }
        except (ImportError, TimeoutError, ProviderTimeoutError,
                ValidationError, json.JSONDecodeError,
                ValueError, AttributeError) as e:
            logger.error(
                "Chain %s step %d unexpected error: %s",
                chain_name,
                i,
                e,
            )
            results[step_name] = {
                "synthesis": f"[Fallback: {e}]",
                "used_fallback": True,
            }

        if step_succeeded:
            results[step_name] = {"synthesis": resp.text, "used_fallback": False}

    all_fallback = all(r.get("used_fallback", False) for r in results.values())

    return {
        "results": results,
        "used_fallback": all_fallback,
        "fallback_stages": list(results.keys()) if all_fallback else [],
    }
