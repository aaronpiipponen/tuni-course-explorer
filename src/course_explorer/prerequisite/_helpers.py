"""One owner for the shared prerequisite primitives.

`domain.py`, `graph.py`, `path.py`, and `satisfaction.py` all declare the same frozen closed
Pydantic base, reject the same blank text, enforce the same official/inferred/composed provenance
shape, measure one witness set's canonical credit total, map a tree's opaque work keys to their
source minimum credits, and check distinct IDs and order the same way. Those live here once so a
change cannot drift between the expression vocabulary, the calculation
tree and its drawing projection, satisfaction, and minimum-credit pathing. Semantics that differ
(field-specific `validate_kind` matrices, the two-field compilation-issue/path-blocker
provenance checks, and the solver) stay in their owning modules. The witness credit/count bounds
themselves are exact family filters owned by the solver and satisfaction DAGs.

The domain type names are imported for type checking only: `domain.py` imports this module for its
expression base and provenance validator, so a runtime reverse import would cycle. At runtime the
already-validated `StrEnum` origin is distinguished by its string values instead.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from course_explorer.prerequisite.domain import (
        InferenceNodeMetadata,
        InferredPrerequisiteCategory,
        OfficialPrerequisiteKind,
        PrerequisiteOrigin,
    )
    from course_explorer.prerequisite.graph import PrerequisiteCalculationTree


class _PrerequisiteModel(BaseModel):
    """Frozen, closed base for every prerequisite expression, graph, path, and satisfaction contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _nonblank(value: str, field_name: str) -> str:
    """Return a nonblank string or reject it with the offending field name."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _unique_ids[T](
    value: tuple[T, ...], field_name: str, *, sorted_required: bool = False
) -> tuple[T, ...]:
    """Reject duplicate IDs or flags with one set-size comparison and optionally require order.

    It is generic over typed identity/flag tuples. It checks only distinctness and order, so blank,
    type and minimum-length rules live with the field and boundary owners. The
    tuple is returned without normalization.
    """
    if len(set(value)) != len(value):
        raise ValueError(f"{field_name} must be unique")
    if sorted_required and value != tuple(sorted(value)):
        raise ValueError(f"{field_name} must be sorted")
    return value


def _validate_origin_shape(
    origin: PrerequisiteOrigin,
    official_kind: OfficialPrerequisiteKind | None,
    inferred_category: InferredPrerequisiteCategory | None,
    inference: InferenceNodeMetadata | None,
) -> None:
    """Enforce exactly one provenance shape consistent with the declared origin."""
    if origin == "official":
        if official_kind is None:
            raise ValueError("official nodes require official_kind")
        if inferred_category is not None:
            raise ValueError("official nodes forbid inferred_category")
        if inference is not None:
            raise ValueError("official nodes forbid inference metadata")
    elif origin == "inferred":
        if official_kind is not None:
            raise ValueError("inferred nodes forbid official_kind")
        if inferred_category is None:
            raise ValueError("inferred nodes require inferred_category")
        if inference is None:
            raise ValueError("inferred nodes require inference metadata")
    else:
        if official_kind is not None or inference is not None:
            raise ValueError("composed nodes forbid both official and inference provenance")
        if inferred_category is not None:
            raise ValueError("composed nodes forbid inferred_category")


def _witness_credits(
    witness_group_ids: frozenset[str], credits_min_by_group_id: dict[str, Decimal]
) -> Decimal:
    """Return one witness set's canonical `credits_min` total."""
    total = Decimal(0)
    for group_id in witness_group_ids:
        credits = credits_min_by_group_id.get(group_id)
        if credits is None:
            raise ValueError(f"course {group_id} is missing from the calculation tree courses")
        total += credits
    return total


def _opaque_credits_by_work_key(tree: PrerequisiteCalculationTree) -> dict[str, Decimal]:
    """Return one opaque work key to source minimum-credit map from the tree's expression."""
    from course_explorer.prerequisite.domain import OpaqueCreditRequirement
    from course_explorer.prerequisite.graph import _iter_expression_occurrences

    credits: dict[str, Decimal] = {}
    if tree.requirements is None:
        return credits
    for _, expression in _iter_expression_occurrences(tree.requirements):
        if isinstance(expression, OpaqueCreditRequirement):
            credits.setdefault(expression.work_key, expression.credits_min)
    return credits
