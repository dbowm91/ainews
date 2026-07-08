"""Smoke tests for Celery app import and configuration.

Validates that the Celery app can be imported and is correctly configured
without requiring a live broker or network calls.
"""

import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _ensure_env(monkeypatch):
    monkeypatch.setenv("FLASK_CONFIG", "testing")
    monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")


def _import_celery_app():
    if "celery_app" in sys.modules:
        return sys.modules["celery_app"].celery_app
    mod = importlib.import_module("celery_app")
    return mod.celery_app


class TestCeleryAppImports:
    def test_celery_instance(self):
        from celery import Celery

        celery_app = _import_celery_app()
        assert isinstance(celery_app, Celery)


class TestCeleryAppHasTasks:
    def test_expected_tasks_registered(self):
        import tasks  # noqa: F401 — triggers shared_task registration

        celery_app = _import_celery_app()
        task_names = set(celery_app.tasks.keys())
        expected = [
            "tasks.select.select_article",
            "tasks.research.research_article",
            "tasks.write.write_article",
            "tasks.edit.edit_article",
        ]
        for name in expected:
            assert name in task_names, f"Expected task {name} not registered"


class TestCeleryAppConfigured:
    def test_main_name(self):
        celery_app = _import_celery_app()
        assert celery_app.main == "ainews"

    def test_broker_url_set(self):
        celery_app = _import_celery_app()
        assert celery_app.conf.broker_url, "broker_url should be non-empty"
