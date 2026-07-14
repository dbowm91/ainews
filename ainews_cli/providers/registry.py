from __future__ import annotations

from ainews_cli.providers.anthropic import AnthropicProviderAdapter
from ainews_cli.providers.eggpool import EggPoolProviderAdapter
from ainews_cli.providers.gemini import GeminiProviderAdapter
from ainews_cli.providers.generic import GenericProviderAdapter
from ainews_cli.providers.ollama import OllamaProviderAdapter
from ainews_cli.providers.openai import OpenAIProviderAdapter
from ainews_cli.providers.protocol import (
    ModelDiscoveryResult,
    ProviderDefinition,
    ProviderProbeResult,
    ProviderSetupAdapter,
)

ADAPTERS: dict[str, type[ProviderSetupAdapter]] = {
    "ollama": OllamaProviderAdapter,
    "openai": OpenAIProviderAdapter,
    "anthropic": AnthropicProviderAdapter,
    "gemini": GeminiProviderAdapter,
    "generic": GenericProviderAdapter,
    "eggpool": EggPoolProviderAdapter,
}


def get_adapter(type_id: str) -> ProviderSetupAdapter:
    cls = ADAPTERS.get(type_id)
    if cls is None:
        raise KeyError(f"Unknown provider type: {type_id!r}. Known: {sorted(ADAPTERS)}")
    return cls()


def list_adapters() -> list[dict[str, str]]:
    return [
        {"type_id": tid, "display_name": cls.display_name}
        for tid, cls in ADAPTERS.items()
    ]


def probe_provider(type_id: str, values: dict) -> ProviderProbeResult:
    adapter = get_adapter(type_id)
    definition = adapter.build_definition(values)
    return adapter.probe(definition, values)


def discover_provider_models(
    type_id: str,
    definition: ProviderDefinition,
    credentials: dict,
) -> ModelDiscoveryResult:
    adapter = get_adapter(type_id)
    return adapter.discover_models(definition, credentials)
