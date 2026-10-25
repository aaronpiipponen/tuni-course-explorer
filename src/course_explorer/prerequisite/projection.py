"""Native display projection, support bindings and relationship-member authority.

This module owns the one drawing projection over `PrerequisiteSolverStructure`. It builds one
normalized display recipe per calculation use context, then walks the root recipe once to emit
nodes, connections, support bindings, relationship members and the native contexts that own them. A
recipe records its course-scoped display identity, the scoped calculation supports it stands for,
its ordered native child slot recipes, its display-only decorations and its stable context key. Each
emitted context carries its native owner and piece, the context identity of every child slot, and
the relationship members its occurrences select.

Drawing normalization happens before any attachment is emitted. Empty and unary logical wrappers
elide, same-operator logical nesting folds, module member cards stay cards, and a structurally nested
module contributes its cards and external obligations to the enclosing drawn module. The external
obligations of a hidden module member draw as an external subtree of the containing module, and the
member's expanded occurrence owns their native contexts. Display identity is the one drawing equality
(kind, displayed values and the set of drawn children). Calculation pieces keep their ordered
multiplicity, provenance and work identity. A mark on a drawn box applies to every calculation piece
bound to it.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal

from pydantic import Field

from course_explorer.prerequisite._helpers import _PrerequisiteModel
from course_explorer.prerequisite.domain import (
    InferredPrerequisiteCategory,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.graph import PrerequisiteIgnoredPartKind
from course_explorer.prerequisite.structure import (
    PrerequisiteProjectionChild,
    PrerequisiteProjectionContext,
    PrerequisiteRelationshipMember,
    PrerequisiteSolverStructure,
    PrerequisiteSourceFact,
    PrerequisiteSupportBinding,
    canonical_number,
    digest,
    display_piece_id,
    module_member_group_ids,
    support_id,
)

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

_MARKABLE_KINDS = frozenset({"module", "cardinality", "credits", "course_count", "opaque_credits"})
_IGNORED_KIND_VALUES = frozenset({kind.value for kind in PrerequisiteIgnoredPartKind}) - {
    PrerequisiteIgnoredPartKind.MISSING_SUBSTITUTION_COURSE.value
}
_DISAPPEARED_MODULE_KINDS = frozenset(
    {
        PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT.value,
        PrerequisiteIgnoredPartKind.FREE_CHOICE.value,
    }
)


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


@dataclass
class _RawNode:
    """One provisional drawn node before display materialization."""

    node_id: str
    kind: DisplayNodeKind
    owner_group_id: str | None = None
    course_group_id: str | None = None
    module_group_id: str | None = None
    require_min: int | None = None
    require_max: int | None = None
    credits_min: Decimal | None = None
    credits_max: Decimal | None = None
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


@dataclass
class _RawEdge:
    """One provisional relationship member between two emitted display identities.

    `context_id` names the native projection context that selects the attachment. A purely
    synthetic annotation edge carries none, so no projection context selects it.
    """

    source: str
    target: str
    fact_id: str
    context_id: str | None = None


@dataclass(frozen=True)
class _Recipe:
    """One normalized display recipe shared by every equal drawing context.

    `key` is the emitted node identity, or `None` when the recipe elides into its parent. A
    transparent recipe binds to `binding_key`, or to the nearest drawn node when it has none. An
    expanded recipe places its descendants at `descendant_anchor`. `children` holds exactly the
    native use's ordered child slots, and `decorations` holds display-only summaries with the
    native child slot that selects them. `attachment_fingerprints` is the cached set of drawing
    targets the recipe reaches: its own fingerprint when visible, otherwise the cached union of
    its children's and decorations' sets.
    """

    key: str | None
    fingerprint: str | None
    attachment_fingerprints: frozenset[str]
    fact_id: str
    bindings: tuple[tuple[str, str, bool], ...] = ()
    children: tuple[_Recipe, ...] = ()
    decorations: tuple[tuple[int, _Recipe], ...] = ()
    use_id: str | None = None
    owner_group_id: str | None = None
    piece_id: str | None = None
    context_key: str | None = None
    binding_key: str | None = None
    descendant_anchor: str | None = None
    via_inferred: bool = False
    via_recommended: bool = False


@dataclass
class _Binding:
    """One scoped support's represented uses and emitted display locations."""

    use_ids: set[str] = field(default_factory=set)
    node_ids: set[str] = field(default_factory=set)
    mark_node_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _EdgeRecord:
    """One emitted endpoint record before the permitted display DTOs are materialized."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    member_ids: tuple[str, ...]
    inferred_only: bool


class _Projector:
    """Request-local recipe builder and one root-reachable emission walk."""

    def __init__(self, structure: PrerequisiteSolverStructure) -> None:
        self.structure = structure
        self.pieces = {piece.piece_id: piece for piece in structure.pieces}
        self.uses = {use.use_id: use for use in structure.uses}
        self.facts = {fact.fact_id: fact for fact in structure.facts}
        self.diagnostics = {
            diagnostic.diagnostic_id: diagnostic for diagnostic in structure.diagnostics
        }
        self.modules = {module.group_id: module for module in structure.modules}
        self.root = structure.root_group_id
        self.nodes: dict[str, _RawNode] = {}
        self.emitted_node_ids: set[str] = set()
        self.edges: list[_RawEdge] = []
        self.bindings: dict[str, _Binding] = {}
        self.contexts: dict[str, PrerequisiteProjectionContext] = {}
        self.support_parts: dict[str, tuple[str, str]] = {}
        self.contained_module_diagnostic_ids: set[str] = set()
        self._memo: dict[tuple[object, ...], _Recipe] = {}
        self._member_memo: dict[str, tuple[str, ...]] = {}
        self._add_node(
            _RawNode(
                node_id=f"course:{structure.root_group_id}",
                kind="course",
                course_group_id=structure.root_group_id,
                is_root=True,
            )
        )
        self.emitted_node_ids.add(f"course:{structure.root_group_id}")

    def bind(
        self,
        support: str,
        *,
        use_id: str,
        node_ids: Collection[str],
        mark: bool,
    ) -> None:
        """Record one scoped support's represented uses and emitted display locations."""
        entry = self.bindings.setdefault(support, _Binding())
        entry.use_ids.add(use_id)
        for node_id in node_ids:
            entry.node_ids.add(node_id)
            if mark:
                entry.mark_node_ids.add(node_id)

    def _add_node(self, node: _RawNode) -> _RawNode:
        """Merge one drawn node with an existing equal identity."""
        existing = self.nodes.get(node.node_id)
        if existing is None:
            self.nodes[node.node_id] = node
            return node
        merged = replace(
            existing,
            via_inferred=existing.via_inferred or node.via_inferred,
            via_recommended=existing.via_recommended or node.via_recommended,
            has_official_provenance=(
                existing.has_official_provenance or node.has_official_provenance
            ),
            has_inferred_provenance=(
                existing.has_inferred_provenance or node.has_inferred_provenance
            ),
            diagnostic_ids=tuple(sorted({*existing.diagnostic_ids, *node.diagnostic_ids})),
            display_as_inferred=(
                existing.kind == "course"
                and not existing.is_root
                and (existing.has_inferred_provenance or node.has_inferred_provenance)
                and not (existing.has_official_provenance or node.has_official_provenance)
            ),
        )
        self.nodes[node.node_id] = merged
        return merged

    def build(
        self,
        use_id: str,
        *,
        owner: str,
        members: frozenset[str] | None,
        module_body: bool,
        structural_module: bool,
        parent_operator: str | None,
        via_inferred: bool,
        via_recommended: bool,
    ) -> _Recipe:
        """Build one normalized recipe with memoized display context."""
        memo_key = (
            owner,
            use_id,
            None if members is None else tuple(sorted(members)),
            module_body,
            structural_module,
            parent_operator,
            via_inferred,
            via_recommended,
        )
        cached = self._memo.get(memo_key)
        if cached is not None:
            return cached
        use = self.uses[use_id]
        piece = self.pieces[use.piece_id]
        fact = self.facts[use.fact_id]
        support = support_id(owner_group_id=owner, piece_id=piece.piece_id)
        self.support_parts[support] = (owner, piece.piece_id)
        node_inferred = via_inferred or fact.origin is PrerequisiteOrigin.INFERRED
        node_recommended = (
            via_recommended
            or fact.official_kind is OfficialPrerequisiteKind.RECOMMENDED
            or fact.inferred_category is InferredPrerequisiteCategory.RECOMMENDED
        )
        if piece.kind == "course" and piece.course_group_id is not None:
            result = self._course(
                use,
                fact,
                group_id=piece.course_group_id,
                support=support,
                members=members,
                via_inferred=node_inferred,
                via_recommended=node_recommended,
            )
        elif piece.kind == "module_block":
            result = self._module(
                use,
                piece,
                fact,
                owner=owner,
                support=support,
                members=members,
                structural_module=structural_module,
                via_inferred=node_inferred,
                via_recommended=node_recommended,
            )
        elif piece.kind == "expanded_course":
            result = self._expanded(
                use,
                support=support,
                owner=owner,
                members=members,
                module_body=module_body,
                via_inferred=node_inferred,
                via_recommended=node_recommended,
            )
        else:
            result = self._connector(
                use,
                piece,
                fact,
                owner=owner,
                support=support,
                members=members,
                module_body=module_body,
                structural_module=structural_module,
                parent_operator=parent_operator,
                via_inferred=node_inferred,
                via_recommended=node_recommended,
            )
        native = replace(
            result,
            use_id=use_id,
            owner_group_id=owner,
            piece_id=piece.piece_id,
            context_key=digest(list(memo_key)),
        )
        self._memo[memo_key] = native
        return native

    def _course(
        self,
        use: object,
        fact: PrerequisiteSourceFact,
        *,
        group_id: str,
        support: str,
        members: frozenset[str] | None,
        via_inferred: bool,
        via_recommended: bool,
    ) -> _Recipe:
        """Represent one course occurrence as a global term or a hidden member card."""
        node_id = f"course:{group_id}"
        fingerprint = digest(["course", group_id])
        is_card = members is not None and group_id in members
        if not is_card:
            self._add_node(
                _RawNode(
                    node_id=node_id,
                    kind="course",
                    course_group_id=group_id,
                    is_root=group_id == self.root,
                    via_inferred=via_inferred,
                    via_recommended=via_recommended,
                    has_official_provenance=fact.origin is PrerequisiteOrigin.OFFICIAL,
                    has_inferred_provenance=fact.origin is PrerequisiteOrigin.INFERRED,
                    display_as_inferred=(
                        group_id != self.root and fact.origin is PrerequisiteOrigin.INFERRED
                    ),
                )
            )
        return _Recipe(
            key=None if is_card else node_id,
            fingerprint=fingerprint,
            attachment_fingerprints=(frozenset() if is_card else frozenset({fingerprint})),
            fact_id=use.fact_id,  # type: ignore[attr-defined]
            bindings=((support, use.use_id, False),),  # type: ignore[attr-defined]
            via_inferred=via_inferred,
            via_recommended=via_recommended,
        )

    def _expanded(
        self,
        use: object,
        *,
        support: str,
        owner: str,
        members: frozenset[str] | None,
        module_body: bool,
        via_inferred: bool,
        via_recommended: bool,
    ) -> _Recipe:
        """Represent one expanded course head and its gated descendant closure."""
        head_use, descendants_use = use.children  # type: ignore[attr-defined]
        head_piece = self.pieces[self.uses[head_use].piece_id]
        head_group_id = head_piece.course_group_id
        head_owner = head_group_id or owner
        head = self.build(
            head_use,
            owner=head_owner,
            members=members,
            module_body=module_body,
            structural_module=False,
            parent_operator=None,
            via_inferred=via_inferred,
            via_recommended=via_recommended,
        )
        descendant_members = members
        if members is not None and head_group_id is not None and head_group_id not in members:
            descendant_members = None
        path_inferred = via_inferred or head.via_inferred
        path_recommended = via_recommended or head.via_recommended
        descendants = self.build(
            descendants_use,
            owner=head_owner,
            members=descendant_members,
            module_body=module_body,
            structural_module=False,
            parent_operator=None,
            via_inferred=path_inferred,
            via_recommended=path_recommended,
        )
        own_binding = ((support, use.use_id, False),)  # type: ignore[attr-defined]
        visible_head = head.key is not None
        return _Recipe(
            key=None,
            fingerprint=head.fingerprint if visible_head else None,
            attachment_fingerprints=(
                frozenset({head.fingerprint})
                if visible_head
                else descendants.attachment_fingerprints
            ),
            fact_id=use.fact_id,  # type: ignore[attr-defined]
            bindings=(*head.bindings, *own_binding),
            children=(head, descendants),
            binding_key=head.key,
            descendant_anchor=head.key,
            via_inferred=path_inferred,
            via_recommended=path_recommended,
        )

    def _module(
        self,
        use: object,
        piece: object,
        fact: PrerequisiteSourceFact,
        *,
        owner: str,
        support: str,
        members: frozenset[str] | None,
        structural_module: bool,
        via_inferred: bool,
        via_recommended: bool,
    ) -> _Recipe:
        """Emit one module box or elide structural nesting into its enclosing module."""
        member_ids = use.member_group_ids  # type: ignore[attr-defined]
        if structural_module:
            body = self.build(
                use.children[0],  # type: ignore[attr-defined]
                owner=owner,
                members=members,
                module_body=True,
                structural_module=True,
                parent_operator=None,
                via_inferred=via_inferred,
                via_recommended=via_recommended,
            )
            self.contained_module_diagnostic_ids.update(use.diagnostic_ids)  # type: ignore[attr-defined]
            return _Recipe(
                key=None,
                fingerprint=None,
                attachment_fingerprints=body.attachment_fingerprints,
                fact_id=use.fact_id,  # type: ignore[attr-defined]
                bindings=((support, use.use_id, False),),  # type: ignore[attr-defined]
                children=(body,),
                via_inferred=via_inferred,
                via_recommended=via_recommended,
            )
        body = self.build(
            use.children[0],  # type: ignore[attr-defined]
            owner=owner,
            members=frozenset(member_ids),
            module_body=True,
            structural_module=True,
            parent_operator=None,
            via_inferred=via_inferred,
            via_recommended=via_recommended,
        )
        for diagnostic_id in use.diagnostic_ids:  # type: ignore[attr-defined]
            diagnostic = self.diagnostics[diagnostic_id]
            if (
                diagnostic.module_group_id is not None
                and diagnostic.module_group_id != piece.module_group_id  # type: ignore[attr-defined]
            ):
                self.contained_module_diagnostic_ids.add(diagnostic_id)
        module = self.modules.get(piece.module_group_id)  # type: ignore[attr-defined]
        payload = [
            "module",
            piece.module_group_id,  # type: ignore[attr-defined]
            None if module is None else module.module_type.value,
            canonical_number(piece.credits_min),  # type: ignore[attr-defined]
            canonical_number(piece.credits_max),  # type: ignore[attr-defined]
            list(member_ids),
        ]
        fingerprint = digest([*payload, *sorted(body.attachment_fingerprints)])
        node_id = display_piece_id(owner_group_id=owner, fingerprint=fingerprint)
        node = _RawNode(
            node_id=node_id,
            kind="module",
            owner_group_id=owner,
            module_group_id=piece.module_group_id,  # type: ignore[attr-defined]
            credits_min=piece.credits_min,  # type: ignore[attr-defined]
            credits_max=piece.credits_max,  # type: ignore[attr-defined]
            member_group_ids=member_ids,  # type: ignore[attr-defined]
            diagnostic_ids=use.diagnostic_ids,  # type: ignore[attr-defined]
            via_inferred=via_inferred,
            via_recommended=via_recommended,
            has_official_provenance=fact.origin is PrerequisiteOrigin.OFFICIAL,
            has_inferred_provenance=fact.origin is PrerequisiteOrigin.INFERRED,
            markable=True,
        )
        self._add_node(node)
        return _Recipe(
            key=node_id,
            fingerprint=fingerprint,
            attachment_fingerprints=frozenset({fingerprint}),
            fact_id=use.fact_id,  # type: ignore[attr-defined]
            bindings=((support, use.use_id, True),),  # type: ignore[attr-defined]
            children=(body,),
            via_inferred=via_inferred,
            via_recommended=via_recommended,
        )

    def _connector(
        self,
        use: object,
        piece: object,
        fact: PrerequisiteSourceFact,
        *,
        owner: str,
        support: str,
        members: frozenset[str] | None,
        module_body: bool,
        structural_module: bool,
        parent_operator: str | None,
        via_inferred: bool,
        via_recommended: bool,
    ) -> _Recipe:
        """Build one logical or numeric connector recipe and normalize it before emission."""
        kind = piece.kind  # type: ignore[attr-defined]
        logical = kind in ("and", "or", "course_alternatives")
        operator = "and" if kind == "and" else ("or" if logical else None)
        children = tuple(
            self.build(
                child_use,
                owner=owner,
                members=members,
                module_body=module_body,
                structural_module=structural_module,
                parent_operator=operator,
                via_inferred=via_inferred,
                via_recommended=via_recommended,
            )
            for child_use in use.children  # type: ignore[attr-defined]
        )
        decorations: tuple[tuple[int, _Recipe], ...] = ()
        if module_body and kind != "and":
            for index, (child_use, child) in enumerate(zip(use.children, children)):  # type: ignore[attr-defined]
                if child.attachment_fingerprints:
                    continue
                member_ids = self._module_member_group_ids(child_use)
                if member_ids:
                    decorations = (
                        *decorations,
                        (index, self._internal_requirement(owner, member_ids, use.fact_id)),
                    )
        child_targets: set[str] = set()
        for child in children:
            child_targets |= child.attachment_fingerprints
        for _slot, decoration in decorations:
            child_targets |= decoration.attachment_fingerprints
        own_binding = ((support, use.use_id, False),)  # type: ignore[attr-defined]
        if logical and parent_operator == operator:
            return _Recipe(
                key=None,
                fingerprint=None,
                attachment_fingerprints=frozenset(child_targets),
                fact_id=use.fact_id,  # type: ignore[attr-defined]
                bindings=own_binding,
                children=children,
                decorations=decorations,
                via_inferred=via_inferred,
                via_recommended=via_recommended,
            )
        if logical and not child_targets:
            return _Recipe(
                key=None,
                fingerprint=None,
                attachment_fingerprints=frozenset(),
                fact_id=use.fact_id,  # type: ignore[attr-defined]
                bindings=own_binding,
                children=children,
                decorations=decorations,
                via_inferred=via_inferred,
                via_recommended=via_recommended,
            )
        if logical and len(child_targets) == 1:
            return _Recipe(
                key=None,
                fingerprint=None,
                attachment_fingerprints=frozenset(child_targets),
                fact_id=use.fact_id,  # type: ignore[attr-defined]
                bindings=own_binding,
                children=children,
                decorations=decorations,
                via_inferred=via_inferred,
                via_recommended=via_recommended,
            )
        payload = self._payload(piece)
        fingerprint = digest([*payload, *sorted(child_targets)])
        node_id = display_piece_id(owner_group_id=owner, fingerprint=fingerprint)
        display_kind = self._display_kind(kind)
        node = _RawNode(
            node_id=node_id,
            kind=display_kind,
            owner_group_id=owner,
            require_min=piece.require_min,  # type: ignore[attr-defined]
            require_max=piece.require_max,  # type: ignore[attr-defined]
            credits_min=piece.credits_min,  # type: ignore[attr-defined]
            credits_max=piece.credits_max,  # type: ignore[attr-defined]
            count_min=piece.count_min,  # type: ignore[attr-defined]
            count_max=piece.count_max,  # type: ignore[attr-defined]
            referenced_group_id=piece.referenced_group_id,  # type: ignore[attr-defined]
            reason=piece.reason,  # type: ignore[attr-defined]
            detail=piece.detail,  # type: ignore[attr-defined]
            member_group_ids=use.member_group_ids,  # type: ignore[attr-defined]
            diagnostic_ids=use.diagnostic_ids,  # type: ignore[attr-defined]
            via_inferred=via_inferred,
            via_recommended=via_recommended,
            has_official_provenance=fact.origin is PrerequisiteOrigin.OFFICIAL,
            has_inferred_provenance=fact.origin is PrerequisiteOrigin.INFERRED,
            markable=display_kind in _MARKABLE_KINDS,
        )
        self._add_node(node)
        return _Recipe(
            key=node_id,
            fingerprint=fingerprint,
            attachment_fingerprints=frozenset({fingerprint}),
            fact_id=use.fact_id,  # type: ignore[attr-defined]
            bindings=((support, use.use_id, node.markable),),  # type: ignore[attr-defined]
            children=children,
            decorations=decorations,
            via_inferred=via_inferred,
            via_recommended=via_recommended,
        )

    def _internal_requirement(
        self,
        owner: str,
        member_ids: tuple[str, ...],
        fact_id: str,
    ) -> _Recipe:
        """Build one childless requirement disclosure box for the given module members."""
        payload = ["internal_requirement", list(member_ids)]
        fingerprint = digest(payload)
        node_id = display_piece_id(owner_group_id=owner, fingerprint=fingerprint)
        node = _RawNode(
            node_id=node_id,
            kind="internal_requirement",
            owner_group_id=owner,
            member_group_ids=member_ids,
            markable=False,
        )
        self._add_node(node)
        return _Recipe(
            key=node_id,
            fingerprint=fingerprint,
            attachment_fingerprints=frozenset({fingerprint}),
            fact_id=fact_id,
        )

    def _payload(self, piece: object) -> list[object]:
        """Return one piece's display kind and kind-specific identity values."""
        kind = piece.kind  # type: ignore[attr-defined]
        if kind in ("expanded_course", "course_alternatives"):
            kind = "or"
        if kind in ("and", "or"):
            return [kind]
        return [
            kind,
            canonical_number(piece.require_min),  # type: ignore[attr-defined]
            canonical_number(piece.require_max),  # type: ignore[attr-defined]
            canonical_number(piece.credits_min),  # type: ignore[attr-defined]
            canonical_number(piece.credits_max),  # type: ignore[attr-defined]
            canonical_number(piece.count_min),  # type: ignore[attr-defined]
            canonical_number(piece.count_max),  # type: ignore[attr-defined]
            piece.reason,  # type: ignore[attr-defined]
            piece.referenced_group_id,  # type: ignore[attr-defined]
            piece.detail,  # type: ignore[attr-defined]
        ]

    @staticmethod
    def _display_kind(kind: str) -> DisplayNodeKind:
        """Return the drawn kind of one native non-course piece kind."""
        return {
            "and": "and",
            "or": "or",
            "course_alternatives": "or",
            "cardinality": "cardinality",
            "credits": "credits",
            "course_count": "course_count",
            "opaque_credits": "opaque_credits",
            "unresolved": "unresolved",
        }.get(kind, "and")  # type: ignore[return-value]

    def _module_member_group_ids(self, use_id: str) -> tuple[str, ...]:
        """Return one module-body option's represented course member IDs, memoized per use."""
        cached = self._member_memo.get(use_id)
        if cached is not None:
            return cached
        result = module_member_group_ids(
            use_id,
            piece_of_use=lambda current: self.pieces[self.uses[current].piece_id],
            children_of_use=lambda current: self.uses[current].children,
        )
        self._member_memo[use_id] = result
        return result

    def emit(self, recipe: _Recipe) -> str:
        """Emit every drawn node, attachment and native context over the occurrence DAG."""
        root_anchor = f"course:{self.root}"
        root_context_id = self._context_id(recipe, root_anchor, root_anchor)
        pending: list[tuple[_Recipe, str, str]] = [(recipe, root_anchor, root_anchor)]
        while pending:
            current, parent, nearest = pending.pop()
            context_id = self._context_id(current, parent, nearest)
            if context_id in self.contexts:
                continue
            owner_group_id, piece_id = self._native_identity(current)
            if current.key is not None:
                self.emitted_node_ids.add(current.key)
                for support, use_id, mark in current.bindings:
                    self.bind(support, use_id=use_id, node_ids=(current.key,), mark=mark)
                if parent != current.key:
                    self.edges.append(
                        _RawEdge(
                            source=parent,
                            target=current.key,
                            fact_id=current.fact_id,
                            context_id=context_id,
                        )
                    )
                drawn_parent = current.key
                drawn_nearest = current.key
            else:
                anchor = current.binding_key or nearest
                for support, use_id, mark in current.bindings:
                    self.bind(support, use_id=use_id, node_ids=(anchor,), mark=mark)
                drawn_parent = parent
                drawn_nearest = nearest
            children: list[PrerequisiteProjectionChild] = []
            for slot, child in enumerate(current.children):
                if current.key is None and current.descendant_anchor is not None and slot == 1:
                    child_parent = current.descendant_anchor
                    child_nearest = current.descendant_anchor
                else:
                    child_parent = drawn_parent
                    child_nearest = drawn_nearest
                child_context_id = self._context_id(child, child_parent, child_nearest)
                children.append(PrerequisiteProjectionChild(slot=slot, context_id=child_context_id))
                pending.append((child, child_parent, child_nearest))
            for slot, decoration in current.decorations:
                selected = next(
                    (child.context_id for child in children if child.slot == slot),
                    None,
                )
                if selected is None:
                    raise ValueError("a display decoration has no native child slot")
                self._emit_decoration(decoration, drawn_parent, selected)
            self.contexts[context_id] = PrerequisiteProjectionContext(
                context_id=context_id,
                owner_group_id=owner_group_id,
                piece_id=piece_id,
                children=tuple(children),
            )
        return root_context_id

    @staticmethod
    def _context_id(recipe: _Recipe, parent: str, nearest: str) -> str:
        """Return one context's stable identity from its native key and drawn anchors."""
        if recipe.context_key is None:
            raise ValueError("a projection context recipe has no stable context key")
        return f"c:{digest([recipe.context_key, parent, nearest])}"

    @staticmethod
    def _native_identity(recipe: _Recipe) -> tuple[str, str]:
        """Return one recipe's native owner and piece, which a context row requires."""
        if recipe.owner_group_id is None or recipe.piece_id is None:
            raise ValueError("a projection context recipe has no native identity")
        return recipe.owner_group_id, recipe.piece_id

    def _emit_decoration(self, decoration: _Recipe, parent: str, context_id: str) -> None:
        """Emit one display-only summary at its enclosing connector's drawn anchor."""
        if decoration.key is None:
            raise ValueError("a display decoration has no drawn node")
        self.emitted_node_ids.add(decoration.key)
        if parent != decoration.key:
            self.edges.append(
                _RawEdge(
                    source=parent,
                    target=decoration.key,
                    fact_id=decoration.fact_id,
                    context_id=context_id,
                )
            )

    def finalize(self) -> None:
        """Derive ignored annotations after the calculation drawing is complete."""
        anchors: dict[str, set[str]] = {}
        owners: dict[str, str] = {}
        for binding_support, binding in self.bindings.items():
            for use_id in binding.use_ids:
                use = self.uses[use_id]
                for diagnostic_id in use.diagnostic_ids:
                    anchors.setdefault(diagnostic_id, set()).update(binding.node_ids)
                    owners.setdefault(diagnostic_id, self.support_parts[binding_support][0])
        for diagnostic_id in self.structure.root_diagnostic_ids:
            anchors.setdefault(diagnostic_id, set()).add(f"course:{self.root}")
            owners.setdefault(diagnostic_id, self.root)
        for diagnostic_id in sorted(anchors):
            diagnostic = self.diagnostics[diagnostic_id]
            if diagnostic.kind not in _IGNORED_KIND_VALUES:
                continue
            node_ids = sorted(
                node_ids for node_ids in anchors[diagnostic_id] if node_ids in self.emitted_node_ids
            )
            if not node_ids:
                continue
            parent = node_ids[0]
            module_type = None
            if diagnostic.module_group_id is not None:
                module = self.modules.get(diagnostic.module_group_id)
                module_type = None if module is None else module.module_type.value
            already_drawn = any(
                node.kind == "module" and node.module_group_id == diagnostic.module_group_id
                for node in self.nodes.values()
                if node.node_id in self.emitted_node_ids
            )
            if (
                diagnostic_id not in self.contained_module_diagnostic_ids
                and diagnostic.kind in _DISAPPEARED_MODULE_KINDS
                and diagnostic.module_group_id is not None
                and module_type is not None
                and not already_drawn
            ):
                owner = owners.get(diagnostic_id, self.root)
                module_id = display_piece_id(
                    owner_group_id=owner,
                    fingerprint=digest(
                        ["module_disappeared", diagnostic.module_group_id, module_type]
                    ),
                )
                self._add_node(
                    _RawNode(
                        node_id=module_id,
                        kind="module",
                        owner_group_id=owner,
                        module_group_id=diagnostic.module_group_id,
                        diagnostic_ids=(diagnostic.diagnostic_id,),
                        markable=False,
                    )
                )
                self.emitted_node_ids.add(module_id)
                self.edges.append(
                    _RawEdge(
                        source=parent,
                        target=module_id,
                        fact_id=diagnostic.fact_id,
                    )
                )
                parent = module_id
            owner = owners.get(diagnostic_id, self.root)
            payload = [
                "ignored",
                diagnostic.kind,
                list(diagnostic.referenced_group_ids),
                diagnostic.detail,
                diagnostic.module_group_id,
                module_type,
            ]
            ignored_fp = digest(payload)
            ignored_id = display_piece_id(owner_group_id=owner, fingerprint=ignored_fp)
            self._add_node(
                _RawNode(
                    node_id=ignored_id,
                    kind="ignored",
                    owner_group_id=owner,
                    referenced_group_id=diagnostic.module_group_id,
                    reason=diagnostic.kind,
                    detail=diagnostic.detail,
                    diagnostic_ids=(diagnostic.diagnostic_id,),
                    markable=False,
                )
            )
            self.emitted_node_ids.add(ignored_id)
            self.edges.append(
                _RawEdge(
                    source=parent,
                    target=ignored_id,
                    fact_id=diagnostic.fact_id,
                )
            )


def _intern_edges(
    projector: _Projector,
) -> tuple[
    tuple[_EdgeRecord, ...],
    tuple[PrerequisiteRelationshipMember, ...],
    dict[str, tuple[str, ...]],
]:
    """Collapse provisional attachments into endpoint records, members and context selections."""
    grouped: dict[tuple[str, str], dict[str, set[str]]] = {}
    for edge in projector.edges:
        if edge.source not in projector.emitted_node_ids:
            raise ValueError(f"display edge source {edge.source} is not emitted")
        if edge.target not in projector.emitted_node_ids:
            raise ValueError(f"display edge target {edge.target} is not emitted")
        if edge.source == edge.target:
            continue
        contexts = grouped.setdefault((edge.source, edge.target), {}).setdefault(
            edge.fact_id, set()
        )
        if edge.context_id is not None:
            contexts.add(edge.context_id)
    records: list[_EdgeRecord] = []
    members: list[PrerequisiteRelationshipMember] = []
    selections: dict[str, set[str]] = {}
    for (source, target), facts in sorted(grouped.items()):
        member_records: list[PrerequisiteRelationshipMember] = []
        for fact_id, context_ids in sorted(facts.items()):
            member_id = f"m:{digest([source, target, fact_id])}"
            member_records.append(
                PrerequisiteRelationshipMember(
                    member_id=member_id,
                    source_node_id=source,
                    target_node_id=target,
                    fact_id=fact_id,
                )
            )
            for context_id in context_ids:
                selections.setdefault(context_id, set()).add(member_id)
        members.extend(member_records)
        records.append(
            _EdgeRecord(
                edge_id=f"e:{digest([source, target])}",
                source_node_id=source,
                target_node_id=target,
                member_ids=tuple(sorted(member.member_id for member in member_records)),
                inferred_only=all(
                    projector.facts[fact_id].origin is PrerequisiteOrigin.INFERRED
                    for fact_id in facts
                ),
            )
        )
    return (
        tuple(sorted(records, key=lambda item: item.edge_id)),
        tuple(sorted(members, key=lambda item: item.member_id)),
        {context_id: tuple(sorted(member_ids)) for context_id, member_ids in selections.items()},
    )


def project_prerequisite_graph(
    structure: PrerequisiteSolverStructure,
    *,
    max_drawing_elements: int | None = None,
    include_display: bool = True,
) -> PrerequisiteGraphCompilation:
    """Project the native structure once and install bindings, contexts and members on it."""
    projector = _Projector(structure)
    root_context_id: str | None = None
    if structure.root_use_id is not None:
        root_recipe = projector.build(
            structure.root_use_id,
            owner=structure.root_group_id,
            members=None,
            module_body=False,
            structural_module=False,
            parent_operator=None,
            via_inferred=False,
            via_recommended=False,
        )
        root_context_id = projector.emit(root_recipe)
    projector.finalize()
    edge_records, members, selections = _intern_edges(projector)
    nodes = {
        node_id: node
        for node_id, node in projector.nodes.items()
        if node_id in projector.emitted_node_ids
    }
    markable_nodes = {node.node_id for node in nodes.values() if node.markable}
    bindings = tuple(
        PrerequisiteSupportBinding(
            support_id=value,
            owner_group_id=projector.support_parts[value][0],
            piece_id=projector.support_parts[value][1],
            use_ids=tuple(sorted(binding.use_ids)),
            node_ids=tuple(sorted(binding.node_ids)),
            mark_node_ids=tuple(sorted(binding.mark_node_ids & markable_nodes)),
        )
        for value, binding in sorted(projector.bindings.items())
    )
    allowance = prerequisite_drawing_allowance(
        course_count=sum(1 for node in nodes.values() if node.kind == "course"),
        node_count=len(nodes),
        edge_count=len(edge_records),
        max_elements=max_drawing_elements,
    )
    contexts = tuple(
        context.model_copy(update={"member_ids": selections.get(context.context_id, ())})
        for context in sorted(projector.contexts.values(), key=lambda item: item.context_id)
    )
    prepared = structure.model_copy(
        update={
            "bindings": bindings,
            "projection_root_context_id": root_context_id,
            "projection_contexts": contexts,
            "members": members,
        }
    )
    display = None
    if include_display and allowance.allowed:
        display = PrerequisiteDrawingGraph(
            nodes=tuple(
                PrerequisiteDisplayNode(**vars(node))
                for node in sorted(nodes.values(), key=lambda item: item.node_id)
            ),
            edges=tuple(
                PrerequisiteDisplayEdge(
                    edge_id=record.edge_id,
                    source_node_id=record.source_node_id,
                    target_node_id=record.target_node_id,
                    member_ids=record.member_ids,
                    inferred_only=record.inferred_only,
                )
                for record in edge_records
            ),
        )
    return PrerequisiteGraphCompilation(solver=prepared, display=display, drawing=allowance)
