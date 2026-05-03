import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Simple but effective email pattern - catches common mistakes
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*"
    r"\.[a-zA-Z]{2,}$",
)


def is_valid_email(email: str) -> bool:
    """Return True if email looks like a valid address."""
    return bool(_EMAIL_RE.match(email.strip()))


# Re-export from canonical location


def parse_article_headline(
    article: Any,
    fallback_headline: Optional[str] = None,
    include_summary: bool = False,
) -> tuple[str, str]:
    """Extract headline and TLDR from article's final_article JSON.

    Args:
        article: Article model instance.
        fallback_headline: Default headline if none found (e.g. "Untitled").
            If None, uses article.original_title as-is.
        include_summary: If True, also check article.summary as fallback source.

    Returns:
        (headline, tldr) tuple.
    """
    headline = article.original_title or fallback_headline or ""
    tldr = ""
    text = article.final_article
    if not text and include_summary:
        text = article.summary
    if text:
        try:
            data = json.loads(text)
            headline = data.get("headline", headline)
            tldr = data.get("tldr", "")
        except (json.JSONDecodeError, TypeError):
            pass
    return headline, tldr


def get_admin_categories() -> list[str]:
    """Get category names from pipeline config, with fallback."""
    try:
        from schemas.topic import load_topics

        return list(load_topics().topics.keys())
    except (ImportError, AttributeError, KeyError) as e:
        logger.debug("Failed to load topics from config, using fallback: %s", e)
        return ["ai", "privacy", "security", "programming", "hardware"]
