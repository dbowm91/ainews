"""Tests for logging utilities service."""

import time
from unittest.mock import patch


class TestLoggingUtils:
    def test_log_pipeline_event(self):
        from services.logging_utils import log_pipeline_event

        with patch("services.logging_utils.logger") as mock_logger:
            log_pipeline_event("write", "started", article_id=42, run_id=1)
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args
            assert call_kwargs[1]["extra"]["stage"] == "write"
            assert call_kwargs[1]["extra"]["article_id"] == 42

    def test_log_article_event(self):
        from services.logging_utils import log_article_event

        with patch("services.logging_utils.logger") as mock_logger:
            log_article_event(42, "processed", level="info")
            mock_logger.info.assert_called_once()

    def test_log_admin_event(self):
        from services.logging_utils import log_admin_event

        with patch("services.logging_utils.logger") as mock_logger:
            log_admin_event("config_reload", user="admin")
            mock_logger.info.assert_called_once()

    def test_log_duration(self):
        from services.logging_utils import log_duration

        with patch("services.logging_utils.logger") as mock_logger:
            with log_duration("test_op"):
                time.sleep(0.01)
            mock_logger.info.assert_called_once()
            assert "duration_ms" in mock_logger.info.call_args[1]["extra"]
