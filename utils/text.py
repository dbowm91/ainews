"""Text utilities - pure helper functions with minimal dependencies."""

from __future__ import annotations

from typing import Any

__all__ = ["esc_xml_text", "esc_xml_attr", "escape_prompt_data"]


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