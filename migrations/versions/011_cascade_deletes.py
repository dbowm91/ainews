"""add cascade delete rules to foreign keys

Revision ID: 011_cascade_deletes
Revises: 010_subscriber_verification
Create Date: 2026-03-31

Note: SQLite doesn't support ALTER TABLE for FK changes. This migration
is a no-op on existing databases. The cascade rules are enforced via
SQLAlchemy relationship cascades at the application level. New databases
(created by tests) will have the FK-level CASCADE rules.
"""

from typing import Sequence, Union

revision: str = "011_cascade_deletes"
down_revision: Union[str, Sequence[str], None] = "010_subscriber_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FK-level CASCADE not supported via ALTER TABLE in SQLite.
    # SQLAlchemy model-level cascade="all, delete-orphan" handles this
    # at the application level. New databases get FK CASCADE from model defs.
    pass


def downgrade() -> None:
    pass
