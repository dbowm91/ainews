from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineRoleAssignment:
    """A pipeline role assignment."""
    role: str  # selector, researcher, writer, editor
    provider: str
    model: str
    enabled: bool = True


@dataclass
class PipelineProfile:
    """A named pipeline configuration profile."""
    id: str
    display_name: str
    description: str
    assignments: dict[str, PipelineRoleAssignment] = field(default_factory=dict)


@dataclass
class PipelineDiffEntry:
    """A single difference in pipeline configuration."""
    role: str
    field: str
    old_value: Any = None
    new_value: Any = None


@dataclass
class PipelineValidationResult:
    """Result of validating pipeline configuration."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    role_details: dict[str, dict[str, Any]] = field(default_factory=dict)
