from __future__ import annotations

from typing import Any

from ainews_cli.sources.models import SourceTestResult


_SOURCE_ADAPTERS: dict[str, type] = {}


def register_source_adapter(type_id: str) -> Any:
    """Decorator to register a source adapter class."""
    def decorator(cls: type) -> type:
        _SOURCE_ADAPTERS[type_id] = cls
        return cls
    return decorator


def get_source_adapter(type_id: str) -> Any:
    """Get a source adapter instance by type ID."""
    if type_id not in _SOURCE_ADAPTERS:
        raise KeyError(f"Unknown source type: {type_id!r}. Known: {sorted(_SOURCE_ADAPTERS)}")
    return _SOURCE_ADAPTERS[type_id]()


def list_source_adapters() -> list[dict[str, str]]:
    """List all registered source adapter types."""
    adapters = []
    for tid, cls in _SOURCE_ADAPTERS.items():
        adapter = cls()
        adapters.append({
            "type_id": tid,
            "display_name": adapter.metadata.display_name,
            "description": adapter.metadata.description,
        })
    return adapters


def test_source_by_type(type_id: str, config: dict[str, Any]) -> SourceTestResult:
    """Test a source using its adapter."""
    adapter = get_source_adapter(type_id)
    from ainews_cli.sources.models import SourceDefinition
    definition = SourceDefinition(
        id=config.get("id", "test"),
        name=config.get("name", "Test"),
        type=type_id,
        config=config.get("config", {}),
    )
    return adapter.test_source(definition)
