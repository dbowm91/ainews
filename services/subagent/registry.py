from __future__ import annotations

import functools
import json
import logging
import threading
from typing import Any

from services.llm.base import ToolDefinition
from services.tool_selection import StageAwareToolSelector, ToolSelector

from .tools import _build_context_tools, _build_search_tools

logger = logging.getLogger(__name__)

_TOOL_REGISTRY: dict[str, ToolDefinition] = {}
_TOOL_REGISTRY_LOCK = threading.Lock()


def register_tool(definition: ToolDefinition) -> None:
    """Register a tool definition in the global tool registry."""
    _TOOL_REGISTRY[definition.name] = definition


def get_registered_tools() -> list[ToolDefinition]:
    """Get all registered tool definitions."""
    return list(_TOOL_REGISTRY.values())


@functools.lru_cache(maxsize=1)
def _get_all_tools_cached() -> tuple[ToolDefinition, ...]:
    """Build and cache all tool definitions. Returns tuple for hashability."""
    tools = []
    tools.extend(_build_context_tools())
    tools.extend(_build_search_tools())
    return tuple(tools)


def _build_scoped_memory_tools(
    category_id: str,
    *,
    stage_name: str,
    max_tokens: int,
    max_records: int,
    max_chars: int,
    initial_tokens: int = 0,
) -> tuple[ToolDefinition, ...]:
    """Bind read-only tools to the calling article's trusted category."""
    from services.memory import memory_get, memory_search

    budget = {
        "tokens": max(0, max_tokens - max(0, initial_tokens) - 32),
        "records": max_records,
        "chars": max(0, max_chars - 128),
    }

    def bounded_result(rows: list[dict], *, force_truncated: bool = False) -> str:
        kept: list[dict] = []
        truncated = force_truncated
        for row in rows:
            record_cost = 1 + len(row.get("evidence", [])) + len(row.get("lineage", []))
            if record_cost > budget["records"]:
                truncated = True
                break
            encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            cost_chars = len(encoded)
            cost_tokens = (cost_chars + 2) // 3
            if cost_chars > budget["chars"] or cost_tokens > budget["tokens"]:
                truncated = True
                break
            kept.append(row)
            budget["chars"] -= cost_chars
            budget["tokens"] -= cost_tokens
            budget["records"] -= record_cost
        if len(kept) < len(rows):
            truncated = True
        remaining = min(budget["tokens"], (budget["chars"] + 2) // 3)
        logger.info(
            "Editor memory tool budget stage=%s category=%s records_remaining=%d tokens_remaining=%d truncated=%s",
            stage_name,
            category_id,
            budget["records"],
            remaining,
            truncated,
        )
        return json.dumps({"results": kept, "truncated": truncated, "remaining_budget": remaining}, ensure_ascii=False)

    def search(query: str, scope: str = "combined", limit: int = 8) -> str:
        if budget["records"] <= 0 or budget["tokens"] <= 0 or budget["chars"] <= 0:
            return bounded_result([], force_truncated=True)
        records = memory_search(
            query[:512], category_id=category_id, scope=scope,
            limit=min(max(0, min(int(limit), 8)), budget["records"]),
        )
        return bounded_result([{
            "id": record.id, "text": record.text[:1200], "scope": "shared" if record.shared else "category",
            "importance": record.importance, "valid_as_of": record.valid_as_of.isoformat() if record.valid_as_of else None,
            "evidence_article_ids": list(record.source_article_ids), "score_reasons": list(record.score_reasons),
        } for record in records])

    def get(ids: list[int]) -> str:
        if budget["records"] <= 0 or budget["tokens"] <= 0 or budget["chars"] <= 0:
            return bounded_result([], force_truncated=True)
        return bounded_result(memory_get(
            ids[:min(8, budget["records"])], category_id=category_id, allow_shared=True,
            max_evidence_per_item=3, max_lineage_per_item=3,
        ))

    return (
        ToolDefinition(
            name="memory_search",
            description="Search relevant active editorial memory within the current article category and approved shared index.",
            parameters={"type": "object", "properties": {
                "query": {"type": "string", "maxLength": 512},
                "scope": {"type": "string", "enum": ["own", "shared", "combined"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            }, "required": ["query"]},
            fn=search,
        ),
        ToolDefinition(
            name="memory_get",
            description="Get bounded evidence and lineage for memory IDs returned by memory_search.",
            parameters={"type": "object", "properties": {
                "ids": {"type": "array", "items": {"type": "integer"}, "maxItems": 8},
            }, "required": ["ids"]},
            fn=get,
        ),
    )


def initialize_tool_registry(
    tool_names: list[str] | None = None,
    selector: ToolSelector | None = None,
    context: dict[str, Any] | None = None,
) -> list[ToolDefinition]:
    """Initialize the tool registry with built-in tools, optionally filtered.

    Uses cached tool definitions to avoid rebuilding on every call.

    Args:
        tool_names: Optional list of tool names to include (backward compatible).
        selector: Optional ToolSelector for advanced selection strategies.
        context: Optional context dict passed to selector if provided.

    Returns:
        List of selected ToolDefinition objects.
    """
    global _TOOL_REGISTRY

    all_tools = list(_get_all_tools_cached())
    requested_memory_tools = isinstance(selector, StageAwareToolSelector) and selector.tool_names and (
        {"memory_search", "memory_get"} & set(selector.tool_names)
    )
    from schemas.pipeline import load_pipeline_config

    memory_config = load_pipeline_config().memory
    raw_category = context.get("category_id") if context else None
    trusted_category = isinstance(raw_category, str) and bool(raw_category.strip())
    if memory_config.memory_tools_enabled and trusted_category:
        from services.memory.preflight import ensure_memory_schema
        from services.memory.repository import normalize_category

        category = normalize_category(raw_category)
        if category != "uncategorized":
            ensure_memory_schema()
            tools = _build_scoped_memory_tools(
                category,
                stage_name=str(context.get("stage", "unknown")) if context else "unknown",
                max_tokens=min(
                    memory_config.memory_tool_max_tokens_per_stage,
                    max(
                        0,
                        int(context.get("memory_tool_max_tokens", memory_config.memory_tool_max_tokens_per_stage)),
                    ) if context else memory_config.memory_tool_max_tokens_per_stage,
                ),
                max_records=memory_config.memory_tool_max_records_per_stage,
                max_chars=memory_config.memory_tool_max_chars_per_stage,
                initial_tokens=int(context.get("memory_budget_used_tokens", 0)) if context else 0,
            )
            all_tools.extend(tools)
        elif requested_memory_tools:
            logger.warning("Scoped editor-memory tools withheld: category normalized to uncategorized")
    elif requested_memory_tools:
        logger.info("Scoped editor-memory tools withheld: tools disabled or trusted article category missing")

    if isinstance(selector, StageAwareToolSelector) and selector.tool_names is not None:
        available_names = {tool.name for tool in all_tools} | {"memory_search", "memory_get"}
        unknown = sorted(set(selector.tool_names) - available_names)
        if unknown:
            raise ValueError(
                "Unknown configured subagent tools: " + ", ".join(unknown)
            )

    with _TOOL_REGISTRY_LOCK:
        if not _TOOL_REGISTRY:
            for tool in all_tools:
                register_tool(tool)

    if selector is not None:
        return selector.select_tools(all_tools, context)

    if tool_names is not None:
        return [t for t in all_tools if t.name in tool_names]
    return list(all_tools)
