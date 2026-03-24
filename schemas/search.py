from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
import yaml

BASE_DIR = Path(__file__).parent.parent


class SearchProviderDef(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_\-]+$")
    type: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class SearchConfig(BaseModel):
    providers: list[SearchProviderDef] = Field(default_factory=list)
    default_provider: str = "duckduckgo"


def _load_search_config_from_file(path: str | Path) -> SearchConfig:
    p = Path(path)
    if not p.exists():
        return SearchConfig(providers=[
            SearchProviderDef(id="duckduckgo", type="duckduckgo", enabled=True)
        ])
    raw = yaml.safe_load(p.read_text()) or {}
    search_raw = raw.get("search_providers", [])
    default = raw.get("default_search_provider", "duckduckgo")
    providers = [SearchProviderDef(**entry) for entry in search_raw]
    return SearchConfig(providers=providers, default_provider=default)


def load_search_config(
    path: str | Path = BASE_DIR / "providers.yaml",
) -> SearchConfig:
    try:
        from services.config_cache import get_config_cache
        return get_config_cache().get(
            key="search_config",
            loader_fn=lambda: _load_search_config_from_file(path),
            ttl=300,
        )
    except Exception:
        return _load_search_config_from_file(path)
