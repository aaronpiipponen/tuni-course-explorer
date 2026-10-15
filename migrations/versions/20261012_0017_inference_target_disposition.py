"""inference target disposition.

Revision ID: 20261012_0017
Revises: 20261012_0016
Create Date: 2026-10-12

Adds the operator's durable inference decision ``inference_course_processing.disposition``: a
nullable ``done``/``failed`` text choice with no default, so every row without a decision holds NULL
(automatic). Downgrade refuses while any nonnull decision exists. Otherwise it drops this addition.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0017"
down_revision: str | Sequence[str] | None = "20261012_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _disposition_check() -> str:
    """Return the ORM-convention name of the nullable disposition choice check."""
    return op.f("ck_inference_course_processing_disposition_valid")


def upgrade() -> None:
    """Add the nullable operator disposition column and its closed choice check."""
    op.add_column(
        "inference_course_processing",
        sa.Column("disposition", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        _disposition_check(),
        "inference_course_processing",
        "disposition IS NULL OR disposition IN ('done','failed')",
    )


def downgrade() -> None:
    """Refuse while any operator decision exists, else drop only the disposition addition."""
    bind = op.get_bind()
    decided = bind.execute(
        sa.text("SELECT count(*) FROM inference_course_processing WHERE disposition IS NOT NULL")
    ).scalar_one()
    if decided:
        raise RuntimeError(
            "cannot downgrade the inference target disposition while "
            f"{decided} operator decisions are retained; restore from the pre-migration backup "
            "instead"
        )
    op.drop_constraint(_disposition_check(), "inference_course_processing", type_="check")
    op.drop_column("inference_course_processing", "disposition")
