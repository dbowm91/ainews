from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MAX_OPML_SIZE_BYTES = 1024 * 1024  # 1 MB
_MAX_OUTLINE_DEPTH = 10
_MAX_OUTLINE_COUNT = 500


@dataclass
class OPMLImportResult:
    """Result of an OPML import operation."""
    success: bool = True
    dry_run: bool = True
    imported: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    conflicts: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _parse_opml_outlines(
    element: ET.Element,
    depth: int = 0,
    category_path: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Recursively parse OPML outline elements into a flat list."""
    if category_path is None:
        category_path = []
    if depth > _MAX_OUTLINE_DEPTH:
        return []

    outlines: list[dict[str, Any]] = []

    for child in element:
        if child.tag.lower() != "outline":
            continue

        attrs = dict(child.attrib)
        xml_url = attrs.get("xmlUrl", attrs.get("xmlurl", ""))

        if xml_url:
            # This is a feed outline
            title = attrs.get("title", "") or attrs.get("text", "")
            html_url = attrs.get("htmlUrl", attrs.get("htmlurl", ""))
            categories = list(category_path)

            outlines.append({
                "xmlUrl": xml_url,
                "htmlUrl": html_url,
                "title": title,
                "text": attrs.get("text", title),
                "categories": categories,
                "type": attrs.get("type", ""),
            })

        # Recurse into child outlines (folders/categories)
        child_title = attrs.get("title", "") or attrs.get("text", "")
        if child_title:
            child_path = category_path + [child_title]
        else:
            child_path = category_path

        outlines.extend(_parse_opml_outlines(child, depth + 1, child_path))

    return outlines


def _normalize_url(url: str) -> str:
    """Normalize a URL for duplicate detection."""
    url = url.strip()
    url = re.sub(r"/$", "", url)
    url = re.sub(r"^https?://(www\.)", r"https://", url)
    return url.lower()


def _generate_source_id(title: str, existing_ids: set[str]) -> str:
    """Generate a stable source ID from a title."""
    sid = title.lower().strip()
    sid = re.sub(r"[^a-z0-9]+", "_", sid)
    sid = sid.strip("_")
    if not sid:
        sid = "imported"

    base = sid
    counter = 1
    while sid in existing_ids:
        sid = f"{base}_{counter}"
        counter += 1

    return sid


def import_opml(
    file_path: str,
    conflict_strategy: str = "skip",
    dry_run: bool = True,
    existing_sources: list[dict[str, Any]] | None = None,
) -> OPMLImportResult:
    """Import sources from an OPML file.

    Args:
        file_path: Path to the OPML file.
        conflict_strategy: How to handle duplicates: 'skip', 'merge', 'replace', 'rename'.
        dry_run: If True, only preview changes.
        existing_sources: Current sources list for duplicate detection.

    Returns:
        OPMLImportResult with imported, skipped, conflicts, and errors.
    """
    path = Path(file_path)
    if not path.exists():
        return OPMLImportResult(
            success=False,
            dry_run=dry_run,
            errors=[f"File not found: {file_path}"],
        )

    file_size = path.stat().st_size
    if file_size > _MAX_OPML_SIZE_BYTES:
        return OPMLImportResult(
            success=False,
            dry_run=dry_run,
            errors=[f"File too large: {file_size} bytes (max {_MAX_OPML_SIZE_BYTES})"],
        )

    if existing_sources is None:
        existing_sources = []

    existing_ids = {s.get("id", "") for s in existing_sources}
    existing_urls = {
        _normalize_url(_extract_url(s)): s
        for s in existing_sources
        if _extract_url(s)
    }

    try:
        content = path.read_text(encoding="utf-8")
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return OPMLImportResult(
            success=False,
            dry_run=dry_run,
            errors=[f"XML parse error: {e}"],
        )
    except OSError as e:
        return OPMLImportResult(
            success=False,
            dry_run=dry_run,
            errors=[f"Read error: {e}"],
        )

    # Check for XXE indicators
    if "<!ENTITY" in content or "<!DOCTYPE" in content.upper():
        return OPMLImportResult(
            success=False,
            dry_run=dry_run,
            errors=["OPML contains entity declarations (potential XXE). Rejected for safety."],
        )

    outlines = _parse_opml_outlines(root)

    if len(outlines) > _MAX_OUTLINE_COUNT:
        return OPMLImportResult(
            success=False,
            dry_run=dry_run,
            errors=[f"Too many outlines: {len(outlines)} (max {_MAX_OUTLINE_COUNT})"],
        )

    result = OPMLImportResult(success=True, dry_run=dry_run)

    for outline in outlines:
        _process_outline(
            outline, result, conflict_strategy, existing_urls, existing_ids
        )

    result.success = len(result.errors) == 0
    return result


def _process_outline(
    outline: dict[str, Any],
    result: OPMLImportResult,
    conflict_strategy: str,
    existing_urls: dict[str, dict[str, Any]],
    existing_ids: set[str],
) -> None:
    """Process a single OPML outline into the import result."""
    xml_url = outline.get("xmlUrl", "")
    if not xml_url:
        result.errors.append(f"Outline '{outline.get('title', '?')}' has no xmlUrl")
        return

    if not re.match(r"^https?://", xml_url):
        result.errors.append(f"URL scheme not allowed for '{xml_url}' (must be http/https)")
        return

    norm_url = _normalize_url(xml_url)

    # Handle duplicates
    if norm_url in existing_urls:
        existing = existing_urls[norm_url]
        existing_id = existing.get("id", "?")

        if conflict_strategy == "skip":
            result.skipped.append({
                "id": existing_id,
                "url": xml_url,
                "reason": "duplicate",
            })
            return
        elif conflict_strategy == "merge":
            result.skipped.append({
                "id": existing_id,
                "url": xml_url,
                "reason": "merge_not_implemented",
            })
            return

    title = outline.get("title", "") or outline.get("text", "")
    if conflict_strategy == "rename" and norm_url in existing_urls:
        source_id = _generate_source_id(title + "_imported", existing_ids)
    else:
        source_id = _generate_source_id(title, existing_ids)

    result.imported.append({
        "id": source_id,
        "type": "rss",
        "name": title,
        "url": xml_url,
    })
    existing_ids.add(source_id)


def export_opml(
    sources: list[dict[str, Any]],
    title: str = "AI News Sources",
) -> str:
    """Export sources to an OPML string.

    Only exports RSS sources with xmlUrl. Never includes API keys or secrets.

    Args:
        sources: List of source dicts from sources.yaml.
        title: OPML document title.

    Returns:
        OPML XML string.
    """
    opml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        f"  <head><title>{html.escape(title)}</title></head>",
        "  <body>",
    ]

    rss_sources = [s for s in sources if s.get("type") == "rss" and s.get("enabled", True)]

    # Sort deterministically by ID
    rss_sources.sort(key=lambda s: s.get("id", ""))

    for src in rss_sources:
        config = src.get("config", {})
        feed_url = config.get("feed_url", "")
        if not feed_url:
            continue

        name = html.escape(src.get("name", src.get("id", "")))
        # Never include credentials
        safe_url = _strip_credentials(feed_url)

        attrs = f'text="{name}" title="{name}" xmlUrl="{html.escape(safe_url)}"'

        topics = src.get("topics", {})
        if isinstance(topics, dict):
            include = topics.get("include", [])
            if include:
                # Map topic IDs to category-style attributes
                category_str = " ".join(html.escape(t) for t in include)
                attrs += f' category="{category_str}"'

        opml_lines.append(f"    <outline {attrs} />")

    opml_lines.append("  </body>")
    opml_lines.append("</opml>")

    return "\n".join(opml_lines) + "\n"


def _extract_url(source: dict[str, Any]) -> str | None:
    """Extract the primary URL from a source config."""
    src_type = source.get("type", "")
    config = source.get("config", {})
    if src_type == "rss":
        return config.get("feed_url")
    elif src_type == "api":
        return config.get("list_url")
    elif src_type == "web":
        return config.get("listing_url")
    return None


def _strip_credentials(url: str) -> str:
    """Remove credentials from a URL for safe export."""
    if "@" in url:
        scheme_end = url.find("://")
        if scheme_end != -1:
            after_scheme = url[scheme_end + 3:]
            at_pos = after_scheme.find("@")
            if at_pos != -1:
                return url[: scheme_end + 3] + after_scheme[at_pos + 1 :]
    return url
