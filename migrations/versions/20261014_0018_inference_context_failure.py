"""inference target failure context reason.

Revision ID: 20261014_0018
Revises: 20261012_0017
Create Date: 2026-10-14

Adds one accepted value, ``context_exceeded``, to the ``inference_target_failures`` reason check, so a
no-route-fits capacity failure can be retained. The upgrade drops and recreates that constraint.
Downgrade refuses while any ``context_exceeded`` failure row is retained and otherwise restores the
reason list without ``context_exceeded``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0018"
down_revision: str | Sequence[str] | None = "20261012_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREVIOUS_REASONS = (
    "'missing_target_chunks','insufficient_candidates','incomplete_views',"
    "'request_failed','provider_output','invalid_result','ambiguous_code',"
    "'multiple_requirement_sets','target_direct_source'"
)
_CURRENT_REASONS = (
    "'missing_target_chunks','insufficient_candidates','incomplete_views',"
    "'request_failed','provider_output','invalid_result','ambiguous_code',"
    "'multiple_requirement_sets','target_direct_source','context_exceeded'"
)


def _reason_check() -> str:
    """Return the ORM-convention name of the failure-reason choice check."""
    return op.f("ck_inference_target_failures_reason_valid")


def _replace_reason_check(allowed: str) -> None:
    """Replace the named reason check with the supplied allowed reason list."""
    op.drop_constraint(_reason_check(), "inference_target_failures", type_="check")
    op.create_check_constraint(
        _reason_check(), "inference_target_failures", f"reason IN ({allowed})"
    )


def upgrade() -> None:
    """Widen the reason check to accept a no-route-fits capacity failure."""
    _replace_reason_check(_CURRENT_REASONS)


def downgrade() -> None:
    """Refuse while any context-exceeded failure row exists, else restore the reason list without it."""
    bind = op.get_bind()
    retained = bind.execute(
        sa.text("SELECT count(*) FROM inference_target_failures WHERE reason = 'context_exceeded'")
    ).scalar_one()
    if retained:
        raise RuntimeError(
            "cannot downgrade the inference target failure reason while "
            f"{retained} context-exceeded failures are retained; restore from the pre-migration "
            "backup instead"
        )
    _replace_reason_check(_PREVIOUS_REASONS)
