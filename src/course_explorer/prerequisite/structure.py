"""Frozen native prerequisite calculation structure and its request-local interner.

This module owns the one calculation representation the compiler, the solver, satisfaction,
discovery and the graph projector consume. A piece is one structural calculation node interned
once by its provenance-free content. A use binds one source position and its provenance fact to a
piece, and an ordered path through use slots is the implicit occurrence. A piece, a use and a fact
are the only stored forms.

Identities are content digests over flat payloads that refer to interned child IDs, so equal
structures share one piece and different evaluation semantics cannot share one answer. Provenance,
source position, owner and display equality never enter the calculation digest. The builder is
request-local and never retained: it reads no configuration, performs no I/O and holds no cache
beyond one compilation.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from course_explorer.curriculum import CourseSummary, ModuleSummary
from course_explorer.enums import InferredCoverageState
from course_explorer.hashing import json_sha256
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

_SCALAR_FIELDS = (
    "course_group_id",
    "module_group_id",
    "work_key",
    "require_min",
    "require_max",
    "credits_min",
    "credits_max",
    "count_min",
    "count_max",
    "reason",
    "referenced_group_id",
    "detail",
)


def canonical_number(value: Decimal | int | None) -> str | None:
    """Render one numeric bound canonically so equal values compare equal."""
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def digest(payload: object) -> str:
    """Return one deterministic fixed-length content digest of a flat payload."""
    return json_sha256(payload, ensure_ascii=False)[:24]


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

    `children` is ordered and may repeat. Every name in `_SCALAR_FIELDS` enters the identity
    payload, with unused fields set to null, together with `module_rule`, `manual_credits_min` and
    `cycle_closing`.
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


def support_id(*, owner_group_id: str, piece_id: str) -> str:
    """Return one scoped calculation support identity."""
    return f"s:{owner_group_id}:{piece_id}"


def display_piece_id(*, owner_group_id: str, fingerprint: str) -> str:
    """Return one non-course display piece and saved box mark identity."""
    return f"s:{owner_group_id}:d:{fingerprint}"


def module_member_group_ids(
    use_id: str,
    *,
    piece_of_use: Callable[[str], PrerequisitePiece],
    children_of_use: Callable[[str], tuple[str, ...]],
) -> tuple[str, ...]:
    """Return one module body's explicit official member course group IDs.

    A course contributes itself and stops. An expanded course contributes only its first child's
    course identity and stops. A course-alternatives piece walks only its first child, and every
    other kind recurses in child order. The result is sorted and unique.
    """
    found: set[str] = set()

    def walk(current: str) -> None:
        piece = piece_of_use(current)
        children = children_of_use(current)
        if piece.kind == "course" and piece.course_group_id is not None:
            found.add(piece.course_group_id)
            return
        if piece.kind == "expanded_course" and children:
            head = piece_of_use(children[0])
            if head.course_group_id is not None:
                found.add(head.course_group_id)
            return
        if piece.kind == "course_alternatives" and children:
            walk(children[0])
            return
        for child in children:
            walk(child)

    walk(use_id)
    return tuple(sorted(found))


class PrerequisiteStructureBuilder:
    """Request-local interner that assigns every native identity from flat content digests."""

    def __init__(self) -> None:
        """Create one empty request-local interner."""
        self._pieces: dict[str, PrerequisitePiece] = {}
        self._uses: dict[str, PrerequisiteSourceUse] = {}
        self._facts: dict[str, PrerequisiteSourceFact] = {}
        self._diagnostics: dict[str, PrerequisiteDiagnostic] = {}
        self._source_keys: dict[str, tuple[str | int, ...]] = {}

    def intern_fact(
        self,
        *,
        origin: PrerequisiteOrigin,
        official_kind: OfficialPrerequisiteKind | None = None,
        inferred_category: InferredPrerequisiteCategory | None = None,
        inference: InferenceNodeMetadata | None = None,
    ) -> str:
        """Intern one provenance fact and return its identity."""
        payload = [
            origin.value,
            None if official_kind is None else official_kind.value,
            None if inferred_category is None else inferred_category.value,
            None if inference is None else inference.model_dump(mode="json"),
        ]
        fact_id = f"f:{digest(payload)}"
        self._facts.setdefault(
            fact_id,
            PrerequisiteSourceFact(
                fact_id=fact_id,
                origin=origin,
                official_kind=official_kind,
                inferred_category=inferred_category,
                inference=inference,
            ),
        )
        return fact_id

    def intern_piece(
        self,
        *,
        kind: PrerequisitePieceKind,
        children: tuple[str, ...] = (),
        manual_credits_min: Decimal | None = None,
        module_rule: bool = False,
        cycle_closing: bool = False,
        **scalar_payload: object,
    ) -> str:
        """Intern one calculation piece from its kind, ordered children and scalar payload."""
        unknown = set(scalar_payload) - set(_SCALAR_FIELDS)
        if unknown:
            raise ValueError(f"unsupported piece payload fields {sorted(unknown)}")
        values: dict[str, object] = {}
        for name in _SCALAR_FIELDS:
            value = scalar_payload.get(name)
            if isinstance(value, Decimal):
                value = canonical_number(value)
            values[name] = value
        payload = [
            kind,
            values,
            list(children),
            canonical_number(manual_credits_min),
            module_rule,
            cycle_closing,
        ]
        piece_id = f"p:{digest(payload)}"
        self._pieces.setdefault(
            piece_id,
            PrerequisitePiece(
                piece_id=piece_id,
                kind=kind,
                children=children,
                manual_credits_min=manual_credits_min,
                module_rule=module_rule,
                cycle_closing=cycle_closing,
                **scalar_payload,
            ),
        )
        return piece_id

    def intern_use(
        self,
        *,
        piece_id: str,
        fact_id: str,
        children: tuple[str, ...],
        source_key: tuple[str | int, ...],
        diagnostic_ids: tuple[str, ...] = (),
        member_group_ids: tuple[str, ...] = (),
    ) -> str:
        """Intern one source use position, retaining exact child slot order and repetitions."""
        payload = [
            piece_id,
            fact_id,
            list(children),
            list(source_key),
            list(diagnostic_ids),
            list(member_group_ids),
        ]
        use_id = f"u:{digest(payload)}"
        self._uses.setdefault(
            use_id,
            PrerequisiteSourceUse(
                use_id=use_id,
                piece_id=piece_id,
                fact_id=fact_id,
                children=children,
                diagnostic_ids=diagnostic_ids,
                member_group_ids=member_group_ids,
            ),
        )
        self._source_keys.setdefault(use_id, source_key)
        return use_id

    def reintern(
        self,
        use_id: str,
        *,
        children: tuple[str, ...],
        diagnostic_ids: tuple[str, ...] | None = None,
    ) -> str:
        """Re-intern one use with rewritten child slots, preserving its kind and scalar payload."""
        use = self._uses[use_id]
        piece = self._pieces[use.piece_id]
        child_pieces = tuple(self.piece_id_of_use(child) for child in children)
        scalars = {name: getattr(piece, name) for name in _SCALAR_FIELDS}
        new_piece = self.intern_piece(
            kind=piece.kind,
            children=child_pieces,
            manual_credits_min=piece.manual_credits_min,
            module_rule=piece.module_rule,
            cycle_closing=piece.cycle_closing,
            **scalars,
        )
        return self.intern_use(
            piece_id=new_piece,
            fact_id=use.fact_id,
            children=children,
            source_key=self._source_keys[use_id],
            diagnostic_ids=use.diagnostic_ids if diagnostic_ids is None else diagnostic_ids,
            member_group_ids=use.member_group_ids,
        )

    def piece(self, piece_id: str) -> PrerequisitePiece:
        """Return one interned piece by identity."""
        return self._pieces[piece_id]

    def diagnostic(self, diagnostic_id: str) -> PrerequisiteDiagnostic:
        """Return one interned diagnostic by identity."""
        return self._diagnostics[diagnostic_id]

    def use(self, use_id: str) -> PrerequisiteSourceUse:
        """Return one interned source use by identity."""
        return self._uses[use_id]

    def piece_id_of_use(self, use_id: str) -> str:
        """Return the calculation piece one source use evaluates."""
        return self._uses[use_id].piece_id

    def intern_diagnostic(
        self,
        *,
        kind: str,
        fact_id: str,
        referenced_group_ids: tuple[str, ...] = (),
        detail: str | None = None,
        module_group_id: str | None = None,
    ) -> str:
        """Intern one located diagnostic or ignored source part."""
        payload = [kind, fact_id, list(referenced_group_ids), detail, module_group_id]
        diagnostic_id = f"i:{digest(payload)}"
        self._diagnostics.setdefault(
            diagnostic_id,
            PrerequisiteDiagnostic(
                diagnostic_id=diagnostic_id,
                kind=kind,
                fact_id=fact_id,
                referenced_group_ids=referenced_group_ids,
                detail=detail,
                module_group_id=module_group_id,
            ),
        )
        return diagnostic_id

    def finish(
        self,
        *,
        root_group_id: str,
        academic_year_start: int,
        root_use_id: str | None,
        extra_root_use_ids: tuple[str | None, ...] = (),
        root_diagnostic_ids: tuple[str, ...],
        courses: tuple[CourseSummary, ...],
        modules: tuple[ModuleSummary, ...],
        include_recommended: bool,
        include_inferred: bool,
        active_only: bool,
        inferred_coverage: tuple[InferredCoverageRecord, ...],
        excluded_group_ids: tuple[str, ...],
        completed_node_keys: tuple[str, ...],
        excluded_node_keys: tuple[str, ...],
    ) -> PrerequisiteSolverStructure:
        """Freeze only objects reachable from the surviving roots into one ID-sorted structure."""
        use_roots = tuple(
            sorted({value for value in (root_use_id, *extra_root_use_ids) if value is not None})
        )
        reachable_uses: set[str] = set()
        stack = list(use_roots)
        while stack:
            use_id = stack.pop()
            if use_id in reachable_uses:
                continue
            reachable_uses.add(use_id)
            stack.extend(self._uses[use_id].children)
        reachable_pieces = {self._uses[use_id].piece_id for use_id in reachable_uses}
        reachable_diagnostics = set(root_diagnostic_ids)
        for use_id in reachable_uses:
            reachable_diagnostics.update(self._uses[use_id].diagnostic_ids)
        reachable_facts = {self._uses[use_id].fact_id for use_id in reachable_uses}
        reachable_facts.update(
            self._diagnostics[diagnostic_id].fact_id for diagnostic_id in reachable_diagnostics
        )
        return PrerequisiteSolverStructure(
            root_group_id=root_group_id,
            academic_year_start=academic_year_start,
            root_use_id=root_use_id,
            pieces=tuple(
                sorted(
                    (self._pieces[piece_id] for piece_id in reachable_pieces),
                    key=lambda item: item.piece_id,
                )
            ),
            uses=tuple(
                sorted(
                    (self._uses[use_id] for use_id in reachable_uses),
                    key=lambda item: item.use_id,
                )
            ),
            facts=tuple(
                sorted(
                    (self._facts[fact_id] for fact_id in reachable_facts),
                    key=lambda item: item.fact_id,
                )
            ),
            diagnostics=tuple(
                sorted(
                    (self._diagnostics[item] for item in reachable_diagnostics),
                    key=lambda item: item.diagnostic_id,
                )
            ),
            root_diagnostic_ids=tuple(sorted(root_diagnostic_ids)),
            courses=courses,
            modules=modules,
            include_recommended=include_recommended,
            include_inferred=include_inferred,
            active_only=active_only,
            inferred_coverage=inferred_coverage,
            excluded_group_ids=excluded_group_ids,
            completed_node_keys=completed_node_keys,
            excluded_node_keys=excluded_node_keys,
        )


def node_action(
    structure: PrerequisiteSolverStructure,
    support_id_value: str,
    *,
    completed_node_keys: Collection[str],
    excluded_node_keys: Collection[str],
) -> Literal["excluded", "completed"] | None:
    """Return the saved graph-box action for one scoped calculation support.

    Exclusion wins over completion. A support absent from the structure has no current binding and
    therefore no action, so a saved key for a box that is not currently drawn stays inert.
    """
    excluded = frozenset(excluded_node_keys)
    completed = frozenset(completed_node_keys)
    for binding in structure.bindings:
        if binding.support_id != support_id_value:
            continue
        mark_keys = frozenset(binding.mark_node_ids)
        if mark_keys & excluded:
            return "excluded"
        if mark_keys & completed:
            return "completed"
        return None
    return None
