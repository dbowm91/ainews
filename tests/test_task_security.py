"""Tests for services/task_security.py (HMAC task signing)."""

from unittest.mock import patch


class TestTaskSigning:
    """Tests for task HMAC signing and verification."""

    def test_sign_task_creates_valid_signature(self, app):
        """Task signature should create a dictionary with signature."""
        from services.task_security import sign_task

        with app.app_context():
            sig = sign_task("test_task", (1, 2), {"key": "value"})
            assert sig is not None
            assert isinstance(sig, dict)
            assert "_signature" in sig

    def test_verify_task_returns_bool(self, app):
        """verify_task should return a boolean."""
        from services.task_security import verify_task

        with app.app_context():
            result = verify_task("test_task", (), {})
            assert isinstance(result, bool)

    def test_get_signed_kwargs_adds_signature(self, app):
        """get_signed_kwargs should add signature to kwargs."""
        from services.task_security import get_signed_kwargs

        with app.app_context():
            kwargs = {"key": "value"}
            result = get_signed_kwargs("test_task", (1,), kwargs)
            assert "_signature" in result
            assert "task_name" in result

    def test_verify_task_accepts_valid_signature(self, app):
        """verify_task should return True for a valid HMAC signature when secret is configured."""
        from services.task_security import sign_task, verify_task

        with app.app_context():
            task_name = "cleanup_old_article_versions"
            args = ()
            kwargs = {"days_to_keep": 30, "dry_run": False}

            signed = sign_task(task_name, args, kwargs)
            combined_kwargs = {**kwargs, **signed}

            result = verify_task(task_name, args, combined_kwargs)
            assert result is True

    def test_verify_task_rejects_tampered_signature(self, app):
        """verify_task should return False when signature is tampered."""
        from services.task_security import sign_task, verify_task

        with app.app_context():
            task_name = "cleanup_old_article_versions"
            args = ()
            kwargs = {"days_to_keep": 30, "dry_run": False}

            signed = sign_task(task_name, args, kwargs)
            tampered_kwargs = {**kwargs, **signed, "_signature": "tampered_signature"}

            result = verify_task(task_name, args, tampered_kwargs)
            assert result is False

    def test_verify_task_fails_closed_on_missing_secret(self, app):
        """verify_task should return False (fail-closed) when CELERY_TASK_SECRET is not configured."""
        from services.task_security import verify_task

        with app.app_context():
            with patch.dict("os.environ", {}, clear=True):
                result = verify_task("some_task", (), {})
                assert result is False

    def test_verify_task_allows_internal_call(self, app):
        """verify_task should return True when no signature is present (internal .s() call)."""
        from services.task_security import verify_task

        with app.app_context():
            result = verify_task("some_task", (), {"key": "value"})
            assert result is True

    def test_verify_task_rejects_wrong_task_name(self, app):
        """verify_task should return False when task name doesn't match."""
        from services.task_security import sign_task, verify_task

        with app.app_context():
            kwargs = {"days_to_keep": 30}
            signed = sign_task("cleanup_old_article_versions", (), kwargs)
            combined = {**kwargs, **signed}

            result = verify_task("different_task", (), combined)
            assert result is False

    def test_sign_task_no_secret_returns_task_name_only(self, app):
        """sign_task should return only task_name when no secret is configured."""
        from services.task_security import sign_task

        with app.app_context():
            with patch.dict("os.environ", {}, clear=True):
                result = sign_task("my_task", (1,), {"key": "value"})
                assert "task_name" in result
                assert "_signature" not in result

    def test_signature_payload_excludes_signature_key(self, app):
        """_build_signature_payload should exclude _signature from kwargs to prevent signature farming."""
        from services.task_security import _build_signature_payload

        with app.app_context():
            payload1 = _build_signature_payload("task", (), {"key": "value", "_signature": "secret"})
            payload2 = _build_signature_payload("task", (), {"key": "value"})
            assert payload1 == payload2, "_signature should be excluded from payload"

    def test_signature_consistency_across_calls(self, app):
        """Multiple sign calls with same inputs should produce same signature."""
        from services.task_security import sign_task

        with app.app_context():
            kwargs = {"article_id": 42}
            sig1 = sign_task("select_article", (), kwargs)
            sig2 = sign_task("select_article", (), kwargs)
            assert sig1["_signature"] == sig2["_signature"]

    def test_verify_task_rejects_modified_kwargs(self, app):
        """verify_task should return False when kwargs are modified after signing."""
        from services.task_security import sign_task, verify_task

        with app.app_context():
            task_name = "run_all_sources"
            args = ()
            original_kwargs = {"source_ids": [1, 2, 3]}
            signed = sign_task(task_name, args, original_kwargs)
            combined = {**original_kwargs, **signed}

            modified_combined = {**combined, "source_ids": [1, 2, 3, 4]}
            result = verify_task(task_name, args, modified_combined)
            assert result is False