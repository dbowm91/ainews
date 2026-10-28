"""Optional in-process Eggsearch provider. The binding is imported only on use."""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from services.search.base import BaseSearchProvider, SearchResult, register_search_provider
from services.search.evidence import SearchEvidence, SearchOutcome, SearchStatus
from utils.url import UnsafeURLError, validate_url_safe

logger = logging.getLogger(__name__)
MAX_SNIPPET_CHARS = 2_000


def _load_native_client(config: dict[str, Any]) -> Any:
    """Construct the optional SDK client without imposing it on base installs."""
    try:
        module = importlib.import_module("eggsearch")
    except (ImportError, OSError) as exc:
        raise RuntimeError("Eggsearch binding unavailable") from exc
    client_type = getattr(module, "AsyncEggsearch", None)
    if client_type is None:
        raise RuntimeError("Eggsearch binding schema mismatch: AsyncEggsearch missing")
    config_path = config.get("config_path")
    if not isinstance(config_path, str) or not config_path.strip():
        raise ValueError("Eggsearch provider requires an explicit config_path")
    configured = Path(config_path).expanduser()
    if not configured.is_absolute():
        raise ValueError("Eggsearch config_path must be an absolute path")
    resolved = configured.resolve()
    if not resolved.is_file():
        raise ValueError("Eggsearch config_path must identify an existing file")
    return client_type(config_path=str(resolved))


def _canonical_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("invalid source URL")
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("source URL must be public HTTP(S)")
    if parts.username is not None or parts.password is not None:
        raise ValueError("source URL must not contain credentials")
    validate_url_safe(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def _parse_published_at(metadata: dict[str, Any]) -> tuple[datetime | None, str]:
    value = metadata.get("published_at")
    if not isinstance(value, str) or not value.strip():
        return None, "unknown"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None, "invalid_timezone"
        return parsed.astimezone(timezone.utc), "source_metadata"
    except ValueError:
        return None, "invalid"


def _retrieval_errors() -> tuple[type[BaseException], ...]:
    errors: tuple[type[BaseException], ...] = (
        ImportError, OSError, RuntimeError, ValueError, TimeoutError, ConnectionError,
        AttributeError, TypeError,
    )
    try:
        module = importlib.import_module("eggsearch")
    except ImportError:
        return errors
    sdk_error = getattr(module, "EggsearchError", None)
    if isinstance(sdk_error, type) and issubclass(sdk_error, BaseException):
        return errors + (sdk_error,)
    return errors


def _request_search(
    factory: Callable[..., Any], config: dict[str, Any], query: str, limit: int,
) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Eggsearch sync bridge cannot run inside an active event loop")

    async def request() -> Any:
        client = factory(config)
        try:
            return await asyncio.wait_for(
                client.web_search(query=query, max_results=limit, response_detail="compact"),
                timeout=float(config.get("timeout_seconds", 20)),
            )
        finally:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                value = close()
                if asyncio.iscoroutine(value):
                    await asyncio.wait_for(value, timeout=2)

    response = asyncio.run(request())
    if not isinstance(response, dict) or not isinstance(response.get("results", []), list):
        raise ValueError("Eggsearch returned an invalid structured response")
    return response


@register_search_provider("eggsearch")
class EggsearchSearchProvider(BaseSearchProvider):
    """Synchronous ainews seam around the SDK's async per-call lifecycle."""

    def __init__(self, provider_id: str, config: dict, client_factory: Callable[..., Any] | None = None):
        super().__init__(provider_id, config)
        self._client_factory = client_factory or _load_native_client
        self.last_outcome = SearchOutcome([], SearchStatus.DISABLED)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return self.search_detailed(query, max_results).results

    def search_detailed(self, query: str, max_results: int = 5) -> SearchOutcome:
        if not self.config.get("enabled", True):
            self.last_outcome = SearchOutcome([], SearchStatus.DISABLED, provider_attempts=(self.provider_id,))
            return self.last_outcome
        limit = max(1, min(int(max_results), 20))
        started = time.monotonic()
        try:
            response = _request_search(self._client_factory, self.config, query, limit)
            raw_results = response.get("results", [])
            retrieval_summary = response.get("retrieval_summary", {})
            if not isinstance(retrieval_summary, dict):
                retrieval_summary = {}
            failures = response.get("providers_failed", retrieval_summary.get("providers_failed", []))
            warnings = response.get("structured_warnings", response.get("warnings", []))
            if not isinstance(failures, list) or not isinstance(warnings, list):
                raise ValueError("Eggsearch returned malformed diagnostics")
            evidence: list[SearchEvidence] = []
            for card in raw_results[:limit]:
                if not isinstance(card, dict):
                    continue
                metadata = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
                try:
                    url = _canonical_url(card.get("url"))
                except (ValueError, UnsafeURLError):
                    continue
                title = card.get("title")
                snippet = card.get("snippet")
                if not isinstance(title, str) or not isinstance(snippet, str):
                    continue
                source_id = card.get("id", card.get("source_id"))
                if not isinstance(source_id, str) or not source_id.strip():
                    source_id = url
                upstream = card.get("provider_id")
                upstream_ids = (upstream,) if isinstance(upstream, str) and upstream else ()
                published_at, date_status = _parse_published_at(metadata)
                evidence.append(SearchEvidence(
                    source_id=source_id[:256], canonical_url=url,
                    title=title[:500], snippet=snippet[:MAX_SNIPPET_CHARS],
                    provider_id=self.provider_id, upstream_provider_ids=upstream_ids,
                    trust_markers=(card.get("trust_markers") if isinstance(card.get("trust_markers"), dict) else {}),
                    published_at=published_at, published_at_status=date_status,
                    snippet_truncated=len(snippet) > MAX_SNIPPET_CHARS,
                ))
            results = [item.to_search_result() for item in evidence]
            retrieval_status = retrieval_summary.get("status")
            partial = (
                bool(failures) or bool(warnings)
                or bool(retrieval_summary.get("has_failures"))
                or retrieval_status in {"provider_failed", "deadline_prevented_completion"}
            )
            status = SearchStatus.PARTIAL if results and partial else (
                SearchStatus.OK if results else SearchStatus.EMPTY if not partial else SearchStatus.FAILED
            )
            capability = response.get("capability_enforcement", {})
            enforcement = capability if isinstance(capability, dict) else {}
            self.last_outcome = SearchOutcome(
                results=results, status=status, provider_attempts=(self.provider_id,),
                provider_failures=tuple(
                    str(item.get("failure_class", "provider_failed"))[:100]
                    if isinstance(item, dict) else "provider_failed"
                    for item in failures[:20]
                ),
                warnings=tuple(
                    str(item.get("code", "provider_warning"))[:100]
                    if isinstance(item, dict) else "provider_warning"
                    for item in warnings[:20]
                ),
                enforced_capabilities={str(k): bool(v) for k, v in enforcement.items()},
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return self.last_outcome
        except _retrieval_errors() as exc:
            logger.warning("Eggsearch retrieval failed (%s)", type(exc).__name__)
            self.last_outcome = SearchOutcome(
                [], SearchStatus.FAILED, provider_attempts=(self.provider_id,),
                provider_failures=(type(exc).__name__,),
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return self.last_outcome
