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

_CATALOG_MODELS: list[dict[str, object]] = [
    {"id": "gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "context_window": 1048576, "supports_tools": True},
    {"id": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "context_window": 1048576, "supports_tools": True},
    {"id": "gemini-2.0-flash", "display_name": "Gemini 2.0 Flash", "context_window": 1048576, "supports_tools": True},
    {"id": "gemini-1.5-pro", "display_name": "Gemini 1.5 Pro", "context_window": 2097152, "supports_tools": True},
    {"id": "gemini-1.5-flash", "display_name": "Gemini 1.5 Flash", "context_window": 1048576, "supports_tools": True},
]


class GeminiProviderAdapter(BaseProviderAdapter):
    type_id = "gemini"
    display_name = "Google Gemini"

    def fields(self) -> list[ProviderInputField]:
        return [
            ProviderInputField(
                name="api_key",
                label="API Key",
                description="Google AI API key",
                field_type="password",
                required=True,
                env_var="GOOGLE_API_KEY",
                sensitive=True,
            ),
        ]

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint:
        return ProviderEndpoint(
            base_url="https://generativelanguage.googleapis.com",
            display_url="https://generativelanguage.googleapis.com",
            api_type="gemini",
        )

    def build_definition(self, values: dict) -> ProviderDefinition:
        endpoint = self.normalize_endpoint(values)
        api_key = values.get("api_key", "")
        return ProviderDefinition(
            id=values.get("id", "gemini"),
            type_id=self.type_id,
            display_name=self.display_name,
            endpoint=endpoint,
            enabled=values.get("enabled", True),
            is_default=values.get("is_default", False),
            config={
                "base_url": endpoint.base_url,
            },
            env_vars={"GOOGLE_API_KEY": api_key},
        )

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        api_key = credentials.get("api_key", "")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"?key={api_key}"
        )
        import time
        import requests as _req

        start = time.monotonic()
        try:
            resp = _req.get(url, timeout=10)
            elapsed = (time.monotonic() - start) * 1000
            if resp.status_code in (400, 401, 403):
                return ProviderProbeResult(
                    success=False,
                    latency_ms=elapsed,
                    error=f"Authentication failed: HTTP {resp.status_code}",
                    endpoint_resolved=True,
                    auth_success=False,
                    remediation=[
                        "Verify your GOOGLE_API_KEY is correct.",
                        "Ensure the Generative Language API is enabled in your Google Cloud project.",
                    ],
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
            )

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult:
        api_key = credentials.get("api_key", "")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"?key={api_key}"
        )

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
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
                timestamp="google-gemini-catalog-v1",
            )

        raw_models = data.get("models", [])
        models = []
        for m in raw_models:
            name = m.get("name", "")
            if not name:
                continue
            model_id = name.split("/")[-1] if "/" in name else name
            models.append(
                ModelInfo(
                    id=model_id,
                    display_name=m.get("displayName", model_id),
                    provider_type=self.type_id,
                    discovered=True,
                )
            )

        if not models:
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
            )

        return ModelDiscoveryResult(
            success=True,
            models=models,
            provenance="discovered",
        )

    def remediation(self, error: Exception) -> list[str]:
        msg = str(error).lower()
        hints: list[str] = []
        if "401" in msg or "unauthorized" in msg or "403" in msg:
            hints.append("Verify your GOOGLE_API_KEY is correct.")
            hints.append("Enable the Generative Language API in your Google Cloud project.")
        if "429" in msg or "rate limit" in msg:
            hints.append("You are being rate-limited. Wait and retry.")
        return hints or [str(error)]
