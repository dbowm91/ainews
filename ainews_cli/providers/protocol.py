from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ProviderInputField:
    name: str
    label: str
    description: str
    field_type: str  # "text", "password", "url", "select", "bool"
    required: bool = True
    default: str | None = None
    options: list[str] | None = None
    env_var: str | None = None
    sensitive: bool = False


@dataclass
class ProviderEndpoint:
    base_url: str
    display_url: str
    api_type: str  # "openai", "anthropic", "ollama", "gemini"


@dataclass
class ProviderDefinition:
    id: str
    type_id: str
    display_name: str
    endpoint: ProviderEndpoint
    enabled: bool = True
    is_default: bool = False
    config: dict[str, Any] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class ProviderProbeResult:
    success: bool
    latency_ms: float | None = None
    error: str | None = None
    remediation: list[str] | None = None
    endpoint_resolved: bool = False
    auth_success: bool = False
    # The HTTP status the probe actually saw. A probe that only reports
    # success or failure cannot tell "the endpoint answered" from "the
    # endpoint does not implement this route".
    status_code: int | None = None


@dataclass
class ModelInfo:
    id: str
    display_name: str
    provider_type: str
    discovered: bool = True
    context_window: int | None = None
    supports_tools: bool | None = None


@dataclass
class ModelDiscoveryResult:
    success: bool
    models: list[ModelInfo] = field(default_factory=list)
    error: str | None = None
    provenance: str = "discovered"  # "discovered", "catalog", "configured"
    timestamp: str | None = None


@runtime_checkable
class ProviderSetupAdapter(Protocol):
    type_id: str
    display_name: str

    def fields(self) -> list[ProviderInputField]: ...

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint: ...

    def build_definition(self, values: dict) -> ProviderDefinition: ...

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult: ...

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult: ...

    def remediation(self, error: Exception) -> list[str]: ...
