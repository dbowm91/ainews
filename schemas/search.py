from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.common import BASE_DIR, ProviderDef, cached_config_with_mtime, load_yaml_file


class SearchConfig(BaseModel):
    providers: list[ProviderDef] = Field(default_factory=list)
    default_provider: str = "duckduckgo"
    runtime_fallback_providers: list[str] = Field(default_factory=list)
    runtime_deadline_seconds: float = Field(default=20.0, gt=0, le=120)

    @field_validator("runtime_fallback_providers")
    @classmethod
    def validate_fallback_provider_ids(cls, value: list[str]) -> list[str]:
        if any(not item or item.strip() != item for item in value):
            raise ValueError("runtime fallback provider IDs must be non-empty and trimmed")
        if len(value) != len(set(value)):
            raise ValueError("runtime fallback provider IDs must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_fallback_providers(self) -> "SearchConfig":
        definitions = {provider.id: provider for provider in self.providers}
        for provider_id in self.runtime_fallback_providers:
            definition = definitions.get(provider_id)
            if definition is None or not definition.enabled:
                raise ValueError(
                    f"runtime fallback provider '{provider_id}' must be configured and enabled",
                )
        return self


def _load_search_config_from_file(path: str | Path) -> SearchConfig:
    p = Path(path)
    if not p.exists():
        return SearchConfig(
            providers=[ProviderDef(id="duckduckgo", type="duckduckgo", enabled=True)]
        )
    raw = load_yaml_file(p)
    search_raw = raw.get("search_providers", [])
    default = raw.get("default_search_provider", "duckduckgo")
    providers = [ProviderDef(**entry) for entry in search_raw]
    fallback = raw.get("search_runtime_fallback_providers", [])
    deadline = raw.get("search_runtime_deadline_seconds", 20.0)
    return SearchConfig(
        providers=providers, default_provider=default,
        runtime_fallback_providers=fallback,
        runtime_deadline_seconds=deadline,
    )


def load_search_config(
    path: str | Path = BASE_DIR / "providers.yaml",
) -> SearchConfig:
    config_path = Path(path)
    return cached_config_with_mtime(
        key="search_config",
        loader_fn=lambda: _load_search_config_from_file(path),
        config_path=config_path,
    )
