"""Prompt utilities: system prompt loading, safe text escaping, and context truncation for LLM input."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Fallback prompts — pipeline.yaml system_prompt fields are the source of truth.
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Truncation warning injected when content is truncated
TRUNCATION_WARNING = "[Warning: The preceding context was truncated due to length limits. A summary may have been generated to preserve key information.]"


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
        logger.debug("Prompt file not found: %s", path)
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


def sliding_window_truncate(
    text: str, max_chars: int = 8000, ellipsis: str = "\n\n[... truncated ...]\n\n"
) -> str:
    """Truncate text using sliding window to preserve start and end.

    When text exceeds max_chars, keeps the first half and last half with ellipsis
    in between to maintain context from both ends of the content.
    """
    if not text or len(text) <= max_chars:
        return text
    half = (max_chars - len(ellipsis)) // 2
    return text[:half] + ellipsis + text[-half:]


async def summarize_context(text: str, llm_provider=None, max_tokens: int = 512, temperature: float = 0.0) -> str:
    """Summarize text using LLM to preserve key information.

    Args:
        text: The text to summarize
        llm_provider: Optional LLM provider instance. If None, uses default editor provider.
        max_tokens: Max tokens for the summary response
        temperature: Temperature for LLM call

    Returns:
        Summarized text, or empty string on failure
    """
    from services.llm import get_provider_for_role

    if not text:
        return ""

    try:
        if llm_provider is None:
            llm_provider, _, _, _ = get_provider_for_role("editor")

        summary_prompt = (
            "Summarize the following text concisely while preserving all key facts, "
            "names, dates, numbers, and attributions. The summary will be used as "
            "context for another LLM task, so precision is critical.\n\n"
            f"<text_to_summarize>\n{esc_xml_text(text)}\n</text_to_summarize>\n\n"
            "Return only the summary text, no explanation or preamble."
        )

        response = llm_provider.chat(
            messages=[{"role": "user", "content": summary_prompt}],
            model=llm_provider.default_model,
            system="You are a precise summarizer. Preserve all factual claims, names, dates, and numbers.",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.text.strip() if response and response.text else ""
    except Exception as e:
        logger.warning("LLM summarization failed, will fall back to sliding window: %s", e)
        return ""


def smart_truncate_context(
    text: str,
    max_chars: int = 8000,
    llm_provider=None,
    truncation_llm_threshold: int | None = None,
    truncation_llm_max_tokens: int | None = None,
    truncation_llm_temperature: float | None = None,
    truncation_llm_enabled: bool | None = None,
) -> tuple[str, bool]:
    """Truncate context intelligently, choosing strategy based on overflow size.

    Strategy selection:
    - Small overflow (<= threshold): sliding window truncation
    - Large overflow (> threshold) with LLM available: LLM summarization
    - LLM unavailable or disabled: fall back to sliding window

    Args:
        text: The text to truncate
        max_chars: Maximum characters allowed
        llm_provider: Optional LLM provider instance
        truncation_llm_threshold: Threshold for using LLM summarization (from config)
        truncation_llm_max_tokens: Max tokens for summary response
        truncation_llm_temperature: Temperature for LLM call
        truncation_llm_enabled: Whether LLM summarization is enabled

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    from schemas.pipeline import load_pipeline_config

    if not text or len(text) <= max_chars:
        return text, False

    config = load_pipeline_config()

    if truncation_llm_enabled is None:
        truncation_llm_enabled = config.memory.truncation_llm_enabled
    if truncation_llm_threshold is None:
        truncation_llm_threshold = config.memory.truncation_llm_threshold
    if truncation_llm_max_tokens is None:
        truncation_llm_max_tokens = config.memory.truncation_llm_max_tokens
    if truncation_llm_temperature is None:
        truncation_llm_temperature = config.memory.truncation_llm_temperature

    overflow = len(text) - max_chars

    if truncation_llm_enabled and overflow > truncation_llm_threshold:
        import asyncio

        try:
            summary = asyncio.get_event_loop().run_until_complete(
                summarize_context(
                    text,
                    llm_provider=llm_provider,
                    max_tokens=truncation_llm_max_tokens,
                    temperature=truncation_llm_temperature,
                )
            )
            if summary:
                result = f"{summary}\n\n{TRUNCATION_WARNING}"
                return result, True
        except Exception as e:
            logger.warning("LLM summarization failed, falling back to sliding window: %s", e)

    return sliding_window_truncate(text, max_chars), True
