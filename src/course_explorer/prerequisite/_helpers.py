"""One owner for the shared prerequisite primitives.

The prerequisite expression, structure, projection and command contracts share the frozen closed
Pydantic base, and the expression and structure contracts also share the blank-text rejection. The
domain and inference contracts use the distinct-ID and order check, and the expression contract owns
the provenance-shape validator. Those primitives live here once, so a change cannot drift between
the expression vocabulary, the solver structure and its drawing projection, commands, and inference.
Semantics that differ, including field-specific `validate_kind` matrices and the solver, stay in
their owning modules.

The domain type names are imported for type checking only. `domain.py` imports this module for its
expression base and provenance validator, so a runtime reverse import would cycle. At runtime the
already-validated `StrEnum` origin is distinguished by its string values instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from course_explorer.prerequisite.domain import (
        InferenceNodeMetadata,
        InferredPrerequisiteCategory,
        OfficialPrerequisiteKind,
        PrerequisiteOrigin,
    )


class _PrerequisiteModel(BaseModel):
    """Frozen, closed base for the prerequisite expression, structure, projection and command
    contracts."""

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
