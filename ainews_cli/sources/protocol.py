from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ainews_cli.sources.models import (
    SourceAdapterMetadata,
    SourceDefinition,
    SourceTestResult,
)


@runtime_checkable
class SourceSetupAdapter(Protocol):
    """Protocol for source adapter CLI support."""

    type_id: str
    metadata: SourceAdapterMetadata

    def fields(self) -> list[Any]:
        """Return list of input fields for interactive setup."""
        ...

    def build_definition(self, values: dict[str, Any]) -> SourceDefinition:
        """Build a SourceDefinition from input values."""
        ...

    def test_source(self, definition: SourceDefinition) -> SourceTestResult:
        """Test source connectivity and configuration."""
        ...

    def get_endpoint_summary(self, config: dict[str, Any]) -> str:
        """Return a human-readable summary of the endpoint."""
        ...

    def redact_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return a redacted copy of the config for display."""
        ...

    def opml_repr(self, definition: SourceDefinition) -> dict[str, str] | None:
        """Return OPML attributes if representable, else None."""
        ...

    def from_opml(self, attributes: dict[str, str]) -> dict[str, Any] | None:
        """Build config values from OPML attributes. Returns None if cannot handle."""
        ...
