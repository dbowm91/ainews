"""Prompt utilities: system prompt loading, safe text escaping, and context truncation for LLM input."""

import collections
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from functools import lru_cache

from pydantic import ValidationError
from utils.text import esc_xml_attr, esc_xml_text  # noqa: F401 - re-exported for backward compatibility
from services.llm.errors import AuthError, ProviderServerError, ProviderTimeoutError
from services.tracing import get_current_trace_id

logger = logging.getLogger(__name__)

# Fallback prompts — pipeline.yaml system_prompt fields are the source of truth.
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Approximate chars per token for English text (used when tiktoken unavailable)
_CHARS_PER_TOKEN = 4

# In-memory cache for summarize_context results (avoid redundant LLM calls)
_summarize_cache: dict[str, tuple[float, str]] = {}
_SUMMARIZE_CACHE_TTL = 600  # 10 minutes

# Precompiled regex for fast substring search in importance_weighted_truncate
# Compiled once at module load, reused across calls
_regex_cache: dict[str, re.Pattern] = {}


@lru_cache(maxsize=128)
def count_tokens(text: str, model: str | None = None) -> int:
    """Count tokens in text using tiktoken if available, otherwise approximate.

    Args:
        text: The text to count tokens for
        model: Optional model name (currently unused, for future tiktoken support)

    Returns:
        Estimated token count
    """
    try:
        import tiktoken

        if model:
            enc = tiktoken.encoding_for_model(model)
        else:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Fallback: approximate 1 token per 4 chars for English text
        return len(text) // _CHARS_PER_TOKEN


def max_tokens_for_model(model: str | None) -> int:
    """Get approximate max context tokens for a model.

    Returns a reasonable default if model not recognized.
    Common context windows:
    - GPT-4: 8192-128000
    - Claude: 9000-200000
    - Ollama models: vary widely
    """
    if not model:
        return 4096
    model_lower = model.lower()
    if "gpt-4" in model_lower:
        if "turbo" in model_lower or "128k" in model_lower:
            return 128000
        return 8192
    if "claude" in model_lower:
        if "3-5" in model_lower or "3.5" in model_lower:
            return 200000
        return 9000
    return 4096


# Truncation warning injected when content is truncated
TRUNCATION_WARNING = "[Warning: The preceding context was truncated due to length limits. A summary may have been generated to preserve key information.]"


class _PromptFileCache:
    """LRU cache with file-mtime-based invalidation for prompt files."""

    def __init__(self, maxsize: int = 128) -> None:
        self._maxsize = maxsize
        self._cache: dict[str, tuple[float, str | None]] = {}
        self._access_order: collections.OrderedDict[str, None] = collections.OrderedDict()

    def get(self, name: str) -> str | None:
        path = _PROMPTS_DIR / f"{name}.txt"
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            if name in self._cache:
                del self._cache[name]
                self._access_order.pop(name, None)
            return None

        if name in self._cache:
            cached_mtime, cached_content = self._cache[name]
            if mtime == cached_mtime:
                self._access_order.move_to_end(name)
                return cached_content

        try:
            content = path.read_text().strip()
        except FileNotFoundError:
            content = None

        self._cache[name] = (mtime, content)
        self._access_order[name] = None
        self._access_order.move_to_end(name)
        while len(self._access_order) > self._maxsize:
            evicted, _ = self._access_order.popitem(last=False)
            self._cache.pop(evicted, None)
        return content

    def clear(self) -> None:
        self._cache.clear()
        self._access_order.clear()


_prompt_file_cache = _PromptFileCache(maxsize=128)


def load_prompt_file(name: str) -> str | None:
    """Load a prompt from prompts/{name}.txt. Returns None if not found.

    Uses an mtime-based cache: files are re-read when their modification
    time changes. LRU eviction keeps at most 128 entries.
    """
    return _prompt_file_cache.get(name)


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
        f"No system prompt found for role '{role}' (checked YAML and prompts/{role}.txt)",
    )


def sliding_window_truncate(
    text: str,
    max_chars: int = 8000,
    model: str | None = None,
    ellipsis: str = "\n\n[... truncated ...]\n\n",
) -> str:
    """Truncate text using sliding window to preserve start and end.

    When text exceeds max_chars, keeps the first half and last half with ellipsis
    in between to maintain context from both ends of the content.

    Args:
        text: The text to truncate
        max_chars: Maximum characters allowed (default 8000)
        model: Optional model name for token-aware truncation.
               If provided and token count exceeds model's context,
               uses token estimate to determine truncation point.
        ellipsis: String to insert between truncated parts
    """
    if not text:
        return text

    # If model specified, check token count and adjust max_chars if needed
    if model:
        try:
            tokens = count_tokens(text, model)
            model_max = max_tokens_for_model(model)
            # Use 50% of model's context as truncation threshold (reserve rest for output)
            token_threshold = model_max // 2
            if tokens > token_threshold:
                # Approximate chars from tokens and use that as max
                est_chars = tokens * _CHARS_PER_TOKEN
                max_chars = min(max_chars, est_chars // 2)
        except (ImportError, ValueError, AttributeError):
            logger.debug("Token counting failed, using char-based truncation")

    if len(text) <= max_chars:
        return text
    half = (max_chars - len(ellipsis)) // 2
    return text[:half] + ellipsis + text[-half:]


def importance_weighted_truncate(
    text: str,
    max_chars: int = 8000,
    key_topics: list[str] | None = None,
) -> str:
    """Truncate text by keeping highest-scoring segments based on key topics.

    Segments are split by paragraphs. Each segment is scored by the number of
    key topics it contains. Highest-scoring segments are kept up to max_chars,
    preserving their original order.

    Args:
        text: The text to truncate
        max_chars: Maximum characters allowed (default 8000)
        key_topics: List of key topics to score segments against; if None,
                    all segments have score 0 and are selected in original order.

    Returns:
        Truncated text, or empty string if input is empty
    """
    if not text or max_chars <= 0:
        return text if max_chars > 0 else ""

    # Split into non-empty paragraphs
    segments = [seg.strip() for seg in text.split("\n\n") if seg.strip()]
    if not segments:
        return ""

    # Normalize key topics to lowercase for case-insensitive matching
    key_topics = [kt.lower() for kt in key_topics or []]

    # Compile regex patterns once and cache them for fast substring search
    compiled_patterns = []
    for kt in key_topics:
        if kt not in _regex_cache:
            _regex_cache[kt] = re.compile(re.escape(kt), re.IGNORECASE)
        compiled_patterns.append(_regex_cache[kt])

    # Score segments: count how many key topics are present in the segment
    scored_segments = []
    for idx, seg in enumerate(segments):
        score = sum(1 for pat in compiled_patterns if pat.search(seg))
        scored_segments.append((-score, idx, seg))  # Negative score for descending sort

    # Sort segments by score descending (highest first), then original index ascending
    scored_segments.sort(key=lambda x: (x[0], x[1]))

    # Select segments up to max_chars, preserving original order
    selected: list[tuple[int, str]] = []
    total_len = 0
    sep = "\n\n"
    for _neg_score, idx, seg in scored_segments:
        # Calculate length of this segment plus separator if not first
        seg_len = len(seg) + (len(sep) if selected else 0)
        if total_len + seg_len > max_chars:
            continue
        selected.append((idx, seg))
        total_len += seg_len
        if total_len >= max_chars:
            break

    # If no segments selected, fall back to sliding window truncation
    if not selected:
        return sliding_window_truncate(text, max_chars, model=None)

    # Sort selected segments by original index to preserve order
    selected.sort(key=lambda x: x[0])

    # Join with paragraph separators
    return sep.join(seg for _, seg in selected)


def _budget_tokens(text: str, model: str, max_output_tokens: int = 512) -> str:
    """Check prompt against model context limit and truncate if needed.

    Args:
        text: The prompt text to check
        model: Model name for context limit lookup
        max_output_tokens: Tokens to reserve for output (default 512)

    Returns:
        Original text if within budget, otherwise truncated version
    """
    try:
        tokens = count_tokens(text, model)
        model_max = max_tokens_for_model(model)
        available = model_max - max_output_tokens
        if tokens <= available:
            return text

        char_budget = available * _CHARS_PER_TOKEN
        logger.debug(
            "Token budget exceeded for %s: %d tokens, limit %d, truncating to %d chars",
            model, tokens, available, char_budget,
        )
        return sliding_window_truncate(text, char_budget, model=None)
    except (ImportError, ValueError, AttributeError):
        return text


def summarize_context(text: str, llm_provider=None, max_tokens: int = 512, temperature: float = 0.0) -> str:
    """Summarize text using LLM to preserve key information.

    Results are cached for 10 minutes to avoid redundant LLM calls.

    Args:
        text: The text to summarize
        llm_provider: Optional LLM provider instance. If None, uses default editor provider.
        max_tokens: Max tokens for the summary response
        temperature: Temperature for LLM call

    Returns:
        Summarized text, or empty string on failure
    """
    global _summarize_cache

    if not text:
        return ""

    cache_key = hashlib.sha256(f"{text[:500]}:{max_tokens}:{temperature}".encode()).hexdigest()
    now = time.monotonic()
    if cache_key in _summarize_cache:
        expires_at, result = _summarize_cache[cache_key]
        if now < expires_at:
            logger.debug("summarize_context cache hit")
            return result
        del _summarize_cache[cache_key]

    from services.llm import get_provider_for_role

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
        result = response.text.strip() if response and response.text else ""
        _summarize_cache[cache_key] = (now + _SUMMARIZE_CACHE_TTL, result)
        return result
    except (ImportError, json.JSONDecodeError, ValidationError,
            AuthError, ProviderServerError, ProviderTimeoutError,
            ConnectionError, ValueError, AttributeError) as e:
        logger.warning("TraceID=%s: LLM summarization failed, will fall back to sliding window: %s", get_current_trace_id(), e)
        return ""


def smart_truncate_context(
    text: str,
    max_chars: int = 8000,
    model: str | None = None,
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
        model: Optional model name for token-aware truncation
        llm_provider: Optional LLM provider instance
        truncation_llm_threshold: Threshold for using LLM summarization (from config)
        truncation_llm_max_tokens: Max tokens for summary response
        truncation_llm_temperature: Temperature for LLM call
        truncation_llm_enabled: Whether LLM summarization is enabled

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    from schemas.pipeline import load_pipeline_config

    if not text:
        return text, False

    # If model specified, check token count and adjust max_chars if needed
    if model:
        try:
            tokens = count_tokens(text, model)
            model_max = max_tokens_for_model(model)
            token_threshold = model_max // 2
            if tokens > token_threshold:
                est_chars = tokens * _CHARS_PER_TOKEN
                max_chars = min(max_chars, est_chars // 2)
        except (ImportError, ValueError, AttributeError):
            logger.debug("Token counting failed, using char-based truncation")

    if len(text) <= max_chars:
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
        try:
            summary = summarize_context(
                text,
                llm_provider=llm_provider,
                max_tokens=truncation_llm_max_tokens,
                temperature=truncation_llm_temperature,
            )
            if summary:
                result = f"{summary}\n\n{TRUNCATION_WARNING}"
                return result, True
        except (ImportError, json.JSONDecodeError, ValidationError,
                AuthError, ProviderServerError, ProviderTimeoutError,
                ConnectionError, ValueError, AttributeError) as e:
            logger.warning("TraceID=%s: LLM summarization failed, falling back to sliding window: %s", get_current_trace_id(), e)

    return sliding_window_truncate(text, max_chars, model=model), True
