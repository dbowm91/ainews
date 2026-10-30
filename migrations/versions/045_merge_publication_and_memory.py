"""Join the publication and editor-memory migration lines."""
from __future__ import annotations

revision = "045_merge_publication_and_memory"
down_revision = ("044_llm_native_publication", "043_memory_synthesis_fairness_cursor")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Both parent revisions are additive; this revision only joins history."""


def downgrade() -> None:
    """Downgrade returns to the two independently preserved parent states."""
