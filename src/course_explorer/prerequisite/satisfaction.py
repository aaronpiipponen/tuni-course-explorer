"""Pure prerequisite-satisfaction evaluation over the native calculation structure.

This module owns the fixed-basis satisfaction contract shared with discovery coverage. The native
piece DAG is the sole evaluation authority. Caller-owned canonical `group_id` values form the
chosen zero-cost calculation basis. A basis course satisfies its expanded head without traversing
descendants. A canonical course named by the structure's exclusion set is never a witness. Graph-only
marks (manual completion and node exclusion of non-course boxes) are consulted through the one
shared support guard.

Satisfaction is tri-state: a known witness makes a piece `SATISFIED`, no witness with an unresolved
alternative is `UNRESOLVED`, and a proven failure is `UNSATISFIED`. The bottom-up fold lives in
`traversal.py`, and discovery coverage reuses it. Numeric nodes keep the exact witness-family DAG
inherited from `_families._Families`, so an unbounded k-of-n over many leaves never enumerates its
selections.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from pydantic import field_validator

from course_explorer.prerequisite._families import _Families
from course_explorer.prerequisite._helpers import (
    _nonblank,
    _opaque_credits_by_work_key,
    _PrerequisiteModel,
    _unique_ids,
)
from course_explorer.prerequisite.graph import is_course_activity_eligible
from course_explorer.prerequisite.structure import (
    PrerequisitePiece,
    PrerequisiteSolverStructure,
    node_action,
    support_id,
)
from course_explorer.prerequisite.traversal import (
    PieceEvaluator,
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
    """One immutable evaluation of a native structure against the chosen calculation basis."""

    root_group_id: str
    include_recommended: bool
    include_inferred: bool
    active_only: bool
    basis_group_ids: tuple[str, ...]
    requirements_state: PrerequisiteSatisfactionState

    @field_validator("root_group_id")
    @classmethod
    def reject_blank_root(cls, value: str) -> str:
        """Require a nonblank canonical root identity."""
        return _nonblank(value, "root_group_id")

    @field_validator("basis_group_ids")
    @classmethod
    def require_sorted_unique_state(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require distinct caller-state IDs in sorted order."""
        return _unique_ids(value, "satisfaction group IDs", sorted_required=True)


class _WitnessFamilies(_Families[tuple[str, str]]):
    """One transient zero-suppressed decision DAG of exact satisfaction witness families."""

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

    def attested(self, support: str, credits_min: Decimal | None) -> int:
        """Return the singleton family holding exactly one attested manual-completion witness."""
        self._attested_credits[support] = credits_min
        return self.singleton(((_ATTESTED_KIND, support),))

    def credit_weight(self, variable: tuple[str, str]) -> Decimal:
        """Return one witness variable's minimum-credit weight."""
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
    """One piece's exact witness family plus whether an unknown witness could exist."""

    family: int
    has_unresolved_alternative: bool

    @property
    def is_known(self) -> bool:
        """Return whether at least one known witness satisfies this piece."""
        return self.family != _WitnessFamilies.ZERO


def _state_from_candidates(evaluation: _CandidateEvaluation) -> PrerequisiteSatisfactionState:
    """Map one candidate evaluation to its tri-state satisfaction."""
    if evaluation.family != _WitnessFamilies.ZERO:
        return PrerequisiteSatisfactionState.SATISFIED
    if evaluation.has_unresolved_alternative:
        return PrerequisiteSatisfactionState.UNRESOLVED
    return PrerequisiteSatisfactionState.UNSATISFIED


@dataclass
class _SatisfactionEvaluator(PieceEvaluator[_CandidateEvaluation]):
    """One satisfaction fold over a native structure and the chosen calculation basis."""

    structure: PrerequisiteSolverStructure
    basis_group_ids: frozenset[str]
    families: _WitnessFamilies
    apply_graph_marks: bool = True
    completed_node_keys: frozenset[str] = frozenset()
    excluded_node_keys: frozenset[str] = frozenset()
    memo: dict[tuple[str, str], _CandidateEvaluation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Build the request-local piece index once."""
        PieceEvaluator.__init__(self, self.structure)

    def evaluate(self, piece_id: str, owner_group_id: str) -> _CandidateEvaluation:
        """Return one piece's memoized candidate evaluation under its owner course."""
        key = (owner_group_id, piece_id)
        cached = self.memo.get(key)
        if cached is not None:
            return cached
        result = super().evaluate(piece_id, owner_group_id)
        self.memo[key] = result
        return result

    def node_override(
        self, piece: PrerequisitePiece, owner_group_id: str
    ) -> _CandidateEvaluation | None:
        """Apply the shared support guard: exclusion first, then manual completion."""
        if not self.apply_graph_marks:
            return None
        support = support_id(owner_group_id=owner_group_id, piece_id=piece.piece_id)
        action = node_action(
            self.structure,
            support,
            completed_node_keys=self.completed_node_keys,
            excluded_node_keys=self.excluded_node_keys,
        )
        if action == "excluded":
            return _CandidateEvaluation(
                family=_WitnessFamilies.ZERO, has_unresolved_alternative=False
            )
        if action == "completed":
            return _CandidateEvaluation(
                family=self.families.attested(support, piece.manual_credits_min),
                has_unresolved_alternative=False,
            )
        return None

    def expanded_course(
        self, piece: PrerequisitePiece, owner_group_id: str
    ) -> _CandidateEvaluation:
        """Evaluate an expanded branch as its head and, for a non-basis head, its closure."""
        head = self.piece(piece.children[0])
        head_owner = head.course_group_id or owner_group_id
        head_evaluation = self.evaluate(head.piece_id, head_owner)
        if head.course_group_id in self.basis_group_ids:
            return head_evaluation
        if not head_evaluation.is_known and not head_evaluation.has_unresolved_alternative:
            return head_evaluation
        descendant_evaluation = self.evaluate(piece.children[1], head_owner)
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

    def course(self, piece: PrerequisitePiece, owner_group_id: str) -> _CandidateEvaluation:
        """Evaluate one course leaf. Only an eligible basis course is a witness."""
        group_id = piece.course_group_id or ""
        if not is_course_activity_eligible(
            self.structure, group_id, self.basis_group_ids, for_calculation=True
        ):
            return _CandidateEvaluation(
                family=_WitnessFamilies.ZERO, has_unresolved_alternative=False
            )
        if group_id in self.basis_group_ids:
            return _CandidateEvaluation(
                family=self.families.course(group_id), has_unresolved_alternative=False
            )
        return _CandidateEvaluation(
            family=_WitnessFamilies.ZERO,
            has_unresolved_alternative=piece.cycle_closing,
        )

    def module_block(self, piece: PrerequisitePiece, owner_group_id: str) -> _CandidateEvaluation:
        """Fold an unmarked module boundary transparently over its inlined child."""
        return self.evaluate(piece.children[0], owner_group_id)

    def opaque_credits(self, piece: PrerequisitePiece, owner_group_id: str) -> _CandidateEvaluation:
        """Evaluate one opaque obligation: an explicit zero requirement is satisfied, else unknown."""
        if piece.credits_min == 0:
            return _CandidateEvaluation(
                family=_WitnessFamilies.ONE, has_unresolved_alternative=False
            )
        return _CandidateEvaluation(family=_WitnessFamilies.ZERO, has_unresolved_alternative=False)

    def unresolved(self, piece: PrerequisitePiece, owner_group_id: str) -> _CandidateEvaluation:
        """Evaluate one unresolved requirement as an unknown route with no known witness."""
        return _CandidateEvaluation(family=_WitnessFamilies.ZERO, has_unresolved_alternative=True)

    def conjunction(
        self,
        piece: PrerequisitePiece,
        owner_group_id: str,
        children: tuple[_CandidateEvaluation, ...],
    ) -> _CandidateEvaluation:
        """Combine an ordinary logical conjunction's child evaluations."""
        return self._combine_required(children)

    def alternatives(
        self,
        piece: PrerequisitePiece,
        owner_group_id: str,
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
        piece: PrerequisitePiece,
        owner_group_id: str,
        children: tuple[_CandidateEvaluation, ...],
    ) -> _CandidateEvaluation:
        """Fold allowed child selections as one position DP over witness families."""
        upper = piece.require_max if piece.require_max is not None else len(children)
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
        for count in range(piece.require_min or 0, upper + 1):
            family = self.families.union(family, rows[count])
        viable = sum(1 for child in children if child.is_known or child.has_unresolved_alternative)
        unresolved_children = sum(1 for child in children if child.has_unresolved_alternative)
        return _CandidateEvaluation(
            family=family,
            has_unresolved_alternative=(
                unresolved_children > 0 and max(piece.require_min or 0, 1) <= min(upper, viable)
            ),
        )

    def bounded(
        self, piece: PrerequisitePiece, owner_group_id: str, child: _CandidateEvaluation
    ) -> _CandidateEvaluation:
        """Keep known-measure witnesses inside the bounds. Carry unknown support as unresolved."""
        if piece.kind == "credits":
            weight = self.families.credit_weight
            lower: Decimal | int = piece.credits_min or Decimal(0)
            upper: Decimal | int | None = piece.credits_max
            is_unknown = self.families.is_unknown_credit
        else:
            weight = _WitnessFamilies.count_weight
            lower = piece.count_min or 0
            upper = piece.count_max
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
    """One request-local satisfaction context over a fixed native structure and basis."""

    def __init__(
        self,
        structure: PrerequisiteSolverStructure,
        basis_group_ids: Collection[str],
        *,
        apply_graph_marks: bool = True,
    ) -> None:
        self.structure = structure
        self.apply_graph_marks = apply_graph_marks
        self.basis_group_ids = _normalize_state_ids(basis_group_ids, label="basis group_id")
        self._evaluator = _SatisfactionEvaluator(
            structure=structure,
            basis_group_ids=self.basis_group_ids,
            families=_WitnessFamilies(
                _credits_min_by_group_id(structure), _opaque_credits_by_work_key(structure)
            ),
            apply_graph_marks=apply_graph_marks,
            completed_node_keys=frozenset(structure.completed_node_keys),
            excluded_node_keys=frozenset(structure.excluded_node_keys),
        )

    def evaluate(
        self, piece_id: str | None, *, owner_group_id: str | None = None
    ) -> PrerequisiteSatisfactionState:
        """Return one piece's public tri-state. A `None` piece is satisfied."""
        if piece_id is None:
            return PrerequisiteSatisfactionState.SATISFIED
        owner = owner_group_id or self.structure.root_group_id
        state = _state_from_candidates(self._evaluator.evaluate(piece_id, owner))
        return state


def _normalize_state_ids(values: Collection[str], *, label: str) -> frozenset[str]:
    """Normalize one caller-supplied ID collection into a nonblank frozen set."""
    normalized: set[str] = set()
    for group_id in values:
        normalized.add(_nonblank(group_id, label))
    return frozenset(normalized)


def _credits_min_by_group_id(structure: PrerequisiteSolverStructure) -> dict[str, Decimal]:
    """Return one canonical course ID to minimum-credit map from the structure summaries."""
    return {course.group_id: course.credits_min for course in structure.courses}


def _root_use(structure: PrerequisiteSolverStructure) -> tuple[str, str]:
    """Return the root requirements use and its owner course."""
    return structure.root_use_id or "", structure.root_group_id


def evaluate_prerequisite_satisfaction(
    structure: PrerequisiteSolverStructure,
    basis_group_ids: Collection[str],
) -> PrerequisiteSatisfactionEvaluation:
    """Evaluate a native structure against one basis of covered canonical courses."""
    session = PrerequisiteSatisfactionSession(structure, basis_group_ids)
    if structure.root_group_id in structure.excluded_group_ids:
        requirements_state = PrerequisiteSatisfactionState.UNSATISFIED
    elif structure.root_group_id in session.basis_group_ids:
        requirements_state = PrerequisiteSatisfactionState.SATISFIED
    else:
        root_use_id, root_owner = _root_use(structure)
        piece_id = (
            next(
                (use.piece_id for use in structure.uses if use.use_id == root_use_id),
                None,
            )
            if root_use_id
            else None
        )
        requirements_state = session.evaluate(piece_id, owner_group_id=root_owner)
    return PrerequisiteSatisfactionEvaluation(
        root_group_id=structure.root_group_id,
        include_recommended=structure.include_recommended,
        include_inferred=structure.include_inferred,
        active_only=structure.active_only,
        basis_group_ids=tuple(sorted(session.basis_group_ids)),
        requirements_state=requirements_state,
    )


def evaluate_prerequisite_piece(
    structure: PrerequisiteSolverStructure,
    piece_id: str | None,
    basis_group_ids: Collection[str],
    *,
    owner_group_id: str | None = None,
) -> PrerequisiteSatisfactionState:
    """Evaluate one selected piece through the same satisfaction fold as the full report."""
    session = PrerequisiteSatisfactionSession(structure, basis_group_ids)
    return session.evaluate(piece_id, owner_group_id=owner_group_id)
