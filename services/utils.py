import json
import re
from typing import Optional

from sqlalchemy.orm import Query


# Simple but effective email pattern - catches common mistakes
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*"
    r"\.[a-zA-Z]{2,}$"
)


def is_valid_email(email: str) -> bool:
    """Return True if email looks like a valid address."""
    return bool(_EMAIL_RE.match(email.strip()))


def paginate_query(
    query: Query,
    page: int,
    per_page: int,
) -> tuple[list, bool, int]:
    """Paginate a SQLAlchemy query using the LIMIT+1 pattern.

    Fetches per_page+1 rows to detect if a next page exists without
    a separate COUNT query.

    Args:
        query: SQLAlchemy query to paginate.
        page: Current page number (1-indexed).
        per_page: Number of items per page.

    Returns:
        Tuple of (items, has_next, next_page).
    """
    rows = query.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(rows) > per_page
    if has_next:
        rows = rows[:per_page]
    return rows, has_next, page + 1


def parse_article_headline(
    article,
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
