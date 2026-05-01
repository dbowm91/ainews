"""Tool selection strategies for stage-aware tool filtering."""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from services.llm.base import ToolDefinition


class ToolSelector(Protocol):
    """Protocol for tool selection strategies."""

    def select_tools(
        self,
        available_tools: Sequence[ToolDefinition],
        context: dict[str, Any] | None = None,
    ) -> list[ToolDefinition]:
        """Select tools based on strategy.

        Args:
            available_tools: All available tool definitions.
            context: Optional context for selection (e.g., stage name, query).

        Returns:
            List of selected tool definitions.
        """
        ...


class StageAwareToolSelector:
    """Select tools based on stage configuration.

    Builds on existing initialize_tool_registry() pattern.
    """

    def __init__(self, tool_names: list[str] | None = None) -> None:
        """Initialize with optional tool name filter.

        Args:
            tool_names: List of tool names to include. If None, all tools included.
        """
        self.tool_names = tool_names

    def select_tools(
        self,
        available_tools: Sequence[ToolDefinition],
        context: dict[str, Any] | None = None,
    ) -> list[ToolDefinition]:
        """Select tools based on configured tool names.

        Args:
            available_tools: All available tool definitions.
            context: Optional context (unused by this selector).

        Returns:
            Filtered list of tools.
        """
        if self.tool_names is None:
            return list(available_tools)

        tool_name_set = set(self.tool_names)
        return [t for t in available_tools if t.name in tool_name_set]


class KeywordToolSelector:
    """Select tools based on keyword relevance in tool descriptions.

    Simple implementation that boosts tools whose descriptions
    match keywords in the query context.
    """

    def __init__(
        self,
        keyword_map: dict[str, list[str]] | None = None,
        default_tools: list[str] | None = None,
    ) -> None:
        """Initialize with keyword mappings.

        Args:
            keyword_map: Map of keywords to tool names.
                e.g., {"search": ["web_search"], "article": ["get_article_by_id"]}
            default_tools: Tools to include if no keywords match.
        """
        self.keyword_map = keyword_map or {}
        self.default_tools = default_tools or []

    def select_tools(
        self,
        available_tools: Sequence[ToolDefinition],
        context: dict[str, Any] | None = None,
    ) -> list[ToolDefinition]:
        """Select tools based on keyword matching.

        Args:
            available_tools: All available tool definitions.
            context: Dict that may contain 'query' key for keyword matching.

        Returns:
            List of selected tools based on keyword relevance.
        """
        if not context or "query" not in context:
            return self._get_default_tools(available_tools)

        query = context["query"].lower()
        matched_tools: set[str] = set()

        for keyword, tool_names in self.keyword_map.items():
            if keyword.lower() in query:
                matched_tools.update(tool_names)

        if not matched_tools:
            return self._get_default_tools(available_tools)

        return [t for t in available_tools if t.name in matched_tools]

    def _get_default_tools(
        self,
        available_tools: Sequence[ToolDefinition],
    ) -> list[ToolDefinition]:
        """Get default tools if no keywords match."""
        if not self.default_tools:
            return list(available_tools)
        return [t for t in available_tools if t.name in self.default_tools]
