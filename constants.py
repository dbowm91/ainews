"""Shared constants for pagination and other configuration values."""

# Pipeline retry limits (single source of truth)
MAX_STAGE_RETRIES = 3
MAX_TOTAL_RETRIES = 10

# Pipeline hard timeout (article can be in pipeline for at most this many seconds)
PIPELINE_TIMEOUT_SECONDS = 3600

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


# Valid pipeline status transitions
# Each status maps to the set of statuses it can transition to
VALID_TRANSITIONS: dict[str, frozenset] = {
    PipelineStatus.PENDING: frozenset([PipelineStatus.RESEARCHING]),
    PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.FAILED]),
    PipelineStatus.WRITING: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
    PipelineStatus.EDITING: frozenset([PipelineStatus.REVIEW, PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.REVIEW: frozenset([PipelineStatus.DONE, PipelineStatus.FAILED]),
    PipelineStatus.DONE: frozenset(),  # Terminal state
    PipelineStatus.SKIPPED: frozenset(),  # Terminal state
    PipelineStatus.FAILED: frozenset([PipelineStatus.PENDING]),  # Can be reprocessed
}


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Check if a pipeline status transition is valid."""
    valid_next = VALID_TRANSITIONS.get(from_status, frozenset())
    return to_status in valid_next or to_status == from_status


def get_valid_next_statuses(current_status: str) -> frozenset:
    """Get the set of valid next statuses from the current status."""
    return VALID_TRANSITIONS.get(current_status, frozenset())


STAGE_STATUS_MAP = {
    "pending": "select",
    "selecting": "select",
    "selected": "research",
    "researching": "research",
    "writing": "write",
    "written": "edit",
    "editing": "edit",
    "selector": "select",
    "researcher": "research",
    "writer": "write",
    "editor": "edit",
    "select": "select",
    "research": "research",
    "write": "write",
    "edit": "edit",
}


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
