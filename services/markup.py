"""Rendering and sanitization for LLM-authored article content.

The writer stage produces the article body as Markdown, but some models emit
HTML instead. Both have to end up as safe, structured HTML:

* A Markdown body that is rendered as plain text shows the reader literal
  ``**bold**`` and ``### heading`` markers.
* An HTML body that is rendered as plain text shows the reader ``<p>`` tags.

Two failure modes had to be fixed together:

1. **Rendering.** The body was emitted into the template verbatim, so the
   reader saw raw Markdown.
2. **Structure.** ``sanitize_final_article`` used an allowlist that did not
   include block level tags. When a model emitted ``<p>`` paragraphs, bleach
   stripped the tags and kept the text, welding every paragraph into one
   unreadable wall of text.

``render_body`` therefore guarantees paragraph structure before rendering and
``sanitize_html`` keeps block level elements so the structure survives.
"""

from __future__ import annotations

import logging
import re

import bleach  # type: ignore[import-untyped]
import markdown as markdown_lib  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

#: Tags that survive sanitization. Block level elements are included so that
#: paragraph structure is preserved rather than welded together.
ALLOWED_TAGS = [
    "p",
    "br",
    "hr",
    "div",
    "span",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "del",
    "mark",
    "sup",
    "sub",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "blockquote",
    "pre",
    "code",
    "kbd",
    "samp",
    "a",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
]

#: Attributes allowed per tag.
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "a": ["href", "title"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
    "code": ["class"],
    "pre": ["class"],
    "ol": ["start"],
}

#: URI schemes allowed in ``href``.
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

#: Elements whose *content* must be discarded, not just their tags.
_DANGEROUS_BLOCKS = re.compile(
    r"<\s*(script|style|iframe|object|embed|noscript|template|svg|math|form)\b"
    r".*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_SELF_CLOSING = re.compile(
    r"<\s*(script|style|iframe|object|embed|noscript|template|svg|math|form)\b[^>]*/?>",
    re.IGNORECASE,
)

#: Signals that a body is HTML rather than Markdown.
_HTML_SIGNALS = re.compile(
    r"<\s*(p|div|h[1-6]|ul|ol|li|blockquote|pre|br|table|section|article|figure)\b",
    re.IGNORECASE,
)

#: Sentence boundary used when splitting a wall of text into paragraphs.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]*[A-Z0-9])")

#: Paragraph shaping for text that has no paragraph breaks at all.
_SENTENCES_PER_PARAGRAPH = 4
_MAX_PARAGRAPH_CHARS = 700


def _strip_dangerous_blocks(text: str) -> str:
    """Remove dangerous elements together with their content."""
    text = _DANGEROUS_BLOCKS.sub("", text)
    return _DANGEROUS_SELF_CLOSING.sub("", text)


def sanitize_html(html: str) -> str:
    """Return ``html`` with everything outside the allowlist neutralised."""
    if not html:
        return ""
    cleaned = _strip_dangerous_blocks(html)
    try:
        return str(
            bleach.clean(
                cleaned,
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                protocols=ALLOWED_PROTOCOLS,
                strip=False,
            )
        )
    except Exception:
        logger.exception("Failed to sanitize article markup")
        return ""


def looks_like_html(text: str) -> bool:
    """Return True when ``text`` contains block level HTML markup."""
    return bool(_HTML_SIGNALS.search(text or ""))


def _split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences."""
    parts = [part.strip() for part in _SENTENCE_BOUNDARY.split(text)]
    return [part for part in parts if part]


def _paragraphs_from_blob(text: str) -> str:
    """Break a single unbroken run of text into readable paragraphs."""
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return text

    paragraphs: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current and (
            len(current) >= _SENTENCES_PER_PARAGRAPH
            or current_len + len(sentence) > _MAX_PARAGRAPH_CHARS
        ):
            paragraphs.append(" ".join(current))
            current = []
            current_len = 0
        current.append(sentence)
        current_len += len(sentence) + 1
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def paragraphize(text: str) -> str:
    """Ensure ``text`` is broken into paragraphs.

    Text that already has blank line separated blocks is returned unchanged.
    Hard wrapped text (single newlines) is split on those newlines. A single
    unbroken run of text is split into sentences and grouped into paragraphs.
    """
    if not text:
        return ""
    stripped = text.strip()
    if not stripped:
        return ""
    if "\n\n" in stripped:
        return stripped
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) > 1:
        return "\n\n".join(lines)
    return _paragraphs_from_blob(stripped)


def render_markdown(text: str) -> str:
    """Render Markdown to sanitized HTML."""
    if not text:
        return ""
    try:
        rendered = str(
            markdown_lib.markdown(
                paragraphize(text),
                extensions=["extra", "sane_lists"],
            )
        )
    except Exception:
        logger.exception("Failed to render article markdown")
        return sanitize_html(text)
    return sanitize_html(rendered)


def render_inline(text: str) -> str:
    """Render Markdown to sanitized HTML without a wrapping paragraph."""
    if not text:
        return ""
    rendered = render_markdown(text)
    match = re.fullmatch(r"<p>(.*)</p>", rendered.strip(), re.DOTALL)
    if match:
        return match.group(1)
    return rendered


def render_body(text: str) -> str:
    """Render an article body to sanitized HTML.

    Handles both a Markdown body and an HTML body, and guarantees that the
    result has paragraph structure even when the source was a single
    uninterrupted run of text.
    """
    if not text:
        return ""
    stripped = text.strip()
    if not stripped:
        return ""
    if looks_like_html(stripped):
        return sanitize_html(stripped)
    return render_markdown(stripped)


def strip_tags(html: str) -> str:
    """Return the plain text of an HTML fragment."""
    if not html:
        return ""
    try:
        return str(bleach.clean(html, tags=[], attributes={}, strip=True))
    except Exception:
        logger.exception("Failed to strip tags from article markup")
        return ""
