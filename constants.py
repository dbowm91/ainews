"""Shared constants for pagination and other configuration values."""

# Pagination constants
PER_PAGE_PUBLIC = 20
PER_PAGE_ADMIN_ARTICLES = 25
PER_PAGE_ADMIN_SUBSCRIBERS = 50
PER_PAGE_PIPELINE = 20
PER_PAGE_NEWSLETTERS = 20
PER_PAGE_PIPELINE_LOGS = 100

# Pipeline status values
VALID_PIPELINE_STATUSES = frozenset(
    {
        "pending",
        "researching",
        "writing",
        "editing",
        "review",
        "done",
        "skipped",
        "failed",
    }
)

# Impact score bounds
IMPACT_SCORE_MIN = 0
IMPACT_SCORE_MAX = 100

# Content extraction minimum text length
MIN_CONTENT_LENGTH = 200

# Dead-letter: minutes before an in-progress article is considered stuck
STUCK_THRESHOLD_MINUTES = 60
