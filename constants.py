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


VALID_PIPELINE_STATUSES = frozenset(
    {
        PipelineStatus.PENDING,
        PipelineStatus.RESEARCHING,
        PipelineStatus.WRITING,
        PipelineStatus.EDITING,
        PipelineStatus.REVIEW,
        PipelineStatus.DONE,
        PipelineStatus.SKIPPED,
        PipelineStatus.FAILED,
    }
)


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
