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

_DEFAULT_BASE_URL = "https://api.openai.com/v1"

_EXCLUDED_MODEL_PATTERNS = ("embedding", "tts", "dall-e", "whisper", "moderation", "ft:")


class OpenAIProviderAdapter(BaseProviderAdapter):
    type_id = "openai"
    display_name = "OpenAI"

    def fields(self) -> list[ProviderInputField]:
        return [
            ProviderInputField(
                name="api_key",
                label="API Key",
                description="OpenAI API key",
                field_type="password",
                required=True,
                env_var="OPENAI_API_KEY",
                sensitive=True,
            ),
            ProviderInputField(
                name="base_url",
                label="Base URL",
                description="API base URL",
                field_type="url",
                default=_DEFAULT_BASE_URL,
            ),
            ProviderInputField(
                name="organization",
                label="Organization",
                description="Optional organization ID",
                field_type="text",
                required=False,
                default="",
            ),
        ]

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint:
        url = context.get("base_url", _DEFAULT_BASE_URL).rstrip("/")
        return ProviderEndpoint(
            base_url=url,
            display_url=url,
            api_type="openai",
        )

    def build_definition(self, values: dict) -> ProviderDefinition:
        endpoint = self.normalize_endpoint(values)
        api_key = values.get("api_key", "")
        return ProviderDefinition(
            id=values.get("id", "openai"),
            type_id=self.type_id,
            display_name=self.display_name,
            endpoint=endpoint,
            enabled=values.get("enabled", True),
            is_default=values.get("is_default", False),
            config={
                "base_url": endpoint.base_url,
                "organization": values.get("organization", ""),
            },
            env_vars={"OPENAI_API_KEY": api_key},
        )

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        url = f"{definition.endpoint.base_url}/models"
        api_key = credentials.get("api_key", "")
        headers = {"Authorization": f"Bearer {api_key}"}
        return self.probe_with_timeout(url, headers=headers)

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult:
        url = f"{definition.endpoint.base_url}/models"
        api_key = credentials.get("api_key", "")
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            resp = requests.get(url, headers=headers, timeout=10)
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
            if any(p in mid.lower() for p in _EXCLUDED_MODEL_PATTERNS):
                continue
            models.append(
                ModelInfo(
                    id=mid,
                    display_name=mid,
                    provider_type=self.type_id,
                    discovered=True,
                    context_window=m.get("context_length"),
                )
            )

        return ModelDiscoveryResult(
            success=True,
            models=models,
            provenance="discovered",
        )

    def remediation(self, error: Exception) -> list[str]:
        msg = str(error).lower()
        hints: list[str] = []
        if "401" in msg or "unauthorized" in msg:
            hints.append("Verify your OPENAI_API_KEY is correct and not expired.")
        if "429" in msg or "rate limit" in msg:
            hints.append("You are being rate-limited. Wait and retry.")
        return hints or [str(error)]
