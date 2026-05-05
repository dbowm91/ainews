"""Text utilities - pure helper functions with minimal dependencies."""

from __future__ import annotations

__all__ = ["esc_xml_text", "esc_xml_attr"]


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