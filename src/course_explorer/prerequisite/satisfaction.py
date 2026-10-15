"""Pure prerequisite-satisfaction evaluation over one already-filtered calculation tree.

This module owns the one fixed-basis satisfaction contract minimum-credit pathing shares. It
consumes a `PrerequisiteCalculationTree` exactly as produced by `graph.py`. The calculation tree is
the sole evaluation authority. Caller-owned canonical `group_id` values form the chosen zero-cost
calculation basis and its completed-history subset. A completed expanded course skips its expanded
descendants while a selected-but-incomplete basis course includes its closure. A canonical course named
by the tree's exclusion set is never a witness, even when it is in the basis or completed: exclusion
is a calculation rule carried by the tree. Graph-only marks (manual completion and node exclusion of
non-course nodes) are consulted through the one shared node guard.

Satisfaction is tri-state. A known satisfying witness of basis canonical courses makes a node
`SATISFIED`. A node with no witness but at least one unresolved alternative is `UNRESOLVED`. A node
proven unsatisfiable is `UNSATISFIED`. This module evaluates candidates over the fixed basis. The
bottom-up fold itself lives in `traversal.py`, shared with pathing.

Numeric nodes need the exact set of witness identities and totals, so
this module carries every candidate result as one family in a compact zero-suppressed decision DAG
(`_WitnessFamilies`, the satisfaction subclass of the shared `_families._Families` core). Union,
AND-join, cardinality and credit/count filtering are exact operations over that DAG, so an unbounded
k-of-n over many leaves never enumerates its selections. The DAG is transient per-session algorithm
state, never a cache.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from pydantic import field_validator, model_validator

from course_explorer.prerequisite._families import _Families
from course_explorer.prerequisite._helpers import (
    _nonblank,
    _opaque_credits_by_work_key,
    _PrerequisiteModel,
    _unique_ids,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    ModuleBlockRequirement,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteGraphNodeState,
    PrerequisiteNodeOccurrence,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteCalculationTree,
    _iter_expression_occurrences,
    is_course_activity_eligible,
    node_action,
)
from course_explorer.prerequisite.traversal import (
    ExpressionEvaluator,
    conjunction_is_unresolved,
)

_COURSE_KIND = "course"
_OPAQUE_KIND = "opaque"
_ATTESTED_KIND = "attested"


class PrerequisiteSatisfactionState(StrEnum):
    """Tri-state satisfaction of one prerequisite requirement."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNRESOLVED = "unresolved"


class PrerequisiteSatisfactionEvaluation(_PrerequisiteModel):
    """One immutable evaluation of a compiled tree against the chosen calculation basis.

    `basis_group_ids` is the chosen zero-cost basis and `completed_group_ids` is the caller's
    completed history, a required subset of that basis. The two are distinct: a completed expanded
    course skips its expanded descendants, while a selected-but-incomplete basis course satisfies
    its own node and its prerequisite closure.
    """

    root_group_id: str
    include_recommended: bool
    include_inferred: bool
    active_only: bool
    basis_group_ids: tuple[str, ...]
    completed_group_ids: tuple[str, ...]
    requirements_state: PrerequisiteSatisfactionState

    @field_validator("root_group_id")
    @classmethod
    def reject_blank_root(cls, value: str) -> str:
        """Require a nonblank canonical root identity."""
        return _nonblank(value, "root_group_id")

    @field_validator("basis_group_ids", "completed_group_ids")
    @classmethod
    def require_sorted_unique_state(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require distinct caller-state IDs in sorted order."""
        return _unique_ids(value, "satisfaction group IDs", sorted_required=True)

    @model_validator(mode="after")
    def require_completed_in_basis(self) -> PrerequisiteSatisfactionEvaluation:
        """Require completed history inside the chosen basis."""
        offenders = sorted(set(self.completed_group_ids) - set(self.basis_group_ids))
        if offenders:
            raise ValueError(
                f"completed courses must be in the calculation basis: {', '.join(offenders)}"
            )
        return self


class _WitnessFamilies(_Families[tuple[str, str]]):
    """One transient zero-suppressed decision DAG of exact satisfaction witness families.

    A family is a set of typed `(kind, identity)` witness variables. A course witness uses its
    canonical group ID. An opaque witness uses its stable work key. An attested manual-completion
    witness uses its source action key. The kind keeps a course, an opaque obligation and an attested
    completion distinct even when their identity text could coincide. Terminal `ZERO` is the empty
    family and terminal `ONE` holds exactly the empty witness. A variable's weight is its credit/count
    measure for the enclosing filter. An attested witness with no supplied source extent has an
    unknown credit measure, and every non-course witness has an unknown course count. The interned
    nodes, union/join/filter operations and their memos are inherited from the shared
    `_families._Families` core and are transient state for one session, never a cache.
    """

    def __init__(
        self,
        credits_min_by_group_id: dict[str, Decimal],
        opaque_credits_by_work_key: dict[str, Decimal],
    ) -> None:
        super().__init__()
        self._credits_min_by_group_id = credits_min_by_group_id
        self._opaque_credits_by_work_key = opaque_credits_by_work_key
        self._attested_credits: dict[str, Decimal | None] = {}

    def course(self, group_id: str) -> int:
        """Return the singleton family holding exactly the one-course witness."""
        return self.singleton(((_COURSE_KIND, group_id),))

    def opaque(self, work_key: str) -> int:
        """Return the singleton family holding exactly one opaque-work witness."""
        return self.singleton(((_OPAQUE_KIND, work_key),))

    def attested(self, action_key: str, credits_min: Decimal | None) -> int:
        """Return the singleton family holding exactly one attested manual-completion witness."""
        self._attested_credits[action_key] = credits_min
        return self.singleton(((_ATTESTED_KIND, action_key),))

    def credit_weight(self, variable: tuple[str, str]) -> Decimal:
        """Return one witness variable's minimum-credit weight. Unknown attested is never filtered."""
        kind, identity = variable
        if kind == _OPAQUE_KIND:
            return self._opaque_credits_by_work_key.get(identity, Decimal(0))
        if kind == _ATTESTED_KIND:
            credits = self._attested_credits[identity]
            if credits is None:
                raise ValueError("unknown-measure attested witness cannot be credit-weighted")
            return credits
        return self._credits_min_by_group_id.get(identity, Decimal(0))

    @staticmethod
    def count_weight(variable: tuple[str, str]) -> int:
        """Return one witness variable's unit course-count weight."""
        return 1 if variable[0] == _COURSE_KIND else 0

    def is_unknown_credit(self, variable: tuple[str, str]) -> bool:
        """Return whether one witness variable has no known source credit extent."""
        return variable[0] == _ATTESTED_KIND and self._attested_credits.get(variable[1]) is None

    @staticmethod
    def is_unknown_count(variable: tuple[str, str]) -> bool:
        """Return whether one witness variable is not a real counted course."""
        return variable[0] != _COURSE_KIND


@dataclass(frozen=True)
class _CandidateEvaluation:
    """One node's exact witness family plus whether an unknown witness could exist.

    `family` is a `_WitnessFamilies` handle. The `ZERO` terminal is the only "no known witness"
    value, and the `ONE` terminal is the distinct empty-witness family, so the two are distinct families.
    """

    family: int
    has_unresolved_alternative: bool

    @property
    def is_known(self) -> bool:
        """Return whether at least one known witness satisfies this node."""
        return self.family != _WitnessFamilies.ZERO


def _state_from_candidates(evaluation: _CandidateEvaluation) -> PrerequisiteSatisfactionState:
    """Map one candidate evaluation to its tri-state satisfaction."""
    if evaluation.family != _WitnessFamilies.ZERO:
        return PrerequisiteSatisfactionState.SATISFIED
    if evaluation.has_unresolved_alternative:
        return PrerequisiteSatisfactionState.UNRESOLVED
    return PrerequisiteSatisfactionState.UNSATISFIED


@dataclass(frozen=True)
class _SatisfactionEvaluator(ExpressionEvaluator[_CandidateEvaluation]):
    """One satisfaction fold over a compiled tree and the chosen calculation basis.

    Results are memoized by expression object identity and occurrence, because graph marks and
    cycle occurrences make a node's result occurrence-scoped. `retained` holds every evaluated
    expression alive for the session so a released caller-created expression can never have its
    `id` reused as a stale memo key. The memo is transient session state, never a cache.
    """

    tree: PrerequisiteCalculationTree
    basis_group_ids: frozenset[str]
    completed_group_ids: frozenset[str]
    families: _WitnessFamilies
    apply_graph_marks: bool = True
    completed_node_keys: frozenset[str] = frozenset()
    excluded_node_keys: frozenset[str] = frozenset()
    occurrence_by_action_key: dict[str, PrerequisiteNodeOccurrence] = field(default_factory=dict)
    action_key_by_occurrence: dict[str, str] = field(default_factory=dict)
    cycle_occurrence_ids: frozenset[str] = frozenset()
    memo: dict[tuple[int, str], _CandidateEvaluation] = field(default_factory=dict)
    retained: list[PrerequisiteExpression] = field(default_factory=list)

    def evaluate(
        self, expression: PrerequisiteExpression, occurrence_id: str
    ) -> _CandidateEvaluation:
        """Return one expression occurrence's memoized candidate evaluation."""
        key = (id(expression), occurrence_id)
        cached = self.memo.get(key)
        if cached is not None:
            return cached
        result = super().evaluate(expression, occurrence_id)
        self.memo[key] = result
        self.retained.append(expression)
        return result

    def node_override(
        self, expression: PrerequisiteExpression, occurrence_id: str
    ) -> _CandidateEvaluation | None:
        """Apply the shared node guard: exclusion first, then manual completion."""
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
            return _CandidateEvaluation(
                family=_WitnessFamilies.ZERO, has_unresolved_alternative=False
            )
        if action == "completed":
            credits_min = None if node is None else node.manual_credits_min
            return _CandidateEvaluation(
                family=self.families.attested(action_key, credits_min),
                has_unresolved_alternative=False,
            )
        return None

    def expanded_course(
        self, expression: AndRequirement, occurrence_id: str
    ) -> _CandidateEvaluation:
        """Evaluate one expanded active course: head plus its prerequisite closure.

        A completed head satisfies the requirement by itself and its historical descendants stay
        skipped. A selected-but-incomplete basis head is the one direct witness while its exact
        prerequisite closure is evaluated for truth, matching PATH's head-only witness
        projection so both public folds measure only the real head.
        """
        head, descendants = expression.children
        head_evaluation = self.evaluate(head, f"{occurrence_id}.0")
        if (
            head.course_group_id in self.completed_group_ids
            and head.course_group_id not in self.tree.excluded_group_ids
        ):
            return head_evaluation
        if not head_evaluation.is_known and not head_evaluation.has_unresolved_alternative:
            return head_evaluation
        descendant_evaluation = self.evaluate(descendants, f"{occurrence_id}.1")
        projected = self.families.project(descendant_evaluation.family, lambda _variable: True)
        return self._combine_required(
            (
                head_evaluation,
                _CandidateEvaluation(
                    family=projected,
                    has_unresolved_alternative=descendant_evaluation.has_unresolved_alternative,
                ),
            )
        )

    def course(self, expression: CourseRequirement, occurrence_id: str) -> _CandidateEvaluation:
        """Evaluate one course leaf. Only an eligible basis course is a witness.

        A cycle-closing occurrence resolves only through completed history, never selected basis: a
        selected-only cycle is an unknown route, while a completed course resolves it.
        """
        group_id = expression.course_group_id
        if not is_course_activity_eligible(
            self.tree, group_id, self.basis_group_ids, for_calculation=True
        ):
            return _CandidateEvaluation(
                family=_WitnessFamilies.ZERO, has_unresolved_alternative=False
            )
        if occurrence_id in self.cycle_occurrence_ids:
            if group_id in self.completed_group_ids:
                return _CandidateEvaluation(
                    family=self.families.course(group_id), has_unresolved_alternative=False
                )
            return _CandidateEvaluation(
                family=_WitnessFamilies.ZERO, has_unresolved_alternative=True
            )
        if group_id in self.basis_group_ids:
            return _CandidateEvaluation(
                family=self.families.course(group_id), has_unresolved_alternative=False
            )
        return _CandidateEvaluation(family=_WitnessFamilies.ZERO, has_unresolved_alternative=False)

    def module_block(
        self, expression: ModuleBlockRequirement, occurrence_id: str
    ) -> _CandidateEvaluation:
        """Fold an unmarked module boundary transparently over its inlined child."""
        return self.evaluate(expression.child, f"{occurrence_id}.0")

    def opaque_credits(
        self, expression: OpaqueCreditRequirement, occurrence_id: str
    ) -> _CandidateEvaluation:
        """Evaluate one opaque obligation: an explicit zero requirement is satisfied, else unknown."""
        if expression.credits_min == 0:
            return _CandidateEvaluation(
                family=_WitnessFamilies.ONE, has_unresolved_alternative=False
            )
        return _CandidateEvaluation(family=_WitnessFamilies.ZERO, has_unresolved_alternative=False)

    def unresolved(
        self, expression: UnresolvedRequirement, occurrence_id: str
    ) -> _CandidateEvaluation:
        """Evaluate one unresolved requirement as an unknown route with no known witness."""
        return _CandidateEvaluation(family=_WitnessFamilies.ZERO, has_unresolved_alternative=True)

    def conjunction(
        self,
        expression: AndRequirement,
        occurrence_id: str,
        children: tuple[_CandidateEvaluation, ...],
    ) -> _CandidateEvaluation:
        """Combine an ordinary logical conjunction's child evaluations."""
        return self._combine_required(children)

    def alternatives(
        self,
        expression: OrRequirement,
        occurrence_id: str,
        children: tuple[_CandidateEvaluation, ...],
    ) -> _CandidateEvaluation:
        """Union every known child witness family and OR the unresolved flag."""
        family = _WitnessFamilies.ZERO
        for child in children:
            family = self.families.union(family, child.family)
        return _CandidateEvaluation(
            family=family,
            has_unresolved_alternative=any(child.has_unresolved_alternative for child in children),
        )

    def cardinality(
        self,
        expression: CardinalityRequirement,
        occurrence_id: str,
        children: tuple[_CandidateEvaluation, ...],
    ) -> _CandidateEvaluation:
        """Fold allowed child selections as one position DP over witness families."""
        upper = expression.require_max if expression.require_max is not None else len(children)
        upper = min(upper, len(children))
        rows = [_WitnessFamilies.ZERO] * (upper + 1)
        rows[0] = _WitnessFamilies.ONE
        for child in children:
            next_row = [_WitnessFamilies.ZERO] * (upper + 1)
            for count in range(upper + 1):
                selected = rows[count]
                if count > 0:
                    selected = self.families.union(
                        selected, self.families.join(rows[count - 1], child.family)
                    )
                next_row[count] = selected
            rows = next_row
        family = _WitnessFamilies.ZERO
        for count in range(expression.require_min, upper + 1):
            family = self.families.union(family, rows[count])
        viable = sum(1 for child in children if child.is_known or child.has_unresolved_alternative)
        unresolved_children = sum(1 for child in children if child.has_unresolved_alternative)
        return _CandidateEvaluation(
            family=family,
            has_unresolved_alternative=(
                unresolved_children > 0 and max(expression.require_min, 1) <= min(upper, viable)
            ),
        )

    def bounded(
        self,
        expression: CreditRequirement | CourseCountRequirement,
        occurrence_id: str,
        child: _CandidateEvaluation,
    ) -> _CandidateEvaluation:
        """Keep known-measure witnesses inside the bounds. Carry unknown support as unresolved."""
        if isinstance(expression, CreditRequirement):
            weight = self.families.credit_weight
            lower: Decimal | int = expression.credits_min
            upper: Decimal | int | None = expression.credits_max
            is_unknown = self.families.is_unknown_credit
        else:
            weight = _WitnessFamilies.count_weight
            lower = expression.count_min
            upper = expression.count_max
            is_unknown = _WitnessFamilies.is_unknown_count
        if lower == 0 and upper is None:
            return child
        known, has_unknown_member = self.families.split_by_predicate(child.family, is_unknown)
        family = self.families.filter(known, weight=weight, lower=lower, upper=upper)
        nontrivial = lower > 0 or upper is not None
        return _CandidateEvaluation(
            family=family,
            has_unresolved_alternative=(
                child.has_unresolved_alternative or (has_unknown_member and nontrivial)
            ),
        )

    def _combine_required(
        self, child_evaluations: tuple[_CandidateEvaluation, ...]
    ) -> _CandidateEvaluation:
        """Join child witness families with ordinary AND semantics."""
        family = _WitnessFamilies.ONE
        for child in child_evaluations:
            family = self.families.join(family, child.family)
        return _CandidateEvaluation(
            family=family,
            has_unresolved_alternative=conjunction_is_unresolved(child_evaluations),
        )


class PrerequisiteSatisfactionSession:
    """One request-local satisfaction context over a fixed tree, basis and completed history.

    The constructor owns the shared setup the full-report and standalone-expression entry points
    reuse: it normalizes the caller state once, indexes the tree's node occurrences and cycle
    locations once, builds the one witness-family owner and one memoizing evaluator. Every expression
    evaluated through the session shares those transient results. A session never crosses a tree,
    basis, completed-history, policy or request boundary.
    """

    def __init__(
        self,
        tree: PrerequisiteCalculationTree,
        basis_group_ids: Collection[str],
        *,
        completed_group_ids: Collection[str],
        apply_graph_marks: bool = True,
    ) -> None:
        self.tree = tree
        self.apply_graph_marks = apply_graph_marks
        self.basis_group_ids = _normalize_state_ids(basis_group_ids, label="basis group_id")
        self.completed_group_ids = _normalize_state_ids(
            completed_group_ids, label="completed group_id"
        )
        self._occurrence_by_expression_id: dict[int, str] = {}
        if tree.requirements is not None:
            for occurrence_id, expression in _iter_expression_occurrences(tree.requirements):
                self._occurrence_by_expression_id.setdefault(id(expression), occurrence_id)
        occurrence_by_action_key: dict[str, PrerequisiteNodeOccurrence] = {}
        action_key_by_occurrence: dict[str, str] = {}
        for occurrence in tree.node_occurrences:
            occurrence_by_action_key.setdefault(occurrence.action_key, occurrence)
            action_key_by_occurrence.setdefault(occurrence.occurrence_id, occurrence.action_key)
        self._evaluator = _SatisfactionEvaluator(
            tree=tree,
            basis_group_ids=self.basis_group_ids,
            completed_group_ids=self.completed_group_ids,
            families=_WitnessFamilies(
                _credits_min_by_group_id(tree), _opaque_credits_by_work_key(tree)
            ),
            apply_graph_marks=apply_graph_marks,
            completed_node_keys=frozenset(tree.completed_node_keys),
            excluded_node_keys=frozenset(tree.excluded_node_keys),
            occurrence_by_action_key=occurrence_by_action_key,
            action_key_by_occurrence=action_key_by_occurrence,
            cycle_occurrence_ids=frozenset(
                issue.occurrence_id
                for issue in tree.issues
                if issue.reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
            ),
        )

    def evaluate(
        self, expression: PrerequisiteExpression | None, *, occurrence_id: str | None = None
    ) -> PrerequisiteSatisfactionState:
        """Return one expression's public tri-state through the shared satisfaction fold.

        A `None` expression is satisfied. When no occurrence is supplied the expression's original
        tree location is resolved once, so a caller-supplied subtree sees its own graph marks
        while a standalone unmarked expression test keeps its neutral result.
        """
        if expression is None:
            return PrerequisiteSatisfactionState.SATISFIED
        if occurrence_id is None:
            occurrence_id = self._resolve_occurrence(expression)
        state = _state_from_candidates(self._evaluator.evaluate(expression, occurrence_id))
        return state

    def _resolve_occurrence(self, expression: PrerequisiteExpression) -> str:
        """Return the original tree occurrence ID of one expression, or the root fallback."""
        return self._occurrence_by_expression_id.get(id(expression), "r")


def _normalize_state_ids(values: Collection[str], *, label: str) -> frozenset[str]:
    """Normalize one caller-supplied ID collection into a nonblank frozen set."""
    normalized: set[str] = set()
    for group_id in values:
        normalized.add(_nonblank(group_id, label))
    return frozenset(normalized)


def _credits_min_by_group_id(tree: PrerequisiteCalculationTree) -> dict[str, Decimal]:
    """Return one canonical course ID to minimum-credit map from the tree's summaries."""
    return {course.group_id: course.credits_min for course in tree.courses}


def evaluate_prerequisite_satisfaction(
    tree: PrerequisiteCalculationTree,
    basis_group_ids: Collection[str],
    *,
    completed_group_ids: Collection[str],
) -> PrerequisiteSatisfactionEvaluation:
    """Evaluate one compiled tree against the chosen calculation basis and completed history.

    The supplied tree is not mutated and no repository or config is consulted. `basis_group_ids`
    is the chosen zero-cost basis. `completed_group_ids` is the caller's completed history and must
    be a subset of it. The two are distinct: a completed expanded course skips its historical
    closure, while a selected-but-incomplete basis course satisfies its own node but keeps its
    prerequisites. IDs outside this tree are retained in the returned caller state but ignored in
    its candidates.
    """
    session = PrerequisiteSatisfactionSession(
        tree, basis_group_ids, completed_group_ids=completed_group_ids
    )
    if tree.root.group_id in tree.excluded_group_ids:
        requirements_state = PrerequisiteSatisfactionState.UNSATISFIED
    elif tree.root.group_id in session.completed_group_ids:
        requirements_state = PrerequisiteSatisfactionState.SATISFIED
    else:
        requirements_state = session.evaluate(tree.requirements, occurrence_id="r")
    return PrerequisiteSatisfactionEvaluation(
        root_group_id=tree.root.group_id,
        include_recommended=tree.include_recommended,
        include_inferred=tree.include_inferred,
        active_only=tree.active_only,
        basis_group_ids=tuple(sorted(session.basis_group_ids)),
        completed_group_ids=tuple(sorted(session.completed_group_ids)),
        requirements_state=requirements_state,
    )


def evaluate_prerequisite_expression(
    tree: PrerequisiteCalculationTree,
    expression: PrerequisiteExpression | None,
    basis_group_ids: Collection[str],
    *,
    completed_group_ids: Collection[str],
) -> PrerequisiteSatisfactionState:
    """Evaluate one selected subtree through the same satisfaction fold as the full report.

    Discovery consumes this to decide a single category root or one course-alternative slot. The
    caller passes the same chosen basis as its completed history because a direct discovery
    expression contains no course-ancestor closure. This marks no stored or browser sibling
    completed. A `None` expression is satisfied, exactly like the public rootless-tree result.
    """
    session = PrerequisiteSatisfactionSession(
        tree, basis_group_ids, completed_group_ids=completed_group_ids
    )
    return session.evaluate(expression)


def evaluate_prerequisite_node_states(
    tree: PrerequisiteCalculationTree,
    basis_group_ids: Collection[str],
    *,
    completed_group_ids: Collection[str],
) -> tuple[PrerequisiteGraphNodeState, ...]:
    """Return one aggregated action state per stable node action key.

    Course completion comes from the shared completed-course history and course exclusion from the
    tree's canonical exclusion set. A non-course node's manual completion comes only from the
    graph-only mark set. Module `completed_by_courses` evaluates the module's real child through one
    completed-only session with graph marks and exclusions disabled. Ignored disclosures are marked
    but never treated as calculation witnesses. This is a derived request result for UI, not a
    second completion store.
    """
    basis = frozenset(basis_group_ids)
    completed = frozenset(completed_group_ids)
    occurrence_by_action_key: dict[str, list[str]] = {}
    for occurrence in tree.node_occurrences:
        occurrence_by_action_key.setdefault(occurrence.action_key, []).append(
            occurrence.occurrence_id
        )
    expression_by_occurrence: dict[str, PrerequisiteExpression] = {}
    if tree.requirements is not None:
        expression_by_occurrence = dict(_iter_expression_occurrences(tree.requirements))
    completed_node_keys = frozenset(tree.completed_node_keys)
    excluded_node_keys = frozenset(tree.excluded_node_keys)
    excluded_group_ids = frozenset(tree.excluded_group_ids)
    # One shallow unmarked/unexcluded tree input serves both derived sessions: graph marks and
    # exclusions are disabled so a module/structural state measures only the caller's chosen basis and
    # completed history through the shared satisfaction fold, and the two sessions are built once and
    # reused for every represented module/structural occurrence.
    shallow = tree.model_copy(
        update={
            "completed_node_keys": (),
            "excluded_node_keys": (),
            "excluded_group_ids": (),
        }
    )
    completed_session = PrerequisiteSatisfactionSession(
        shallow, completed, completed_group_ids=completed, apply_graph_marks=False
    )
    basis_session = PrerequisiteSatisfactionSession(
        shallow, basis, completed_group_ids=completed, apply_graph_marks=False
    )
    states: list[PrerequisiteGraphNodeState] = []
    for action_key in sorted(occurrence_by_action_key):
        occurrence_ids = tuple(sorted(occurrence_by_action_key[action_key]))
        if action_key.startswith("course:"):
            group_id = action_key[len("course:") :]
            states.append(
                PrerequisiteGraphNodeState(
                    action_key=action_key,
                    occurrence_ids=occurrence_ids,
                    is_excluded=group_id in excluded_group_ids,
                    manually_completed=False,
                    completed_by_courses=group_id in completed,
                    satisfied_by_basis=group_id in basis,
                )
            )
            continue
        manually_completed = action_key in completed_node_keys
        is_excluded = action_key in excluded_node_keys
        completed_by_courses = False
        satisfied_by_basis = False
        representative = expression_by_occurrence.get(occurrence_ids[0])
        if representative is not None:
            # A module boundary folds transparently over its child, so the representative expression
            # itself measures both derived states at its explicit original occurrence.
            completed_by_courses = (
                completed_session.evaluate(representative, occurrence_id=occurrence_ids[0])
                is PrerequisiteSatisfactionState.SATISFIED
            )
            satisfied_by_basis = (
                basis_session.evaluate(representative, occurrence_id=occurrence_ids[0])
                is PrerequisiteSatisfactionState.SATISFIED
            )
        states.append(
            PrerequisiteGraphNodeState(
                action_key=action_key,
                occurrence_ids=occurrence_ids,
                is_excluded=is_excluded,
                manually_completed=manually_completed,
                completed_by_courses=completed_by_courses,
                satisfied_by_basis=satisfied_by_basis,
            )
        )
    display_occurrences_by_key: dict[str, set[str]] = {}
    for part in tree.ignored_parts:
        display_occurrences_by_key.setdefault(part.action_key, set()).add(part.part_id)
        if part.module is not None:
            display_occurrences_by_key.setdefault(f"module:{part.module.group_id}", set()).add(
                part.part_id
            )
    for action_key, display_ids in display_occurrences_by_key.items():
        if action_key in occurrence_by_action_key:
            continue
        states.append(
            PrerequisiteGraphNodeState(
                action_key=action_key,
                occurrence_ids=tuple(sorted(display_ids)),
                is_excluded=action_key in excluded_node_keys,
                manually_completed=action_key in completed_node_keys,
                completed_by_courses=False,
                satisfied_by_basis=False,
            )
        )
    return tuple(sorted(states, key=lambda state: state.action_key))
