"""Tests for database migrations (Flask-Migrate/Alembic)."""

from flask_migrate import upgrade, downgrade
from extensions import db

import pytest

pytestmark = pytest.mark.skip(
    reason="Alembic config (migrations/alembic.ini) not available in test environment"
)


class TestMigrations:
    """Test that migrations can be applied and rolled back."""

    def test_upgrade_head(self, app):
        """Run migrations to head."""
        with app.app_context():
            # This will apply all migrations
            upgrade()
            # Verify that tables exist (at least one table)
            insp = db.engine.inspector()
            tables = insp.get_table_names()
            assert len(tables) > 0
            # Downgrade back to base
            downgrade()
            # After downgrade, tables may be empty (depends on base migration)
            # We'll just ensure no errors.

    def test_downgrade_base(self, app):
        """Downgrade to base and upgrade again."""
        with app.app_context():
            upgrade()
            downgrade()
            upgrade()
            # Should succeed without errors
