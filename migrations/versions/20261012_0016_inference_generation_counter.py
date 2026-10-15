"""inference generation counter.

Revision ID: 20261012_0016
Revises: 20261008_0015
Create Date: 2026-10-12

Adds the two durable facts the deterministic generation-retry policy needs: the canonical-course
lifetime ``inference_course_processing.generation_attempt_count`` (no-reuse local seed ordinal) and
the per-cycle-target ``inference_processing_targets.generation_started`` (greedy-once-per-calculation
flag). Both are nonnullable with zero/false server defaults. Downgrade refuses while any lifetime
count is nonzero or any target calculation has started. Otherwise it drops these additions.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0016"
down_revision: str | Sequence[str] | None = "20261008_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _counter_check() -> str:
    """Return the ORM-convention name of the lifetime counter's nonnegative check."""
    return op.f("ck_inference_course_processing_generation_attempt_count_nonnegative")


def upgrade() -> None:
    """Add the lifetime generation counter and the calculation-started flag with zero defaults."""
    op.add_column(
        "inference_course_processing",
        sa.Column(
            "generation_attempt_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        _counter_check(),
        "inference_course_processing",
        "generation_attempt_count >= 0",
    )
    op.add_column(
        "inference_processing_targets",
        sa.Column(
            "generation_started",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Refuse while any lifetime count is nonzero or any calculation has started, else drop additions."""
    bind = op.get_bind()
    used = bind.execute(
        sa.text(
            "SELECT count(*) FROM inference_course_processing WHERE generation_attempt_count <> 0"
        )
    ).scalar_one()
    started = bind.execute(
        sa.text("SELECT count(*) FROM inference_processing_targets WHERE generation_started")
    ).scalar_one()
    if used or started:
        raise RuntimeError(
            "cannot downgrade the inference generation counter while "
            f"{used} canonical lifetime counts are nonzero or {started} target calculations started; "
            "restore from the pre-migration backup instead"
        )
    op.drop_column("inference_processing_targets", "generation_started")
    op.drop_constraint(_counter_check(), "inference_course_processing", type_="check")
    op.drop_column("inference_course_processing", "generation_attempt_count")
