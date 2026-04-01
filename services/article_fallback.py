"""Shared fallback article construction for pipeline and dead-letter use."""

import json


def build_fallback_article_json(article) -> str:
    return json.dumps(
        {
            "headline": article.original_title or "Untitled",
            "tldr": (article.extracted_text or "")[:200],
            "why_it_matters": "",
            "body": article.extracted_text or article.original_title or "",
            "key_points": [],
            "what_to_watch": "",
            "citations": [],
            "original_attribution": {
                "source": article.original_url or "",
                "author": article.original_author or "",
            },
            "tags": [],
        }
    )
