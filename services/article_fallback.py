"""Shared fallback article construction for pipeline and dead-letter use."""

import json

from services.markup import paragraphize


def build_fallback_article_json(article) -> str:
    """Build a degraded article from the extracted source text.

    A degraded article has no model-written structure, so the raw extracted
    text is used as the body. It is paragraphised first: scraped text often
    arrives as one uninterrupted run, which rendered as a single wall of text
    with no readable breaks.
    """
    extracted = article.extracted_text or ""
    return json.dumps(
        {
            "headline": article.original_title or "Untitled",
            "tldr": (extracted or "")[:200],
            "why_it_matters": "",
            "body": paragraphize(extracted) or (article.original_title or ""),
            "key_points": [],
            "what_to_watch": "",
            "citations": [],
            "original_attribution": {
                "source": article.original_url or "",
                "author": article.original_author or "",
            },
            "tags": [],
        },
    )
