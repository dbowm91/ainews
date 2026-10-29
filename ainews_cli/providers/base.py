from __future__ import annotations

import os
import re
import time
from urllib.parse import urlparse

import requests

from ainews_cli.providers.protocol import (
    ModelDiscoveryResult,
    ProviderDefinition,
    ProviderEndpoint,
    ProviderInputField,
    ProviderProbeResult,
)

TIMEOUT_DEFAULTS: dict[str, float] = {
    "connect": 3,
    "read": 5,
    "total": 10,
}

_DOCKER_ENV_VAR = "AINEWS_RUNNING_IN_DOCKER"
_MODEL_ID_NORMALIZE_RE = re.compile(r"[^a-z0-9._:-]")


def _probe_endpoint(url: str, timeout: float | None = None) -> tuple[bool, float]:
    timeout = timeout or TIMEOUT_DEFAULTS["total"]
    start = time.monotonic()
    try:
        resp = requests.get(url, timeout=timeout)
        elapsed = (time.monotonic() - start) * 1000
        return resp.status_code < 500, elapsed
    except requests.RequestException:
        elapsed = (time.monotonic() - start) * 1000
        return False, elapsed


def _probe_auth(
    url: str, headers: dict[str, str], timeout: float | None = None
) -> tuple[bool, float]:
    timeout = timeout or TIMEOUT_DEFAULTS["total"]
    start = time.monotonic()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        elapsed = (time.monotonic() - start) * 1000
        return resp.status_code < 500, elapsed
    except requests.RequestException:
        elapsed = (time.monotonic() - start) * 1000
        return False, elapsed


class BaseProviderAdapter:
    type_id: str = ""
    display_name: str = ""

    def fields(self) -> list[ProviderInputField]:
        raise NotImplementedError

    def normalize_endpoint(self, context: dict) -> ProviderEndpoint:
        raise NotImplementedError

    def build_definition(self, values: dict) -> ProviderDefinition:
        raise NotImplementedError

    def probe(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ProviderProbeResult:
        raise NotImplementedError

    def discover_models(
        self, definition: ProviderDefinition, credentials: dict
    ) -> ModelDiscoveryResult:
        raise NotImplementedError

    def remediation(self, error: Exception) -> list[str]:
        return [str(error)]

    def probe_with_timeout(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        total_timeout: float | None = None,
    ) -> ProviderProbeResult:
        ct = connect_timeout or TIMEOUT_DEFAULTS["connect"]
        rt = read_timeout or TIMEOUT_DEFAULTS["read"]
        tt = total_timeout or TIMEOUT_DEFAULTS["total"]

        start = time.monotonic()
        try:
            resp = requests.get(
                url,
                headers=headers or {},
                timeout=(ct, rt),
            )
            elapsed = (time.monotonic() - start) * 1000

            if resp.status_code >= 500:
                return ProviderProbeResult(
                    success=False,
                    latency_ms=elapsed,
                    error=f"Server error: HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    remediation=[
                        "Check provider status page for outages.",
                        "Verify the endpoint URL is correct.",
                    ],
                )

            if resp.status_code == 401 or resp.status_code == 403:
                return ProviderProbeResult(
                    success=False,
                    latency_ms=elapsed,
                    error=f"Authentication failed: HTTP {resp.status_code}",
                    endpoint_resolved=True,
                    auth_success=False,
                    status_code=resp.status_code,
                    remediation=[
                        "Verify your API key is correct and not expired.",
                        "Check that the API key has the required permissions.",
                    ],
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
        except requests.ConnectionError:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderProbeResult(
                success=False,
                latency_ms=elapsed,
                error="Connection refused or unreachable",
                remediation=[
                    "Verify the provider is running.",
                    "Check the endpoint URL.",
                    "Check firewall rules.",
                ],
            )
        except requests.RequestException as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderProbeResult(
                success=False,
                latency_ms=elapsed,
                error=self.sanitize_error(exc),
            )

    @staticmethod
    def sanitize_error(exc: Exception) -> str:
        msg = str(exc)
        msg = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer ***", msg)
        msg = re.sub(r"api[_-]?key[=:]\s*\S+", "api_key=***", msg, flags=re.IGNORECASE)
        return msg

    @staticmethod
    def normalize_model_id(model_id: str) -> str:
        normalized = model_id.strip().lower()
        normalized = _MODEL_ID_NORMALIZE_RE.sub("-", normalized)
        normalized = re.sub(r"-+", "-", normalized)
        return normalized.strip("-")

    @staticmethod
    def docker_localhost_warning(url: str) -> str | None:
        if os.environ.get(_DOCKER_ENV_VAR, "") != "1":
            return None
        parsed = urlparse(url)
        if parsed.hostname in ("localhost", "127.0.0.1"):
            return (
                "WARNING: You are running inside Docker but the endpoint uses "
                "localhost, which refers to the container itself, not the host. "
                "Use 'host.docker.internal' or the Compose service name instead."
            )
        return None

    @staticmethod
    def redact_credentials(text: str) -> str:
        text = re.sub(r"(Bearer\s+)[A-Za-z0-9._-]+", r"\1***", text)
        text = re.sub(
            r"(api[_-]?key[=:]\s*)(\S+)",
            r"\1***",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(Authorization:\s*Bearer\s+)[A-Za-z0-9._-]+",
            r"\1***",
            text,
            flags=re.IGNORECASE,
        )
        return text
