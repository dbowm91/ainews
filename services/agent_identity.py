"""The name the site attributes its summaries to.

An operator can set a site-wide agent name and a per-topic override from the
admin panel. When neither is set, the site keeps naming the model that
wrote the article, which is what it has always shown.

The names live in ``topics.yaml`` next to the topic definitions, because
that is the file the admin panel already edits and the file the topic
routes already read.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# What the site says when there is no configured name and no writer model.
FALLBACK_AGENT_NAME = "ai agent"


def configured_agent_name(topic: Optional[str] = None) -> str:
    """Return the configured agent name for a topic, or the site-wide one.

    A topic-specific name wins over the site-wide one. An empty string
    means the caller should fall back to the model that wrote the article.
    """
    try:
        from schemas.topic import load_topics

        config = load_topics()
    except Exception:
        logger.exception("Failed to load the topic configuration for the agent name")
        return ""

    if topic:
        entry = config.topics.get(topic)
        if entry is not None and entry.agent_name:
            return entry.agent_name.strip()

    site_name = config.site.agent_name
    return site_name.strip() if isinstance(site_name, str) else ""


def agent_display_name(article: Any) -> str:
    """Return the name to show as the author of an article's summary.

    The configured name wins. Without one, the article names the model
    that wrote it, which is the behaviour the site has always had.
    """
    configured = configured_agent_name(getattr(article, "category", None))
    if configured:
        return configured

    writer_model = getattr(article, "writer_model", None)
    return writer_model or FALLBACK_AGENT_NAME
