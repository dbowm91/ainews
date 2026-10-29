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


def _build_scoped_memory_tools(category_id: str) -> tuple[ToolDefinition, ...]:
    """Bind read-only tools to the calling article's trusted category."""
    from services.memory import memory_get, memory_search

    def search(query: str, scope: str = "combined", limit: int = 8) -> str:
        records = memory_search(
            query[:512], category_id=category_id, scope=scope,
            limit=max(0, min(int(limit), 8)),
        )
        return json.dumps([{
            "id": record.id, "text": record.text[:1200], "scope": "shared" if record.shared else "category",
            "importance": record.importance, "valid_as_of": record.valid_as_of.isoformat() if record.valid_as_of else None,
            "evidence_article_ids": list(record.source_article_ids), "score_reasons": list(record.score_reasons),
        } for record in records])

    def get(ids: list[int]) -> str:
        return json.dumps(memory_get(ids[:8], category_id=category_id, allow_shared=True))

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
    if context and isinstance(context.get("category_id"), str):
        all_tools.extend(_build_scoped_memory_tools(context["category_id"]))
    elif isinstance(selector, StageAwareToolSelector) and selector.tool_names and (
        {"memory_search", "memory_get"} & set(selector.tool_names)
    ):
        all_tools.extend(_build_scoped_memory_tools("uncategorized"))

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
