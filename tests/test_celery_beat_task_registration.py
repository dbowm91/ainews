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
import os
import subprocess
import sys

import pytest


@pytest.fixture(scope="module")
def registered_task_names() -> set[str]:
    """Mirror the worker bootstrap order, then list registered task names."""
    os.environ.setdefault("FLASK_CONFIG", "testing")
    os.environ.setdefault("SECRET_KEY", "test-celery-bootstrap-secret")
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
        "maintain_editorial_memory",
        "purge_trend_memory",
        "recalculate_impact_scores",
        "cleanup_old_article_versions",
        "generate_daily_newsletters",
        "retry_failed_newsletter_deliveries",
        "cleanup_inactive_subscribers",
    ):
        assert hasattr(tasks, name), f"tasks.{name} is not exported"


def test_celery_cli_app_import_registers_tasks_without_manual_import() -> None:
    """The actual ``celery -A celery_app:celery_app worker`` bootstrap must register tasks."""
    code = (
        "from celery_app import celery_app; "
        "assert 'tasks.crawl.run_all_sources' in celery_app.tasks; "
        "assert 'tasks.scheduler.auto_approve_review_articles' in celery_app.tasks"
    )
    env = os.environ.copy()
    env.update({"FLASK_CONFIG": "testing", "SECRET_KEY": "a" * 64})
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
