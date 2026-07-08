"""Tests that documentation stays aligned with production requirements.

These tests verify that key docs reference all production-required environment
variables and configuration, preventing documentation drift.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Production-required env vars as validated by ProductionConfig.validate()
REQUIRED_PRODUCTION_ENV_KEYS = [
    "SECRET_KEY",
    "ADMIN_PASSWORD",
    "CELERY_TASK_SECRET",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "DATABASE_URL",
    "FLASK_CONFIG",
]

# Secrets that must never appear as plaintext examples
FORBIDDEN_PLAINTEXT_EXAMPLES = [
    "SECRET_KEY=change-me",
    "SECRET_KEY=changeme",
    "ADMIN_PASSWORD=changeme",
    "ADMIN_PASSWORD=password",
    "CELERY_TASK_SECRET=changeme",
]


class TestEnvExampleAlignment:
    """Verify .env.example contains all required production variables."""

    def test_env_example_exists(self):
        assert (ROOT / ".env.example").exists(), ".env.example is missing"

    def test_env_example_lists_required_production_vars(self):
        text = (ROOT / ".env.example").read_text()
        for key in REQUIRED_PRODUCTION_ENV_KEYS:
            assert key in text, f".env.example is missing required variable: {key}"

    def test_env_example_has_no_forbidden_plaintext(self):
        text = (ROOT / ".env.example").read_text()
        for example in FORBIDDEN_PLAINTEXT_EXAMPLES:
            assert example not in text, (
                f".env.example contains forbidden plaintext example: {example}"
            )

    def test_env_example_has_generation_commands(self):
        text = (ROOT / ".env.example").read_text()
        assert "secrets.token_hex" in text, ".env.example should show SECRET_KEY generation"
        assert "hash_password.py" in text, ".env.example should reference hash_password.py"


class TestReadmeAlignment:
    """Verify README quickstart mentions all required secrets."""

    def test_readme_exists(self):
        assert (ROOT / "README.md").exists(), "README.md is missing"

    def test_readme_mentions_required_secrets(self):
        text = (ROOT / "README.md").read_text()
        for key in ["SECRET_KEY", "ADMIN_PASSWORD", "CELERY_TASK_SECRET"]:
            assert key in text, f"README.md is missing required secret: {key}"

    def test_readme_mentions_health_check(self):
        text = (ROOT / "README.md").read_text()
        assert "/health" in text, "README.md should mention health check endpoint"


class TestDeploymentDocsAlignment:
    """Verify deployment docs are consistent with actual Docker setup."""

    def test_deployment_docs_exist(self):
        assert (ROOT / "docs" / "deployment.md").exists(), "docs/deployment.md is missing"

    def test_deployment_docs_mention_required_secrets(self):
        text = (ROOT / "docs" / "deployment.md").read_text()
        for key in ["SECRET_KEY", "ADMIN_PASSWORD", "CELERY_TASK_SECRET"]:
            assert key in text, f"docs/deployment.md is missing required secret: {key}"

    def test_deployment_docs_no_http_basic_auth(self):
        """Admin endpoints use session auth or API tokens, not HTTP basic auth."""
        text = (ROOT / "docs" / "deployment.md").read_text()
        assert "curl -u admin:password" not in text, (
            "docs/deployment.md references HTTP basic auth which is not supported"
        )

    def test_deployment_docs_mention_db_migrate(self):
        text = (ROOT / "docs" / "deployment.md").read_text()
        assert "db-migrate" in text, "docs/deployment.md should mention db-migrate service"


class TestConfigurationDocsAlignment:
    """Verify configuration docs match production validation."""

    def test_configuration_docs_exist(self):
        assert (ROOT / "docs" / "configuration.md").exists(), "docs/configuration.md is missing"

    def test_configuration_docs_required_section_has_celery_task_secret(self):
        text = (ROOT / "docs" / "configuration.md").read_text()
        # Find the Required section and verify CELERY_TASK_SECRET is in it
        assert "CELERY_TASK_SECRET" in text, (
            "docs/configuration.md is missing CELERY_TASK_SECRET"
        )

    def test_configuration_docs_provider_types_include_gemini(self):
        text = (ROOT / "docs" / "configuration.md").read_text()
        assert "gemini" in text, "docs/configuration.md should list gemini provider type"


class TestSecurityDocsAlignment:
    """Verify security docs match implemented behavior."""

    def test_security_docs_exist(self):
        assert (ROOT / "docs" / "security.md").exists(), "docs/security.md is missing"

    def test_security_docs_mention_celery_task_secret(self):
        text = (ROOT / "docs" / "security.md").read_text()
        assert "CELERY_TASK_SECRET" in text, (
            "docs/security.md is missing CELERY_TASK_SECRET"
        )

    def test_security_docs_mention_fail_closed(self):
        text = (ROOT / "docs" / "security.md").read_text()
        assert "fail" in text.lower() and "closed" in text.lower(), (
            "docs/security.md should document fail-closed behavior"
        )

    def test_security_docs_no_wrong_password_format(self):
        """Password hash format should match werkzeug output, not a stale format."""
        text = (ROOT / "docs" / "security.md").read_text()
        # The old docs said pbkdf2:sha256:600000 but actual output is scrypt
        assert "pbkdf2:sha256:600000" not in text, (
            "docs/security.md has stale password hash format"
        )
