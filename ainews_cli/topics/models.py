from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TopicDefinition:
    """A topic configuration definition."""
    id: str
    display_name: str
    description: str
    color: str = "blue"
    icon: str | None = None
    query: str = ""
    keywords: list[str] = field(default_factory=list)
    # Computed fields
    requires_restart: bool = False
    article_count: int = 0


@dataclass
class TopicTestResult:
    """Result of validating a topic configuration."""
    topic_id: str
    success: bool
    message: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class TopicMutationResult:
    """Result of a topic mutation operation."""
    success: bool
    topic_id: str | None = None
    operation: str = ""  # "add", "update", "remove"
    message: str = ""
    requires_restart: bool = False
    diff: list[dict[str, str]] = field(default_factory=list)
