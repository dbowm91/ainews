from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from schemas.pipeline import SubagentStageConfig
from services.llm import get_provider_for_role

SUBAGENT_WORKERS = int(os.environ.get("SUBAGENT_WORKERS", "8"))
_subagent_executor = ThreadPoolExecutor(max_workers=SUBAGENT_WORKERS, thread_name_prefix="subagent")


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
