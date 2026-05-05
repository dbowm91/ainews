from __future__ import annotations

import warnings

warnings.warn(
    "Importing from models.py is deprecated. Use `from models import ...` instead.",
    DeprecationWarning,
    stacklevel=2,
)

from models import (
    AdminUser,
    ApiToken,
    Article,
    ArticleMetric,
    ArticleVersion,
    AuditLog,
    Citation,
    Newsletter,
    PipelineLog,
    PipelineRun,
    SearchQuery,
    ShareConfig,
    Source,
    Subscriber,
    Tag,
    TopicNote,
    TrendMemory,
    Webhook,
    WebhookEvent,
    article_tags,
    decode_short_url,
    encode_short_url,
    slugify,
)

__all__ = [
    "AdminUser",
    "ApiToken",
    "Article",
    "ArticleMetric",
    "ArticleVersion",
    "AuditLog",
    "Citation",
    "Newsletter",
    "PipelineLog",
    "PipelineRun",
    "SearchQuery",
    "ShareConfig",
    "Source",
    "Subscriber",
    "Tag",
    "TopicNote",
    "TrendMemory",
    "Webhook",
    "WebhookEvent",
    "article_tags",
    "decode_short_url",
    "encode_short_url",
    "slugify",
]