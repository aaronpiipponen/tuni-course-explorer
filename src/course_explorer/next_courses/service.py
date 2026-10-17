"""Pure next-course discovery: direct-prerequisite coverage, eligibility and ordering.

This module owns the request-local arithmetic and ordering for "What Can I Study Next?".
It consumes already-compiled direct category roots, the chosen basis, and the requested mode, and
computes its result in memory. Coverage is built on the shared `traversal.ExpressionEvaluator` fold, so it is a
course-share meter over each category's OR-of-AND options. Full ALL-mode eligibility is decided by
the shared satisfaction owner with the
actual numeric constraints. Official and inferred contributions are distinguishable through the
relationship-local, official-wins `depends_on_inferred` flag.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedOrRole,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    ModuleBlockRequirement,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteOrigin,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import (
    DirectPrerequisiteCompilation,
    is_course_activity_eligible,
    is_expanded_course_branch,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionSession,
    PrerequisiteSatisfactionState,
)
from course_explorer.prerequisite.traversal import ExpressionEvaluator
from course_explorer.search.lookup import DisplayLanguage, name_code_key, official_display_name


class NextCourseMode(StrEnum):
    """Which direct-prerequisite eligibility mode one discovery request uses."""

    ALL = "all"
    AT_LEAST_ONE = "at_least_one"


class _NextCourseModel(BaseModel):
    """Frozen, closed base for the next-course result contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NextCourseResult(_NextCourseModel):
    """One proposed next course with its direct-prerequisite coverage and inferred attribution.

    Coverage is a fraction `[0, 1]` of the best-matching option's direct course slots the basis
    satisfies, and `None` when the category holds no course slot at all. `depends_on_inferred`
    is relationship-local with
    official precedence: true only when enabled inferred relationships make the course eligible but
    its official-only direct compilation leaves it ineligible under the same basis and mode.
    """

    course: CourseSummary
    required_coverage: float | None
    recommended_coverage: float | None
    depends_on_inferred: bool


@dataclass(frozen=True)
class _CoverageSlot:
    """One counted prerequisite slot: its stable key and whether the basis covers it."""

    key: str
    covered: bool


def _fraction(slots: frozenset[_CoverageSlot]) -> float:
    """Return the covered share of one slot set, or `0.0` for an empty set."""
    if not slots:
        return 0.0
    covered = sum(1 for slot in slots if slot.covered)
    return covered / len(slots)


def _coverage(slots: frozenset[_CoverageSlot]) -> float | None:
    """Return the covered share of one slot set, or `None` when the set holds no slot."""
    return None if not slots else _fraction(slots)


def _ranked(fraction: float | None) -> float:
    """Return one coverage fraction for ordering, where a category without slots counts as zero."""
    return 0.0 if fraction is None else fraction


def _head_course_group_id(expression: PrerequisiteExpression) -> str:
    """Return the canonical course a course-alternative OR's represented branch names."""
    if isinstance(expression, CourseRequirement):
        return expression.course_group_id
    if is_expanded_course_branch(expression):
        return expression.children[0].course_group_id
    raise ValueError("a course-alternative branch must be headed by one canonical course")


@dataclass(frozen=True)
class _CoverageEvaluator(ExpressionEvaluator[frozenset[_CoverageSlot]]):
    """One course-share coverage fold over a direct category expression.

    A direct course is one canonical slot, covered only when the shared satisfaction session says
    its leaf is satisfied. A composed `COURSE_ALTERNATIVES` OR is one slot for the course it
    replaces,
    covered only when the whole alternative expression is satisfied, so a partly met multi-course
    substitution never counts. Other AND/numeric nodes union canonical slots (repeats do not inflate
    the meter), other OR nodes use the best covered share of one child, and an unresolved
    occurrence is one unfulfilled slot keyed by its occurrence ID. The session memoizes subtree
    results within one candidate, so repeated occurrences never re-fold.
    """

    session: PrerequisiteSatisfactionSession

    def expanded_course(
        self, expression: AndRequirement, occurrence_id: str
    ) -> frozenset[_CoverageSlot]:
        """Union an expanded course's head and descendant slots."""
        head, descendants = expression.children
        return self.evaluate(head, f"{occurrence_id}.0") | self.evaluate(
            descendants, f"{occurrence_id}.1"
        )

    def course(self, expression: CourseRequirement, occurrence_id: str) -> frozenset[_CoverageSlot]:
        """Return one canonical course slot, covered only when its leaf is satisfied."""
        covered = self.session.evaluate(expression) is PrerequisiteSatisfactionState.SATISFIED
        return frozenset({_CoverageSlot(expression.course_group_id, covered)})

    def unresolved(
        self, expression: UnresolvedRequirement, occurrence_id: str
    ) -> frozenset[_CoverageSlot]:
        """Return one unknown, unfulfilled slot keyed by the occurrence ID."""
        return frozenset({_CoverageSlot(f"unresolved:{occurrence_id}", False)})

    def module_block(
        self, expression: ModuleBlockRequirement, occurrence_id: str
    ) -> frozenset[_CoverageSlot]:
        """Fold a module boundary transparently over its inlined child slots."""
        return self.evaluate(expression.child, f"{occurrence_id}.0")

    def opaque_credits(
        self, expression: OpaqueCreditRequirement, occurrence_id: str
    ) -> frozenset[_CoverageSlot]:
        """Return no slot: an opaque obligation supplies no fabricated course witness."""
        return frozenset()

    def conjunction(
        self,
        expression: AndRequirement,
        occurrence_id: str,
        children: tuple[frozenset[_CoverageSlot], ...],
    ) -> frozenset[_CoverageSlot]:
        """Union every child's canonical slots, deduplicating repeats."""
        return frozenset().union(*children)

    def alternatives(
        self,
        expression: OrRequirement,
        occurrence_id: str,
        children: tuple[frozenset[_CoverageSlot], ...],
    ) -> frozenset[_CoverageSlot]:
        """Keep one slot for a course-alternative OR, otherwise the best-covered option."""
        if (
            expression.origin is PrerequisiteOrigin.COMPOSED
            and expression.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
        ):
            covered = self.session.evaluate(expression) is PrerequisiteSatisfactionState.SATISFIED
            return frozenset(
                {_CoverageSlot(_head_course_group_id(expression.children[0]), covered)}
            )
        best_index = max(
            range(len(children)), key=lambda index: (_fraction(children[index]), -index)
        )
        return children[best_index]

    def cardinality(
        self,
        expression: CardinalityRequirement,
        occurrence_id: str,
        children: tuple[frozenset[_CoverageSlot], ...],
    ) -> frozenset[_CoverageSlot]:
        """Union the child course slots. Numeric bounds are enforced by the satisfaction owner."""
        return frozenset().union(*children)

    def bounded(
        self,
        expression: CreditRequirement | CourseCountRequirement,
        occurrence_id: str,
        child: frozenset[_CoverageSlot],
    ) -> frozenset[_CoverageSlot]:
        """Pass the wrapped child's course slots as-is."""
        return child


def _candidate_outcome(
    compilation: DirectPrerequisiteCompilation,
    basis_group_ids: frozenset[str],
    mode: NextCourseMode,
) -> tuple[float | None, float | None] | None:
    """Return one candidate's `(required, recommended)` coverage, or `None` when ineligible.

    A basis course, an activity-ineligible candidate, and a candidate with no enabled prerequisite
    category are always excluded, and a category whose slot set is empty reports no coverage
    rather than a zero share. AT LEAST ONE requires one covered direct prerequisite slot. ALL
    requires both category roots satisfied through the shared satisfaction owner (a `None` category
    is neutral). One session per candidate shares subtree results between the coverage fold and the
    ALL root check.
    """
    tree = compilation.tree
    candidate_id = tree.root.group_id
    if candidate_id in basis_group_ids:
        return None
    if not is_course_activity_eligible(tree, candidate_id, ()):
        return None
    if compilation.required is None and compilation.recommended is None:
        return None
    session = PrerequisiteSatisfactionSession(
        tree, basis_group_ids, completed_group_ids=basis_group_ids
    )
    evaluator = _CoverageEvaluator(session=session)
    required_slots = (
        evaluator.evaluate(compilation.required, "required")
        if compilation.required is not None
        else frozenset()
    )
    recommended_slots = (
        evaluator.evaluate(compilation.recommended, "recommended")
        if compilation.recommended is not None
        else frozenset()
    )
    if not required_slots and not recommended_slots:
        # Empty, fully dropped, or free-choice-only requirements supply no canonical prerequisite
        # slot, so they never flood discovery. A real covered slot governs AT LEAST ONE.
        return None
    if mode is NextCourseMode.AT_LEAST_ONE:
        if not any(slot.covered for slot in required_slots | recommended_slots):
            return None
    else:
        for pool in (compilation.required, compilation.recommended):
            if pool is None:
                continue
            if session.evaluate(pool) is not PrerequisiteSatisfactionState.SATISFIED:
                return None
    return _coverage(required_slots), _coverage(recommended_slots)


def evaluate_next_course_outcomes(
    compilations: Sequence[DirectPrerequisiteCompilation],
    basis_group_ids: Collection[str],
    *,
    mode: NextCourseMode,
) -> dict[str, tuple[float | None, float | None] | None]:
    """Return one root-keyed `(required, recommended)` outcome per compilation.

    Every root is recorded, including `None` for an ineligible candidate, so a caller can evaluate
    once and reuse the mapping for both eligibility scoping and final result creation. It is the one
    shared outcome owner. Supplied maps must come from the same compilations, basis and mode.
    """
    basis = frozenset(basis_group_ids)
    return {
        compilation.tree.root.group_id: _candidate_outcome(compilation, basis, mode)
        for compilation in compilations
    }


def eligible_next_course_group_ids(
    compilations: Sequence[DirectPrerequisiteCompilation],
    basis_group_ids: Collection[str],
    *,
    mode: NextCourseMode,
    candidate_outcomes: Mapping[str, tuple[float | None, float | None] | None] | None = None,
) -> tuple[str, ...]:
    """Return the sorted canonical IDs eligible in one direct-compilation pass.

    The command uses this shared eligibility core to bound the official-only recompile to the
    candidates that actually qualify, so the one final result-service call receives an official
    compilation for every result it can report. A supplied `candidate_outcomes` map is consumed
    directly (indexed by root, never missing-as-ineligible). Otherwise this owner computes it.
    """
    outcomes = (
        candidate_outcomes
        if candidate_outcomes is not None
        else evaluate_next_course_outcomes(compilations, basis_group_ids, mode=mode)
    )
    return tuple(
        sorted(
            compilation.tree.root.group_id
            for compilation in compilations
            if outcomes[compilation.tree.root.group_id] is not None
        )
    )


def next_courses_from_compilations(
    compilations: Sequence[DirectPrerequisiteCompilation],
    basis_group_ids: Collection[str],
    *,
    mode: NextCourseMode,
    display_language: DisplayLanguage,
    official_compilations: Sequence[DirectPrerequisiteCompilation] = (),
    candidate_outcomes: Mapping[str, tuple[float | None, float | None] | None] | None = None,
) -> tuple[NextCourseResult, ...]:
    """Return the ordered next-course list for one already-compiled candidate set.

    `official_compilations`, when supplied, carries the same candidates compiled with
    `include_inferred=False`. A result is marked inferred-dependent only when the official-only
    compilation is present and ineligible under the same basis and mode, using a distinct outcome
    map from the same owner. Without it (inference off) every result is false, without a second
    compile. A supplied `candidate_outcomes` map is consumed directly instead of recomputing the
    first-pass outcomes. ALL sorts by the displayed name/code key. AT LEAST ONE sorts by descending
    required then recommended coverage, then the same key.
    """
    outcomes = (
        candidate_outcomes
        if candidate_outcomes is not None
        else evaluate_next_course_outcomes(compilations, basis_group_ids, mode=mode)
    )
    official_by_root = {
        compilation.tree.root.group_id: compilation for compilation in official_compilations
    }
    official_outcomes = (
        evaluate_next_course_outcomes(official_compilations, basis_group_ids, mode=mode)
        if official_compilations
        else {}
    )
    results: list[NextCourseResult] = []
    for compilation in compilations:
        candidate_id = compilation.tree.root.group_id
        outcome = outcomes[candidate_id]
        if outcome is None:
            continue
        required_coverage, recommended_coverage = outcome
        official = official_by_root.get(candidate_id)
        depends_on_inferred = official is not None and official_outcomes[candidate_id] is None
        results.append(
            NextCourseResult(
                course=compilation.tree.root,
                required_coverage=required_coverage,
                recommended_coverage=recommended_coverage,
                depends_on_inferred=depends_on_inferred,
            )
        )
    return _sorted_results(tuple(results), mode=mode, display_language=display_language)


def _sorted_results(
    results: tuple[NextCourseResult, ...],
    *,
    mode: NextCourseMode,
    display_language: DisplayLanguage,
) -> tuple[NextCourseResult, ...]:
    """Order one result tuple by the mode's ordering key."""

    def name_key(result: NextCourseResult) -> tuple[bool, str, str, str]:
        return name_code_key(result.course, official_display_name(result.course, display_language))

    if mode is NextCourseMode.AT_LEAST_ONE:
        return tuple(
            sorted(
                results,
                key=lambda result: (
                    -_ranked(result.required_coverage),
                    -_ranked(result.recommended_coverage),
                    name_key(result),
                ),
            )
        )
    return tuple(sorted(results, key=name_key))
