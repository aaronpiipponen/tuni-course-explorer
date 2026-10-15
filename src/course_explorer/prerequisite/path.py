"""Pure minimum-new-credit pathing over one compiled prerequisite calculation tree.

This module owns the one dependency-free exact-default optimization contract consumed by the
prerequisite CLI, with one scalar-greedy approximate restart for oversized searches. It reads the
already-filtered authoritative `PrerequisiteCalculationTree`
inside a `PrerequisiteGraphCompilation`. Official `CourseSummary.credits_min` is the sole course cost: each
not-basis canonical `group_id` is charged once across the global union of selected courses, and
chosen-basis courses cost zero. Under active-only scope the compiled tree contains the active
courses and the retained inactive courses, and the shared `is_course_activity_eligible` predicate
excludes a retained inactive course outside the chosen basis from candidates and charges.
A course named by the tree's exclusion set is likewise never a candidate and never charged, even
when it is in the basis or completed: only routes that must pass through it are blocked, and a
result reports the excluded courses that blocked requirements so a `no_solution` is explainable.
An approximate route is explicitly marked and is subject to the source's full prerequisite and
numeric rules. A bounded heuristic miss is `approximation_failed` with a size-triggered
`search_too_large` problem, never a claim of impossibility.

The caller supplies the chosen zero-cost basis and its completed-history subset separately, so a
completed expanded course costs zero without its historical descendants while a selected-but-
incomplete basis course carries its full prerequisite closure.

The solver folds an exact compact candidate frontier bottom-up. A candidate carries the canonical
witness courses that satisfy the current requirement (what enclosing credit/count constraints
measure), the complete recursively required not-basis course closure (the sole cost set),
deterministic evidence pairing every selected course with each tree leaf occurrence it satisfies,
and the module deficits of its branch. Each shortfall partition holds one zero-suppressed decision
DAG over tagged `(first_occurrence_rank, kind, identity, role)` variables (the support), plus one
transient provenance node recording the operation that produced it, so a cardinality rule never
enumerates its selections and no forward per-label evidence family is carried. The `kind`
(`course`/`opaque`/`attested`) keeps a canonical course, an opaque source block and a manual
attested completion distinct. The `role` separates a measured witness from the sole new-work cost
set. The internal variable order follows the authoritative tree's first course/opaque occurrence,
which fixes one fold variable order on large nested choice rules. Public selection is order-independent
because the winning identity is chosen by canonical typed-identity prefix walks. Winning evidence is
reconstructed exactly backwards from that identity through the recorded operation DAG using the
shared family core's exact inverse join/projection and variable restriction, so equal-identity
alternatives union every valid derivation while rejected routes stay excluded. A numeric wrapper
keeps known-measure members for exact filtering and carries unknown-measure support as a separate
unresolved alternative instead of poisoning the known ones. Every evaluated known occurrence also
carries one typed `(node, action_key, occurrence_id)` selection label. Unresolved source structure
(course cycles) and proven-impossible constraints return an explicit non-exact result instead
of a fabricated partial answer.

When the exact family/provenance allocation limit is exceeded, one separate scalar-greedy fold
chooses a single viable OR branch and the N cheapest cardinality positions. A numeric lower-bound
miss may extend the next ranked chosen-prefix cursor within source maxima. It never enumerates
combinations or reopens a discarded branch. The fallback has no allocation or elapsed-time limit,
validates the guards and numeric witnesses, and returns the marked failure when its
chosen derivation cannot satisfy them.

Under active-only scope one exception exists: an otherwise satisfiable official
`MODULE_RULE` that activity scope alone pushed below its own lower bound returns `SHORTFALL` with the
deterministic maximum achievable active-course result and one explicit deficit per deficient rule
occurrence. A local all-course diagnostic that runs this same evaluator proves the failure is
activity-only. Malformed, missing, cyclic, and genuinely impossible structure keeps its
strict `UNRESOLVED` or `NO_SOLUTION` outcome, and the official rule remains reported unsatisfied.
"""

from __future__ import annotations

import heapq
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import field_validator

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite._families import _Families
from course_explorer.prerequisite._helpers import (
    _nonblank,
    _opaque_credits_by_work_key,
    _PrerequisiteModel,
    _unique_ids,
    _witness_credits,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteNodeProblem,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import (
    InferredCoverageRecord,
    PrerequisiteCalculationTree,
    is_course_activity_eligible,
    is_expanded_course_branch,
    node_action,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionEvaluation,
    PrerequisiteSatisfactionState,
    evaluate_prerequisite_satisfaction,
)
from course_explorer.prerequisite.traversal import (
    ExpressionEvaluator,
    conjunction_is_unresolved,
)


class PrerequisitePathState(StrEnum):
    """Exactness of one minimum-new-credit path result."""

    EXACT = "exact"
    APPROXIMATE = "approximate"
    APPROXIMATION_FAILED = "approximation_failed"
    UNRESOLVED = "unresolved"
    NO_SOLUTION = "no_solution"
    SHORTFALL = "shortfall"


class PrerequisiteModuleShortfallKind(StrEnum):
    """Which official module-rule family activity scope left below its lower bound."""

    ALL_MANDATORY = "all_mandatory"
    CARDINALITY = "cardinality"
    CREDITS = "credits"
    COURSE_COUNT = "course_count"


class PrerequisitePathBlockerKind(StrEnum):
    """Category of represented source structure that prevents an exact answer."""

    UNRESOLVED_REQUIREMENT = "unresolved_requirement"
    COURSE_CYCLE = "course_cycle"


class PrerequisitePathCourse(_PrerequisiteModel):
    """One selected canonical new course with every tree occurrence it satisfies."""

    course: CourseSummary
    occurrence_ids: tuple[str, ...]

    @field_validator("occurrence_ids")
    @classmethod
    def require_sorted_unique_occurrences(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require distinct tree occurrence IDs in sorted order."""
        return _unique_ids(value, "path course occurrence IDs", sorted_required=True)


class PrerequisitePathBlocker(_PrerequisiteModel):
    """One explicit represented condition that makes an exact answer impossible."""

    kind: PrerequisitePathBlockerKind
    occurrence_id: str | None = None
    reason: UnresolvedPrerequisiteReason | None = None
    referenced_group_id: str | None = None
    detail: str | None = None
    course_group_path: tuple[str, ...] = ()
    origin: PrerequisiteOrigin
    official_kind: OfficialPrerequisiteKind | None = None

    @field_validator("occurrence_id", "referenced_group_id", "detail")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        """Reject a provided-but-blank diagnostic field."""
        if value is not None:
            _nonblank(value, "path blocker diagnostic text")
        return value

    @field_validator("course_group_path")
    @classmethod
    def reject_blank_group_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require nonblank canonical group IDs when a course path is present."""
        for group_id in value:
            _nonblank(group_id, "path blocker course_group_path entry")
        return value


class PrerequisiteModuleShortfall(_PrerequisiteModel):
    """One official module rule that activity scope left below its own lower bound.

    A shortfall measures the module's direct witness courses, never the recursively charged
    closure. Count families (`ALL_MANDATORY`, `CARDINALITY`, `COURSE_COUNT`) carry exactly the
    three count fields. `CREDITS` carries exactly the three credit fields.
    """

    kind: PrerequisiteModuleShortfallKind
    occurrence_id: str
    required_count: int | None = None
    achieved_count: int | None = None
    count_deficit: int | None = None
    required_credits: Decimal | None = None
    achieved_credits: Decimal | None = None
    credit_deficit: Decimal | None = None

    @field_validator("occurrence_id")
    @classmethod
    def reject_blank_occurrence(cls, value: str) -> str:
        """Require the exact recursive calculation-tree occurrence that owns the deficit."""
        return _nonblank(value, "module shortfall occurrence_id")


def _shortfall_sort_key(
    shortfall: PrerequisiteModuleShortfall,
) -> tuple[str, str, int, int, int, str, str, str]:
    """Return the deterministic identity/order key shared by the DTO and the solver."""
    return (
        shortfall.occurrence_id,
        shortfall.kind.value,
        shortfall.required_count if shortfall.required_count is not None else -1,
        shortfall.achieved_count if shortfall.achieved_count is not None else -1,
        shortfall.count_deficit if shortfall.count_deficit is not None else -1,
        str(shortfall.required_credits) if shortfall.required_credits is not None else "",
        str(shortfall.achieved_credits) if shortfall.achieved_credits is not None else "",
        str(shortfall.credit_deficit) if shortfall.credit_deficit is not None else "",
    )


def _merge_shortfalls(
    shortfalls: Iterable[PrerequisiteModuleShortfall],
) -> tuple[PrerequisiteModuleShortfall, ...]:
    """Return sorted unique shortfalls, rejecting conflicting values for one identity."""
    by_key: dict[tuple[str, str], PrerequisiteModuleShortfall] = {}
    for shortfall in shortfalls:
        identity = (shortfall.occurrence_id, shortfall.kind.value)
        existing = by_key.get(identity)
        if existing is None:
            by_key[identity] = shortfall
        elif existing != shortfall:
            raise ValueError(
                "conflicting module shortfalls for one occurrence and kind: "
                f"{shortfall.occurrence_id} {shortfall.kind.value}"
            )
    return tuple(sorted(by_key.values(), key=_shortfall_sort_key))


def _blocker_sort_key(
    blocker: PrerequisitePathBlocker,
) -> tuple[str, str, tuple[str, ...], str, str, str]:
    """Return the deterministic identity/order key shared by the DTO and the solver."""
    return (
        blocker.kind.value,
        blocker.occurrence_id or "",
        blocker.course_group_path,
        blocker.reason.value if blocker.reason is not None else "",
        blocker.referenced_group_id or "",
        blocker.detail or "",
    )


class PrerequisitePathOpaqueWork(_PrerequisiteModel):
    """One distinct new opaque source obligation charged by a path result."""

    work_key: str
    credits_min: Decimal
    occurrence_ids: tuple[str, ...]

    @field_validator("work_key")
    @classmethod
    def reject_blank_work_key(cls, value: str) -> str:
        """Require a nonblank stable opaque work identity."""
        return _nonblank(value, "opaque work_key")

    @field_validator("occurrence_ids")
    @classmethod
    def require_sorted_unique_occurrences(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require distinct tree occurrence IDs in sorted order."""
        return _unique_ids(value, "opaque work occurrence IDs", sorted_required=True)


class MinimumCreditPathEvaluation(_PrerequisiteModel):
    """One immutable path result paired with the satisfaction evaluation it started from."""

    satisfaction: PrerequisiteSatisfactionEvaluation
    state: PrerequisitePathState
    new_courses: tuple[PrerequisitePathCourse, ...]
    total_new_credits: Decimal | None
    blockers: tuple[PrerequisitePathBlocker, ...]
    shortfalls: tuple[PrerequisiteModuleShortfall, ...]
    inferred_coverage: tuple[InferredCoverageRecord, ...]
    blocked_excluded_group_ids: tuple[str, ...] = ()
    new_opaque_work: tuple[PrerequisitePathOpaqueWork, ...] = ()
    selected_occurrence_ids: tuple[str, ...] = ()
    problems: tuple[PrerequisiteNodeProblem, ...] = ()
    blocked_excluded_node_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PathCandidate:
    """One exact candidate: typed witness set, recursive new-work closure, and typed evidence.

    `witness_group_ids` are the canonical course witnesses measured by enclosing credit/count
    constraints. `witness_non_course_ids` are the typed opaque/attested witness identities.
    `new_group_ids` is the complete recursively required course closure outside the chosen basis and
    `new_opaque_work_ids` the opaque source work. Together they are the sole cost set. `evidence`
    pairs each selected identity or selected node with every tree occurrence it satisfies.
    """

    witness_group_ids: frozenset[str]
    new_group_ids: frozenset[str]
    evidence: frozenset[tuple[str, str, str]]
    new_opaque_work_ids: frozenset[str] = frozenset()
    witness_non_course_ids: frozenset[tuple[str, str]] = frozenset()
    shortfalls: tuple[PrerequisiteModuleShortfall, ...] = ()


@dataclass(frozen=True)
class _PathEvaluation:
    """One compact candidate frontier plus any viable unresolved alternative and blockers."""

    candidates: _PathFrontier
    has_unresolved_alternative: bool
    blockers: tuple[PrerequisitePathBlocker, ...]

    @property
    def is_known(self) -> bool:
        """Return whether at least one known candidate satisfies this node."""
        return self.candidates.is_known


@dataclass(frozen=True)
class _GreedyRoute:
    """One chosen scalar derivation and its available cardinality extensions."""

    candidate: _PathCandidate
    witnesses: frozenset[tuple[str, str]]
    scalar_cost: Decimal
    positions: tuple[tuple[int, _GreedyRoute], ...] = ()
    extension_positions: tuple[tuple[int, _GreedyRoute], ...] = ()
    children: tuple[_GreedyRoute, ...] = ()
    kind: str = "leaf"
    expression: PrerequisiteExpression | None = None
    occurrence_id: str = ""


@dataclass(frozen=True)
class _GreedyEvaluation:
    """One route selected locally by the scalar greedy fold, or no viable route."""

    route: _GreedyRoute | None
    has_unresolved_alternative: bool = False
    blockers: tuple[PrerequisitePathBlocker, ...] = ()

    @property
    def is_known(self) -> bool:
        """Return whether this fold found one route."""
        return self.route is not None


def _candidate_sort_key(candidate: _PathCandidate) -> tuple[object, ...]:
    """Return the deterministic ordering key for one candidate."""
    return (
        tuple(sorted(candidate.witness_group_ids)),
        tuple(sorted(candidate.new_group_ids)),
        tuple(sorted(candidate.new_opaque_work_ids)),
        tuple(sorted(candidate.witness_non_course_ids)),
        tuple(sorted(candidate.evidence)),
        tuple(_shortfall_sort_key(shortfall) for shortfall in candidate.shortfalls),
    )


def _merge_blockers(
    blockers: Iterable[PrerequisitePathBlocker],
) -> tuple[PrerequisitePathBlocker, ...]:
    """Return sorted unique blockers keyed by their deterministic identity."""
    by_key: dict[tuple[str, str, tuple[str, ...], str, str, str], PrerequisitePathBlocker] = {}
    for blocker in blockers:
        by_key.setdefault(_blocker_sort_key(blocker), blocker)
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True)
class _BestSupport:
    """One support identity selected by the exact optimization key.

    The selected identities are kept typed by kind so the public tie order (fewest inactive new
    canonical courses, then opaque work IDs before canonical course IDs, then non-course witness
    identities) is exact.
    """

    credits: Decimal
    inactive_new_count: int
    new_course_ids: tuple[str, ...]
    new_opaque_work_ids: tuple[str, ...]
    witness_course_ids: tuple[str, ...]
    witness_non_course_ids: tuple[tuple[str, str], ...]

    def variables(self, families: _PathFamilies) -> frozenset[tuple[int, str, str, str]]:
        """Return this identity's tagged `(rank, kind, identity, role)` variables through its owner."""
        new_variables = frozenset(
            families.new_variable(_PathFamilies.COURSE, group_id)
            for group_id in self.new_course_ids
        ) | frozenset(
            families.new_variable(_PathFamilies.OPAQUE, work_key)
            for work_key in self.new_opaque_work_ids
        )
        witness_variables = frozenset(
            families.witness_variable(_PathFamilies.COURSE, group_id)
            for group_id in self.witness_course_ids
        ) | frozenset(
            families.witness_variable(kind, identity)
            for kind, identity in self.witness_non_course_ids
        )
        return new_variables | witness_variables


@dataclass(frozen=True)
class _PathTrace:
    """One node of the transient provenance DAG of a path calculation's actual operations.

    References are indices into `_PathFamilies`' append-only list and always point to earlier nodes.
    A `leaf` carries either one typed `(kind, identity, occurrence_id)` label or none for a
    neutral identity. Non-leaf operations are unlabeled. The trace is the sole evidence-
    reconstruction input.
    """

    support: int
    operation: str
    inputs: tuple[int, ...]
    label: tuple[str, str, str] | None = None


class _PathSizeLimitExceeded(RuntimeError):
    """One attempt allocated beyond its configured PATH family/provenance budget."""


class _PathFamilies(_Families[tuple[int, str, str, str]]):
    """One transient zero-suppressed decision DAG of tagged PATH witness/new identities.

    A support family is a set of `(witness set, new-work closure)` identities. Variables are
    `(first_occurrence_rank, kind, identity, role)` quadruples: the rank comes from the authoritative
    tree's first course/opaque occurrence (attested identities register their own rank), so a node's
    added variable order is independent of canonical ID order. The explicit `kind` (`course`,
    `opaque` or `attested`) keeps a canonical course, an opaque source block and a manual attested
    completion distinct, and the `role` tag separates a witness occurrence (measured by enclosing
    credit/count nodes) from its new-work occurrence (the sole cost set). Node interning, union,
    union-product join, weighted bound filtering, existential projection, empty-subset removal and
    the exact intersection/restriction/preimage inverses are inherited from the shared
    `_families._Families` core. This subclass adds only PATH's variable, weight, optimization and
    provenance glue. Nodes, traces and memos are transient state for one path calculation, never a
    cache.
    """

    COURSE = "course"
    OPAQUE = "opaque"
    ATTESTED = "attested"
    NODE = "node"
    WITNESS = "witness"
    NEW = "new"
    LEAF = "leaf"
    UNION = "union"
    JOIN = "join"
    IDENTITY = "identity"
    PROJECT = "project"

    def __init__(
        self,
        credits_min_by_group_id: dict[str, Decimal],
        group_order: tuple[tuple[str, str], ...],
        opaque_credits_by_work_key: dict[str, Decimal] | None = None,
        *,
        inactive_group_ids: frozenset[str],
        max_compact_nodes: int | None = None,
    ) -> None:
        super().__init__()
        self._max_compact_nodes = max_compact_nodes
        self._inactive_group_ids = inactive_group_ids
        self._credits_min_by_group_id = credits_min_by_group_id
        self._opaque_credits_by_work_key = opaque_credits_by_work_key or {}
        self._attested_credits: dict[str, Decimal | None] = {}
        self._rank: dict[tuple[str, str], int] = {}
        self._order: list[tuple[str, str]] = []
        for kind, identity in group_order:
            self._register(kind, identity)
        self._traces: list[_PathTrace] = []

    def _check_size(self) -> None:
        if (
            self._max_compact_nodes is not None
            and len(self._nodes) + len(self._traces) > self._max_compact_nodes
        ):
            raise _PathSizeLimitExceeded

    def _make(self, variable: tuple[int, str, str, str], low: int, high: int) -> int:
        handle = super()._make(variable, low, high)
        self._check_size()
        return handle

    def _register(self, kind: str, identity: str) -> int:
        """Register one identity's stable internal rank, creating it once."""
        key = (kind, identity)
        existing = self._rank.get(key)
        if existing is not None:
            return existing
        rank = len(self._order)
        self._rank[key] = rank
        self._order.append(key)
        return rank

    def register_attested(self, action_key: str, credits_min: Decimal | None) -> None:
        """Register one attested manual-completion identity and its known source extent."""
        self._attested_credits[action_key] = credits_min
        self._register(self.ATTESTED, action_key)

    def witness_variable(self, kind: str, identity: str) -> tuple[int, str, str, str]:
        """Return the tagged variable marking one identity as a witness."""
        return (self._rank_of(kind, identity), kind, identity, self.WITNESS)

    def new_variable(self, kind: str, identity: str) -> tuple[int, str, str, str]:
        """Return the tagged variable marking one identity as a new charge."""
        return (self._rank_of(kind, identity), kind, identity, self.NEW)

    def _rank_of(self, kind: str, identity: str) -> int:
        """Return one identity's registered rank, never a fabricated default."""
        rank = self._rank.get((kind, identity))
        if rank is None:
            raise ValueError(f"{kind} identity {identity!r} has no registered path rank")
        return rank

    def is_witness(self, variable: tuple[int, str, str, str]) -> bool:
        """Return whether one tagged variable is a witness occurrence."""
        return variable[3] == self.WITNESS

    def is_new(self, variable: tuple[int, str, str, str]) -> bool:
        """Return whether one tagged variable is a new-work occurrence."""
        return variable[3] == self.NEW

    def _measure(self, kind: str, identity: str) -> Decimal | None:
        """Return one identity's source minimum-credit measure, or `None` when unknown."""
        if kind == self.OPAQUE:
            return self._opaque_credits_by_work_key.get(identity, Decimal(0))
        if kind == self.ATTESTED:
            return self._attested_credits.get(identity)
        return self._credits_min_by_group_id.get(identity, Decimal(0))

    def credit_weight(self, variable: tuple[int, str, str, str]) -> Decimal:
        """Return one variable's credit weight: a known witness measure, else zero."""
        if variable[3] != self.WITNESS:
            return Decimal(0)
        measure = self._measure(variable[1], variable[2])
        if measure is None:
            raise ValueError("unknown-measure attested witness cannot be credit-weighted")
        return measure

    def count_weight(self, variable: tuple[int, str, str, str]) -> int:
        """Return one variable's course-count weight: one for a real course witness, else zero."""
        if variable[3] != self.WITNESS or variable[1] != self.COURSE:
            return 0
        return 1

    def new_credit_weight(self, variable: tuple[int, str, str, str]) -> Decimal:
        """Return one variable's new-work credit weight: a known measure for NEW, else zero."""
        if variable[3] != self.NEW:
            return Decimal(0)
        measure = self._measure(variable[1], variable[2])
        return Decimal(0) if measure is None else measure

    def is_unknown_credit(self, variable: tuple[int, str, str, str]) -> bool:
        """Return whether one witness variable has no known source credit extent."""
        return (
            variable[3] == self.WITNESS
            and variable[1] == self.ATTESTED
            and self._attested_credits.get(variable[2]) is None
        )

    def inactive_new_weight(self, variable: tuple[int, str, str, str]) -> int:
        """Return one variable's inactive-new-course weight: one for an inactive new course, else zero."""
        if variable[3] != self.NEW or variable[1] != self.COURSE:
            return 0
        return 1 if variable[2] in self._inactive_group_ids else 0

    @staticmethod
    def is_unknown_count(variable: tuple[int, str, str, str]) -> bool:
        """Return whether one witness variable is not a real counted course."""
        return variable[3] == _PathFamilies.WITNESS and variable[1] != _PathFamilies.COURSE

    def leaf_trace(self, support: int, label: tuple[str, str, str] | None = None) -> int:
        """Record one leaf node holding a typed occurrence label or a neutral identity."""
        return self._add_trace(support, self.LEAF, (), label)

    def union_trace(self, support: int, first: int, second: int) -> int:
        """Record one union of two provenance nodes into the resulting support."""
        return self._add_trace(support, self.UNION, (first, second))

    def join_trace(self, support: int, first: int, second: int) -> int:
        """Record one union-product join of two provenance nodes into the resulting support."""
        return self._add_trace(support, self.JOIN, (first, second))

    def identity_trace(self, support: int, source: int) -> int:
        """Record one support-only identity/restriction over an earlier provenance node."""
        return self._add_trace(support, self.IDENTITY, (source,))

    def project_trace(self, support: int, source: int) -> int:
        """Record one existential witness projection over an earlier provenance node."""
        return self._add_trace(support, self.PROJECT, (source,))

    def _add_trace(
        self,
        support: int,
        operation: str,
        inputs: tuple[int, ...],
        label: tuple[str, str, str] | None = None,
    ) -> int:
        """Append one provenance node and return its index."""
        self._traces.append(_PathTrace(support, operation, inputs, label))
        self._check_size()
        return len(self._traces) - 1

    def minimum_new_credits(self, family: int) -> Decimal | None:
        """Return the least new-course credit total over a support family, or `None` when empty.

        The fold is exact over the zero-suppressed DAG: the low branch keeps the running total and
        the high branch adds a variable's `credits_min` only when it is a NEW occurrence, so no
        member is materialized.
        """
        memo: dict[int, Decimal | None] = {}

        def visit(handle: int) -> Decimal | None:
            if handle == self.ZERO:
                return None
            if handle == self.ONE:
                return Decimal(0)
            if handle in memo:
                return memo[handle]
            variable, low, high = self._nodes[handle - 2]
            best_low = visit(low)
            suffix = visit(high)
            if suffix is None:
                best_high = None
            else:
                measure = (
                    self._measure(variable[1], variable[2]) if variable[3] == self.NEW else None
                )
                extra = Decimal(0) if measure is None else measure
                best_high = suffix + extra
            if best_low is None:
                result = best_high
            elif best_high is None:
                result = best_low
            else:
                result = best_low if best_low <= best_high else best_high
            memo[handle] = result
            return result

        return visit(family)

    def minimum_inactive_new_count(self, family: int) -> int | None:
        """Return the least inactive-new-course count over a support family, or `None` when empty.

        The same exact zero-suppressed DAG fold as the credit bound, with a variable's nonnegative
        inactivity weight added only on its high branch, so no member is materialized.
        """
        memo: dict[int, int | None] = {}

        def visit(handle: int) -> int | None:
            if handle == self.ZERO:
                return None
            if handle == self.ONE:
                return 0
            if handle in memo:
                return memo[handle]
            variable, low, high = self._nodes[handle - 2]
            suffix = visit(high)
            best_low = visit(low)
            if suffix is None:
                best_high = None
            else:
                best_high = suffix + self.inactive_new_weight(variable)
            if best_low is None:
                result = best_high
            elif best_high is None:
                result = best_low
            else:
                result = best_low if best_low <= best_high else best_high
            memo[handle] = result
            return result

        return visit(family)

    def best_support(self, family: int) -> _BestSupport | None:
        """Return the member minimizing new credits, then fewest inactive new courses, then ties.

        The minimum new-credit total is found by one exact support-DAG fold, then the same fold
        restricts to the fewest inactive canonical new courses on that cost-restricted DAG. The
        filtered family is successively restricted to the exact opaque, course and witness
        coordinates selected by projected prefix walks. No member is materialized and no suffix
        tuple is assumed to sort before its extension.
        """
        if family == self.ZERO:
            return None
        singleton_variables: list[tuple[int, str, str, str]] = []
        handle = family
        while handle >= 2:
            variable, low, high = self._nodes[handle - 2]
            if low != self.ZERO:
                break
            singleton_variables.append(variable)
            handle = high
        if handle == self.ONE:
            return _BestSupport(
                credits=sum(
                    (
                        self._measure(kind, identity) or Decimal(0)
                        for _, kind, identity, role in singleton_variables
                        if role == self.NEW
                    ),
                    Decimal(0),
                ),
                inactive_new_count=sum(
                    self.inactive_new_weight(variable) for variable in singleton_variables
                ),
                new_course_ids=tuple(
                    sorted(
                        identity
                        for _, kind, identity, role in singleton_variables
                        if role == self.NEW and kind == self.COURSE
                    )
                ),
                new_opaque_work_ids=tuple(
                    sorted(
                        identity
                        for _, kind, identity, role in singleton_variables
                        if role == self.NEW and kind == self.OPAQUE
                    )
                ),
                witness_course_ids=tuple(
                    sorted(
                        identity
                        for _, kind, identity, role in singleton_variables
                        if role == self.WITNESS and kind == self.COURSE
                    )
                ),
                witness_non_course_ids=tuple(
                    sorted(
                        (kind, identity)
                        for _, kind, identity, role in singleton_variables
                        if role == self.WITNESS and kind != self.COURSE
                    )
                ),
            )
        credits = self.minimum_new_credits(family)
        if credits is None:
            return None
        cost_filtered = self.filter(
            family, weight=self.new_credit_weight, lower=credits, upper=credits
        )
        inactive_new_count = self.minimum_inactive_new_count(cost_filtered)
        if inactive_new_count is None:
            return None
        restricted = self.filter(
            cost_filtered,
            weight=self.inactive_new_weight,
            lower=inactive_new_count,
            upper=inactive_new_count,
        )
        new_opaque_ids = tuple(
            identity for _, identity in self._least_identities(restricted, self.NEW, (self.OPAQUE,))
        )
        restricted = self._restrict_kind(restricted, self.NEW, self.OPAQUE, new_opaque_ids)
        new_course_ids = tuple(
            identity for _, identity in self._least_identities(restricted, self.NEW, (self.COURSE,))
        )
        restricted = self._restrict_kind(restricted, self.NEW, self.COURSE, new_course_ids)
        witness_course_ids = tuple(
            identity
            for _, identity in self._least_identities(restricted, self.WITNESS, (self.COURSE,))
        )
        restricted = self._restrict_kind(restricted, self.WITNESS, self.COURSE, witness_course_ids)
        witness_non_course_ids = self._least_identities(
            restricted, self.WITNESS, (self.ATTESTED, self.OPAQUE)
        )
        return _BestSupport(
            credits=credits,
            inactive_new_count=inactive_new_count,
            new_course_ids=new_course_ids,
            new_opaque_work_ids=new_opaque_ids,
            witness_course_ids=witness_course_ids,
            witness_non_course_ids=witness_non_course_ids,
        )

    def _restrict_kind(self, family: int, role: str, kind: str, selected: tuple[str, ...]) -> int:
        """Restrict a family to exactly one kind's selected identities and no others of that kind."""
        chosen = set(selected)
        restricted = family
        for candidate_kind, identity in self._order:
            if candidate_kind != kind:
                continue
            restricted = self.restrict_variable(
                restricted,
                self._variable(role, kind, identity),
                present=identity in chosen,
            )
        return restricted

    def _variable(self, role: str, kind: str, identity: str) -> tuple[int, str, str, str]:
        """Return one tagged variable for a known kind, identity and role."""
        return (self._rank_of(kind, identity), kind, identity, role)

    def _least_identities(
        self, family: int, role: str, kinds: tuple[str, ...]
    ) -> tuple[tuple[str, str], ...]:
        """Return the lexicographically least sorted identity tuple of one kind and role.

        Identities are scanned in ascending canonical order, independent of the DAG variable order.
        The walk projects away every other role and kind, then keeps a feasible subfamily and a selected
        prefix. If the prefix itself is a member it
        stops, because a tuple precedes every proper extension. Otherwise the first next identity
        whose inclusion leaves a nonempty support is appended. Earlier omitted identities stay
        excluded and chosen ones stay included, so no subset is enumerated. A kind with no selectable
        identity yields the empty tuple.
        """
        family = self.project(
            family, lambda variable: variable[3] != role or variable[1] not in kinds
        )
        identities: set[tuple[str, str]] = set()
        pending = [family]
        visited: set[int] = set()
        while pending:
            handle = pending.pop()
            if handle < 2 or handle in visited:
                continue
            visited.add(handle)
            variable, low, high = self._nodes[handle - 2]
            if variable[3] == role and variable[1] in kinds:
                identities.add((variable[1], variable[2]))
            pending.extend((low, high))
        ordered = sorted(identities)
        if not ordered:
            return ()
        prefix: list[tuple[str, str]] = []
        feasible = family
        position = 0
        while True:
            member = frozenset(self._variable(role, kind, identity) for kind, identity in prefix)
            if self.contains(feasible, member):
                return tuple(prefix)
            while position < len(ordered):
                kind, identity = ordered[position]
                position += 1
                included = self.restrict_variable(
                    feasible, self._variable(role, kind, identity), present=True
                )
                if included != self.ZERO:
                    feasible = included
                    prefix.append((kind, identity))
                    break
            else:
                # No further identity of this kind can be selected. The kind's subsequence is exactly
                # the current prefix (empty when the family holds no identity of this kind).
                return tuple(prefix)

    def reconstruct_evidence(
        self, trace: int, member: frozenset[tuple[int, str, str, str]]
    ) -> frozenset[tuple[str, str, str]]:
        """Return every typed occurrence label present in any valid derivation of `member`.

        The backwards allowed family at a node is the set of that node's outputs that extend to the
        selected root identity. Reachable provenance nodes are visited in descending creation-index
        order, so every consumer has already contributed before a node is processed once: incoming
        allowed families are unioned, intersected with the node's output support, and propagated
        through the exact inverse of the operation that produced it. A leaf collects its label. A
        union intersects each input support. An identity passes the constraint to its input. A join
        uses `join_preimage`. A projection uses `project_preimage`. Induction over this
        already-executed operation DAG therefore collects precisely the labels a forward
        per-label family produces, including every duplicate derivation and excluding rejected
        routes. Detached activity diagnostics are never reachable from the root trace.
        """
        allowed: dict[int, int] = {trace: self.singleton(member)}
        pending = [-trace]
        processed: set[int] = set()
        labels: set[tuple[str, str, str]] = set()
        while pending:
            index = -heapq.heappop(pending)
            if index in processed:
                continue
            processed.add(index)
            node_allowed = allowed.get(index)
            if node_allowed is None:
                continue
            node = self._traces[index]
            constrained = self.intersection(node_allowed, node.support)
            if constrained == self.ZERO:
                continue
            if node.operation == self.LEAF:
                if node.label is not None:
                    labels.add(node.label)
            elif node.operation == self.UNION:
                for input_index in node.inputs:
                    self._accumulate_allowed(
                        allowed,
                        pending,
                        input_index,
                        self.intersection(constrained, self._traces[input_index].support),
                    )
            elif node.operation == self.IDENTITY:
                self._accumulate_allowed(allowed, pending, node.inputs[0], constrained)
            elif node.operation == self.JOIN:
                first, second = node.inputs
                first_allowed, second_allowed = self.join_preimage(
                    self._traces[first].support, self._traces[second].support, constrained
                )
                self._accumulate_allowed(allowed, pending, first, first_allowed)
                self._accumulate_allowed(allowed, pending, second, second_allowed)
            elif node.operation == self.PROJECT:
                input_index = node.inputs[0]
                self._accumulate_allowed(
                    allowed,
                    pending,
                    input_index,
                    self.project_preimage(
                        self._traces[input_index].support, constrained, self.is_witness
                    ),
                )
            else:
                raise ValueError(f"unknown path trace operation {node.operation!r}")
        return frozenset(labels)

    def _accumulate_allowed(
        self, allowed: dict[int, int], pending: list[int], index: int, family: int
    ) -> None:
        """Union one incoming allowed family onto a provenance node and schedule it."""
        if family == self.ZERO:
            return
        existing = allowed.get(index)
        if existing is None:
            allowed[index] = family
        else:
            merged = self.union(existing, family)
            if merged == existing:
                return
            allowed[index] = merged
        heapq.heappush(pending, -index)


def _support_key(support: _BestSupport) -> tuple[object, ...]:
    """Return the exact support optimization key in the public typed tie order.

    The order is total distinct new credits, fewest inactive new canonical courses, sorted new opaque
    work IDs, sorted new canonical course IDs, sorted course witness IDs, then sorted non-course
    witness identities.
    """
    return (
        support.credits,
        support.inactive_new_count,
        support.new_opaque_work_ids,
        support.new_course_ids,
        support.witness_course_ids,
        support.witness_non_course_ids,
    )


@dataclass(frozen=True)
class _PathPartition:
    """One shortfall partition: exact support identities plus its operation provenance trace."""

    support: int
    trace: int


@dataclass(frozen=True)
class _PathFrontier:
    """One transient path frontier of shortfall partitions over tagged identity families."""

    families: _PathFamilies
    partitions: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition]

    @classmethod
    def neutral(cls, families: _PathFamilies) -> _PathFrontier:
        """Return the single empty-shortfall partition holding the neutral leaf identity."""
        return cls(families, {(): _PathPartition(families.ONE, families.leaf_trace(families.ONE))})

    @classmethod
    def empty(cls, families: _PathFamilies) -> _PathFrontier:
        """Return the frontier with no candidate partition."""
        return cls(families, {})

    @property
    def is_known(self) -> bool:
        """Return whether at least one partition holds a nonempty support family."""
        return any(
            partition.support != self.families.ZERO for partition in self.partitions.values()
        )

    def union(self, other: _PathFrontier) -> _PathFrontier:
        """Return the per-partition union of two frontiers, merging provenance on shared keys."""
        merged: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition] = {}
        for key in set(self.partitions) | set(other.partitions):
            left = self.partitions.get(key)
            right = other.partitions.get(key)
            if left is None:
                merged[key] = right  # type: ignore[assignment]
            elif right is None:
                merged[key] = left
            else:
                unioned = _union_partitions(self.families, left, right)
                if unioned is not None:
                    merged[key] = unioned
        return _PathFrontier(self.families, merged)

    def join(self, other: _PathFrontier) -> _PathFrontier:
        """Return the shortfall-merged union-product of two frontiers with one join trace each."""
        families = self.families
        merged: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition] = {}
        for left_key, left in self.partitions.items():
            for right_key, right in other.partitions.items():
                key = _merge_shortfalls((*left_key, *right_key))
                support = families.join(left.support, right.support)
                if support == families.ZERO:
                    continue
                part = _PathPartition(
                    support, families.join_trace(support, left.trace, right.trace)
                )
                existing = merged.get(key)
                merged[key] = (
                    part if existing is None else _union_partitions(families, existing, part)  # type: ignore[assignment]
                )
        return _PathFrontier(families, merged)

    def filter(
        self,
        *,
        weight,
        lower,
        upper,
    ) -> _PathFrontier:
        """Return the frontier keeping identities inside the inclusive bounds, one identity trace each."""
        families = self.families
        kept: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition] = {}
        for key, partition in self.partitions.items():
            support = families.filter(partition.support, weight=weight, lower=lower, upper=upper)
            if support == families.ZERO:
                continue
            kept[key] = _PathPartition(support, families.identity_trace(support, partition.trace))
        return _PathFrontier(families, kept)

    def partition_unknown(self, is_unknown) -> tuple[_PathFrontier, bool]:
        """Return the frontier without unknown-measure members, and whether any remained.

        Every known-measure member is kept exactly (with an identity provenance step), while any
        member carrying an unknown-measure token is reported separately so a numeric wrapper can keep
        the known alternatives instead of letting one unknown token poison them.
        """
        families = self.families
        kept: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition] = {}
        has_unknown = False
        for key, partition in self.partitions.items():
            known, partition_has_unknown = families.split_by_predicate(
                partition.support, is_unknown
            )
            has_unknown = has_unknown or partition_has_unknown
            if known == families.ZERO:
                continue
            kept[key] = _PathPartition(known, families.identity_trace(known, partition.trace))
        return _PathFrontier(families, kept), has_unknown

    def project_witnesses(self) -> _PathFrontier:
        """Return the frontier with every witness variable existentially removed, one project trace each."""
        families = self.families
        projected: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition] = {}
        for key, partition in self.partitions.items():
            support = families.project(partition.support, families.is_witness)
            if support == families.ZERO:
                continue
            projected[key] = _PathPartition(
                support, families.project_trace(support, partition.trace)
            )
        return _PathFrontier(families, projected)

    def without_empty_module_marker(self) -> _PathFrontier:
        """Return the frontier without each activity-empty module marker identity."""
        families = self.families
        kept: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition] = {}
        for key, partition in self.partitions.items():
            if len(key) != 1 or not _is_empty_module_marker(key[0]):
                kept[key] = partition
                continue
            support = families.remove_empty(partition.support)
            if support == families.ZERO:
                continue
            kept[key] = _PathPartition(support, families.identity_trace(support, partition.trace))
        return _PathFrontier(families, kept)

    def attach_shortfall(self, shortfall: PrerequisiteModuleShortfall) -> _PathFrontier:
        """Return the frontier with one deficit added to every partition, preserving provenance."""
        families = self.families
        attached: dict[tuple[PrerequisiteModuleShortfall, ...], _PathPartition] = {}
        for key, partition in self.partitions.items():
            new_key = _merge_shortfalls((*key, shortfall))
            existing = attached.get(new_key)
            if existing is None:
                attached[new_key] = partition
            else:
                attached[new_key] = _union_partitions(families, existing, partition)  # type: ignore[assignment]
        return _PathFrontier(families, attached)

    def restrict(self, keep) -> _PathFrontier:
        """Return the sub-frontier whose partition keys satisfy `keep`, preserving provenance."""
        return _PathFrontier(
            self.families,
            {key: partition for key, partition in self.partitions.items() if keep(key)},
        )


def _union_partitions(
    families: _PathFamilies, left: _PathPartition, right: _PathPartition
) -> _PathPartition | None:
    """Return the union of two same-key partitions, or `None` when the support is empty.

    Both source traces are kept even when the supports are equal, because duplicate identities must
    union the evidence of every valid derivation.
    """
    support = families.union(left.support, right.support)
    if support == families.ZERO:
        return None
    return _PathPartition(support, families.union_trace(support, left.trace, right.trace))


def _combine_frontiers(families: _PathFamilies, groups: Iterable[_PathFrontier]) -> _PathFrontier:
    """Return the join of every group frontier, starting from the neutral frontier."""
    combined = _PathFrontier.neutral(families)
    for group in groups:
        combined = combined.join(group)
    return combined


def _is_empty_module_marker(shortfall: PrerequisiteModuleShortfall) -> bool:
    """Return whether one deficit is the bare module course-unit marker `1 -> 0`.

    The bare module course-unit shortcut returns exactly the neutral identity carrying one
    `ALL_MANDATORY` deficit `1 -> 0`. Its enclosing module rule owns that position, so this marker is
    counted as a missing position rather than an achieved contribution. Any other deficit shape is a
    present position and keeps its own records.
    """
    return (
        shortfall.kind is PrerequisiteModuleShortfallKind.ALL_MANDATORY
        and shortfall.required_count == 1
        and shortfall.achieved_count == 0
    )


def _frontier_candidate(
    frontier: _PathFrontier,
    credits_min_by_group_id: dict[str, Decimal],
    opaque_credits_by_work_key: dict[str, Decimal],
    inactive_group_ids: frozenset[str],
) -> _PathCandidate:
    """Return the exact winning candidate across every partition of a known frontier.

    Each partition contributes its own optimization winner. Only the contenders whose `_support_key`
    is globally smallest reconstruct evidence from their provenance trace, so the expensive reverse
    pass runs for tied identities only. The tied candidates are then compared by the
    `_candidate_selection_key`, with `_candidate_sort_key` as the stable shortfall/evidence
    tie-break. Evidence is never merged across different shortfall partitions.
    """
    families = frontier.families
    contenders: list[
        tuple[tuple[PrerequisiteModuleShortfall, ...], _PathPartition, _BestSupport]
    ] = []
    best_support_key: tuple[object, ...] | None = None
    for shortfalls, partition in frontier.partitions.items():
        support = families.best_support(partition.support)
        if support is None:
            continue
        support_key = _support_key(support)
        if best_support_key is None or support_key < best_support_key:
            best_support_key = support_key
            contenders = [(shortfalls, partition, support)]
        elif support_key == best_support_key:
            contenders.append((shortfalls, partition, support))
    if not contenders:
        raise ValueError("known frontier has no candidate support")
    best: _PathCandidate | None = None
    best_key: tuple[object, ...] | None = None
    for shortfalls, partition, support in contenders:
        member = support.variables(families)
        evidence = families.reconstruct_evidence(partition.trace, member)
        candidate = _PathCandidate(
            witness_group_ids=frozenset(support.witness_course_ids),
            new_group_ids=frozenset(support.new_course_ids),
            new_opaque_work_ids=frozenset(support.new_opaque_work_ids),
            witness_non_course_ids=frozenset(support.witness_non_course_ids),
            evidence=evidence,
            shortfalls=shortfalls,
        )
        key = (
            _candidate_selection_key(
                candidate,
                credits_min_by_group_id,
                opaque_credits_by_work_key,
                inactive_group_ids,
            ),
            _candidate_sort_key(candidate),
        )
        if best_key is None or key < best_key:
            best_key = key
            best = candidate
    if best is None:
        raise ValueError("known frontier has no candidate support")
    return best


def _least_new_credits(frontier: _PathFrontier) -> Decimal:
    """Return the minimum new-course credit total across a known frontier's partitions."""
    least: Decimal | None = None
    for partition in frontier.partitions.values():
        credits = frontier.families.minimum_new_credits(partition.support)
        if credits is None:
            continue
        if least is None or credits < least:
            least = credits
    if least is None:
        raise ValueError("known frontier has no candidate support")
    return least


def _is_module_rule_position(expression: PrerequisiteExpression) -> bool:
    """Return whether one expression node carries compiler module-rule provenance.

    Only a node the module-rule compiler generated carries official `MODULE_RULE` provenance, so an
    ordinary compulsory/recommended/substitution course position is never counted or neutral-filled
    as a module position.
    """
    return (
        expression.origin is PrerequisiteOrigin.OFFICIAL
        and expression.official_kind is OfficialPrerequisiteKind.MODULE_RULE
    )


def _count_shortfall(
    kind: PrerequisiteModuleShortfallKind,
    occurrence_id: str,
    *,
    required_count: int,
    achieved_count: int,
) -> PrerequisiteModuleShortfall:
    """Build one count-family module deficit for the exact occurrence that owns it."""
    return PrerequisiteModuleShortfall(
        kind=kind,
        occurrence_id=occurrence_id,
        required_count=required_count,
        achieved_count=achieved_count,
        count_deficit=required_count - achieved_count,
    )


def _credit_shortfall(
    occurrence_id: str,
    *,
    required_credits: Decimal,
    achieved_credits: Decimal,
) -> PrerequisiteModuleShortfall:
    """Build one credit-family module deficit for the exact occurrence that owns it."""
    return PrerequisiteModuleShortfall(
        kind=PrerequisiteModuleShortfallKind.CREDITS,
        occurrence_id=occurrence_id,
        required_credits=required_credits,
        achieved_credits=achieved_credits,
        credit_deficit=required_credits - achieved_credits,
    )


@dataclass(frozen=True)
class _PathEvaluator(ExpressionEvaluator[_PathEvaluation]):
    """One exact bottom-up path fold over a compiled tree and the chosen calculation basis.

    `basis_group_ids` is the sole zero-cost basis, `completed_group_ids` the sole completed-history
    input, and `activity_exception_group_ids` the sole activity-exception input.
    `allow_module_shortfall` is set for exactly one activity-scoped primary pass and cleared for the
    same-node all-course diagnostic, so no second solver or activity policy exists. `families` is the
    one invocation-local tagged-identity DAG every node folds through. The optional
    `blocked_excluded_group_ids` collector is set only by the primary pass: a denied excluded course
    head or leaf is recorded there so a path result can explain which exclusions blocked
    requirements. Nested diagnostic and reduced probes use a derived copy of this evaluator and
    share the same families DAG.
    """

    tree: PrerequisiteCalculationTree
    basis_group_ids: frozenset[str]
    completed_group_ids: frozenset[str]
    activity_exception_group_ids: frozenset[str]
    allow_module_shortfall: bool
    families: _PathFamilies
    blocked_excluded_group_ids: set[str] | None = None
    blocked_excluded_node_keys: set[str] | None = None
    problems: list[PrerequisiteNodeProblem] | None = None
    completed_node_keys: frozenset[str] = frozenset()
    excluded_node_keys: frozenset[str] = frozenset()
    occurrence_by_action_key: dict[str, object] = field(default_factory=dict)
    action_key_by_occurrence: dict[str, str] = field(default_factory=dict)
    cycle_occurrence_ids: frozenset[str] = frozenset()
    cycle_path_by_occurrence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    apply_graph_marks: bool = True

    def evaluate(self, expression: PrerequisiteExpression, occurrence_id: str) -> _PathEvaluation:
        """Dispatch once, then attach this occurrence's neutral node-selection label.

        Every known result gains one typed `(node, action_key, occurrence_id)` label joined onto each
        of its partitions, so exact selected-occurrence evidence covers basis, structural and attested
        selections as well as new courses. An excluded or unsatisfied node has no known partition and
        therefore selects nothing.
        """
        result = super().evaluate(expression, occurrence_id)
        if not result.candidates.is_known:
            return result
        action_key = self.action_key_by_occurrence.get(occurrence_id)
        if action_key is None:
            return result
        families = self.families
        label = (_PathFamilies.NODE, action_key, occurrence_id)
        neutral = _PathFrontier(
            families,
            {(): _PathPartition(families.ONE, families.leaf_trace(families.ONE, label))},
        )
        return _PathEvaluation(
            candidates=result.candidates.join(neutral),
            has_unresolved_alternative=result.has_unresolved_alternative,
            blockers=result.blockers,
        )

    def node_override(
        self, expression: PrerequisiteExpression, occurrence_id: str
    ) -> _PathEvaluation | None:
        """Apply the shared node guard: exclusion first, then manual completion.

        An excluded non-course node yields no candidate and no blocker before any child traversal.
        A manually completed node yields a witness-only attested result at zero new cost, so it
        fulfils its enclosing requirement without inventing member courses.
        """
        if not self.apply_graph_marks:
            return None
        action_key = self.action_key_by_occurrence.get(occurrence_id)
        if action_key is None:
            return None
        node = self.occurrence_by_action_key.get(action_key)
        action = node_action(
            node,
            completed_node_keys=self.completed_node_keys,
            excluded_node_keys=self.excluded_node_keys,
        )
        if action == "excluded":
            if self.blocked_excluded_node_keys is not None:
                self.blocked_excluded_node_keys.add(action_key)
            self._record_problem(
                "no_solution",
                "excluded_node",
                expression,
                occurrence_id,
                action_key=action_key,
            )
            return _PathEvaluation(_PathFrontier.empty(self.families), False, ())
        if action == "completed":
            families = self.families
            credits_min = None if node is None else node.manual_credits_min
            families.register_attested(action_key, credits_min)
            support = families.singleton(
                (families.witness_variable(_PathFamilies.ATTESTED, action_key),)
            )
            return _PathEvaluation(
                _PathFrontier(
                    families,
                    {(): _PathPartition(support, families.leaf_trace(support))},
                ),
                False,
                (),
            )
        return None

    def _record_problem(
        self,
        state: Literal["no_solution", "unresolved", "shortfall"],
        reason: str,
        expression: PrerequisiteExpression,
        occurrence_id: str,
        *,
        action_key: str | None = None,
        referenced_group_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Append one located node problem to the primary collector, when present.

        Diagnostic passes disable the collector, so only the primary fold's local failures reach a
        result. The key defaults to the node's stable source action identity.
        """
        if self.problems is None:
            return
        key = action_key or self.action_key_by_occurrence.get(occurrence_id)
        if key is None:
            key = occurrence_id
        self.problems.append(
            PrerequisiteNodeProblem(
                occurrence_id=occurrence_id,
                action_key=key,
                state=state,
                reason=reason,
                origin=expression.origin,
                official_kind=expression.official_kind,
                inferred_category=expression.inferred_category,
                inference=expression.inference,
                referenced_group_id=referenced_group_id,
                detail=detail,
            )
        )

    def module_block(
        self, expression: ModuleBlockRequirement, occurrence_id: str
    ) -> _PathEvaluation:
        """Fold an unmarked module boundary transparently over its inlined child."""
        return self.evaluate(expression.child, f"{occurrence_id}.0")

    def opaque_credits(
        self, expression: OpaqueCreditRequirement, occurrence_id: str
    ) -> _PathEvaluation:
        """Evaluate one opaque obligation as distinct new source work charged once.

        A zero source minimum is a real zero requirement. A positive minimum is one witness and one
        new-charge identity keyed by the stable work key, so repeated identical work is charged once
        and different blocks stay independent.
        """
        families = self.families
        if expression.credits_min == 0:
            return _PathEvaluation(_PathFrontier.neutral(families), False, ())
        work_key = expression.work_key
        support = families.singleton(
            (
                families.witness_variable(_PathFamilies.OPAQUE, work_key),
                families.new_variable(_PathFamilies.OPAQUE, work_key),
            )
        )
        return _PathEvaluation(
            _PathFrontier(
                families,
                {
                    (): _PathPartition(
                        support,
                        families.leaf_trace(
                            support, (_PathFamilies.OPAQUE, work_key, occurrence_id)
                        ),
                    )
                },
            ),
            False,
            (),
        )

    def expanded_course(self, expression: AndRequirement, occurrence_id: str) -> _PathEvaluation:
        """Evaluate one compiler expanded-course branch: head course plus its prerequisite closure.

        Only a completed head returns the immediate zero-cost result without any descendant: a
        completed course satisfies its requirement and its historical prerequisites are never
        charged. Every other eligible head evaluates its descendants, contributes no new course of
        its own when it is in the chosen basis but `{head}` when it is not, and unions the descendant
        closure, evidence, and deficits, so a selected-but-incomplete basis head costs its full
        prerequisite closure. An excluded head is denied before the completed-head shortcut and
        records itself on the primary collector without traversing its historical descendants.
        """
        head, descendants = expression.children
        head_group_id = head.course_group_id
        families = self.families
        if not is_course_activity_eligible(
            self.tree, head_group_id, self.activity_exception_group_ids, for_calculation=True
        ):
            # An inactive or excluded head is neither proposed nor charged. Another route may win. Its
            # denial is a located problem so a mandatory blockage is explainable.
            head_occurrence_id = f"{occurrence_id}.0"
            if head_group_id in self.tree.excluded_group_ids:
                if self.blocked_excluded_group_ids is not None:
                    self.blocked_excluded_group_ids.add(head_group_id)
                self._record_problem(
                    "no_solution",
                    "excluded_node",
                    head,
                    head_occurrence_id,
                    action_key=f"course:{head_group_id}",
                    referenced_group_id=head_group_id,
                )
            else:
                self._record_problem(
                    "no_solution",
                    "inactive_course",
                    head,
                    head_occurrence_id,
                    action_key=f"course:{head_group_id}",
                    referenced_group_id=head_group_id,
                )
            return _PathEvaluation(_PathFrontier.empty(families), False, ())
        head_label = (_PathFamilies.COURSE, head_group_id, f"{occurrence_id}.0")
        head_occurrence_id = f"{occurrence_id}.0"
        head_variables = [families.witness_variable(_PathFamilies.COURSE, head_group_id)]
        if head_group_id not in self.basis_group_ids:
            head_variables.append(families.new_variable(_PathFamilies.COURSE, head_group_id))
        head_support = families.singleton(head_variables)
        head_frontier = _PathFrontier(
            families,
            {(): _PathPartition(head_support, families.leaf_trace(head_support, head_label))},
        )
        action_key = self.action_key_by_occurrence.get(head_occurrence_id)
        if action_key is not None:
            node_label = (_PathFamilies.NODE, action_key, head_occurrence_id)
            node_support = families.singleton(())
            node_frontier = _PathFrontier(
                families,
                {(): _PathPartition(node_support, families.leaf_trace(node_support, node_label))},
            )
            head_frontier = head_frontier.join(node_frontier)
        if head_group_id in self.completed_group_ids:
            # A completed course satisfies its requirement without any historical descendant.
            return _PathEvaluation(
                head_frontier,
                False,
                (),
            )
        descendant_evaluation = self.evaluate(descendants, f"{occurrence_id}.1")
        # Project the descendant witnesses away, then add the fixed head witness and its own new
        # charge. Descendant new IDs, evidence and deficits remain, so the head is measured but the
        # closure is charged exactly once.
        combined = head_frontier.join(descendant_evaluation.candidates.project_witnesses())
        return _PathEvaluation(
            candidates=combined,
            has_unresolved_alternative=descendant_evaluation.has_unresolved_alternative,
            blockers=(
                descendant_evaluation.blockers
                if descendant_evaluation.has_unresolved_alternative
                else ()
            ),
        )

    def course(self, expression: CourseRequirement, occurrence_id: str) -> _PathEvaluation:
        """Evaluate one course leaf into its witness, activity-empty, or denial result."""
        group_id = expression.course_group_id
        families = self.families
        if not is_course_activity_eligible(
            self.tree, group_id, self.activity_exception_group_ids, for_calculation=True
        ):
            if group_id in self.tree.excluded_group_ids:
                # An excluded head or leaf yields no candidate, unresolved alternative, or
                # shortfall regardless of activity or basis. Another route may win.
                if self.blocked_excluded_group_ids is not None:
                    self.blocked_excluded_group_ids.add(group_id)
                self._record_problem(
                    "no_solution",
                    "excluded_node",
                    expression,
                    occurrence_id,
                    referenced_group_id=group_id,
                )
                return _PathEvaluation(_PathFrontier.empty(families), False, ())
            # A module course unit unavailable only by activity is one reduced all-mandatory
            # position. Every other activity-ineligible leaf is no candidate and no blocker.
            if (
                expression.official_kind is OfficialPrerequisiteKind.MODULE_RULE
                and self.tree.active_only
                and self.allow_module_shortfall
                and self._all_course_diagnostic_allows_shortfall(
                    expression, occurrence_id=occurrence_id
                )
            ):
                shortfall = _count_shortfall(
                    PrerequisiteModuleShortfallKind.ALL_MANDATORY,
                    occurrence_id,
                    required_count=1,
                    achieved_count=0,
                )
                self._record_problem("shortfall", "activity_shortfall", expression, occurrence_id)
                return _PathEvaluation(
                    _PathFrontier(
                        families,
                        {
                            (shortfall,): _PathPartition(
                                families.ONE, families.leaf_trace(families.ONE)
                            )
                        },
                    ),
                    False,
                    (),
                )
            # A leaf unavailable only by activity scope is a located no-solution so a mandatory
            # blockage is explainable, even when another route wins.
            self._record_problem(
                "no_solution",
                "inactive_course",
                expression,
                occurrence_id,
                referenced_group_id=group_id,
            )
            return _PathEvaluation(_PathFrontier.empty(families), False, ())
        if occurrence_id in self.cycle_occurrence_ids and group_id not in self.completed_group_ids:
            # A cycle-closing occurrence resolves only through completed history, never selected
            # basis: a selected-only cycle is a located unknown route, not a tree-wide rejection.
            self._record_problem(
                "unresolved",
                UnresolvedPrerequisiteReason.COURSE_CYCLE.value,
                expression,
                occurrence_id,
                referenced_group_id=group_id,
            )
            return _PathEvaluation(
                _PathFrontier.empty(families),
                True,
                (
                    PrerequisitePathBlocker(
                        kind=PrerequisitePathBlockerKind.COURSE_CYCLE,
                        occurrence_id=occurrence_id,
                        reason=UnresolvedPrerequisiteReason.COURSE_CYCLE,
                        course_group_path=self.cycle_path_by_occurrence.get(occurrence_id, ()),
                        origin=expression.origin,
                        official_kind=expression.official_kind,
                    ),
                ),
            )
        variables = [families.witness_variable(_PathFamilies.COURSE, group_id)]
        if group_id not in self.basis_group_ids:
            variables.append(families.new_variable(_PathFamilies.COURSE, group_id))
        support = families.singleton(variables)
        return _PathEvaluation(
            _PathFrontier(
                families,
                {
                    (): _PathPartition(
                        support,
                        families.leaf_trace(
                            support, (_PathFamilies.COURSE, group_id, occurrence_id)
                        ),
                    )
                },
            ),
            False,
            (),
        )

    def unresolved(self, expression: UnresolvedRequirement, occurrence_id: str) -> _PathEvaluation:
        """Evaluate one unresolved requirement into one explicit blocker."""
        self._record_problem(
            "unresolved",
            expression.reason.value,
            expression,
            occurrence_id,
            referenced_group_id=expression.referenced_group_id,
            detail=expression.detail,
        )
        return _PathEvaluation(
            candidates=_PathFrontier.empty(self.families),
            has_unresolved_alternative=True,
            blockers=(
                PrerequisitePathBlocker(
                    kind=PrerequisitePathBlockerKind.UNRESOLVED_REQUIREMENT,
                    occurrence_id=occurrence_id,
                    reason=expression.reason,
                    referenced_group_id=expression.referenced_group_id,
                    detail=expression.detail,
                    origin=expression.origin,
                    official_kind=expression.official_kind,
                ),
            ),
        )

    def conjunction(
        self, expression: AndRequirement, occurrence_id: str, children: tuple[_PathEvaluation, ...]
    ) -> _PathEvaluation:
        """Evaluate an ordinary conjunction and optionally reduce an activity-only module rule."""
        has_unresolved = conjunction_is_unresolved(children)
        blockers = (
            _merge_blockers(
                blocker
                for child in children
                if child.has_unresolved_alternative
                for blocker in child.blockers
            )
            if has_unresolved
            else ()
        )
        combined = _combine_frontiers(self.families, (child.candidates for child in children))
        if (
            expression.official_kind is not OfficialPrerequisiteKind.MODULE_RULE
            or not self.tree.active_only
            or not self.allow_module_shortfall
        ):
            # An ordinary conjunction passes nested module deficits through with no reduction, and
            # the conjunction's own bound is its own.
            return _PathEvaluation(
                candidates=combined,
                has_unresolved_alternative=has_unresolved,
                blockers=blockers,
            )
        if not has_unresolved:
            reduced = self._reduce_module_conjunction(expression, occurrence_id, children)
            if reduced is not None:
                return reduced
        return _PathEvaluation(
            candidates=combined,
            has_unresolved_alternative=has_unresolved,
            blockers=blockers,
        )

    def alternatives(
        self, expression: OrRequirement, occurrence_id: str, children: tuple[_PathEvaluation, ...]
    ) -> _PathEvaluation:
        """Union every known child candidate and every child's unresolved route and blockers."""
        combined = _PathFrontier.empty(self.families)
        for child in children:
            combined = combined.union(child.candidates)
        return _PathEvaluation(
            candidates=combined,
            has_unresolved_alternative=any(child.has_unresolved_alternative for child in children),
            blockers=_merge_blockers(
                blocker
                for child in children
                if child.has_unresolved_alternative
                for blocker in child.blockers
            ),
        )

    def cardinality(
        self,
        expression: CardinalityRequirement,
        occurrence_id: str,
        children: tuple[_PathEvaluation, ...],
    ) -> _PathEvaluation:
        """Fold every allowed-size position selection and optionally reduce an activity-only rule."""
        families = self.families
        child_evaluations = children
        # Every candidate, including one carrying only nested deficits, is selectable.
        # An activity-empty module position has no candidate and is not selectable.
        child_frontiers = tuple(
            child.candidates.without_empty_module_marker() for child in child_evaluations
        )
        upper = expression.require_max if expression.require_max is not None else len(children)
        # Cap the DP's computational upper at the available child count without changing the reported
        # source bounds or the minimum: an above-count maximum is unreachable.
        upper = min(upper, len(children))
        # Rolling position DP: rows[count] is the exact family of identities selecting exactly
        # `count` of the processed child positions, counting positions rather than unique course IDs.
        rows = [_PathFrontier.empty(families) for _ in range(upper + 1)]
        rows[0] = _PathFrontier.neutral(families)
        for frontier in child_frontiers:
            next_rows = [_PathFrontier.empty(families) for _ in range(upper + 1)]
            for count in range(upper + 1):
                selected = rows[count]
                if count > 0:
                    selected = selected.union(rows[count - 1].join(frontier))
                next_rows[count] = selected
            rows = next_rows
        collected = _PathFrontier.empty(families)
        for count in range(expression.require_min, upper + 1):
            collected = collected.union(rows[count])
        viable = sum(
            1 for child in child_evaluations if child.is_known or child.has_unresolved_alternative
        )
        unresolved_children = sum(
            1 for child in child_evaluations if child.has_unresolved_alternative
        )
        has_unresolved = unresolved_children > 0 and max(expression.require_min, 1) <= min(
            upper, viable
        )
        blockers = (
            _merge_blockers(
                blocker
                for child in child_evaluations
                if child.has_unresolved_alternative
                for blocker in child.blockers
            )
            if has_unresolved
            else ()
        )
        if not collected.is_known and not has_unresolved:
            reduced = self._reduce_cardinality(expression, occurrence_id, child_frontiers)
            if reduced is not None:
                return reduced
            self._record_problem("no_solution", "too_few_positions", expression, occurrence_id)
        return _PathEvaluation(
            candidates=collected,
            has_unresolved_alternative=has_unresolved,
            blockers=blockers,
        )

    def bounded(
        self,
        expression: CreditRequirement | CourseCountRequirement,
        occurrence_id: str,
        child: _PathEvaluation,
    ) -> _PathEvaluation:
        """Keep known in-bound witnesses. Carry unknown-measure support as a located unknown route."""
        families = self.families
        if isinstance(expression, CreditRequirement):
            weight = families.credit_weight
            lower: Decimal | int = expression.credits_min
            upper: Decimal | int | None = expression.credits_max
            is_unknown = families.is_unknown_credit
            unknown_reason = UnresolvedPrerequisiteReason.UNKNOWN_CREDIT_EXTENT
        else:
            weight = families.count_weight
            lower = expression.count_min
            upper = expression.count_max
            is_unknown = families.is_unknown_count
            unknown_reason = UnresolvedPrerequisiteReason.UNKNOWN_COURSE_COUNT
        if not (lower > 0 or upper is not None):
            # A zero-minimum/unbounded wrapper needs no measure: every known or unknown witness passes.
            return _PathEvaluation(
                candidates=child.candidates,
                has_unresolved_alternative=child.has_unresolved_alternative,
                blockers=child.blockers,
            )
        known_frontier, has_unknown_member = child.candidates.partition_unknown(is_unknown)
        kept = known_frontier.filter(weight=weight, lower=lower, upper=upper)
        if has_unknown_member:
            # Unknown support is a real unresolved alternative for a bound with a positive minimum or
            # finite maximum, but it never poisons the viable known alternatives kept above.
            self._record_problem("unresolved", unknown_reason.value, expression, occurrence_id)
        if not kept.is_known and not child.has_unresolved_alternative and not has_unknown_member:
            reduced = self._reduce_bounded(expression, occurrence_id, known_frontier)
            if reduced is not None:
                return reduced
            self._record_problem("no_solution", "unreachable_bound", expression, occurrence_id)
        return _PathEvaluation(
            candidates=kept,
            has_unresolved_alternative=(child.has_unresolved_alternative or has_unknown_member),
            blockers=child.blockers,
        )

    def _all_course_diagnostic_allows_shortfall(
        self, expression: PrerequisiteExpression, *, occurrence_id: str
    ) -> bool:
        """Return whether the same node solves strictly once activity hides nothing.

        The local all-course diagnostic runs the one recursive evaluator with every represented
        course activity-eligible and reduced results disabled. It is the sole proof that a node below
        its bound fails because of activity scope rather than malformed, missing,
        ambiguous, cyclic, or genuinely impossible official structure.
        """
        diagnostic = replace(
            self,
            activity_exception_group_ids=frozenset(course.group_id for course in self.tree.courses),
            allow_module_shortfall=False,
            blocked_excluded_group_ids=None,
            blocked_excluded_node_keys=None,
            problems=None,
        ).evaluate(expression, occurrence_id)
        return diagnostic.is_known and not diagnostic.has_unresolved_alternative

    def _activity_fills_module_position(
        self, expression: PrerequisiteExpression, *, occurrence_id: str
    ) -> bool:
        """Return whether an empty module-rule position may be filled by the neutral candidate.

        The position must be a module-rule node that both solves strictly once every represented
        course is activity-eligible *and* actually reduces under the primary active-only pass. The
        first condition rejects malformed, missing, cyclic, and genuinely impossible
        structure. The second rejects a module node whose own position an ordinary prerequisite
        emptied, because neutral-filling it would weaken that non-module prerequisite. An
        expanded-course wrapper never qualifies: its head is a module course unit but also active, so
        an empty wrapper means an unavailable ordinary prerequisite.
        """
        if not _is_module_rule_position(expression) or is_expanded_course_branch(expression):
            return False
        if not self._all_course_diagnostic_allows_shortfall(
            expression, occurrence_id=occurrence_id
        ):
            return False
        reduced = replace(
            self,
            activity_exception_group_ids=self.basis_group_ids,
            allow_module_shortfall=True,
            blocked_excluded_group_ids=None,
            blocked_excluded_node_keys=None,
            problems=None,
        ).evaluate(expression, occurrence_id)
        return any(
            key and partition.support != self.families.ZERO
            for key, partition in reduced.candidates.partitions.items()
        )

    def _module_positions(
        self,
        expression: PrerequisiteExpression,
        child_evaluations: tuple[_PathEvaluation, ...],
        *,
        occurrence_id: str,
    ) -> tuple[tuple[_PathFrontier, ...], tuple[bool, ...]]:
        """Return one candidate frontier per module-rule child position plus per-position achievement.

        A position with at least one real candidate is achieved and keeps its own strict or reduced
        records. A position with only an activity-empty module marker, or with no candidate at all,
        becomes the neutral frontier and is not achieved when its own same-node all-course diagnostic
        proves activity scope alone emptied it. Any other empty position yields no group, so the whole
        rule is unreducible without absorbing unrelated structure into a module deficit.
        """
        groups: list[_PathFrontier] = []
        achieved_flags: list[bool] = []
        for index, evaluation in enumerate(child_evaluations):
            achieving = evaluation.candidates.without_empty_module_marker()
            if achieving.is_known:
                groups.append(achieving)
                achieved_flags.append(True)
                continue
            child_expression = expression.children[index]
            if self._activity_fills_module_position(
                child_expression, occurrence_id=f"{occurrence_id}.{index}"
            ):
                groups.append(_PathFrontier.neutral(self.families))
                achieved_flags.append(False)
                continue
            groups.append(_PathFrontier.empty(self.families))
            achieved_flags.append(False)
        return tuple(groups), tuple(achieved_flags)

    def _reduce_module_conjunction(
        self,
        expression: AndRequirement,
        occurrence_id: str,
        child_evaluations: tuple[_PathEvaluation, ...],
    ) -> _PathEvaluation | None:
        """Reduce an all-mandatory module rule emptied only by activity, or return `None`.

        A position that achieves records its own result. Each activity-empty module position is
        neutral-filled and becomes exactly one parent all-mandatory deficit. When every position
        achieves, the rule's own bound is met and nested records propagate without a duplicate parent
        deficit. A position that failed for any other reason yields no group, so the whole rule is
        unreducible without absorbing unrelated structure into a module deficit.
        """
        groups, achieved_flags = self._module_positions(
            expression, child_evaluations, occurrence_id=occurrence_id
        )
        achieved_count = sum(1 for achieved in achieved_flags if achieved)
        if all(group.is_known for group in groups) and achieved_count == len(groups):
            return _PathEvaluation(
                candidates=_combine_frontiers(self.families, groups),
                has_unresolved_alternative=False,
                blockers=(),
            )
        if (
            all(group.is_known for group in groups)
            and achieved_count < len(groups)
            and self._all_course_diagnostic_allows_shortfall(
                expression, occurrence_id=occurrence_id
            )
        ):
            reduced = _combine_frontiers(self.families, groups)
            if reduced.is_known:
                self._record_problem("shortfall", "activity_shortfall", expression, occurrence_id)
                return _PathEvaluation(
                    candidates=reduced.attach_shortfall(
                        _count_shortfall(
                            PrerequisiteModuleShortfallKind.ALL_MANDATORY,
                            occurrence_id,
                            required_count=len(expression.children),
                            achieved_count=achieved_count,
                        )
                    ),
                    has_unresolved_alternative=False,
                    blockers=(),
                )
        return None

    def _reduce_cardinality(
        self,
        expression: CardinalityRequirement,
        occurrence_id: str,
        child_frontiers: tuple[_PathFrontier, ...],
    ) -> _PathEvaluation | None:
        """Reduce a cardinality node emptied only by activity, or return `None`.

        No allowed-size selection exists, so activity scope alone may have removed child positions.
        The largest selectable count below this node's minimum becomes its exact achieved count, and
        each retained nested deficit carries onto the reduced candidate.
        """
        families = self.families
        selectable_positions = tuple(
            index for index, frontier in enumerate(child_frontiers) if frontier.is_known
        )
        achieved_count = len(selectable_positions)
        if (
            self.tree.active_only
            and self.allow_module_shortfall
            # Every position outside the selection must be activity-empty. Otherwise an
            # ordinary prerequisite failure would be absorbed into a fabricated deficit.
            and all(
                self._activity_fills_module_position(
                    expression.children[index],
                    occurrence_id=f"{occurrence_id}.{index}",
                )
                for index in range(len(expression.children))
                if index not in selectable_positions
            )
            and self._all_course_diagnostic_allows_shortfall(
                expression, occurrence_id=occurrence_id
            )
        ):
            reduced = _combine_frontiers(
                families, (child_frontiers[index] for index in selectable_positions)
            )
            self._record_problem("shortfall", "activity_shortfall", expression, occurrence_id)
            return _PathEvaluation(
                candidates=reduced.attach_shortfall(
                    _count_shortfall(
                        PrerequisiteModuleShortfallKind.CARDINALITY,
                        occurrence_id,
                        required_count=expression.require_min,
                        achieved_count=achieved_count,
                    )
                ),
                has_unresolved_alternative=False,
                blockers=(),
            )
        return None

    def _reduce_bounded(
        self,
        expression: CreditRequirement | CourseCountRequirement,
        occurrence_id: str,
        child_frontier: _PathFrontier,
    ) -> _PathEvaluation | None:
        """Reduce a credit/count node missing only its lower bound, or return `None`.

        The node misses only its lower bound, so activity scope may be why. The greatest reachable
        witness total/count strictly below the minimum becomes the achieved measure. Nested records
        stay. The maximum is an exact recursive fold over the support DAG, never a materialized
        candidate list.
        """
        if not (
            self.tree.active_only
            and self.allow_module_shortfall
            and self._all_course_diagnostic_allows_shortfall(
                expression, occurrence_id=occurrence_id
            )
        ):
            return None
        families = self.families
        if isinstance(expression, CreditRequirement):
            weight = families.credit_weight
            lower: Decimal | int = expression.credits_min
        else:
            weight = families.count_weight
            lower = expression.count_min
        best: Decimal | int | None = None
        for partition in child_frontier.partitions.values():
            value = families.max_weight_strictly_below(
                partition.support, weight=weight, budget=lower
            )
            if value is not None and (best is None or value > best):
                best = value
        if best is None:
            return None
        below = child_frontier.filter(weight=weight, lower=best, upper=best)
        if isinstance(expression, CreditRequirement):
            shortfall = _credit_shortfall(
                occurrence_id,
                required_credits=expression.credits_min,
                achieved_credits=best,
            )
        else:
            shortfall = _count_shortfall(
                PrerequisiteModuleShortfallKind.COURSE_COUNT,
                occurrence_id,
                required_count=expression.count_min,
                achieved_count=int(best),
            )
        self._record_problem("shortfall", "activity_shortfall", expression, occurrence_id)
        return _PathEvaluation(
            candidates=below.attach_shortfall(shortfall),
            has_unresolved_alternative=False,
            blockers=(),
        )


@dataclass(frozen=True)
class _GreedyPathEvaluator(ExpressionEvaluator[_GreedyEvaluation]):
    """Choose one scalar route per expression occurrence without constructing route families."""

    tree: PrerequisiteCalculationTree
    basis_group_ids: frozenset[str]
    completed_group_ids: frozenset[str]
    credits_min_by_group_id: dict[str, Decimal]
    opaque_credits_by_work_key: dict[str, Decimal]
    occurrence_by_action_key: dict[str, object]
    action_key_by_occurrence: dict[str, str]
    cycle_occurrence_ids: frozenset[str]
    cycle_path_by_occurrence: dict[str, tuple[str, ...]]
    inactive_group_ids: frozenset[str]
    blocked_excluded_group_ids: set[str] = field(default_factory=set)
    blocked_excluded_node_keys: set[str] = field(default_factory=set)

    def _leaf(
        self,
        candidate: _PathCandidate,
        witnesses: frozenset[tuple[str, str]],
        expression: PrerequisiteExpression,
        occurrence_id: str,
        *,
        scalar_cost: Decimal,
        kind: str = "leaf",
    ) -> _GreedyEvaluation:
        return _GreedyEvaluation(
            _GreedyRoute(
                candidate=candidate,
                witnesses=witnesses,
                scalar_cost=scalar_cost,
                kind=kind,
                expression=expression,
                occurrence_id=occurrence_id,
            )
        )

    def _node_label(self, occurrence_id: str) -> frozenset[tuple[str, str, str]]:
        action_key = self.action_key_by_occurrence.get(occurrence_id)
        return (
            frozenset({(_PathFamilies.NODE, action_key, occurrence_id)})
            if action_key is not None
            else frozenset()
        )

    def _combine(
        self,
        routes: tuple[_GreedyRoute, ...],
        expression: PrerequisiteExpression,
        occurrence_id: str,
        *,
        kind: str,
        positions: tuple[tuple[int, _GreedyRoute], ...] = (),
        extensions: tuple[tuple[int, _GreedyRoute], ...] = (),
        witnesses: frozenset[tuple[str, str]] | None = None,
    ) -> _GreedyRoute:
        candidate = _PathCandidate(
            witness_group_ids=frozenset().union(*(r.candidate.witness_group_ids for r in routes)),
            new_group_ids=frozenset().union(*(r.candidate.new_group_ids for r in routes)),
            evidence=frozenset().union(*(r.candidate.evidence for r in routes)),
            new_opaque_work_ids=frozenset().union(
                *(r.candidate.new_opaque_work_ids for r in routes)
            ),
            witness_non_course_ids=frozenset().union(
                *(r.candidate.witness_non_course_ids for r in routes)
            ),
        )
        return _GreedyRoute(
            candidate=candidate,
            witnesses=(
                frozenset().union(*(r.witnesses for r in routes))
                if witnesses is None
                else witnesses
            ),
            scalar_cost=sum((r.scalar_cost for r in routes), Decimal(0)),
            positions=positions,
            extension_positions=extensions,
            children=routes,
            kind=kind,
            expression=expression,
            occurrence_id=occurrence_id,
        )

    def evaluate(self, expression: PrerequisiteExpression, occurrence_id: str) -> _GreedyEvaluation:
        """Apply graph-node exclusion/completion before the shared structural dispatcher."""
        action_key = self.action_key_by_occurrence.get(occurrence_id)
        if action_key is not None:
            node = self.occurrence_by_action_key.get(action_key)
            action = node_action(
                node,
                completed_node_keys=frozenset(self.tree.completed_node_keys),
                excluded_node_keys=frozenset(self.tree.excluded_node_keys),
            )
            if action == "excluded":
                self.blocked_excluded_node_keys.add(action_key)
                return _GreedyEvaluation(None)
            if action == "completed":
                witness = frozenset({(_PathFamilies.ATTESTED, action_key)})
                candidate = _PathCandidate(
                    witness_group_ids=frozenset(),
                    new_group_ids=frozenset(),
                    evidence=self._node_label(occurrence_id),
                    witness_non_course_ids=witness,
                )
                return self._leaf(
                    candidate,
                    witness,
                    expression,
                    occurrence_id,
                    scalar_cost=Decimal(0),
                    kind="attested",
                )
        result = super().evaluate(expression, occurrence_id)
        if result.route is None:
            return result
        labels = self._node_label(occurrence_id)
        if not labels:
            return result
        route = result.route
        candidate = replace(route.candidate, evidence=route.candidate.evidence | labels)
        return replace(result, route=replace(route, candidate=candidate))

    def expanded_course(self, expression: AndRequirement, occurrence_id: str) -> _GreedyEvaluation:
        head, descendants = expression.children
        group_id = head.course_group_id
        if not is_course_activity_eligible(
            self.tree, group_id, self.basis_group_ids, for_calculation=True
        ):
            if group_id in self.tree.excluded_group_ids:
                self.blocked_excluded_group_ids.add(group_id)
            return _GreedyEvaluation(None)
        witness = frozenset({(_PathFamilies.COURSE, group_id)})
        evidence = frozenset({(_PathFamilies.COURSE, group_id, f"{occurrence_id}.0")})
        action = self.action_key_by_occurrence.get(f"{occurrence_id}.0")
        if action is not None:
            evidence |= frozenset({(_PathFamilies.NODE, action, f"{occurrence_id}.0")})
        charged = frozenset() if group_id in self.basis_group_ids else frozenset({group_id})
        head_candidate = _PathCandidate(
            witness_group_ids=frozenset({group_id}), new_group_ids=charged, evidence=evidence
        )
        head_route = _GreedyRoute(
            candidate=head_candidate,
            witnesses=witness,
            scalar_cost=Decimal(0)
            if group_id in self.basis_group_ids
            else self.credits_min_by_group_id[group_id],
            kind="head",
            expression=head,
            occurrence_id=f"{occurrence_id}.0",
        )
        if group_id in self.completed_group_ids:
            return _GreedyEvaluation(replace(head_route, kind="expanded"))
        descendant = self.evaluate(descendants, f"{occurrence_id}.1")
        if descendant.route is None:
            return descendant
        combined = self._combine(
            (head_route, descendant.route),
            expression,
            occurrence_id,
            kind="expanded",
            witnesses=witness,
        )
        combined = replace(
            combined,
            candidate=replace(
                combined.candidate,
                witness_group_ids=frozenset({group_id}),
                witness_non_course_ids=frozenset(),
            ),
        )
        return _GreedyEvaluation(
            combined, descendant.has_unresolved_alternative, descendant.blockers
        )

    def course(self, expression: CourseRequirement, occurrence_id: str) -> _GreedyEvaluation:
        group_id = expression.course_group_id
        if not is_course_activity_eligible(
            self.tree, group_id, self.basis_group_ids, for_calculation=True
        ):
            if group_id in self.tree.excluded_group_ids:
                self.blocked_excluded_group_ids.add(group_id)
            return _GreedyEvaluation(None)
        if occurrence_id in self.cycle_occurrence_ids and group_id not in self.completed_group_ids:
            blocker = PrerequisitePathBlocker(
                kind=PrerequisitePathBlockerKind.COURSE_CYCLE,
                occurrence_id=occurrence_id,
                reason=UnresolvedPrerequisiteReason.COURSE_CYCLE,
                course_group_path=self.cycle_path_by_occurrence.get(occurrence_id, ()),
                origin=expression.origin,
                official_kind=expression.official_kind,
            )
            return _GreedyEvaluation(None, True, (blocker,))
        witness = frozenset({(_PathFamilies.COURSE, group_id)})
        charged = frozenset() if group_id in self.basis_group_ids else frozenset({group_id})
        candidate = _PathCandidate(
            witness_group_ids=frozenset({group_id}),
            new_group_ids=charged,
            evidence=frozenset({(_PathFamilies.COURSE, group_id, occurrence_id)}),
        )
        return self._leaf(
            candidate,
            witness,
            expression,
            occurrence_id,
            scalar_cost=Decimal(0)
            if group_id in self.basis_group_ids
            else self.credits_min_by_group_id[group_id],
        )

    def module_block(
        self, expression: ModuleBlockRequirement, occurrence_id: str
    ) -> _GreedyEvaluation:
        return self.evaluate(expression.child, f"{occurrence_id}.0")

    def opaque_credits(
        self, expression: OpaqueCreditRequirement, occurrence_id: str
    ) -> _GreedyEvaluation:
        if expression.credits_min == 0:
            candidate = _PathCandidate(frozenset(), frozenset(), frozenset())
            return self._leaf(
                candidate, frozenset(), expression, occurrence_id, scalar_cost=Decimal(0)
            )
        key = expression.work_key
        witness = frozenset({(_PathFamilies.OPAQUE, key)})
        candidate = _PathCandidate(
            witness_group_ids=frozenset(),
            new_group_ids=frozenset(),
            new_opaque_work_ids=frozenset({key}),
            witness_non_course_ids=witness,
            evidence=frozenset({(_PathFamilies.OPAQUE, key, occurrence_id)}),
        )
        return self._leaf(
            candidate, witness, expression, occurrence_id, scalar_cost=expression.credits_min
        )

    def unresolved(
        self, expression: UnresolvedRequirement, occurrence_id: str
    ) -> _GreedyEvaluation:
        blocker = PrerequisitePathBlocker(
            kind=PrerequisitePathBlockerKind.UNRESOLVED_REQUIREMENT,
            occurrence_id=occurrence_id,
            reason=expression.reason,
            referenced_group_id=expression.referenced_group_id,
            detail=expression.detail,
            origin=expression.origin,
            official_kind=expression.official_kind,
        )
        return _GreedyEvaluation(None, True, (blocker,))

    def conjunction(
        self,
        expression: AndRequirement,
        occurrence_id: str,
        children: tuple[_GreedyEvaluation, ...],
    ) -> _GreedyEvaluation:
        if any(child.route is None for child in children):
            return _GreedyEvaluation(
                None,
                conjunction_is_unresolved(children),
                _merge_blockers(b for child in children for b in child.blockers),
            )
        routes = tuple(child.route for child in children if child.route is not None)
        return _GreedyEvaluation(self._combine(routes, expression, occurrence_id, kind="and"))

    def alternatives(
        self, expression: OrRequirement, occurrence_id: str, children: tuple[_GreedyEvaluation, ...]
    ) -> _GreedyEvaluation:
        viable = [child.route for child in children if child.route is not None]
        if not viable:
            return _GreedyEvaluation(
                None,
                any(child.has_unresolved_alternative for child in children),
                _merge_blockers(b for child in children for b in child.blockers),
            )
        chosen = min(
            viable,
            key=lambda route: _candidate_selection_key(
                route.candidate,
                self.credits_min_by_group_id,
                self.opaque_credits_by_work_key,
                self.inactive_group_ids,
                ranking_cost=route.scalar_cost,
            ),
        )
        return _GreedyEvaluation(self._combine((chosen,), expression, occurrence_id, kind="or"))

    def cardinality(
        self,
        expression: CardinalityRequirement,
        occurrence_id: str,
        children: tuple[_GreedyEvaluation, ...],
    ) -> _GreedyEvaluation:
        viable = [
            (index, child.route) for index, child in enumerate(children) if child.route is not None
        ]
        viable.sort(
            key=lambda item: (
                _candidate_selection_key(
                    item[1].candidate,
                    self.credits_min_by_group_id,
                    self.opaque_credits_by_work_key,
                    self.inactive_group_ids,
                    ranking_cost=item[1].scalar_cost,
                ),
                item[0],
            )
        )
        required = expression.require_min
        maximum = min(
            expression.require_max if expression.require_max is not None else len(children),
            len(children),
        )
        if len(viable) < required:
            return _GreedyEvaluation(None)
        selected = tuple(viable[:required])
        remaining = tuple(viable[required:maximum])
        routes = tuple(route for _, route in selected)
        route = self._combine(
            routes,
            expression,
            occurrence_id,
            kind="cardinality",
            positions=selected,
            extensions=remaining,
        )
        return _GreedyEvaluation(route)

    def bounded(
        self,
        expression: CreditRequirement | CourseCountRequirement,
        occurrence_id: str,
        child: _GreedyEvaluation,
    ) -> _GreedyEvaluation:
        if child.route is None:
            return child
        route = child.route
        lower: Decimal | int = (
            expression.credits_min
            if isinstance(expression, CreditRequirement)
            else expression.count_min
        )
        upper: Decimal | int | None = (
            expression.credits_max
            if isinstance(expression, CreditRequirement)
            else expression.count_max
        )
        if lower == 0 and upper is None:
            return _GreedyEvaluation(
                replace(
                    route,
                    kind="bounded",
                    expression=expression,
                    occurrence_id=occurrence_id,
                    positions=(),
                    children=(route,),
                )
            )
        metric = self._metric(route.witnesses, isinstance(expression, CreditRequirement))
        while metric is not None and metric < lower:
            extension = min(
                (
                    candidate
                    for candidate in self._next_extensions(route)
                    if (
                        (
                            value := self._metric(
                                candidate.witnesses, isinstance(expression, CreditRequirement)
                            )
                        )
                        is not None
                        and (upper is None or value <= upper)
                    )
                ),
                key=lambda candidate: _candidate_selection_key(
                    candidate.candidate,
                    self.credits_min_by_group_id,
                    self.opaque_credits_by_work_key,
                    self.inactive_group_ids,
                    ranking_cost=candidate.scalar_cost,
                ),
                default=None,
            )
            if extension is None:
                return _GreedyEvaluation(None)
            route = extension
            metric = self._metric(route.witnesses, isinstance(expression, CreditRequirement))
        if metric is None or (upper is not None and metric > upper) or metric < lower:
            return _GreedyEvaluation(None)
        return _GreedyEvaluation(
            replace(
                route,
                kind="bounded",
                expression=expression,
                occurrence_id=occurrence_id,
                positions=(),
                children=(route,),
            )
        )

    def _metric(self, witnesses: frozenset[tuple[str, str]], credits: bool) -> Decimal | int | None:
        total: Decimal | int = Decimal(0) if credits else 0
        for kind, identity in witnesses:
            if kind == _PathFamilies.COURSE:
                total += self.credits_min_by_group_id[identity] if credits else 1
            elif kind == _PathFamilies.OPAQUE:
                if not credits:
                    return None
                total += self.opaque_credits_by_work_key[identity]
            else:
                node = self.occurrence_by_action_key[identity]
                extent = node.manual_credits_min
                if (credits and extent is None) or not credits:
                    return None
                total += extent
        return total

    def _next_extensions(self, route: _GreedyRoute) -> tuple[_GreedyRoute, ...]:
        choices: list[_GreedyRoute] = []
        if route.kind == "cardinality" and route.extension_positions:
            index, option = route.extension_positions[0]
            rebuilt = self._combine(
                tuple(r for _, r in route.positions) + (option,),
                route.expression,
                route.occurrence_id,
                kind="cardinality",
                positions=route.positions + ((index, option),),
                extensions=route.extension_positions[1:],
            )
            if self._valid(rebuilt):
                choices.append(rebuilt)
        if route.kind == "expanded":
            return tuple(choices)
        for position, child in enumerate(route.children):
            for extended in self._next_extensions(child):
                replaced = list(route.children)
                replaced[position] = extended
                if route.kind == "cardinality":
                    selected_positions = list(route.positions)
                    selected_positions[position] = (selected_positions[position][0], extended)
                    rebuilt = self._combine(
                        tuple(replaced),
                        route.expression,
                        route.occurrence_id,
                        kind=route.kind,
                        positions=tuple(selected_positions),
                        extensions=route.extension_positions,
                    )
                else:
                    rebuilt = self._combine(
                        tuple(replaced),
                        route.expression,
                        route.occurrence_id,
                        kind=route.kind,
                        positions=route.positions,
                        extensions=route.extension_positions,
                    )
                if self._valid(rebuilt):
                    choices.append(rebuilt)
        return tuple(choices)

    def _valid(self, route: _GreedyRoute) -> bool:
        """Certify every selected guard, cardinality position, and nested numeric bound."""
        if route.kind == "attested":
            return True
        if not all(self._valid(child) for child in route.children):
            return False
        expression = route.expression
        if isinstance(expression, CardinalityRequirement):
            count = len(route.positions)
            if count < expression.require_min or (
                expression.require_max is not None and count > expression.require_max
            ):
                return False
        if isinstance(expression, (CreditRequirement, CourseCountRequirement)):
            if not route.children:
                return False
            credits = isinstance(expression, CreditRequirement)
            lower = expression.credits_min if credits else expression.count_min
            upper = expression.credits_max if credits else expression.count_max
            if lower == 0 and upper is None:
                return True
            value = self._metric(route.children[0].witnesses, credits)
            if value is None or value < lower or (upper is not None and value > upper):
                return False
        return True


def _solve_greedy_path(
    tree: PrerequisiteCalculationTree,
    satisfaction: PrerequisiteSatisfactionEvaluation,
) -> MinimumCreditPathEvaluation:
    """Run one scalar greedy derivation after the exact attempt exceeds its allocation budget."""
    if tree.requirements is None:
        return _exact_zero(satisfaction, tree.inferred_coverage)
    credits = {course.group_id: course.credits_min for course in tree.courses}
    summaries = {course.group_id: course for course in tree.courses}
    opaque = _opaque_credits_by_work_key(tree)
    occurrence_by_action_key: dict[str, object] = {}
    action_key_by_occurrence: dict[str, str] = {}
    for occurrence in tree.node_occurrences:
        occurrence_by_action_key.setdefault(occurrence.action_key, occurrence)
        action_key_by_occurrence.setdefault(occurrence.occurrence_id, occurrence.action_key)
    evaluator = _GreedyPathEvaluator(
        tree=tree,
        basis_group_ids=frozenset(satisfaction.basis_group_ids),
        completed_group_ids=frozenset(satisfaction.completed_group_ids),
        credits_min_by_group_id=credits,
        opaque_credits_by_work_key=opaque,
        occurrence_by_action_key=occurrence_by_action_key,
        action_key_by_occurrence=action_key_by_occurrence,
        cycle_occurrence_ids=frozenset(
            issue.occurrence_id
            for issue in tree.issues
            if issue.reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
        ),
        cycle_path_by_occurrence={
            issue.occurrence_id: issue.course_group_path
            for issue in tree.issues
            if issue.reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
        },
        inactive_group_ids=frozenset(
            course.group_id for course in tree.courses if not course.is_active
        ),
    )
    evaluation = evaluator.evaluate(tree.requirements, "r")
    route = evaluation.route
    if route is None or not evaluator._valid(route):
        return _approximation_failed(tree, satisfaction)
    return _exact_result(
        satisfaction,
        route.candidate,
        summaries,
        opaque,
        tree.inferred_coverage,
        tuple(sorted(evaluator.blocked_excluded_group_ids)),
        state=PrerequisitePathState.APPROXIMATE,
        shortfalls=(),
        problems=(),
        blocked_excluded_node_keys=tuple(sorted(evaluator.blocked_excluded_node_keys)),
    )


def _candidate_selection_key(
    candidate: _PathCandidate,
    credits_min_by_group_id: dict[str, Decimal],
    opaque_credits_by_work_key: dict[str, Decimal],
    inactive_group_ids: frozenset[str],
    *,
    ranking_cost: Decimal | None = None,
) -> tuple[object, ...]:
    """Return the exact selection key: new credits, inactive new courses, then typed ties."""
    total = ranking_cost
    if total is None:
        total = _witness_credits(candidate.new_group_ids, credits_min_by_group_id)
        total += sum(
            (
                opaque_credits_by_work_key.get(work_key, Decimal(0))
                for work_key in candidate.new_opaque_work_ids
            ),
            Decimal(0),
        )
    return (
        total,
        len(candidate.new_group_ids & inactive_group_ids),
        tuple(sorted(candidate.new_opaque_work_ids)),
        tuple(sorted(candidate.new_group_ids)),
        tuple(sorted(candidate.witness_group_ids)),
        tuple(sorted(candidate.witness_non_course_ids)),
        tuple(sorted(candidate.evidence)),
    )


def _build_new_courses(
    candidate: _PathCandidate, summaries_by_group_id: dict[str, CourseSummary]
) -> tuple[PrerequisitePathCourse, ...]:
    """Build sorted selected courses with every matching leaf occurrence as evidence."""
    courses: list[PrerequisitePathCourse] = []
    for group_id in sorted(candidate.new_group_ids):
        summary = summaries_by_group_id[group_id]
        occurrence_ids = tuple(
            sorted(
                occurrence_id
                for kind, identity, occurrence_id in candidate.evidence
                if kind == _PathFamilies.COURSE and identity == group_id
            )
        )
        courses.append(PrerequisitePathCourse(course=summary, occurrence_ids=occurrence_ids))
    return tuple(courses)


def _build_opaque_work(
    candidate: _PathCandidate, opaque_credits_by_work_key: dict[str, Decimal]
) -> tuple[PrerequisitePathOpaqueWork, ...]:
    """Build sorted distinct new opaque work with every matching occurrence as evidence."""
    work: list[PrerequisitePathOpaqueWork] = []
    for work_key in sorted(candidate.new_opaque_work_ids):
        occurrence_ids = tuple(
            sorted(
                occurrence_id
                for kind, identity, occurrence_id in candidate.evidence
                if kind == _PathFamilies.OPAQUE and identity == work_key
            )
        )
        work.append(
            PrerequisitePathOpaqueWork(
                work_key=work_key,
                credits_min=opaque_credits_by_work_key.get(work_key, Decimal(0)),
                occurrence_ids=occurrence_ids,
            )
        )
    return tuple(work)


def _exact_zero(
    satisfaction: PrerequisiteSatisfactionEvaluation,
    coverage: tuple[InferredCoverageRecord, ...],
    blocked_excluded_group_ids: tuple[str, ...] = (),
) -> MinimumCreditPathEvaluation:
    """Return the exact zero-cost result for an already-satisfied or neutral requirement."""
    return MinimumCreditPathEvaluation(
        satisfaction=satisfaction,
        state=PrerequisitePathState.EXACT,
        new_courses=(),
        total_new_credits=Decimal(0),
        blockers=(),
        shortfalls=(),
        inferred_coverage=coverage,
        blocked_excluded_group_ids=blocked_excluded_group_ids,
    )


def _non_exact(
    satisfaction: PrerequisiteSatisfactionEvaluation,
    state: PrerequisitePathState,
    blockers: tuple[PrerequisitePathBlocker, ...],
    coverage: tuple[InferredCoverageRecord, ...],
    blocked_excluded_group_ids: tuple[str, ...] = (),
    *,
    problems: tuple[PrerequisiteNodeProblem, ...] = (),
    blocked_excluded_node_keys: tuple[str, ...] = (),
) -> MinimumCreditPathEvaluation:
    """Return a non-exact result carrying no fabricated courses or credit total."""
    return MinimumCreditPathEvaluation(
        satisfaction=satisfaction,
        state=state,
        new_courses=(),
        total_new_credits=None,
        blockers=blockers,
        shortfalls=(),
        inferred_coverage=coverage,
        blocked_excluded_group_ids=blocked_excluded_group_ids,
        problems=problems,
        blocked_excluded_node_keys=blocked_excluded_node_keys,
    )


def _path_group_order(expression: PrerequisiteExpression | None) -> tuple[tuple[str, str], ...]:
    """Return each course/opaque identity in authoritative tree-first occurrence order.

    The authoritative expression's ordered children are scanned depth-first, a numeric `.child`
    included, recording each typed identity's first occurrence once. Only structure is scanned: no
    eligibility, expression-evaluation or cost policy is applied. An expanded-course head precedes
    its descendants because it is the first ordered child, which keeps large nested choice rules
    tractable without letting internal order affect any public canonical-ID tie.
    """
    if expression is None:
        return ()
    order: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    stack: list[PrerequisiteExpression] = [expression]
    while stack:
        node = stack.pop()
        if isinstance(node, CourseRequirement):
            key = (_PathFamilies.COURSE, node.course_group_id)
        elif isinstance(node, OpaqueCreditRequirement):
            key = (_PathFamilies.OPAQUE, node.work_key)
        else:
            if isinstance(node, (AndRequirement, OrRequirement, CardinalityRequirement)):
                stack.extend(reversed(node.children))
            elif isinstance(
                node, (CreditRequirement, CourseCountRequirement, ModuleBlockRequirement)
            ):
                stack.append(node.child)
            continue
        if key not in seen:
            seen.add(key)
            order.append(key)
    return tuple(order)


def _evaluate_primary_candidates(
    tree: PrerequisiteCalculationTree,
    *,
    basis_group_ids: frozenset[str],
    completed_group_ids: frozenset[str],
    credits_min_by_group_id: dict[str, Decimal],
    opaque_credits_by_work_key: dict[str, Decimal],
    inactive_group_ids: frozenset[str],
    max_compact_nodes: int | None,
) -> tuple[
    _PathFrontier,
    _PathFrontier,
    _PathEvaluation,
    tuple[str, ...],
    tuple[PrerequisiteNodeProblem, ...],
    tuple[str, ...],
]:
    """Return this tree's strict frontier, reduced frontier, evaluation, blocks, problems, node keys.

    The primary pass runs once with the basis as its sole activity exception set and module
    reduction allowed. Strict partitions carry no module deficit and use the exact
    semantics. Reduced partitions exist only when every strict route was blocked by activity scope.
    The completed-history input is threaded through so the primary and all-course diagnostic
    passes share one history semantics. The fourth item is the sorted canonical IDs of excluded
    course heads/leaves this primary pass actually denied. The fifth is the sorted located node
    problems of its local failures. The sixth is the sorted graph-only excluded node action keys it
    denied, regardless of whether another option later wins.
    """
    blocked_excluded: set[str] = set()
    blocked_node_keys: set[str] = set()
    problems: list[PrerequisiteNodeProblem] = []
    occurrence_by_action_key: dict[str, object] = {}
    action_key_by_occurrence: dict[str, str] = {}
    for occurrence in tree.node_occurrences:
        occurrence_by_action_key.setdefault(occurrence.action_key, occurrence)
        action_key_by_occurrence.setdefault(occurrence.occurrence_id, occurrence.action_key)
    evaluation = _PathEvaluator(
        tree=tree,
        basis_group_ids=basis_group_ids,
        completed_group_ids=completed_group_ids,
        activity_exception_group_ids=basis_group_ids,
        allow_module_shortfall=True,
        families=_PathFamilies(
            credits_min_by_group_id,
            _path_group_order(tree.requirements),
            opaque_credits_by_work_key,
            inactive_group_ids=inactive_group_ids,
            max_compact_nodes=max_compact_nodes,
        ),
        blocked_excluded_group_ids=blocked_excluded,
        blocked_excluded_node_keys=blocked_node_keys,
        problems=problems,
        completed_node_keys=frozenset(tree.completed_node_keys),
        excluded_node_keys=frozenset(tree.excluded_node_keys),
        occurrence_by_action_key=occurrence_by_action_key,
        action_key_by_occurrence=action_key_by_occurrence,
        cycle_occurrence_ids=frozenset(
            issue.occurrence_id
            for issue in tree.issues
            if issue.reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
        ),
        cycle_path_by_occurrence={
            issue.occurrence_id: issue.course_group_path
            for issue in tree.issues
            if issue.reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
        },
    ).evaluate(tree.requirements, "r")
    strict = evaluation.candidates.restrict(lambda key: not key)
    reduced = evaluation.candidates.restrict(bool)
    return (
        strict,
        reduced,
        evaluation,
        tuple(sorted(blocked_excluded)),
        tuple(
            sorted(
                set(problems),
                key=lambda problem: (
                    problem.occurrence_id,
                    problem.action_key,
                    problem.state,
                    problem.reason,
                ),
            )
        ),
        tuple(sorted(blocked_node_keys)),
    )


def calculate_minimum_new_credits(
    tree: PrerequisiteCalculationTree,
    basis_group_ids: Collection[str],
    *,
    completed_group_ids: Collection[str],
    max_compact_nodes: int | None = None,
) -> MinimumCreditPathEvaluation:
    """Return the exact or explicitly approximate minimum-new-credit route."""
    if max_compact_nodes is not None and max_compact_nodes <= 0:
        raise ValueError("max_compact_nodes must be positive")
    satisfaction = evaluate_prerequisite_satisfaction(
        tree, basis_group_ids, completed_group_ids=completed_group_ids
    )
    coverage = tree.inferred_coverage
    if tree.root.group_id in tree.excluded_group_ids:
        root_problem = PrerequisiteNodeProblem(
            occurrence_id="root",
            action_key=f"course:{tree.root.group_id}",
            state="no_solution",
            reason="excluded_node",
            origin=PrerequisiteOrigin.COMPOSED,
            referenced_group_id=tree.root.group_id,
        )
        return _non_exact(
            satisfaction,
            PrerequisitePathState.NO_SOLUTION,
            (),
            coverage,
            (tree.root.group_id,),
            problems=(root_problem,),
            blocked_excluded_node_keys=(f"course:{tree.root.group_id}",),
        )
    if satisfaction.requirements_state is PrerequisiteSatisfactionState.SATISFIED:
        return _exact_zero(satisfaction, coverage)
    try:
        return _solve_path(tree, satisfaction, max_compact_nodes=max_compact_nodes)
    except _PathSizeLimitExceeded:
        if max_compact_nodes is None:
            raise
    return _solve_greedy_path(tree, satisfaction)


def _solve_path(
    tree: PrerequisiteCalculationTree,
    satisfaction: PrerequisiteSatisfactionEvaluation,
    *,
    max_compact_nodes: int | None,
) -> MinimumCreditPathEvaluation:
    """Return the exact globally minimum new canonical courses and `credits_min` total.

    Satisfied requirements are exact zero regardless of unused unresolved or cyclic branches.
    Otherwise a positive-cost known candidate beside an unresolved alternative is unresolved,
    because unknown source structure could be cheaper. A known zero-credit candidate remains exact
    because costs are nonnegative. The supplied calculation tree is the sole authority: it carries
    the activity scope, a course in the chosen basis costs zero, and a completed course skips its
    historical descendants while a selected-but-incomplete basis course keeps its closure. Under
    active-only scope an otherwise satisfiable official module rule that activity alone pushed below
    its lower bound returns `SHORTFALL` with its exact deficits instead of `NO_SOLUTION`. Every other
    case keeps its strict outcome. Cycle-closing leaves and real unresolved nodes propagate only
    through traversed viable branches.
    """
    coverage = tree.inferred_coverage

    credits_min_by_group_id = {course.group_id: course.credits_min for course in tree.courses}
    summaries_by_group_id = {course.group_id: course for course in tree.courses}
    opaque_credits_by_work_key = _opaque_credits_by_work_key(tree)
    inactive_group_ids = frozenset(
        course.group_id for course in tree.courses if not course.is_active
    )
    (
        strict,
        reduced,
        evaluation,
        blocked_excluded,
        problems,
        blocked_excluded_node_keys,
    ) = _evaluate_primary_candidates(
        tree,
        basis_group_ids=frozenset(satisfaction.basis_group_ids),
        completed_group_ids=frozenset(satisfaction.completed_group_ids),
        credits_min_by_group_id=credits_min_by_group_id,
        opaque_credits_by_work_key=opaque_credits_by_work_key,
        inactive_group_ids=inactive_group_ids,
        max_compact_nodes=max_compact_nodes,
    )

    if not strict.is_known and reduced.is_known:
        # A reduced candidate never claims official satisfaction, so the official evaluation must
        # be plain UNSATISFIED. An unresolved official rule yields its unresolved result.
        if satisfaction.requirements_state is not PrerequisiteSatisfactionState.UNSATISFIED:
            return _non_exact(
                satisfaction,
                PrerequisitePathState.UNRESOLVED,
                evaluation.blockers,
                coverage,
                blocked_excluded,
                problems=problems,
                blocked_excluded_node_keys=blocked_excluded_node_keys,
            )
        if evaluation.has_unresolved_alternative:
            return _non_exact(
                satisfaction,
                PrerequisitePathState.UNRESOLVED,
                evaluation.blockers,
                coverage,
                blocked_excluded,
                problems=problems,
                blocked_excluded_node_keys=blocked_excluded_node_keys,
            )
        selected = _frontier_candidate(
            reduced, credits_min_by_group_id, opaque_credits_by_work_key, inactive_group_ids
        )
        return _exact_result(
            satisfaction,
            selected,
            summaries_by_group_id,
            opaque_credits_by_work_key,
            coverage,
            blocked_excluded,
            state=PrerequisitePathState.SHORTFALL,
            shortfalls=_merge_shortfalls(selected.shortfalls),
            problems=problems,
            blocked_excluded_node_keys=blocked_excluded_node_keys,
        )

    if not strict.is_known:
        if evaluation.has_unresolved_alternative:
            return _non_exact(
                satisfaction,
                PrerequisitePathState.UNRESOLVED,
                evaluation.blockers,
                coverage,
                blocked_excluded,
                problems=problems,
                blocked_excluded_node_keys=blocked_excluded_node_keys,
            )
        return _non_exact(
            satisfaction,
            PrerequisitePathState.NO_SOLUTION,
            (),
            coverage,
            blocked_excluded,
            problems=problems,
            blocked_excluded_node_keys=blocked_excluded_node_keys,
        )

    if evaluation.has_unresolved_alternative:
        least_known = _least_new_credits(strict)
        if least_known > 0:
            return _non_exact(
                satisfaction,
                PrerequisitePathState.UNRESOLVED,
                evaluation.blockers,
                coverage,
                blocked_excluded,
                problems=problems,
                blocked_excluded_node_keys=blocked_excluded_node_keys,
            )

    selected = _frontier_candidate(
        strict, credits_min_by_group_id, opaque_credits_by_work_key, inactive_group_ids
    )
    return _exact_result(
        satisfaction,
        selected,
        summaries_by_group_id,
        opaque_credits_by_work_key,
        coverage,
        blocked_excluded,
        state=PrerequisitePathState.EXACT,
        shortfalls=(),
        problems=problems,
        blocked_excluded_node_keys=blocked_excluded_node_keys,
    )


def _approximation_failed(
    tree: PrerequisiteCalculationTree,
    satisfaction: PrerequisiteSatisfactionEvaluation,
) -> MinimumCreditPathEvaluation:
    """Return a content-free, size-triggered failure instead of claiming impossibility."""
    problem = PrerequisiteNodeProblem(
        occurrence_id="root",
        action_key=f"course:{tree.root.group_id}",
        state="unresolved",
        reason="search_too_large",
        origin=PrerequisiteOrigin.COMPOSED,
        detail="Exact search was too large; the approximation found no valid route.",
    )
    return MinimumCreditPathEvaluation(
        satisfaction=satisfaction,
        state=PrerequisitePathState.APPROXIMATION_FAILED,
        new_courses=(),
        total_new_credits=None,
        blockers=(),
        shortfalls=(),
        inferred_coverage=tree.inferred_coverage,
        problems=(problem,),
    )


def _exact_result(
    satisfaction: PrerequisiteSatisfactionEvaluation,
    selected: _PathCandidate,
    summaries_by_group_id: dict[str, CourseSummary],
    opaque_credits_by_work_key: dict[str, Decimal],
    coverage: tuple[InferredCoverageRecord, ...],
    blocked_excluded_group_ids: tuple[str, ...],
    *,
    state: PrerequisitePathState,
    shortfalls: tuple[PrerequisiteModuleShortfall, ...],
    problems: tuple[PrerequisiteNodeProblem, ...],
    blocked_excluded_node_keys: tuple[str, ...] = (),
) -> MinimumCreditPathEvaluation:
    """Build one exact, approximate, or shortfall result with distinct course and opaque evidence."""
    new_courses = _build_new_courses(selected, summaries_by_group_id)
    new_opaque_work = _build_opaque_work(selected, opaque_credits_by_work_key)
    total = sum((entry.course.credits_min for entry in new_courses), Decimal(0)) + sum(
        (entry.credits_min for entry in new_opaque_work), Decimal(0)
    )
    selected_occurrence_ids = tuple(
        sorted(
            occurrence_id
            for kind, _identity, occurrence_id in selected.evidence
            if kind == _PathFamilies.NODE
        )
    )
    return MinimumCreditPathEvaluation(
        satisfaction=satisfaction,
        state=state,
        new_courses=new_courses,
        total_new_credits=total,
        blockers=(),
        shortfalls=shortfalls,
        inferred_coverage=coverage,
        blocked_excluded_group_ids=blocked_excluded_group_ids,
        new_opaque_work=new_opaque_work,
        selected_occurrence_ids=selected_occurrence_ids,
        problems=problems,
        blocked_excluded_node_keys=blocked_excluded_node_keys,
    )
