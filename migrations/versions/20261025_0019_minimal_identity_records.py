"""Inference identity records without copied content hashes.

Revision ID: 20261025_0019
Revises: 20261014_0018
Create Date: 2026-10-25

Drops the persisted prompt-content and schema digests from the shared execution row and the
persisted input digest from target work. The rendered request carries content identity, and target
work reaches its input digest through the work key. Upgrade performs explicit DDL drops. Downgrade
refuses because the removed identity data cannot be restored.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261025_0019"
down_revision: str | Sequence[str] | None = "20261014_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_CHECKS = (
    "ck_inference_pipeline_runs_prompt_content_sha256_sha256",
    "ck_inference_pipeline_runs_schema_sha256_sha256",
)
_RUN_COLUMNS = (
    "prompt_content_sha256",
    "schema_sha256",
)


def upgrade() -> None:
    """Drop the three identity hashes and their checks."""
    for name in _RUN_CHECKS:
        op.drop_constraint(op.f(name), "inference_pipeline_runs", type_="check")
    for column in _RUN_COLUMNS:
        op.drop_column("inference_pipeline_runs", column)

    op.drop_constraint(
        op.f("ck_inference_target_work_input_sha256_sha256"),
        "inference_target_work",
        type_="check",
    )
    op.drop_column("inference_target_work", "input_sha256")


def downgrade() -> None:
    """Refuse the irreversible identity-record conversion."""
    raise RuntimeError(
        "20261025_0019 removes inference identity hashes that cannot be restored; "
        "restore from the pre-migration backup instead of downgrading"
    )
