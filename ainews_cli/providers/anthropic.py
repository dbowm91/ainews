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

_DEFAULT_BASE_URL = "https://api.anthropic.com"

_CATALOG_MODELS: list[dict[str, object]] = [
    {"id": "claude-opus-4-20250514", "display_name": "Claude Opus 4", "context_window": 200000, "supports_tools": True},
    {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4", "context_window": 200000, "supports_tools": True},
    {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet", "context_window": 200000, "supports_tools": True},
    {"id": "claude-3-5-haiku-20241022", "display_name": "Claude 3.5 Haiku", "context_window": 200000, "supports_tools": True},
    {"id": "claude-3-opus-20240229", "display_name": "Claude 3 Opus", "context_window": 200000, "supports_tools": True},
    {"id": "claude-3-sonnet-20240229", "display_name": "Claude 3 Sonnet", "context_window": 200000, "supports_tools": True},
    {"id": "claude-3-haiku-20240307", "display_name": "Claude 3 Haiku", "context_window": 200000, "supports_tools": True},
]


class AnthropicProviderAdapter(BaseProviderAdapter):
    type_id = "anthropic"
    display_name = "Anthropic"

    def fields(self) -> list[ProviderInputField]:
        return [
            ProviderInputField(
                name="api_key",
                label="API Key",
                description="Anthropic API key",
                field_type="password",
                required=True,
                env_var="ANTHROPIC_API_KEY",
                sensitive=True,
            ),
            ProviderInputField(
                name="base_url",
                label="Base URL",
                description="API base URL",
                field_type="url",
                default=_DEFAULT_BASE_URL,
            ),
        ]

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint:
        url = context.get("base_url", _DEFAULT_BASE_URL).rstrip("/")
        return ProviderEndpoint(
            base_url=url,
            display_url=url,
            api_type="anthropic",
        )

    def build_definition(self, values: dict) -> ProviderDefinition:
        endpoint = self.normalize_endpoint(values)
        api_key = values.get("api_key", "")
        return ProviderDefinition(
            id=values.get("id", "anthropic"),
            type_id=self.type_id,
            display_name=self.display_name,
            endpoint=endpoint,
            enabled=values.get("enabled", True),
            is_default=values.get("is_default", False),
            config={
                "base_url": endpoint.base_url,
            },
            env_vars={"ANTHROPIC_API_KEY": api_key},
        )

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        url = f"{definition.endpoint.base_url}/v1/messages"
        api_key = credentials.get("api_key", "")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }
        import time

        start = time.monotonic()
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            elapsed = (time.monotonic() - start) * 1000
            if resp.status_code in (401, 403):
                return ProviderProbeResult(
                    success=False,
                    latency_ms=elapsed,
                    error=f"Authentication failed: HTTP {resp.status_code}",
                    endpoint_resolved=True,
                    auth_success=False,
                    remediation=[
                        "Verify your ANTHROPIC_API_KEY is correct.",
                        "Check API key permissions.",
                    ],
                )
            if resp.status_code == 400:
                return ProviderProbeResult(
                    success=True,
                    latency_ms=elapsed,
                    endpoint_resolved=True,
                    auth_success=True,
                )
            if resp.status_code < 500:
                return ProviderProbeResult(
                    success=True,
                    latency_ms=elapsed,
                    endpoint_resolved=True,
                    auth_success=True,
                )
            return ProviderProbeResult(
                success=False,
                latency_ms=elapsed,
                error=f"Server error: HTTP {resp.status_code}",
            )
        except (requests.RequestException, ValueError) as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderProbeResult(
                success=False,
                latency_ms=elapsed,
                error=self.sanitize_error(exc),
                remediation=["Check network connectivity to api.anthropic.com."],
            )

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult:
        models: list[ModelInfo] = []
        for m in _CATALOG_MODELS:
            models.append(
                ModelInfo(
                    id=m["id"],  # type: ignore[arg-type]
                    display_name=m["display_name"],  # type: ignore[arg-type]
                    provider_type=self.type_id,
                    discovered=False,
                    context_window=m.get("context_window"),  # type: ignore[arg-type]
                    supports_tools=m.get("supports_tools"),  # type: ignore[arg-type]
                )
            )

        return ModelDiscoveryResult(
            success=True,
            models=models,
            provenance="catalog",
            timestamp="anthropic-catalog-v1",
        )

    def remediation(self, error: Exception) -> list[str]:
        msg = str(error).lower()
        hints: list[str] = []
        if "401" in msg or "unauthorized" in msg:
            hints.append("Verify your ANTHROPIC_API_KEY is correct and not expired.")
        if "429" in msg or "rate limit" in msg:
            hints.append("You are being rate-limited. Wait and retry.")
        return hints or [str(error)]
