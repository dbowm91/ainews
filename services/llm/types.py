from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_used: int = 0


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    required: list[str] = field(default_factory=list)
    fn: Optional[Callable[..., Any]] = field(default=None, repr=False)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    id: str
    name: str
    content: str


@dataclass
class ToolCallingResponse:
    text: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: int = 0


class BatchError(Exception):
    def __init__(self, errors: list[Optional[Exception]], results: list):
        self.errors = errors
        self.results = results
        failed = sum(1 for e in errors if e is not None)
        super().__init__(f"{failed}/{len(errors)} calls failed")