from __future__ import annotations

# Re-export public API from submodules
from .chain import run_subagent_chain, _resolve_template_variables
from .conditions import _evaluate_condition
from .config import _get_subagent_provider_and_config
from .registry import (
    _TOOL_REGISTRY,
    _get_all_tools_cached,
    get_registered_tools,
    initialize_tool_registry,
    register_tool,
)
from .runner import (
    _SUBAGENT_TASK_TEMPLATES,
    _escape_prompt_data,
    _get_task_template,
    _load_prompt_template,
    run_subagent,
    run_subagent_with_tools,
)
from .tools import (
    _build_context_tools,
    _build_search_tools,
    _context_tool_get_article_by_id,
    _context_tool_get_related_articles,
    _context_tool_get_source_health,
    _context_tool_get_topic_note,
    _context_tool_get_topic_notes_for_topics,
    _context_tool_get_trend_memory,
    _context_tool_search_articles,
    _get_search_provider,
    _search_web,
)

# Backward-compat re-exports from schemas
from schemas.llm_responses import (  # noqa: F401, E402
    EditContextualizationResponse,
    ResearchSynthesisResponse,
    SubagentResponse,
)
from schemas.pipeline import BASE_DIR, SubagentStageConfig, resolve_subagent_config  # noqa: F401, E402

# Re-export services for backward compat with tests that patch these
from services.logging_utils import log_pipeline_event, traced_llm_call  # noqa: F401, E402
from services.metrics import get_metrics, time_histogram  # noqa: F401, E402
from services.llm.base import ToolDefinition  # noqa: F401, E402
from services.llm import get_provider_for_role, get_provider_by_id  # noqa: F401, E402


__all__ = [
    "EditContextualizationResponse",
    "ResearchSynthesisResponse",
    "SubagentResponse",
    "BASE_DIR",
    "SubagentStageConfig",
    "resolve_subagent_config",
    "ToolDefinition",
    "run_subagent",
    "run_subagent_with_tools",
    "run_subagent_chain",
    "initialize_tool_registry",
    "register_tool",
    "get_registered_tools",
    "_evaluate_condition",
    "_get_all_tools_cached",
    "_build_context_tools",
    "_build_search_tools",
    "_context_tool_get_topic_note",
    "_context_tool_get_topic_notes_for_topics",
    "_context_tool_get_related_articles",
    "_context_tool_get_trend_memory",
    "_context_tool_get_article_by_id",
    "_context_tool_search_articles",
    "_context_tool_get_source_health",
    "_search_web",
    "_get_search_provider",
    "_SUBAGENT_TASK_TEMPLATES",
    "_get_task_template",
    "_escape_prompt_data",
    "_load_prompt_template",
    "_resolve_template_variables",
    "_TOOL_REGISTRY",
    "_get_subagent_provider_and_config",
    "log_pipeline_event",
    "traced_llm_call",
    "get_metrics",
    "time_histogram",
    "get_provider_for_role",
    "get_provider_by_id",
]
