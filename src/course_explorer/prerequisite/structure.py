"""Frozen native prerequisite calculation structure.

This module owns the one calculation representation the compiler, the solver, discovery and the
drawing projector consume. A piece is one structural calculation node. A use binds one source
position and its provenance fact to a piece, and an ordered path through use slots is the implicit
occurrence. Native code assigns every piece, use, fact and diagnostic identity. The DTOs here hold
those identities and their ordered relationships.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from course_explorer.curriculum import CourseSummary, ModuleSummary
from course_explorer.enums import InferredCoverageState
from course_explorer.prerequisite._helpers import _nonblank, _PrerequisiteModel
from course_explorer.prerequisite.domain import (
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    InferredSetCoverage,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)

PrerequisitePieceKind = Literal[
    "course",
    "and",
    "or",
    "expanded_course",
    "course_alternatives",
    "cardinality",
    "credits",
    "course_count",
    "module_block",
    "opaque_credits",
    "unresolved",
]


class InferredCoverageRecord(_PrerequisiteModel):
    """One current inferred set's coverage seen during active-course traversal."""

    target_group_id: str
    coverage_state: InferredCoverageState
    coverage: InferredSetCoverage

    @field_validator("target_group_id")
    @classmethod
    def reject_blank_target(cls, value: str) -> str:
        """Require a nonblank canonical target identity."""
        return _nonblank(value, "target_group_id")


class PrerequisiteSourceFact(_PrerequisiteModel):
    """One provenance shape shared by every source use that carries it."""

    fact_id: str
    origin: PrerequisiteOrigin
    official_kind: OfficialPrerequisiteKind | None = None
    inferred_category: InferredPrerequisiteCategory | None = None
    inference: InferenceNodeMetadata | None = None

    @field_validator("fact_id")
    @classmethod
    def reject_blank_fact(cls, value: str) -> str:
        """Require a nonblank fact identity."""
        return _nonblank(value, "fact_id")


class PrerequisitePiece(_PrerequisiteModel):
    """One structural calculation node with ordered child piece slots.

    `children` is ordered and may repeat. The twelve scalar fields from `course_group_id` through
    `detail` enter the native identity payload, with unused fields set to null, together with
    `module_rule`, `manual_credits_min` and `cycle_closing`.
    """

    piece_id: str
    kind: PrerequisitePieceKind
    children: tuple[str, ...] = ()
    course_group_id: str | None = None
    module_group_id: str | None = None
    work_key: str | None = None
    require_min: int | None = None
    require_max: int | None = None
    credits_min: Decimal | None = Field(default=None, ge=0)
    credits_max: Decimal | None = Field(default=None, ge=0)
    count_min: int | None = None
    count_max: int | None = None
    reason: str | None = None
    referenced_group_id: str | None = None
    detail: str | None = None
    manual_credits_min: Decimal | None = Field(default=None, ge=0)
    module_rule: bool = False
    cycle_closing: bool = False

    @field_validator("piece_id")
    @classmethod
    def reject_blank_piece(cls, value: str) -> str:
        """Require a nonblank piece identity."""
        return _nonblank(value, "piece_id")


class PrerequisiteDiagnostic(_PrerequisiteModel):
    """One explicit located compilation problem or ignored source part."""

    diagnostic_id: str
    kind: str
    fact_id: str
    referenced_group_ids: tuple[str, ...] = ()
    detail: str | None = None
    module_group_id: str | None = None

    @field_validator("diagnostic_id", "kind", "fact_id")
    @classmethod
    def reject_blank_diagnostic(cls, value: str) -> str:
        """Require nonblank identity and kind text."""
        return _nonblank(value, "diagnostic field")


class PrerequisiteSourceUse(_PrerequisiteModel):
    """One source position's ordered child use slots and its provenance fact.

    `children` contains use IDs, never piece IDs. At slot `j` the child use's `piece_id` is this
    use's piece's `children[j]`, a producer guarantee that needs no second validation walk.
    """

    use_id: str
    piece_id: str
    fact_id: str
    children: tuple[str, ...] = ()
    diagnostic_ids: tuple[str, ...] = ()
    member_group_ids: tuple[str, ...] = ()

    @field_validator("use_id", "piece_id", "fact_id")
    @classmethod
    def reject_blank_use(cls, value: str) -> str:
        """Require nonblank use, piece and fact identities."""
        return _nonblank(value, "source use field")


class PrerequisiteSupportBinding(_PrerequisiteModel):
    """One scoped calculation support and the source uses and display locations it stands for.

    `node_ids` are the display nodes that bind this support. `mark_node_ids` are the markable box
    locations a saved mark applies through. Elided and hidden supports locate at their nearest
    emitted containing node.
    """

    support_id: str
    owner_group_id: str
    piece_id: str
    use_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    mark_node_ids: tuple[str, ...] = ()

    @field_validator("support_id", "owner_group_id", "piece_id")
    @classmethod
    def reject_blank_binding(cls, value: str) -> str:
        """Require nonblank support, owner and piece identities."""
        return _nonblank(value, "support binding field")


class PrerequisiteRelationshipMember(_PrerequisiteModel):
    """One relationship member between two emitted display identities."""

    member_id: str
    source_node_id: str
    target_node_id: str
    fact_id: str


class PrerequisiteProjectionChild(_PrerequisiteModel):
    """One native child slot and the projection context it selects."""

    slot: int
    context_id: str


class PrerequisiteProjectionContext(_PrerequisiteModel):
    """One native calculation context and the relationship members it selects."""

    context_id: str
    owner_group_id: str
    piece_id: str
    children: tuple[PrerequisiteProjectionChild, ...] = ()
    member_ids: tuple[str, ...] = ()


class PrerequisiteSolverStructure(_PrerequisiteModel):
    """One root's native calculation structure with frozen, ID-sorted id tables."""

    root_group_id: str
    academic_year_start: int = Field(gt=0)
    root_use_id: str | None = None
    pieces: tuple[PrerequisitePiece, ...] = ()
    uses: tuple[PrerequisiteSourceUse, ...] = ()
    facts: tuple[PrerequisiteSourceFact, ...] = ()
    diagnostics: tuple[PrerequisiteDiagnostic, ...] = ()
    root_diagnostic_ids: tuple[str, ...] = ()
    courses: tuple[CourseSummary, ...] = ()
    modules: tuple[ModuleSummary, ...] = ()
    include_recommended: bool = False
    include_inferred: bool = False
    active_only: bool = False
    inferred_coverage: tuple[InferredCoverageRecord, ...] = ()
    excluded_group_ids: tuple[str, ...] = ()
    completed_node_keys: tuple[str, ...] = ()
    excluded_node_keys: tuple[str, ...] = ()
    bindings: tuple[PrerequisiteSupportBinding, ...] = ()
    projection_root_context_id: str | None = None
    projection_contexts: tuple[PrerequisiteProjectionContext, ...] = ()
    members: tuple[PrerequisiteRelationshipMember, ...] = ()
