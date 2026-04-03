"""Shared constants for pagination and other configuration values."""

# Pipeline retry limits (single source of truth)
MAX_STAGE_RETRIES = 3
MAX_TOTAL_RETRIES = 10

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
        "selecting",
        "researching",
        "writing",
        "editing",
        "review",
        "done",
        "skipped",
        "failed",
    }
)


class PipelineStatus:
    """Pipeline status constants to avoid typos."""

    PENDING = "pending"
    SELECTING = "selecting"  # Added for completeness, though not in DB
    RESEARCHING = "researching"
    WRITING = "writing"
    EDITING = "editing"
    REVIEW = "review"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


# Log truncation constants
MAX_LOG_TITLE_LENGTH = 100


def truncate_for_log(text: str, max_length: int = MAX_LOG_TITLE_LENGTH) -> str:
    """Truncate text for logging, preserving readability."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


# Impact score bounds
IMPACT_SCORE_MIN = 0
IMPACT_SCORE_MAX = 100

# Content extraction minimum text length
MIN_CONTENT_LENGTH = 200


def _get_min_content_length() -> int:
    """Get min content length from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get("MIN_CONTENT_LENGTH", MIN_CONTENT_LENGTH)
    except RuntimeError:
        return MIN_CONTENT_LENGTH


# Dead-letter: minutes before an in-progress article is considered stuck
STUCK_THRESHOLD_MINUTES = 60

# Soft cutoff: minutes after which a stuck article is considered for retry/dead-letter
RETRY_SOFT_CUTOFF_MINUTES = 15


def _get_stuck_threshold_minutes() -> int:
    """Get stuck threshold from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get(
            "STUCK_THRESHOLD_MINUTES", STUCK_THRESHOLD_MINUTES
        )
    except RuntimeError:
        return STUCK_THRESHOLD_MINUTES


def _get_retry_soft_cutoff_minutes() -> int:
    """Get retry soft cutoff from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get(
            "RETRY_SOFT_CUTOFF_MINUTES", RETRY_SOFT_CUTOFF_MINUTES
        )
    except RuntimeError:
        return RETRY_SOFT_CUTOFF_MINUTES
