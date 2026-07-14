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

_DEFAULT_ENDPOINT = "http://eggpool:11300/v1"
_DOCKER_ENV_VAR = "AINEWS_RUNNING_IN_DOCKER"

_ENDPOINT_PRESETS: list[dict[str, str]] = [
    {"label": "Docker Compose network", "value": "http://eggpool:11300/v1"},
    {"label": "Host machine service", "value": "http://host.docker.internal:11300/v1"},
    {"label": "Local development", "value": "http://localhost:11300/v1"},
]


class EggPoolProviderAdapter(BaseProviderAdapter):
    type_id = "eggpool"
    display_name = "EggPool"

    def fields(self) -> list[ProviderInputField]:
        return [
            ProviderInputField(
                name="endpoint",
                label="EggPool Endpoint",
                description="Base URL for the EggPool API",
                field_type="url",
                default=_DEFAULT_ENDPOINT,
            ),
            ProviderInputField(
                name="api_key",
                label="API Key",
                description="EggPool API key",
                field_type="password",
                required=False,
                default="",
                env_var="EGGPOOL_API_KEY",
                sensitive=True,
            ),
            ProviderInputField(
                name="model",
                label="Model",
                description="Model to use (use 'auto' for automatic selection)",
                field_type="text",
                default="auto",
            ),
        ]

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint:
        url = context.get("endpoint", _DEFAULT_ENDPOINT).rstrip("/")
        parsed = urlparse(url)
        display = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 11300}"
        return ProviderEndpoint(
            base_url=url,
            display_url=display,
            api_type="openai",
        )

    def build_definition(self, values: dict) -> ProviderDefinition:
        endpoint = self.normalize_endpoint(values)
        api_key = values.get("api_key", "")
        return ProviderDefinition(
            id=values.get("id", "eggpool"),
            type_id=self.type_id,
            display_name=self.display_name,
            endpoint=endpoint,
            enabled=values.get("enabled", True),
            is_default=values.get("is_default", False),
            config={
                "base_url": endpoint.base_url,
                "model": values.get("model", "auto"),
            },
            env_vars={"EGGPOOL_API_KEY": api_key} if api_key else {},
        )

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        models_url = f"{definition.endpoint.base_url}/models"
        api_key = credentials.get("api_key", "")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        result = self.probe_with_timeout(models_url, headers=headers or None)

        if not result.success:
            health_url = definition.endpoint.base_url.rstrip("/").replace("/v1", "/health")
            health_ok, _ = self.probe_with_timeout(
                health_url, headers=headers or None
            ).success, 0
            if health_ok and result.error and "connection" in result.error.lower():
                result.remediation = result.remediation or []
                result.remediation.insert(
                    0,
                    "EggPool health endpoint is reachable but /v1/models failed. "
                    "Check that the model service is running.",
                )

        warning = self.docker_localhost_warning(definition.endpoint.base_url)
        if warning and not result.success:
            result.remediation = result.remediation or []
            result.remediation.insert(0, warning)

        return result

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult:
        url = f"{definition.endpoint.base_url}/models"
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

        if not models:
            return ModelDiscoveryResult(
                success=True,
                models=[],
                error="No models found on EggPool endpoint",
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
            hints.append("Ensure EggPool is running.")
            hints.append(self.docker_localhost_warning(_DEFAULT_ENDPOINT) or "")
            hints.append("Check endpoint presets: Docker Compose, host machine, or LAN.")
        if "401" in msg or "unauthorized" in msg:
            hints.append("Verify your EGGPOOL_API_KEY is correct.")
        return [h for h in hints if h] or [str(error)]

    @staticmethod
    def endpoint_presets() -> list[dict[str, str]]:
        return list(_ENDPOINT_PRESETS)
