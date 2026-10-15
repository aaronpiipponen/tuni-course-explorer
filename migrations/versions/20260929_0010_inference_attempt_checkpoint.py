"""inference attempt checkpoint.

Revision ID: 20260929_0010
Revises: 20260917_0009
Create Date: 2026-09-29

This chain step holds the revision link between `20260917_0009` and `20260929_0011`. Upgrade and
downgrade perform no schema or data change.
"""

from collections.abc import Sequence

revision: str = "20260929_0010"
down_revision: str | Sequence[str] | None = "20260917_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the chain step. This revision performs no schema or data change."""


def downgrade() -> None:
    """Reverse the chain step. This revision performs no schema or data change."""
