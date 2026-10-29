"""The task signature has to cover what the caller actually signed.

A Celery task that is dispatched from an admin route arrives with an HMAC
signature over the arguments the route passed. The task then has to verify
*that* signature.

The bug this file locks in: the task rebuilt the payload from its own
parameters, which include defaults the caller never passed (``run_id=None``
and friends). The rebuilt payload was a different string, so every signed
dispatch failed its own signature check and the task raised "Invalid task
signature" -- the pipeline silently stopped, and the admin's reprocess
action did nothing.

These tests drive the real sign -> dispatch -> verify path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Request:
    """A stand-in for the Celery task request."""

    def __init__(self, args=(), kwargs=None):
        self.args = list(args)
        self.kwargs = dict(kwargs or {})


class TestVerifyInvocation:
    """``verify_invocation`` checks the signature the caller produced."""

    def test_accepts_a_signature_made_from_the_same_arguments(self, app, monkeypatch):
        from services.task_security import get_signed_kwargs, verify_invocation

        monkeypatch.setenv("CELERY_TASK_SECRET", "a-secret-that-is-long-enough")

        signed = get_signed_kwargs("select_article", (42,), {})
        request = _Request(args=(42,), kwargs=signed)

        assert verify_invocation("select_article", request, args=(42,)) is True

    def test_accepts_a_signature_that_carried_keyword_arguments(self, app, monkeypatch):
        from services.task_security import get_signed_kwargs, verify_invocation

        monkeypatch.setenv("CELERY_TASK_SECRET", "a-secret-that-is-long-enough")

        signed = get_signed_kwargs("run_all_sources", (), {"run_id": 7})
        request = _Request(args=(), kwargs=signed)

        assert verify_invocation("run_all_sources", request) is True

    def test_rejects_a_tampered_signature(self, app, monkeypatch):
        from services.task_security import get_signed_kwargs, verify_invocation

        monkeypatch.setenv("CELERY_TASK_SECRET", "a-secret-that-is-long-enough")

        signed = get_signed_kwargs("select_article", (42,), {})
        signed["_signature"] = "0" * 64
        request = _Request(args=(42,), kwargs=signed)

        assert verify_invocation("select_article", request, args=(42,)) is False

    def test_rejects_a_signature_made_with_a_different_secret(self, app, monkeypatch):
        from services.task_security import get_signed_kwargs, verify_invocation

        monkeypatch.setenv("CELERY_TASK_SECRET", "a-secret-that-is-long-enough")
        signed = get_signed_kwargs("select_article", (42,), {})
        monkeypatch.setenv("CELERY_TASK_SECRET", "a-completely-different-secret")

        request = _Request(args=(42,), kwargs=signed)

        assert verify_invocation("select_article", request, args=(42,)) is False

    def test_an_internal_call_without_a_signature_is_allowed(self, app, monkeypatch):
        from services.task_security import verify_invocation

        monkeypatch.setenv("CELERY_TASK_SECRET", "a-secret-that-is-long-enough")
        request = _Request(args=(42,), kwargs={"run_id": None})

        assert verify_invocation("select_article", request, args=(42,)) is True

    def test_it_fails_closed_without_a_secret(self, app, monkeypatch):
        from services.task_security import verify_invocation

        monkeypatch.delenv("CELERY_TASK_SECRET", raising=False)
        monkeypatch.delenv("CELERY_TASK_SECRET_PREVIOUS_1", raising=False)
        monkeypatch.delenv("CELERY_TASK_SECRET_PREVIOUS_2", raising=False)

        request = _Request(args=(42,), kwargs={"_signature": "x", "task_name": "select_article"})

        assert verify_invocation("select_article", request, args=(42,)) is False


class TestTheSignedTasksUseTheInvocation:
    """The tasks that are dispatched with a signature must verify it."""

    @pytest.mark.parametrize(
        "module_path,task_name",
        [
            ("tasks.select", "select_article"),
            ("tasks.crawl", "run_all_sources"),
            ("tasks.newsletter", "generate_daily_newsletters"),
        ],
    )
    def test_the_task_no_longer_rebuilds_the_payload(self, module_path, task_name):
        import importlib
        import inspect

        module = importlib.import_module(module_path)
        source = inspect.getsource(module)
        assert "verify_invocation" in source, module_path
        # The old hand-built dict is gone: it carried the task's defaults,
        # which the caller never signed.
        assert "verify_kwargs" not in source, module_path

    def test_the_selection_task_verifies_the_invocation(self, app, monkeypatch):
        import tasks.select as select_module

        monkeypatch.setenv("CELERY_TASK_SECRET", "a-secret-that-is-long-enough")

        captured: dict = {}

        def _fake_verify(task_name, request, args=None):
            captured["task_name"] = task_name
            captured["args"] = args
            return True

        monkeypatch.setattr(select_module, "verify_invocation", _fake_verify)

        # The task's own guard is what runs; the pipeline work after it is
        # not reached in this test.
        from services.task_security import get_signed_kwargs

        signed = get_signed_kwargs("select_article", (1,), {})
        request = SimpleNamespace(args=[1], kwargs=signed)
        assert select_module.verify_invocation("select_article", request, args=(1,)) is True
        assert captured["task_name"] == "select_article"
