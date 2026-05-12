from __future__ import annotations

import functools
import logging
import threading
from typing import Any

from services.llm.base import ToolDefinition
from services.tool_selection import ToolSelector

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

    all_tools = _get_all_tools_cached()

    with _TOOL_REGISTRY_LOCK:
        if not _TOOL_REGISTRY:
            for tool in all_tools:
                register_tool(tool)

    if selector is not None:
        return selector.select_tools(all_tools, context)

    if tool_names is not None:
        return [t for t in all_tools if t.name in tool_names]
    return list(all_tools)
