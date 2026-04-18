"""Article JSON parsing utilities.

Extracted from services/article.py for single-responsibility.
Handles parsing of final_article and summary JSON fields on Article objects.
"""

import json
import logging

logger = logging.getLogger(__name__)


def parse_article_json(article) -> None:
    """Attach pre-parsed JSON dicts to article objects.

    This modifies the article object in-place by adding _fa and _summary attributes.
    """
    fa_raw = getattr(article, "final_article", None)
    if fa_raw:
        try:
            article._fa = json.loads(fa_raw)
        except (json.JSONDecodeError, TypeError):
            article._fa = None
    else:
        article._fa = None

    summary_raw = getattr(article, "summary", None)
    if summary_raw:
        try:
            article._summary = json.loads(summary_raw)
        except (json.JSONDecodeError, TypeError):
            article._summary = None
    else:
        article._summary = None


def parse_articles(articles: list) -> list:
    """Batch-parse JSON for a list of articles."""
    for article in articles:
        parse_article_json(article)
    return articles
