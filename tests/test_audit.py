"""Tests for audit service."""

from unittest.mock import patch


class TestAudit:
    def test_log_admin_action_logs(self):
        from services.audit import log_admin_action

        with patch("services.audit.logger") as mock_logger:
            log_admin_action("article_edit", target_type="article", target_id=42)
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["extra"]["audit"] is True
            assert call_kwargs["extra"]["action"] == "article_edit"
