from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.common import (
    BASE_DIR,
    MAX_TOKENS_FIELD,
    ProviderDef,
    cached_config_with_mtime,
    config_cache_key,
    load_yaml_file,
    resolve_env_var,
)


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    host: str = "http://localhost:11434"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD
    local: bool = False


class OpenAIConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_key: str = Field(default="")
    base_url: str = "https://api.openai.com/v1"
    model: str = Field(..., min_length=1)
    max_tokens: int = MAX_TOKENS_FIELD
    headers: dict[str, str] = Field(default_factory=dict)
    # An endpoint that needs no credential and may live on loopback or a
    # private network: a local inference server such as LM Studio or
    # llama.cpp. Declaring it is an explicit operator statement, and it is
    # what allows the SSRF guard to let a private address through.
    local: bool = False

    @model_validator(mode="after")
    def validate_api_key(self) -> "OpenAIConfig":
        resolved = resolve_env_var(self.api_key, required=True) if self.api_key else ""
        if not resolved and not self.local:
            raise ValueError("api_key must not be empty")
        self.api_key = resolved
        return self


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


def default_providers_path() -> Path:
    """Return the providers file the application reads.

    ``LLM_PROVIDERS_FILE`` overrides the repository default. The variable is
    referenced by the CI smoke environment and by the operator documentation,
    so it has to be honoured here rather than only in the installer.
    """
    override = os.environ.get("LLM_PROVIDERS_FILE")
    if override:
        return Path(override)
    return BASE_DIR / "providers.yaml"


def load_providers_config(
    path: str | Path | None = None,
) -> LLMProvidersConfig:
    resolved = Path(path) if path is not None else default_providers_path()
    return cached_config_with_mtime(
        key=config_cache_key("providers", resolved),
        loader_fn=lambda: _load_providers_config_from_file(resolved),
        config_path=resolved,
    )
