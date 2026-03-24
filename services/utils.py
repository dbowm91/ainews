import json
from typing import Optional


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
