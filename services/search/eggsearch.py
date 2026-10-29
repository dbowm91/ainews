"""Optional in-process Eggsearch provider. The binding is imported only on use."""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from services.search.base import BaseSearchProvider, SearchResult, register_search_provider
from services.search.evidence import ProviderFailure, SearchEvidence, SearchOutcome, SearchStatus
from utils.url import UnsafeURLError, validate_url_safe

logger = logging.getLogger(__name__)
MAX_SNIPPET_CHARS = 2_000
MAX_PROVIDER_RESULTS = 20
URL_FILTER_HEADROOM = 5


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


def _capability_states(raw: Any) -> dict[str, str]:
    """Normalize map/list telemetry without truthiness assumptions."""
    entries: list[tuple[str, Any]] = []
    if isinstance(raw, dict) and any(key.endswith("_count") for key in raw):
        # Compact projection preserves aggregate counts but loses per-capability identity.
        return {}
    if isinstance(raw, dict) and any(
        key in raw for key in ("requested", "enforced", "approximated", "not_enforced")
    ):
        requested = raw.get("requested", [])
        states = {_safe_label(item, "unknown")[:80]: "unknown" for item in requested[:32]} if isinstance(requested, list) else {}
        for category, status in (
            ("enforced", "enforced"), ("approximated", "approximated"),
            ("not_enforced", "not_enforced"),
        ):
            values = raw.get(category, [])
            if isinstance(values, list):
                for item in values[:32]:
                    states[_safe_label(item, "unknown")[:80]] = status
        return states
    if isinstance(raw, dict):
        entries = list(raw.items())[:32]
    elif isinstance(raw, list):
        for item in raw[:32]:
            if isinstance(item, dict):
                name = item.get("capability", item.get("name", item.get("id")))
                if isinstance(name, str):
                    entries.append((name, item.get("status", item.get("state", item.get("enforcement")))))
    states: dict[str, str] = {}
    for key, value in entries:
        state = value.get("status", value.get("state")) if isinstance(value, dict) else value
        if state is True:
            normalized = "enforced"
        elif state is False:
            normalized = "not_enforced"
        elif isinstance(state, str) and state.lower() in {
            "enforced", "approximated", "not_enforced", "unenforced", "unknown",
        }:
            normalized = "not_enforced" if state.lower() == "unenforced" else state.lower()
        else:
            normalized = "unknown"
        states[_safe_label(key, "unknown")[:80]] = normalized
    return states


def _requested_freshness(value: Any) -> bool:
    if isinstance(value, dict):
        return "freshness" in value or "freshness_filter" in value
    return isinstance(value, (list, tuple, set)) and any(
        item in {"freshness", "freshness_filter"} for item in value
    )


def _normalize_requested(value: Any) -> dict[str, tuple[str, ...]]:
    if isinstance(value, dict):
        names = value.get("requested")
        if isinstance(names, list):
            return {"requested": tuple(_safe_label(item, "unknown")[:80] for item in names[:32])}
        return {"requested": tuple(_safe_label(key, "unknown")[:80] for key in list(value)[:32])}
    if isinstance(value, (list, tuple, set)):
        return {"requested": tuple(_safe_label(item, "unknown")[:80] for item in list(value)[:32])}
    return {}


def _safe_label(value: Any, default: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))[:100]
    return label or default


def _sanitize_message(value: Any) -> str:
    message = str(value)[:500]
    message = re.sub(
        r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]", message,
    )
    message = re.sub(
        r"(?i)(authorization)\s*[:=]\s*[^,;]+",
        r"\1=[REDACTED]", message,
    )
    message = re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1[REDACTED]@", message)
    message = re.sub(
        r"(?i)([?&](?:api_?key|token|secret|key)=)[^&#\s]+",
        r"\1[REDACTED]", message,
    )
    return message[:300]


def _is_transient_failure(error_class: str) -> bool:
    normalized = error_class.lower()
    return any(
        marker in normalized
        for marker in ("timeout", "transport", "connection", "unavailable", "rate_limit", "rate limited")
    )


def _provider_failures(raw: list[Any]) -> tuple[ProviderFailure, ...]:
    """Extract a bounded failure summary from native provider entries."""
    return tuple(
        ProviderFailure(
            provider_id=_safe_label(item.get("id", item.get("provider_id", "unknown")), "unknown"),
            error_class=_safe_label(
                item.get("error_class", item.get("failure_class", "unknown")), "unknown",
            ),
            message=_sanitize_message(item.get("message", "")),
            retryable=item.get("retryable") is True,
        )
        for item in raw[:20] if isinstance(item, dict)
    )


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
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Eggsearch sync bridge cannot run inside an active event loop")

    async def request() -> Any:
        budget = timeout_seconds or float(config.get("timeout_seconds", 20))
        deadline = time.monotonic() + budget
        client = factory(config)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Eggsearch request deadline exhausted during setup")
            return await asyncio.wait_for(
                client.web_search(query=query, max_results=limit, response_detail="standard"),
                timeout=remaining,
            )
        finally:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Eggsearch request deadline exhausted before close")
                value = close()
                if asyncio.iscoroutine(value):
                    await asyncio.wait_for(value, timeout=min(2.0, remaining))

    response = asyncio.run(request())
    if not isinstance(response, dict) or not isinstance(response.get("results", []), list):
        raise ValueError("Eggsearch returned an invalid structured response")
    return response


def _map_results(raw_results: Any, provider_id: str, limit: int) -> list[SearchResult]:
    if not isinstance(raw_results, list):
        raise ValueError("Eggsearch returned malformed results")
    evidence: list[SearchEvidence] = []
    for card in raw_results:
        if len(evidence) >= limit:
            break
        if not isinstance(card, dict):
            continue
        metadata = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
        try:
            url = _canonical_url(card.get("url"))
        except (ValueError, UnsafeURLError):
            continue
        title, snippet = card.get("title"), card.get("snippet")
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
            provider_id=provider_id, upstream_provider_ids=upstream_ids,
            trust_markers=(card.get("trust_markers") if isinstance(card.get("trust_markers"), dict) else {}),
            published_at=published_at, published_at_status=date_status,
            snippet_truncated=len(snippet) > MAX_SNIPPET_CHARS,
        ))
    return [item.to_search_result() for item in evidence]


@register_search_provider("eggsearch")
class EggsearchSearchProvider(BaseSearchProvider):
    """Synchronous ainews seam around the SDK's async per-call lifecycle."""

    _native_slots = threading.BoundedSemaphore(8)

    def __init__(self, provider_id: str, config: dict, client_factory: Callable[..., Any] | None = None):
        super().__init__(provider_id, config)
        self._client_factory = client_factory or _load_native_client

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return self.search_detailed(query, max_results).results

    def search_detailed(
        self, query: str, max_results: int = 5, timeout_seconds: float | None = None,
    ) -> SearchOutcome:
        budget = timeout_seconds or float(self.config.get("timeout_seconds", 20))
        deadline = time.monotonic() + budget
        acquired = self._native_slots.acquire(timeout=max(0.0, budget))
        remaining = deadline - time.monotonic()
        if not acquired or remaining <= 0:
            if acquired:
                self._native_slots.release()
            return SearchOutcome(
                [], SearchStatus.FAILED, provider_attempts=(self.provider_id,),
                provider_failures=("capacity_deadline_exceeded",),
                failure_details=(ProviderFailure(self.provider_id, "capacity_deadline_exceeded"),),
                deadline_exceeded=True, retryable=True,
            )
        try:
            return self._search_detailed(query, max_results, remaining)
        finally:
            self._native_slots.release()

    def _search_detailed(
        self, query: str, max_results: int, timeout_seconds: float,
    ) -> SearchOutcome:
        if not self.config.get("enabled", True):
            return SearchOutcome([], SearchStatus.DISABLED, provider_attempts=(self.provider_id,))
        limit = max(1, min(int(max_results), MAX_PROVIDER_RESULTS))
        provider_limit = min(MAX_PROVIDER_RESULTS, limit + URL_FILTER_HEADROOM)
        started = time.monotonic()
        try:
            response = _request_search(
                self._client_factory, self.config, query, provider_limit, timeout_seconds,
            )
            raw_results = response.get("results", [])
            retrieval_summary = response.get("retrieval_summary", {})
            if not isinstance(retrieval_summary, dict):
                retrieval_summary = {}
            retrieval_status = retrieval_summary.get("status")
            compact_retrieval = response.get("retrieval_status")
            if retrieval_status is None and isinstance(compact_retrieval, str):
                retrieval_status = compact_retrieval
            compact_has_failures = (
                isinstance(compact_retrieval, dict)
                and (
                    bool(compact_retrieval.get("has_failures"))
                    or (
                        isinstance(compact_retrieval.get("failed_job_count"), int)
                        and compact_retrieval["failed_job_count"] > 0
                    )
                )
            )
            failures = response.get("providers_failed", retrieval_summary.get("providers_failed", []))
            warnings = response.get("structured_warnings", response.get("warnings", []))
            if not isinstance(failures, list) or not isinstance(warnings, list):
                raise ValueError("Eggsearch returned malformed diagnostics")
            results = _map_results(raw_results, self.provider_id, limit)
            partial = (
                bool(failures)
                or bool(retrieval_summary.get("has_failures")) or compact_has_failures
                or retrieval_status in {"provider_failed", "deadline_prevented_completion", "partial"}
            )
            deadline_exceeded = retrieval_status == "deadline_prevented_completion"
            status = SearchStatus.PARTIAL if results and partial else (
                SearchStatus.OK if results else SearchStatus.EMPTY if not partial else SearchStatus.FAILED
            )
            raw_capabilities = response.get("capability_enforcement")
            if raw_capabilities is None:
                raw_capabilities = response.get("capability_summary")
            requested = response.get("requested_capabilities")
            if requested is None and isinstance(raw_capabilities, dict):
                requested = raw_capabilities.get("requested", {})
            enforcement = _capability_states(raw_capabilities)
            if _requested_freshness(requested):
                freshness_state = enforcement.get(
                    "freshness_filter", enforcement.get("freshness", "unknown"),
                )
                for result in results:
                    result.metadata["freshness_status"] = (
                        "date_unverified" if freshness_state != "enforced" else "enforcement_reported"
                    )
            normalized_requested = _normalize_requested(requested)
            failure_details = _provider_failures(failures)
            diagnostics = tuple(
                _safe_label(item.get("code", "provider_warning"), "provider_warning")
                if isinstance(item, dict) else "provider_warning"
                for item in warnings[:20]
            )
            if raw_results and not results:
                diagnostics += ("all_results_filtered_by_url_validation",)
            return SearchOutcome(
                results=results, status=status, provider_attempts=(self.provider_id,),
                provider_failures=tuple(item.error_class for item in failure_details),
                failure_details=failure_details,
                warnings=diagnostics,
                requested_capabilities=normalized_requested,
                enforced_capabilities=enforcement, deadline_exceeded=deadline_exceeded,
                retryable=bool(failure_details) and all(
                    item.retryable or _is_transient_failure(item.error_class)
                    for item in failure_details
                ),
                duration_ms=(time.monotonic() - started) * 1000,
            )
        except _retrieval_errors() as exc:
            logger.warning("Eggsearch retrieval failed (%s)", type(exc).__name__)
            return SearchOutcome(
                [], SearchStatus.FAILED, provider_attempts=(self.provider_id,),
                provider_failures=(type(exc).__name__,),
                deadline_exceeded=isinstance(exc, TimeoutError),
                retryable=(
                    isinstance(exc, (ImportError, OSError, ConnectionError, TimeoutError))
                    or (type(exc) is RuntimeError and str(exc) == "Eggsearch binding unavailable")
                ),
                duration_ms=(time.monotonic() - started) * 1000,
            )
