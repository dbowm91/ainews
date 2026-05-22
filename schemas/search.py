from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from schemas.common import BASE_DIR, ProviderDef, cached_config_with_mtime, load_yaml_file


class SearchConfig(BaseModel):
    providers: list[ProviderDef] = Field(default_factory=list)
    default_provider: str = "duckduckgo"


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
    return SearchConfig(providers=providers, default_provider=default)


def load_search_config(
    path: str | Path = BASE_DIR / "providers.yaml",
) -> SearchConfig:
    config_path = BASE_DIR / "providers.yaml"
    return cached_config_with_mtime(
        key="search_config",
        loader_fn=lambda: _load_search_config_from_file(path),
        config_path=config_path,
    )
