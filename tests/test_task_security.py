"""Tests for services/task_security.py (HMAC task signing)."""


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