"""Pure next-course discovery: direct-prerequisite coverage, eligibility and ordering.

This module owns the request-local arithmetic and ordering for "What Can I Study Next?". It
consumes already-compiled native direct category roots, the chosen basis and the requested mode.
Coverage is a course-share meter over each category's OR-of-AND options, carried as a canonical
course-slot set plus its implicit unresolved slot count. Full ALL-mode eligibility is decided by the
shared satisfaction owner with the actual numeric constraints. Official and inferred contributions
stay distinguishable through the relationship-local, official-wins `depends_on_inferred` flag.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite.graph import (
    DirectPrerequisiteCompilation,
    is_course_activity_eligible,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionSession,
    PrerequisiteSatisfactionState,
)
from course_explorer.prerequisite.structure import (
    PrerequisitePiece,
    PrerequisiteSolverStructure,
)
from course_explorer.prerequisite.traversal import PieceEvaluator
from course_explorer.search.lookup import DisplayLanguage, name_code_key, official_display_name


class NextCourseMode(StrEnum):
    """Which direct-prerequisite eligibility mode one discovery request uses."""

    ALL = "all"
    AT_LEAST_ONE = "at_least_one"


class _NextCourseModel(BaseModel):
    """Frozen, closed base for the next-course result contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NextCourseResult(_NextCourseModel):
    """One proposed next course with its direct-prerequisite coverage and inferred attribution."""

    course: CourseSummary
    required_coverage: float | None
    recommended_coverage: float | None
    depends_on_inferred: bool


@dataclass(frozen=True)
class _CoverageSlot:
    """One counted prerequisite slot: its stable key and whether the basis covers it."""

    key: str
    covered: bool


@dataclass(frozen=True)
class _Coverage:
    """One coverage fold result: canonical slots plus the count of implicit unresolved slots."""

    slots: frozenset[_CoverageSlot] = frozenset()
    unresolved: int = 0

    def union(self, other: _Coverage) -> _Coverage:
        """Union canonical slots and sum implicit unresolved positions."""
        return _Coverage(self.slots | other.slots, self.unresolved + other.unresolved)

    @property
    def denominator(self) -> int:
        """Return the coverage denominator: canonical slots plus unresolved positions."""
        return len(self.slots) + self.unresolved

    @property
    def covered(self) -> int:
        """Return the covered canonical slot count."""
        return sum(1 for slot in self.slots if slot.covered)

    @property
    def fraction(self) -> float:
        """Return covered share, or zero for an empty denominator."""
        return 0.0 if self.denominator == 0 else self.covered / self.denominator


_EMPTY_COVERAGE = _Coverage()


def _coverage(value: _Coverage) -> float | None:
    """Return the covered share, or `None` when the category holds no slot at all."""
    return None if value.denominator == 0 else value.fraction


def _ranked(fraction: float | None) -> float:
    """Return one coverage fraction for ordering, where a category without slots counts as zero."""
    return 0.0 if fraction is None else fraction


def _head_course_group_id(structure: PrerequisiteSolverStructure, piece: PrerequisitePiece) -> str:
    """Return the canonical course a course-alternative branch names."""
    pieces = {value.piece_id: value for value in structure.pieces}
    if piece.kind == "course" and piece.course_group_id is not None:
        return piece.course_group_id
    if piece.kind == "expanded_course" and piece.children:
        head = pieces[piece.children[0]]
        if head.course_group_id is not None:
            return head.course_group_id
    raise ValueError("a course-alternative branch must be headed by one canonical course")


@dataclass
class _CoverageEvaluator(PieceEvaluator[_Coverage]):
    """One course-share coverage fold over a native direct category root."""

    structure: PrerequisiteSolverStructure
    session: PrerequisiteSatisfactionSession
    owner_group_id: str
    memo: dict[str, _Coverage] | None = None

    def __post_init__(self) -> None:
        """Build the request-local piece index once."""
        PieceEvaluator.__init__(self, self.structure)
        self.memo = {}

    def evaluate(self, piece_id: str, owner_group_id: str | None = None) -> _Coverage:
        """Return one piece's memoized coverage under its owner."""
        owner = owner_group_id or self.owner_group_id
        key = f"{owner}|{piece_id}"
        cached = self.memo.get(key) if self.memo is not None else None
        if cached is not None:
            return cached
        result = PieceEvaluator.evaluate(self, piece_id, owner)
        if self.memo is not None:
            self.memo[key] = result
        return result

    def expanded_course(self, piece: PrerequisitePiece, owner_group_id: str) -> _Coverage:
        """Union an expanded course's head and descendant slots."""
        head = self.piece(piece.children[0])
        head_owner = head.course_group_id or owner_group_id
        return self.evaluate(head.piece_id, head_owner).union(
            self.evaluate(piece.children[1], head_owner)
        )

    def course(self, piece: PrerequisitePiece, owner_group_id: str) -> _Coverage:
        """Return one canonical course slot, covered only when its piece is satisfied."""
        covered = (
            self.session.evaluate(piece.piece_id, owner_group_id=owner_group_id)
            is PrerequisiteSatisfactionState.SATISFIED
        )
        return _Coverage(frozenset({_CoverageSlot(piece.course_group_id or "", covered)}))

    def unresolved(self, piece: PrerequisitePiece, owner_group_id: str) -> _Coverage:
        """Count one implicit unresolved source slot."""
        del owner_group_id
        return _Coverage(unresolved=1)

    def module_block(self, piece: PrerequisitePiece, owner_group_id: str) -> _Coverage:
        """Fold a module boundary transparently over its inlined child slots."""
        return self.evaluate(piece.children[0], owner_group_id)

    def opaque_credits(self, piece: PrerequisitePiece, owner_group_id: str) -> _Coverage:
        """Return no slot: an opaque obligation supplies no fabricated course witness."""
        del piece, owner_group_id
        return _EMPTY_COVERAGE

    def conjunction(
        self,
        piece: PrerequisitePiece,
        owner_group_id: str,
        children: tuple[_Coverage, ...],
    ) -> _Coverage:
        """Union every child's canonical slots and sum implicit unresolved positions."""
        return _union(children)

    def alternatives(
        self,
        piece: PrerequisitePiece,
        owner_group_id: str,
        children: tuple[_Coverage, ...],
    ) -> _Coverage:
        """Keep one slot for a course-alternative OR, otherwise the best-covered option."""
        if piece.kind == "course_alternatives":
            covered = (
                self.session.evaluate(piece.piece_id, owner_group_id=owner_group_id)
                is PrerequisiteSatisfactionState.SATISFIED
            )
            head = self.piece(piece.children[0])
            return _Coverage(
                frozenset({_CoverageSlot(_head_course_group_id(self.structure, head), covered)})
            )
        if not children:
            return _EMPTY_COVERAGE
        best_index = max(range(len(children)), key=lambda index: (children[index].fraction, -index))
        return children[best_index]

    def cardinality(
        self,
        piece: PrerequisitePiece,
        owner_group_id: str,
        children: tuple[_Coverage, ...],
    ) -> _Coverage:
        """Union the child slots and sum implicit unresolved positions."""
        return _union(children)

    def bounded(self, piece: PrerequisitePiece, owner_group_id: str, child: _Coverage) -> _Coverage:
        """Pass the wrapped child's coverage as-is."""
        del piece, owner_group_id
        return child


def _union(children: tuple[_Coverage, ...]) -> _Coverage:
    """Union canonical slots and sum implicit unresolved positions over child coverage."""
    result = _EMPTY_COVERAGE
    for child in children:
        result = result.union(child)
    return result


def _root_piece_id(structure: PrerequisiteSolverStructure, use_id: str | None) -> str | None:
    """Resolve one category use ID through the structure's own use table."""
    if use_id is None:
        return None
    return next(use.piece_id for use in structure.uses if use.use_id == use_id)


def _candidate_outcome(
    compilation: DirectPrerequisiteCompilation,
    basis_group_ids: frozenset[str],
    mode: NextCourseMode,
) -> tuple[float | None, float | None] | None:
    """Return one candidate's `(required, recommended)` coverage, or `None` when ineligible."""
    structure = compilation.solver
    candidate_id = structure.root_group_id
    if candidate_id in basis_group_ids:
        return None
    if not is_course_activity_eligible(structure, candidate_id, ()):
        return None
    required_piece = _root_piece_id(structure, compilation.required_use_id)
    recommended_piece = _root_piece_id(structure, compilation.recommended_use_id)
    if required_piece is None and recommended_piece is None:
        return None
    session = PrerequisiteSatisfactionSession(structure, basis_group_ids)
    evaluator = _CoverageEvaluator(
        structure=structure,
        session=session,
        owner_group_id=candidate_id,
    )
    required = (
        evaluator.evaluate(required_piece, candidate_id)
        if required_piece is not None
        else _EMPTY_COVERAGE
    )
    recommended = (
        evaluator.evaluate(recommended_piece, candidate_id)
        if recommended_piece is not None
        else _EMPTY_COVERAGE
    )
    if required.denominator == 0 and recommended.denominator == 0:
        return None
    if mode is NextCourseMode.AT_LEAST_ONE:
        if not any(slot.covered for slot in required.slots | recommended.slots):
            return None
    else:
        for piece_id in (required_piece, recommended_piece):
            if piece_id is None:
                continue
            if (
                session.evaluate(piece_id, owner_group_id=candidate_id)
                is not PrerequisiteSatisfactionState.SATISFIED
            ):
                return None
    return _coverage(required), _coverage(recommended)


def evaluate_next_course_outcomes(
    compilations: Sequence[DirectPrerequisiteCompilation],
    basis_group_ids: Collection[str],
    *,
    mode: NextCourseMode,
) -> dict[str, tuple[float | None, float | None] | None]:
    """Return one root-keyed `(required, recommended)` outcome per compilation."""
    basis = frozenset(basis_group_ids)
    return {
        compilation.solver.root_group_id: _candidate_outcome(compilation, basis, mode)
        for compilation in compilations
    }


def eligible_next_course_group_ids(
    compilations: Sequence[DirectPrerequisiteCompilation],
    basis_group_ids: Collection[str],
    *,
    mode: NextCourseMode,
    candidate_outcomes: Mapping[str, tuple[float | None, float | None] | None] | None = None,
) -> tuple[str, ...]:
    """Return the sorted canonical IDs eligible in one direct-compilation pass."""
    outcomes = (
        candidate_outcomes
        if candidate_outcomes is not None
        else evaluate_next_course_outcomes(compilations, basis_group_ids, mode=mode)
    )
    return tuple(
        sorted(
            compilation.solver.root_group_id
            for compilation in compilations
            if outcomes[compilation.solver.root_group_id] is not None
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
    """Return the ordered next-course list for one already-compiled candidate set."""
    outcomes = (
        candidate_outcomes
        if candidate_outcomes is not None
        else evaluate_next_course_outcomes(compilations, basis_group_ids, mode=mode)
    )
    official_by_root = {
        compilation.solver.root_group_id: compilation for compilation in official_compilations
    }
    official_outcomes = (
        evaluate_next_course_outcomes(official_compilations, basis_group_ids, mode=mode)
        if official_compilations
        else {}
    )
    results: list[NextCourseResult] = []
    for compilation in compilations:
        structure = compilation.solver
        candidate_id = structure.root_group_id
        outcome = outcomes[candidate_id]
        if outcome is None:
            continue
        required_coverage, recommended_coverage = outcome
        official = official_by_root.get(candidate_id)
        depends_on_inferred = official is not None and official_outcomes[candidate_id] is None
        summary = next(
            (course for course in structure.courses if course.group_id == candidate_id), None
        )
        if summary is None:
            raise ValueError(f"candidate {candidate_id} is missing from its structure courses")
        results.append(
            NextCourseResult(
                course=summary,
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
