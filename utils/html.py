"""HTML processing utilities - pure functions with minimal dependencies."""

from __future__ import annotations

import re
from html.parser import HTMLParser

__all__ = ["strip_tags", "linkify", "extract_text"]


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []
        self._skip_data = False
        self._skip_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip_data = True
            self._skip_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            if not self._skip_stack:
                self._skip_data = False

    def handle_data(self, data: str) -> None:
        if not self._skip_data:
            self.result.append(data)


def strip_tags(html: str) -> str:
    """Remove all HTML tags."""
    if not html:
        return ""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - fallback to regex strip on parse error
        return re.sub(r"<[^>]+>", "", html)
    text = "".join(parser.result)
    return re.sub(r"\s+", " ", text).strip()


def linkify(text: str) -> str:
    """Convert URLs to clickable links."""
    if not text:
        return ""
    url_pattern = re.compile(
        r'(https?://[^\s<>"{}|\\^`\[\]]+)',
        re.IGNORECASE
    )
    return url_pattern.sub(r'<a href="\1">\1</a>', text)


def extract_text(html: str) -> str:
    """Extract readable text from HTML."""
    text = strip_tags(html)

    try:
        import trafilatura
        downloaded = trafilatura.extract(html)
        if downloaded:
            return downloaded.strip()
    except ImportError:
        pass

    return text