from __future__ import annotations

from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_skip, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult


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

        reachable = 0
        unreachable = 0
        for src in source_list[:3]:
            url = _extract_primary_url(src)
            if not url:
                continue
            try:
                import requests as _requests
                resp = _requests.head(url, timeout=5, allow_redirects=True)
                if resp.status_code < 400:
                    reachable += 1
                else:
                    unreachable += 1
            except Exception:  # noqa: BLE001
                unreachable += 1

        total = reachable + unreachable
        if total == 0:
            checks.append(check_skip(
                "source_connectivity",
                "No sources with URL config found (skipped)",
            ))
        elif unreachable > 0:
            checks.append(check_fail(
                "source_connectivity",
                f"{unreachable}/{total} source(s) unreachable",
                remediation="Check source URLs and network connectivity",
            ))
        else:
            checks.append(check_pass(
                "source_connectivity",
                f"{reachable}/{total} source(s) reachable",
            ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_skip(
            "source_connectivity",
            f"Source connectivity check skipped: {e}",
        ))
