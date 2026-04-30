from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.common import (
    BASE_DIR,
    MAX_TOKENS_FIELD,
    ProviderDef,
    cached_config,
    load_yaml_file,
    resolve_env_var,
)


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    host: str = "http://localhost:11434"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD


class OpenAIConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_key: str = Field(..., min_length=1)
    base_url: str = "https://api.openai.com/v1"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        resolved = resolve_env_var(v, required=True)
        if not resolved:
            raise ValueError("api_key must not be empty")
        return resolved


class AnthropicConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_key: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        resolved = resolve_env_var(v, required=True)
        if not resolved:
            raise ValueError("api_key must not be empty")
        return resolved


class GeminiConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_key: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        resolved = resolve_env_var(v, required=True)
        if not resolved:
            raise ValueError("api_key must not be empty")
        return resolved


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
    from schemas.common import resolve_env_vars

    raw = resolve_env_vars(raw)
    return LLMProvidersConfig(**raw)


def load_providers_config(
    path: str | Path = BASE_DIR / "providers.yaml",
) -> LLMProvidersConfig:
    return cached_config(
        key="providers",
        loader_fn=lambda: _load_providers_config_from_file(path),
    )
