from __future__ import annotations

from urllib.parse import urlparse

import requests

from ainews_cli.providers.base import BaseProviderAdapter
from ainews_cli.providers.protocol import (
    ModelDiscoveryResult,
    ModelInfo,
    ProviderDefinition,
    ProviderEndpoint,
    ProviderInputField,
    ProviderProbeResult,
)

_DEFAULT_ENDPOINT = "http://localhost:11434"
_DOCKER_ENV_VAR = "AINEWS_RUNNING_IN_DOCKER"


class OllamaProviderAdapter(BaseProviderAdapter):
    type_id = "ollama"
    display_name = "Ollama"

    def fields(self) -> list[ProviderInputField]:
        return [
            ProviderInputField(
                name="endpoint",
                label="Ollama Endpoint",
                description="Base URL for the Ollama API",
                field_type="url",
                default=_DEFAULT_ENDPOINT,
                env_var="OLLAMA_HOST",
            ),
            ProviderInputField(
                name="model_prefix",
                label="Model Prefix",
                description="Optional prefix for model IDs (e.g. 'ollama/')",
                field_type="text",
                required=False,
                default="",
            ),
        ]

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint:
        url = context.get("endpoint", _DEFAULT_ENDPOINT).rstrip("/")
        parsed = urlparse(url)
        display = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 11434}"
        return ProviderEndpoint(
            base_url=url,
            display_url=display,
            api_type="ollama",
        )

    def build_definition(self, values: dict) -> ProviderDefinition:
        endpoint = self.normalize_endpoint(values)
        return ProviderDefinition(
            id=values.get("id", "ollama-local"),
            type_id=self.type_id,
            display_name=self.display_name,
            endpoint=endpoint,
            enabled=values.get("enabled", True),
            is_default=values.get("is_default", False),
            config={
                "base_url": endpoint.base_url,
                "model_prefix": values.get("model_prefix", ""),
            },
            env_vars={},
        )

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        url = f"{definition.endpoint.base_url}/api/tags"
        warning = self.docker_localhost_warning(definition.endpoint.base_url)
        result = self.probe_with_timeout(url, total_timeout=5)

        if warning and not result.success:
            result.remediation = result.remediation or []
            result.remediation.insert(0, warning)

        return result

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult:
        url = f"{definition.endpoint.base_url}/api/tags"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            return ModelDiscoveryResult(
                success=False,
                error=str(exc),
                provenance="discovered",
            )

        models_data = data.get("models", [])
        models: list[ModelInfo] = []
        for m in models_data:
            name = m.get("name", "")
            if not name:
                continue
            models.append(
                ModelInfo(
                    id=name,
                    display_name=name,
                    provider_type=self.type_id,
                    discovered=True,
                )
            )

        if not models:
            return ModelDiscoveryResult(
                success=True,
                models=[],
                error="No models found. Pull models with: ollama pull <model>",
                provenance="discovered",
            )

        return ModelDiscoveryResult(
            success=True,
            models=models,
            provenance="discovered",
        )

    def remediation(self, error: Exception) -> list[str]:
        msg = str(error).lower()
        hints: list[str] = []
        if "connection refused" in msg:
            hints.append("Ensure Ollama is running: ollama serve")
            hints.append(self.docker_localhost_warning(_DEFAULT_ENDPOINT) or "")
        if "not found" in msg:
            hints.append("Pull the model: ollama pull <model-name>")
        return [h for h in hints if h]
