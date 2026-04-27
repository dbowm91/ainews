from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from schemas.common import (
    BASE_DIR,
    MAX_TOKENS_FIELD,
    ProviderDef,
    cached_config,
    load_yaml_file,
)


class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD


class OpenAIConfig(BaseModel):
    api_key: str = Field(..., min_length=1)
    base_url: str = "https://api.openai.com/v1"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD


class AnthropicConfig(BaseModel):
    api_key: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD


class GeminiConfig(BaseModel):
    api_key: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD


ADAPTER_CONFIGS: dict[str, type[BaseModel]] = {
    "ollama": OllamaConfig,
    "openai": OpenAIConfig,
    "anthropic": AnthropicConfig,
    "gemini": GeminiConfig,
}


class LLMProvidersConfig(BaseModel):
    providers: list[ProviderDef] = Field(default_factory=list)
    default_provider: str = "ollama-local"


def _load_providers_config_from_file(path: str | Path) -> LLMProvidersConfig:
    p = Path(path)
    if not p.exists():
        return LLMProvidersConfig()
    raw = load_yaml_file(p)
    return LLMProvidersConfig(**raw)


def load_providers_config(
    path: str | Path = BASE_DIR / "providers.yaml",
) -> LLMProvidersConfig:
    return cached_config(
        key="providers",
        loader_fn=lambda: _load_providers_config_from_file(path),
    )
