"""Frozen drawing projection DTOs and their permitted-size allowance.

The native projector owns display identity, drawing normalization, support bindings, projection
contexts and relationship members. `native_compiler` materializes those records into the frozen
models here. This module keeps only the drawing DTOs and the request-local element allowance that
the command and web layers consume.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from course_explorer.prerequisite._helpers import _PrerequisiteModel
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure

DisplayNodeKind = Literal[
    "course",
    "module",
    "and",
    "or",
    "cardinality",
    "credits",
    "course_count",
    "opaque_credits",
    "internal_requirement",
    "unresolved",
    "ignored",
]


class PrerequisiteDisplayNode(_PrerequisiteModel):
    """One drawn box keyed by its course-scoped display identity."""

    node_id: str
    kind: DisplayNodeKind
    owner_group_id: str | None = None
    course_group_id: str | None = None
    module_group_id: str | None = None
    require_min: int | None = None
    require_max: int | None = None
    credits_min: Decimal | None = Field(default=None, ge=0)
    credits_max: Decimal | None = Field(default=None, ge=0)
    count_min: int | None = None
    count_max: int | None = None
    referenced_group_id: str | None = None
    reason: str | None = None
    detail: str | None = None
    member_group_ids: tuple[str, ...] = ()
    diagnostic_ids: tuple[str, ...] = ()
    is_root: bool = False
    via_inferred: bool = False
    via_recommended: bool = False
    has_official_provenance: bool = False
    has_inferred_provenance: bool = False
    display_as_inferred: bool = False
    markable: bool = False


class PrerequisiteDisplayEdge(_PrerequisiteModel):
    """One directed drawing connection grouping every relationship between its endpoint pair."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    member_ids: tuple[str, ...] = ()
    inferred_only: bool = False


class PrerequisiteDrawingGraph(_PrerequisiteModel):
    """One deterministic drawing projection over native display identities."""

    nodes: tuple[PrerequisiteDisplayNode, ...] = ()
    edges: tuple[PrerequisiteDisplayEdge, ...] = ()


class PrerequisiteDrawingAllowance(_PrerequisiteModel):
    """Request-local counts for the drawing surface, separate from calculation."""

    allowed: bool
    limit: int | None
    course_count: int
    node_count: int
    edge_count: int
    element_count: int


class PrerequisiteGraphCompilation(_PrerequisiteModel):
    """One native solver structure paired with its permitted display projection."""

    solver: PrerequisiteSolverStructure
    display: PrerequisiteDrawingGraph | None = None
    drawing: PrerequisiteDrawingAllowance


def prerequisite_drawing_allowance(
    *,
    course_count: int,
    node_count: int,
    edge_count: int,
    max_elements: int | None,
) -> PrerequisiteDrawingAllowance:
    """Count every projected node and edge, separate from calculation."""
    element_count = node_count + edge_count
    return PrerequisiteDrawingAllowance(
        allowed=max_elements is None or element_count <= max_elements,
        limit=max_elements,
        course_count=course_count,
        node_count=node_count,
        edge_count=edge_count,
        element_count=element_count,
    )
