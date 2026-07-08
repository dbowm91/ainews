"""Smoke tests for documentation consistency.

Validates that required environment variables documented in .env.example
are also mentioned in README.md and docs/configuration.md.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

REQUIRED_VARS = {
    "FLASK_CONFIG",
    "SECRET_KEY",
    "ADMIN_PASSWORD",
    "CELERY_TASK_SECRET",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "DATABASE_URL",
}


def _read_env_example():
    """Extract variable names from .env.example."""
    content = (ROOT / ".env.example").read_text()
    vars_found = set()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if "=" in line:
            var_name = line.split("=", 1)[0].strip()
            if var_name and not var_name.startswith("#"):
                vars_found.add(var_name)
    return vars_found


def test_env_example_documents_required_vars():
    """All required env vars are documented in .env.example."""
    env_vars = _read_env_example()
    for var in REQUIRED_VARS:
        assert var in env_vars, f"{var} not found in .env.example"


def test_readme_mentions_required_vars():
    """README mentions all required env vars."""
    readme = (ROOT / "README.md").read_text()
    for var in REQUIRED_VARS:
        assert var in readme, f"{var} not mentioned in README.md"


def test_docs_configuration_mentions_required_vars():
    """docs/configuration.md mentions all required env vars."""
    config_doc = ROOT / "docs" / "configuration.md"
    if not config_doc.exists():
        pytest.skip("docs/configuration.md not found")
    content = config_doc.read_text()
    for var in REQUIRED_VARS:
        assert var in content, f"{var} not mentioned in docs/configuration.md"
