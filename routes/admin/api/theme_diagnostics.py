"""Admin API endpoint for theme registry diagnostics."""

import logging
from typing import Any

from flask import Response

from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response

logger = logging.getLogger(__name__)


@admin_api_bp.route("/themes/diagnostics", methods=["GET"])
@require_auth
def themes_diagnostics() -> tuple[Response, int]:
    """Return theme registry health and per-theme diagnostic data.

    Authenticated admins only. Response includes aggregate registry
    metadata, per-theme summaries (no paths, CSS, or TOML content),
    and aggregate diagnostic counts.
    """
    from services.themes.loader import get_app_registry, get_diagnostics
    from services.themes.registry import EMERGENCY_RESERVED_ID

    registry = get_app_registry()
    if registry is None:
        return api_response(
            error="Theme registry not available",
            status=503,
        )

    diagnostics_obj = get_diagnostics()

    built_at = registry.built_at or (
        diagnostics_obj.built_at if diagnostics_obj else ""
    )

    override_set = set(diagnostics_obj.overrides) if diagnostics_obj else set()

    themes_list: list[dict[str, Any]] = []
    total_errors = 0
    total_warnings = 0
    code_counts: dict[str, int] = {}

    for theme in registry.list_themes():
        warning_count = 0
        warning_codes: list[str] = []
        for diag in theme.warnings:
            if diag.severity.value in ("warning", "error"):
                warning_count += 1
                warning_codes.append(diag.code)
                code_counts[diag.code] = code_counts.get(diag.code, 0) + 1
            if diag.severity.value == "error":
                total_errors += 1
            elif diag.severity.value == "warning":
                total_warnings += 1

        is_emergency = theme.origin.kind == "emergency"
        overrides_bundled = theme.id in override_set

        entry: dict[str, Any] = {
            "id": theme.id,
            "display_name": theme.display_name,
            "appearance": theme.appearance,
            "origin": theme.origin.kind,
            "valid": len(theme.warnings) == 0 or all(
                w.severity.value not in ("error",) for w in theme.warnings
            ),
            "warning_count": warning_count,
            "warning_codes": warning_codes,
            "content_digest": theme.content_digest,
        }

        if is_emergency:
            entry["emergency"] = True

        if overrides_bundled:
            entry["overrides_bundled"] = True

        themes_list.append(entry)

    theme_count_total = len([t for t in registry.list_themes() if t.origin.kind != "emergency"])
    theme_count_bundled = sum(1 for t in registry.list_themes() if t.origin.kind == "bundled")
    theme_count_custom = sum(1 for t in registry.list_themes() if t.origin.kind == "external")

    response: dict[str, Any] = {
        "data": {
            "registry": {
                "theme_count_total": theme_count_total,
                "theme_count_bundled": theme_count_bundled,
                "theme_count_custom": theme_count_custom,
                "default_id": registry.default_id,
                "default_dark_id": registry.default_dark_id,
                "default_light_id": registry.default_light_id,
                "emergency_fallback_active": EMERGENCY_RESERVED_ID in registry.themes,
                "built_at": built_at,
            },
            "themes": themes_list,
            "diagnostics": {
                "errors": total_errors,
                "warnings": total_warnings,
                "codes": code_counts,
            },
        },
    }

    resp, status = api_response(data=response["data"])
    resp.headers["Cache-Control"] = "no-store"
    return resp, status
