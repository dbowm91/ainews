"""Provenance helpers for the public article surfaces.

Two kinds of provenance are shown on the public pages:

* **Human provenance** -- where the story came from: the source, the
  author, when it was published, and how long it takes to read.
* **Machine provenance** -- which pipeline produced it, which model wrote
  it, how the quality gate scored it, and whether the run degraded.

Both are derived from data the pipeline already stores on every row. The
reading time is computed from the body rather than stored: a derived
value does not belong in a column.
"""

from __future__ import annotations

from typing import Any

#: Words per minute for a technical article read on screen.
WORDS_PER_MINUTE = 220

#: Below this many words the reading time is not worth showing.
MIN_WORDS = 60

#: Pipeline statuses that mean the article was produced by the pipeline.
PRODUCED_STATUSES = ("done", "published", "written", "edited")


def article_body_text(article: Any) -> str:
    """Return the longest body text available on an article."""
    for attribute in ("final_article", "draft_article", "summary"):
        value = getattr(article, attribute, None)
        if value:
            return str(value)
    return ""


def word_count(article: Any) -> int:
    """Return the number of words in the article body."""
    text = article_body_text(article)
    if not text:
        return 0
    return len(text.split())


def reading_time_minutes(article: Any) -> int:
    """Return the estimated reading time in whole minutes.

    Returns 0 when the body is too short for the estimate to mean
    anything.
    """
    words = word_count(article)
    if words < MIN_WORDS:
        return 0
    return max(1, round(words / WORDS_PER_MINUTE))


def is_pipeline_produced(article: Any) -> bool:
    """Return True when the article was produced by the pipeline.

    Articles created by hand carry no writer model and no pipeline
    provenance, and the agent line must not pretend otherwise.
    """
    writer_model = getattr(article, "writer_model", None)
    if writer_model:
        return True
    status = getattr(article, "pipeline_status", None)
    return bool(status and status in PRODUCED_STATUSES)


def agent_provenance(article: Any) -> dict[str, Any] | None:
    """Return the machine-provenance view model for an article.

    Returns ``None`` when the article carries no pipeline provenance, so
    that the template can omit the line entirely rather than render an
    empty one.
    """
    if not is_pipeline_produced(article):
        return None

    writer_model = getattr(article, "writer_model", None)
    impact_score = getattr(article, "impact_score", None)
    degradation_count = getattr(article, "degradation_count", None) or 0
    quality_score = getattr(article, "quality_score", None)

    if not writer_model and not impact_score and not quality_score:
        return None

    return {
        "writer_model": writer_model,
        "impact_score": impact_score,
        "quality_score": quality_score,
        "degradation_count": degradation_count,
    }
