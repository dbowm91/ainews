"""Additive, provider-neutral search evidence and outcome contracts."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from services.search.base import SearchResult


class SearchStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    EMPTY = "empty"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass(frozen=True)
class SearchEvidence:
    """A bounded source card; unknown metadata remains explicitly unknown."""

    source_id: str
    canonical_url: str
    title: str
    snippet: str
    provider_id: str
    upstream_provider_ids: tuple[str, ...] = ()
    trust: str = "external_untrusted"
    trust_markers: dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None
    published_at_status: str = "unknown"
    snippet_truncated: bool = False
    diagnostic_ref: str | None = None

    def to_search_result(self) -> SearchResult:
        return SearchResult(
            title=self.title,
            url=self.canonical_url,
            snippet=self.snippet,
            source=self.provider_id,
            metadata={
                "source_id": self.source_id,
                "upstream_provider_ids": list(self.upstream_provider_ids),
                "trust": self.trust,
                "trust_markers": self.trust_markers,
                "retrieved_at": self.retrieved_at.isoformat(),
                "published_at": self.published_at.isoformat() if self.published_at else None,
                "published_at_status": self.published_at_status,
                "snippet_truncated": self.snippet_truncated,
                "diagnostic_ref": self.diagnostic_ref,
            },
        )


@dataclass(frozen=True)
class ProviderFailure:
    """Sanitized, bounded provider failure information from upstream."""

    provider_id: str = "unknown"
    error_class: str = "unknown"
    message: str = ""
    retryable: bool = False


@dataclass(frozen=True)
class SearchOutcome:
    results: list[SearchResult]
    status: SearchStatus
    provider_attempts: tuple[str, ...] = ()
    provider_failures: tuple[str, ...] = ()
    failure_details: tuple[ProviderFailure, ...] = ()
    warnings: tuple[str, ...] = ()
    requested_capabilities: dict[str, Any] = field(default_factory=dict)
    enforced_capabilities: dict[str, str] = field(default_factory=dict)
    deadline_exceeded: bool = False
    duration_ms: float = 0.0
    fallback_used: bool = False
    retryable: bool = False

    def __post_init__(self) -> None:
        # Frozen dataclasses are shallow; detach nested result metadata so cached
        # provider calls cannot share mutable source cards or diagnostics.
        copied_results = [
            SearchResult(
                title=result.title, url=result.url, snippet=result.snippet,
                source=result.source, metadata=copy.deepcopy(result.metadata),
            )
            for result in self.results
        ]
        object.__setattr__(self, "results", copied_results)
        object.__setattr__(self, "requested_capabilities", copy.deepcopy(self.requested_capabilities))
        object.__setattr__(self, "enforced_capabilities", copy.deepcopy(self.enforced_capabilities))

    @classmethod
    def from_legacy(cls, provider_id: str, results: list[SearchResult]) -> "SearchOutcome":
        return cls(
            results=results,
            status=SearchStatus.OK if results else SearchStatus.EMPTY,
            provider_attempts=(provider_id,),
        )
