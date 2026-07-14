from __future__ import annotations

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


class GenericProviderAdapter(BaseProviderAdapter):
    type_id = "generic"
    display_name = "OpenAI-Compatible"

    def fields(self) -> list[ProviderInputField]:
        return [
            ProviderInputField(
                name="base_url",
                label="Base URL",
                description="API base URL (e.g. http://localhost:8000/v1)",
                field_type="url",
                required=True,
            ),
            ProviderInputField(
                name="api_key",
                label="API Key",
                description="Optional API key",
                field_type="password",
                required=False,
                default="",
                sensitive=True,
            ),
            ProviderInputField(
                name="models_path",
                label="Models Path",
                description="Custom path for model listing (default: /v1/models)",
                field_type="text",
                required=False,
                default="/v1/models",
            ),
        ]

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint:
        url = context.get("base_url", "").rstrip("/")
        return ProviderEndpoint(
            base_url=url,
            display_url=url,
            api_type="openai",
        )

    def build_definition(self, values: dict) -> ProviderDefinition:
        endpoint = self.normalize_endpoint(values)
        api_key = values.get("api_key", "")
        return ProviderDefinition(
            id=values.get("id", "generic"),
            type_id=self.type_id,
            display_name=self.display_name,
            endpoint=endpoint,
            enabled=values.get("enabled", True),
            is_default=values.get("is_default", False),
            config={
                "base_url": endpoint.base_url,
                "models_path": values.get("models_path", "/v1/models"),
            },
            env_vars={"GENERIC_API_KEY": api_key} if api_key else {},
        )

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        models_path = definition.config.get("models_path", "/v1/models")
        url = f"{definition.endpoint.base_url}{models_path}"
        api_key = credentials.get("api_key", "")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return self.probe_with_timeout(url, headers=headers or None)

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult:
        models_path = definition.config.get("models_path", "/v1/models")
        url = f"{definition.endpoint.base_url}{models_path}"
        api_key = credentials.get("api_key", "")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = requests.get(url, headers=headers or None, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            return ModelDiscoveryResult(
                success=False,
                error=str(exc),
                provenance="discovered",
            )

        raw_models = data.get("data", [])
        models: list[ModelInfo] = []
        for m in raw_models:
            mid = m.get("id", "")
            if not mid:
                continue
            models.append(
                ModelInfo(
                    id=mid,
                    display_name=mid,
                    provider_type=self.type_id,
                    discovered=True,
                )
            )

        return ModelDiscoveryResult(
            success=True,
            models=models,
            provenance="discovered",
        )

    def remediation(self, error: Exception) -> list[str]:
        msg = str(error).lower()
        hints: list[str] = [
            "OpenAI-compatible endpoints may not support /v1/models listing.",
            "Check the provider documentation for the correct models endpoint.",
        ]
        if "401" in msg or "unauthorized" in msg:
            hints.insert(0, "Verify your API key is correct.")
        if "connection refused" in msg:
            hints.insert(0, "Ensure the provider is running and reachable.")
        return hints
