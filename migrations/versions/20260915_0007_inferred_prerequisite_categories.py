"""inferred_prerequisite_categories.

Revision ID: 20260915_0007
Revises: 20260915_0006
Create Date: 2026-09-15
"""

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0007"
down_revision: str | Sequence[str] | None = "20260915_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUIRED = "required"
_RECOMMENDED = "recommended"
_CONNECTOR_TYPES = ("and", "or")

_SELECT_EXPRESSIONS = sa.text(
    "SELECT s.id AS set_id, c.group_id AS target_group_id, "
    "s.activity_as_of_academic_year_start, s.activity_window_years, "
    "s.producer_kind, s.producer_name, s.producer_version, s.input_hash, "
    "s.coverage_state, s.eligible_source_count, s.processed_source_count, "
    "s.accepted_source_count, s.expression "
    "FROM inferred_prerequisite_sets s "
    "JOIN courses c ON c.id = s.target_course_id "
    "WHERE s.expression IS NOT NULL"
)

_UPDATE_EXPRESSION = sa.text(
    "UPDATE inferred_prerequisite_sets "
    "SET expression = CAST(:expression AS jsonb), payload_hash = :payload_hash "
    "WHERE id = :set_id"
)

_DOWNGRADE_BLOCK_MESSAGE = (
    "cannot downgrade inferred prerequisite categories: a RECOMMENDED occurrence would lose its "
    "category and be relabeled as required under the previous always-required contract"
)


def _require_inferred_node(node: object) -> dict[str, object]:
    """Return one persisted inferred expression object or reject a malformed shape."""
    if not isinstance(node, dict):
        raise ValueError("inferred expression nodes must be JSON objects")
    if node.get("origin") != "inferred":
        raise ValueError("inferred expression nodes must carry inferred origin")
    return node


def _require_children(node: dict[str, object], node_type: str) -> list[object]:
    """Return the ordered child list of one inferred and/or node or reject the shape."""
    children = node.get("children")
    if not isinstance(children, list) or not children:
        raise ValueError(f"inferred {node_type} nodes require a nonempty children list")
    return children


def _add_required_category(node: object) -> dict[str, object]:
    """Copy one inferred occurrence tree, adding REQUIRED on every occurrence."""
    inferred = _require_inferred_node(node)
    if "inferred_category" in inferred:
        raise ValueError("inferred expression node already declares inferred_category")
    node_type = inferred.get("type")
    if node_type == "course":
        if "children" in inferred:
            raise ValueError("inferred course nodes must not carry children")
        return {**inferred, "inferred_category": _REQUIRED}
    if node_type in _CONNECTOR_TYPES:
        children = [
            _add_required_category(child) for child in _require_children(inferred, node_type)
        ]
        return {**inferred, "children": children, "inferred_category": _REQUIRED}
    raise ValueError(f"unsupported inferred expression node type {node_type!r}")


def _strip_required_category(node: object) -> dict[str, object]:
    """Copy one REQUIRED-only inferred tree, removing exactly the inferred_category field."""
    inferred = _require_inferred_node(node)
    category = inferred.get("inferred_category")
    if category == _RECOMMENDED:
        raise ValueError(_DOWNGRADE_BLOCK_MESSAGE)
    if category != _REQUIRED:
        raise ValueError("inferred expression node must declare the REQUIRED category")
    stripped = {key: value for key, value in inferred.items() if key != "inferred_category"}
    node_type = inferred.get("type")
    if node_type == "course":
        if "children" in inferred:
            raise ValueError("inferred course nodes must not carry children")
        return stripped
    if node_type in _CONNECTOR_TYPES:
        stripped["children"] = [
            _strip_required_category(child) for child in _require_children(inferred, node_type)
        ]
        return stripped
    raise ValueError(f"unsupported inferred expression node type {node_type!r}")


def _canonical_payload(row: dict[str, object], expression: dict[str, object]) -> dict[str, object]:
    """Rebuild the exact canonical payload dict the repository hashes.

    Field-for-field mirror of the inferred-set repository's canonical payload: target identity,
    both activity integers, producer kind/name/version, input hash, coverage state, all three
    coverage counts, and the transformed expression. `generated_at` is absent.
    """
    return {
        "target_group_id": row["target_group_id"],
        "activity_as_of_academic_year_start": row["activity_as_of_academic_year_start"],
        "activity_window_years": row["activity_window_years"],
        "producer_kind": row["producer_kind"],
        "producer_name": row["producer_name"],
        "producer_version": row["producer_version"],
        "input_hash": row["input_hash"],
        "coverage_state": row["coverage_state"],
        "eligible_source_count": row["eligible_source_count"],
        "processed_source_count": row["processed_source_count"],
        "accepted_source_count": row["accepted_source_count"],
        "expression": expression,
    }


def _payload_sha256(payload: dict[str, object]) -> str:
    """Hash one canonical payload dict with sorted compact UTF-8 JSON, as the repository does."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _rewrite_expressions(transform) -> None:
    """Transform every nonempty inferred expression and refresh its canonical payload hash.

    All rows are transformed before the first write so a rejection (a malformed node or a
    downgrade-blocking recommendation) fails the whole migration without a partial relabel.
    """
    connection = op.get_bind()
    rows = [dict(row) for row in connection.execute(_SELECT_EXPRESSIONS).mappings()]
    rewritten: list[tuple[object, str, str]] = []
    for row in rows:
        expression = transform(row["expression"])
        payload_hash = _payload_sha256(_canonical_payload(row, expression))
        rewritten.append(
            (
                row["set_id"],
                json.dumps(expression, ensure_ascii=False),
                payload_hash,
            )
        )
    for set_id, expression_json, payload_hash in rewritten:
        connection.execute(
            _UPDATE_EXPRESSION,
            {"set_id": set_id, "expression": expression_json, "payload_hash": payload_hash},
        )


def upgrade() -> None:
    """Add the explicit REQUIRED category to every stored inferred occurrence."""
    _rewrite_expressions(_add_required_category)


def downgrade() -> None:
    """Remove inferred categories from REQUIRED-only rows, refusing any RECOMMENDED data."""
    _rewrite_expressions(_strip_required_category)
