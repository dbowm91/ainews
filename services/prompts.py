"""Prompt utilities: system prompt loading and safe text escaping for LLM input."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


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


def load_prompt_file(name: str) -> str | None:
    """Load a prompt from prompts/{name}.txt. Returns None if not found."""
    path = _PROMPTS_DIR / f"{name}.txt"
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        logger.debug(f"Prompt file not found: {path}")
        return None


def get_system_prompt(role: str, yaml_prompt: str | None) -> str:
    """Get system prompt: YAML override first, then file fallback.

    Args:
        role: The role name (e.g., 'writer', 'editor', 'newsletter_reader')
        yaml_prompt: The system_prompt from pipeline.yaml, or None

    Returns:
        The system prompt string
    """
    if yaml_prompt:
        return yaml_prompt
    file_prompt = load_prompt_file(role)
    if file_prompt:
        return file_prompt
    raise ValueError(
        f"No system prompt found for role '{role}' (checked YAML and prompts/{role}.txt)"
    )
