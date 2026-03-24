from __future__ import annotations
import os
from pathlib import Path
from pydantic import BaseModel, Field
import yaml

BASE_DIR = Path(__file__).parent.parent


class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = Field(..., min_length=1)
    max_tokens: int = Field(default=4096, ge=256, le=128000)


class OpenAIConfig(BaseModel):
    api_key: str = Field(..., min_length=1)
    base_url: str = "https://api.openai.com/v1"
    model: str = Field(..., min_length=1)
    max_tokens: int = Field(default=4096, ge=256, le=128000)


class AnthropicConfig(BaseModel):
    api_key: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = Field(default=4096, ge=256, le=128000)


ADAPTER_CONFIGS: dict[str, type[BaseModel]] = {
    "ollama": OllamaConfig,
    "openai": OpenAIConfig,
    "anthropic": AnthropicConfig,
}


class LLMProviderDef(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_\-]+$")
    type: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class LLMProvidersConfig(BaseModel):
    providers: list[LLMProviderDef] = Field(default_factory=list)
    default_provider: str = "ollama-local"


def _resolve_env_vars(config: dict) -> dict:
    resolved = {}
    for key, val in config.items():
        if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
            env_key = val[2:-1]
            resolved[key] = os.environ.get(env_key, val)
        else:
            resolved[key] = val
    return resolved


def _load_providers_config_from_file(path: str | Path) -> LLMProvidersConfig:
    p = Path(path)
    if not p.exists():
        return LLMProvidersConfig()
    raw = yaml.safe_load(p.read_text()) or {}
    return LLMProvidersConfig(**raw)


def load_providers_config(
    path: str | Path = BASE_DIR / "providers.yaml",
) -> LLMProvidersConfig:
    try:
        from services.config_cache import get_config_cache
        return get_config_cache().get(
            key="providers",
            loader_fn=lambda: _load_providers_config_from_file(path),
            ttl=300,
        )
    except Exception:
        return _load_providers_config_from_file(path)
