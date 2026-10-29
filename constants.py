"""Shared constants for pagination and other configuration values."""

import os

# Celery task retry configuration
CELERY_TASK_MAX_RETRIES = int(os.environ.get("CELERY_TASK_MAX_RETRIES", 3))

# Pipeline retry limits (single source of truth)
MAX_STAGE_RETRIES = 3
MAX_STAGE_FAILURES = 3
MAX_TOTAL_RETRIES = 10

# Pipeline hard timeout (article can be in pipeline for at most this many seconds)
PIPELINE_TIMEOUT_SECONDS = 3600

# LLM request timeout
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0

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
    SELECTING = "selecting"
    SELECTED = "selected"
    RESEARCHING = "researching"
    WRITING = "writing"
    WRITTEN = "written"
    EDITING = "editing"
    REVIEW = "review"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


# Pipeline monitoring stages (order matters for display)
PIPELINE_STAGES = ("crawl", "select", "research", "write", "edit")


# Valid pipeline status transitions
# Each status maps to the set of statuses it can transition to
#
# Every edge here has to match a transition the pipeline actually performs.
# A missing edge does not merely reject a transition -- it raises
# InvalidStateTransitionError in the middle of a stage, which strands the
# article in its current status. It then sits there until the retry task
# dead-letters it an hour later as "stuck in 'pending'".
VALID_TRANSITIONS: dict[str, frozenset] = {
    # pending -> skipped: the selector rejects the article (tasks/select.py)
    # pending -> failed:  the pipeline times out before the first stage moves
    #                     the article on (tasks/pipeline.py)
    PipelineStatus.PENDING: frozenset([
        PipelineStatus.SELECTING,
        PipelineStatus.RESEARCHING,
        PipelineStatus.REVIEW,
        PipelineStatus.SKIPPED,
        PipelineStatus.FAILED,
    ]),
    PipelineStatus.SELECTING: frozenset([PipelineStatus.SELECTED, PipelineStatus.FAILED]),
    PipelineStatus.SELECTED: frozenset([PipelineStatus.RESEARCHING, PipelineStatus.FAILED]),
    PipelineStatus.RESEARCHING: frozenset([PipelineStatus.WRITING, PipelineStatus.FAILED]),
    # writing -> review: the writer's quality gate routes the draft to review
    PipelineStatus.WRITING: frozenset([PipelineStatus.EDITING, PipelineStatus.REVIEW, PipelineStatus.FAILED]),
    PipelineStatus.WRITTEN: frozenset([PipelineStatus.EDITING, PipelineStatus.FAILED]),
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
