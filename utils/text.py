"""Text utilities - pure helper functions with minimal dependencies."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

__all__ = [
    "esc_xml_text",
    "esc_xml_attr",
    "escape_prompt_data",
    "truncate",
    "sanitize_html",
    "extract_hashtags",
]


def esc_xml_text(text: str) -> str:
    """Escape text content for safe embedding in XML tags within LLM prompts."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_xml_attr(text: str) -> str:
    """Escape a value for safe embedding in XML attributes within LLM prompts."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("'", "&apos;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_prompt_data(data: dict[str, Any]) -> dict[str, Any]:
    """Escape all string values in prompt_data for safe XML embedding."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = esc_xml_text(value)
        elif isinstance(value, dict):
            result[key] = escape_prompt_data(value)
        elif isinstance(value, list):
            result[key] = [
                esc_xml_text(str(v)) if isinstance(v, str) else v for v in value
            ]
        else:
            result[key] = value
    return result


def truncate(text: str, length: int, suffix: str = "...") -> str:
    """Truncate text to length, breaking on word boundaries."""
    if length < 0:
        raise ValueError("length must be non-negative")
    if not text:
        return ""
    if len(text) <= length:
        return text
    if length <= len(suffix):
        return suffix[:length]
    truncated = text[: length - len(suffix)]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + suffix


_DANGEROUS_TAGS = frozenset({
    "script", "style", "iframe", "noscript", "object", "embed", "form",
})

_EVENT_HANDLER_ATTRS = frozenset({
    "onerror", "onclick", "onload", "onmouseover", "onmouseout",
    "onfocus", "onblur", "onchange", "onsubmit", "onreset",
    "onkeydown", "onkeyup", "onkeypress", "ondblclick", "oncontextmenu",
})

_JAVASCRIPT_PATTERNS = frozenset(["javascript:", "vbscript:", "data:"])


class _TagStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []

    def handle_data(self, data: str) -> None:
        self.result.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DANGEROUS_TAGS:
            return

        has_dangerous_attrs = False
        filtered_attrs: list[tuple[str, str | None]] = []
        for name, value in attrs:
            name_lower = name.lower()
            if name_lower in _EVENT_HANDLER_ATTRS:
                has_dangerous_attrs = True
                continue
            if value:
                value_lower = value.lower()
                if any(pat in value_lower for pat in _JAVASCRIPT_PATTERNS):
                    has_dangerous_attrs = True
                    continue
            filtered_attrs.append((name, value))

        if has_dangerous_attrs:
            self.result.append(f"<{tag}>")
        else:
            if filtered_attrs:
                attr_str = "".join(
                    f' {name}="{value}"' if value else f' {name}'
                    for name, value in filtered_attrs
                )
                self.result.append(f"<{tag}{attr_str}>")
            else:
                self.result.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DANGEROUS_TAGS:
            return
        self.result.append(f"</{tag}>")

    def handle_comment(self, data: str) -> None:
        pass

    def unknown_decl(self, data: str) -> None:
        pass


def sanitize_html(html: str) -> str:
    """Remove dangerous HTML tags and strip event handler attributes.

    Strips: dangerous tags (script, style, iframe, etc.), event handler
    attributes (onerror, onclick, etc.), javascript: and data: URIs.
    Preserves: safe tags and non-event-handler attributes.
    """
    if not html:
        return ""

    parser = _TagStripper()
    try:
        parser.feed(html)
    except ValueError:
        return html
    except Exception:  # noqa: BLE001 - return original on any other parse error
        return html
    result = "".join(parser.result)
    for pat in _JAVASCRIPT_PATTERNS:
        result = re.sub(rf'href\s*=\s*["\']?{re.escape(pat)}[^"\']*["\']?', f'href="#"', result, flags=re.IGNORECASE)
    return result


def extract_hashtags(text: str) -> list[str]:
    """Extract #hashtags from text."""
    if not text:
        return []
    pattern = r"#[a-zA-Z][a-zA-Z0-9_]*"
    return re.findall(pattern, text)