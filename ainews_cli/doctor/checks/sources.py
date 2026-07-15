from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from ainews_cli.doctor.model import check_fail, check_skip, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult

logger = logging.getLogger(__name__)

_MAX_PROBE_SOURCES = 3

_PROBE_LIMITS_KWARGS: dict[str, Any] = {
    "max_redirects": 3,
    "max_bytes": 4096,
    "connect_timeout": 3.0,
    "read_timeout": 5.0,
    "total_timeout": 10.0,
    "allowed_content_types": (
        "application/rss+xml",
        "application/atom+xml",
        "application/xml",
        "text/xml",
        "text/html",
        "application/xhtml+xml",
        "text/plain",
    ),
}

_HTTP_STATUS_RE = re.compile(r"HTTP (\d+)")


def _extract_primary_url(source: dict) -> str | None:
    """Extract the primary URL from a source config entry."""
    src_type = source.get("type", "")
    config = source.get("config", {})
    if src_type == "rss":
        return config.get("feed_url")
    elif src_type == "api":
        return config.get("list_url")
    elif src_type == "web":
        return config.get("listing_url")
    return None


def probe_source(url: str, source_type: str) -> dict[str, Any]:
    """Probe a source URL using the production-safe fetch client.

    Returns a dict with keys:
        outcome: "reachable" | "degraded" | "blocked" | "unreachable"
        status_code: int | None
        latency_ms: float
        reason_code: str | None
        message: str
    """
    from services.safe_fetch import (
        SafeFetchContentTypeError,
        SafeFetchError,
        SafeFetchLimits,
        SafeFetchTimeoutError,
        SafeFetchTooLargeError,
        UnsafeFetchError,
        safe_fetch_url,
    )

    limits = SafeFetchLimits(**_PROBE_LIMITS_KWARGS)
    start = time.monotonic()

    try:
        result = safe_fetch_url(url, limits=limits)
        latency_ms = (time.monotonic() - start) * 1000
        status = result.status_code

        if 200 <= status < 300:
            return {
                "outcome": "reachable",
                "status_code": status,
                "latency_ms": round(latency_ms, 1),
                "reason_code": None,
                "message": f"HTTP {status}",
            }
        else:
            return {
                "outcome": "degraded",
                "status_code": status,
                "latency_ms": round(latency_ms, 1),
                "reason_code": "http_error",
                "message": f"HTTP {status}",
            }

    except UnsafeFetchError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "outcome": "blocked",
            "status_code": None,
            "latency_ms": round(latency_ms, 1),
            "reason_code": "ssrf_blocked",
            "message": str(exc),
        }

    except SafeFetchTimeoutError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "outcome": "unreachable",
            "status_code": None,
            "latency_ms": round(latency_ms, 1),
            "reason_code": "timeout",
            "message": str(exc),
        }

    except SafeFetchContentTypeError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "outcome": "degraded",
            "status_code": None,
            "latency_ms": round(latency_ms, 1),
            "reason_code": "content_type_rejected",
            "message": str(exc),
        }

    except SafeFetchTooLargeError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "outcome": "reachable",
            "status_code": None,
            "latency_ms": round(latency_ms, 1),
            "reason_code": None,
            "message": f"Responded but body too large: {exc}",
        }

    except SafeFetchError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        msg = str(exc)
        m = _HTTP_STATUS_RE.search(msg)
        if m:
            return {
                "outcome": "degraded",
                "status_code": int(m.group(1)),
                "latency_ms": round(latency_ms, 1),
                "reason_code": "http_error",
                "message": msg,
            }
        if "DNS" in msg or "resolve" in msg.lower():
            return {
                "outcome": "unreachable",
                "status_code": None,
                "latency_ms": round(latency_ms, 1),
                "reason_code": "dns_failure",
                "message": msg,
            }
        if "Connection failed" in msg:
            return {
                "outcome": "unreachable",
                "status_code": None,
                "latency_ms": round(latency_ms, 1),
                "reason_code": "connection_failed",
                "message": msg,
            }
        return {
            "outcome": "unreachable",
            "status_code": None,
            "latency_ms": round(latency_ms, 1),
            "reason_code": "connection_failed",
            "message": msg,
        }

    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "outcome": "unreachable",
            "status_code": None,
            "latency_ms": round(latency_ms, 1),
            "reason_code": "connection_failed",
            "message": str(exc),
        }


def _check_source_connectivity(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        from ainews_config import load_all_configs

        config = load_all_configs(paths)
        sources = config.sources
        if not sources:
            checks.append(check_skip(
                "source_connectivity",
                "No sources configured (skipped)",
            ))
            return

        source_list = sources.get("sources", []) if isinstance(sources, dict) else []
        if not source_list:
            checks.append(check_skip(
                "source_connectivity",
                "No sources configured (skipped)",
            ))
            return

        results: list[dict[str, Any]] = []
        for src in source_list[:_MAX_PROBE_SOURCES]:
            url = _extract_primary_url(src)
            if not url:
                continue
            src_type = src.get("type", "unknown")
            probe = probe_source(url, src_type)
            probe["url"] = url
            probe["source_type"] = src_type
            results.append(probe)

        if not results:
            checks.append(check_skip(
                "source_connectivity",
                "No sources with URL config found (skipped)",
            ))
            return

        reachable = sum(1 for r in results if r["outcome"] == "reachable")
        degraded = sum(1 for r in results if r["outcome"] == "degraded")
        blocked = sum(1 for r in results if r["outcome"] == "blocked")
        unreachable = sum(1 for r in results if r["outcome"] == "unreachable")
        total = len(results)
        avg_latency = (
            sum(r["latency_ms"] for r in results) / total if total else 0
        )

        details: dict[str, Any] = {
            "probed": total,
            "reachable": reachable,
            "degraded": degraded,
            "blocked": blocked,
            "unreachable": unreachable,
            "avg_latency_ms": round(avg_latency, 1),
            "sources": [
                {
                    "url": r["url"],
                    "source_type": r["source_type"],
                    "outcome": r["outcome"],
                    "status_code": r["status_code"],
                    "latency_ms": r["latency_ms"],
                    "reason_code": r["reason_code"],
                    "message": r["message"],
                }
                for r in results
            ],
        }

        if unreachable > 0 or blocked > 0:
            checks.append(check_fail(
                "source_connectivity",
                f"{unreachable + blocked}/{total} source(s) unreachable/blocked",
                remediation="Check source URLs, network connectivity, and SSRF allowlists",
                details=details,
            ))
        elif degraded > 0:
            checks.append(check_fail(
                "source_connectivity",
                f"{degraded}/{total} source(s) degraded",
                remediation="Check source URLs — servers responded with errors or unexpected content types",
                details=details,
            ))
        else:
            checks.append(check_pass(
                "source_connectivity",
                f"{reachable}/{total} source(s) reachable (avg {avg_latency:.0f}ms)",
                details=details,
            ))

    except Exception as e:  # noqa: BLE001
        checks.append(check_skip(
            "source_connectivity",
            f"Source connectivity check skipped: {e}",
        ))
