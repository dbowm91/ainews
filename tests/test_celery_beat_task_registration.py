"""Every task named in the beat schedule must be registered on the worker.

The Celery worker bootstraps with ``from celery_app import celery_app``
followed by ``import tasks``. A task whose defining module is never imported
never registers, and the beat dispatch then fails at runtime with
"Received unregistered task of type ...". That failure only appears when the
beat actually fires, so it is invisible to ordinary unit tests.

This module asserts the invariant directly: every ``task`` string in the
beat schedule resolves to a registered task.
"""

import importlib

import pytest


@pytest.fixture(scope="module")
def registered_task_names() -> set[str]:
    """Mirror the worker bootstrap order, then list registered task names."""
    celery_module = importlib.import_module("celery_app")
    importlib.import_module("tasks")
    return set(celery_module.celery_app.tasks.keys())


def test_beat_schedule_is_not_empty(registered_task_names: set[str]) -> None:
    """Guard against a vacuous pass if the schedule fails to load."""
    from config import Config

    schedule = Config.get_beat_schedule()
    assert schedule, "beat schedule must not be empty"


def test_all_beat_scheduled_tasks_are_registered(registered_task_names: set[str]) -> None:
    """Every beat-scheduled task name must resolve to a registered task."""
    from config import Config

    schedule = Config.get_beat_schedule()
    missing = {
        entry_name: entry["task"]
        for entry_name, entry in schedule.items()
        if entry["task"] not in registered_task_names
    }
    assert not missing, f"beat-scheduled tasks not registered on the worker: {missing}"


def test_previously_unregistered_task_modules_are_imported() -> None:
    """The task modules behind the beat schedule must be importable from `tasks`."""
    import tasks

    for name in (
        "cleanup_old_pipeline_logs",
        "cleanup_expired_verifications",
        "cleanup_stale_limiter_slots",
        "consolidate_trend_memory",
        "purge_trend_memory",
        "recalculate_impact_scores",
        "cleanup_old_article_versions",
        "generate_daily_newsletters",
        "retry_failed_newsletter_deliveries",
        "cleanup_inactive_subscribers",
    ):
        assert hasattr(tasks, name), f"tasks.{name} is not exported"
