from __future__ import annotations

import time

import requests

from ainews_cli.providers.base import TIMEOUT_DEFAULTS, BaseProviderAdapter
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
        config: dict = {
            "base_url": endpoint.base_url,
            "organization": values.get("organization", ""),
        }
        model = values.get("model")
        if model:
            config["model"] = model
        headers = values.get("headers") or {}
        if isinstance(headers, dict) and headers:
            config["headers"] = {str(k): str(v) for k, v in headers.items()}
        return ProviderDefinition(
            id=values.get("id", "openai"),
            type_id=self.type_id,
            display_name=self.display_name,
            endpoint=endpoint,
            enabled=values.get("enabled", True),
            is_default=values.get("is_default", False),
            config=config,
            env_vars={"OPENAI_API_KEY": api_key},
        )

    def _request_headers(
        self, definition: ProviderDefinition, credentials: dict
    ) -> dict[str, str]:
        """Authorization plus whatever custom headers the provider declares.

        Some OpenAI-compatible gateways require a routing header of their own
        -- an account or session id -- and reject a request without it. The
        application sends those headers when it calls the provider, so the
        probe has to send them too or it would report a working provider as
        broken.
        """
        api_key = credentials.get("api_key", "")
        headers = {"Authorization": f"Bearer {api_key}"}
        extra = definition.config.get("headers") or {}
        if isinstance(extra, dict):
            headers.update(
                {str(k): str(v) for k, v in extra.items() if v is not None and str(v) != ""}
            )
        return headers

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        url = f"{definition.endpoint.base_url}/models"
        headers = self._request_headers(definition, credentials)
        result = self.probe_with_timeout(url, headers=headers)
        if result.status_code in (404, 405):
            # The endpoint does not implement /models. That is normal for an
            # OpenAI-compatible gateway, and it says nothing about whether
            # the provider can serve a request. Prove it with a completion.
            return self._probe_with_completion(definition, credentials, headers)
        return result

    def _probe_with_completion(
        self,
        definition: ProviderDefinition,
        credentials: dict,
        headers: dict[str, str],
    ) -> ProviderProbeResult:
        """Verify a provider with one minimal completion.

        A reasoning model can spend the whole (small) token budget thinking
        and return an empty message, so success is judged on the response
        being well formed -- HTTP 200 with a choice -- not on the text.
        """
        url = f"{definition.endpoint.base_url}/chat/completions"
        model = definition.config.get("model") or credentials.get("model") or ""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 16,
        }
        start = time.monotonic()
        try:
            resp = requests.post(
                url,
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
                timeout=(TIMEOUT_DEFAULTS["connect"], TIMEOUT_DEFAULTS["read"]),
            )
            elapsed = (time.monotonic() - start) * 1000
            if resp.status_code >= 400:
                return ProviderProbeResult(
                    success=False,
                    latency_ms=elapsed,
                    error=f"Completion failed: HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    endpoint_resolved=True,
                    auth_success=resp.status_code not in (401, 403),
                    remediation=[
                        "Check the endpoint URL and the model name.",
                        "Verify the API key has access to the model.",
                    ],
                )
            body = resp.json()
            if not body.get("choices"):
                return ProviderProbeResult(
                    success=False,
                    latency_ms=elapsed,
                    error="Completion response contained no choices",
                    status_code=resp.status_code,
                    endpoint_resolved=True,
                )
            return ProviderProbeResult(
                success=True,
                latency_ms=elapsed,
                endpoint_resolved=True,
                auth_success=True,
                status_code=resp.status_code,
            )
        except requests.Timeout:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderProbeResult(
                success=False,
                latency_ms=elapsed,
                error="Request timed out",
                remediation=[
                    "Check your network connection.",
                    "Verify the endpoint URL is correct and reachable.",
                ],
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
        url = f"{definition.endpoint.base_url}/models"
        headers = self._request_headers(definition, credentials)

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
