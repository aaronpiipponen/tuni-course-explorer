"""Read-only composition for the machine-readable next-course command.

This module owns the process-level orchestration behind `scripts/next_courses.py`. It validates
caller input before any settings load or I/O, resolves the combined
selected/completed inputs through the shared id-or-code lookup, projects a bounded candidate
superset through the discovery reads, compiles only those candidates' direct options through the
compiler, returns one transient JSON report, and lets every fail-loud service error propagate. It
writes no stored data. The validated request preparation and the report read are shared owners the
recommendation command composes over one resolved database settings value.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import get_args

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import DatabaseSettings, load_database_settings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.next_courses.report_cache import (
    NextCourseRawKey,
    NextCourseReportCache,
    NextCourseReportKey,
)
from course_explorer.next_courses.service import (
    NextCourseMode,
    NextCourseResult,
    eligible_next_course_group_ids,
    evaluate_next_course_outcomes,
    next_courses_from_compilations,
)
from course_explorer.prerequisite.commands import PrerequisiteCalculationBasis
from course_explorer.prerequisite.equivalence_repository import InferredEquivalenceRepository
from course_explorer.prerequisite.graph import PrerequisiteGraphCompiler
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from course_explorer.search.lookup import DisplayLanguage
from course_explorer.search.projection import LookupProjection
from course_explorer.search.resolver import CourseResolver


class NextCoursesReport(BaseModel):
    """One transient next-course result and its effective request policy.

    The two canonical input sets and the chosen basis are request context carried by the CLI, the
    web backend and the recommendation command. They are not stored state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_group_ids: tuple[str, ...]
    completed_group_ids: tuple[str, ...]
    basis: PrerequisiteCalculationBasis
    mode: NextCourseMode
    display_language: DisplayLanguage
    include_inferred: bool
    active_only: bool
    results: tuple[NextCourseResult, ...]


def run_next_courses_command(
    *,
    selected_courses: Collection[str] = (),
    completed_courses: Collection[str] = (),
    basis: str = "completed",
    mode: str = "all",
    display_language: DisplayLanguage,
    include_inferred: bool = False,
    active_only: bool = True,
    database_settings: DatabaseSettings | None = None,
    report_cache: NextCourseReportCache | None = None,
    projection: LookupProjection | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> NextCoursesReport:
    """Compose one next-course discovery report from the caller's selected/completed sets.

    Inputs are resolved in one bulk id-or-code lookup and deduplicated to canonical sets. A supplied
    projection answers that resolution without a database read. When no selected input is supplied
    the completed set is also the selected set. Otherwise completed must be a subset of selected. An
    empty chosen basis returns an empty report without any candidate or compiler read. The native
    fact loader reads the request's course and module facts through this process's database fact
    handle. A supplied report cache answers a repeated request of this dataset from its raw alias
    before the inputs are resolved, and from its canonical key after resolution. A supplied session
    factory carries the serving engine and is never disposed here.
    """
    inputs = prepare_next_course_inputs(
        selected_courses=selected_courses,
        completed_courses=completed_courses,
        basis=basis,
        mode=mode,
        display_language=display_language,
        include_inferred=include_inferred,
        active_only=active_only,
    )
    resolved_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    return read_next_courses(
        inputs,
        resolved_settings,
        report_cache=report_cache,
        projection=projection,
        session_factory=session_factory,
    )


@dataclass(frozen=True)
class NextCourseInputs:
    """One validated discovery request, independent of settings and database state."""

    selected_inputs: tuple[str, ...]
    completed_inputs: tuple[str, ...]
    normalized_basis: PrerequisiteCalculationBasis
    normalized_mode: NextCourseMode
    display_language: DisplayLanguage
    include_inferred: bool
    active_only: bool


def prepare_next_course_inputs(
    *,
    selected_courses: Collection[str] = (),
    completed_courses: Collection[str] = (),
    basis: str = "completed",
    mode: str = "all",
    display_language: DisplayLanguage,
    include_inferred: bool = False,
    active_only: bool = True,
) -> NextCourseInputs:
    """Validate and materialize one discovery request without loading settings or opening a database."""
    normalized_basis = PrerequisiteCalculationBasis(basis)
    normalized_mode = NextCourseMode(mode)
    if display_language not in get_args(DisplayLanguage):
        raise ValueError(f"display_language must be one of {get_args(DisplayLanguage)}")
    selected_inputs = tuple(selected_courses)
    completed_inputs = tuple(completed_courses)
    for identifier in (*selected_inputs, *completed_inputs):
        if not identifier.strip():
            raise ValueError("course identities must not be blank")
    return NextCourseInputs(
        selected_inputs=selected_inputs,
        completed_inputs=completed_inputs,
        normalized_basis=normalized_basis,
        normalized_mode=normalized_mode,
        display_language=display_language,
        include_inferred=include_inferred,
        active_only=active_only,
    )


def read_next_courses(
    inputs: NextCourseInputs,
    database_settings: DatabaseSettings,
    *,
    report_cache: NextCourseReportCache | None = None,
    projection: LookupProjection | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> NextCoursesReport:
    """Read one discovery report over the supplied database settings under the validated inputs."""
    selected_inputs = inputs.selected_inputs
    completed_inputs = inputs.completed_inputs
    normalized_basis = inputs.normalized_basis
    normalized_mode = inputs.normalized_mode
    display_language = inputs.display_language
    include_inferred = inputs.include_inferred
    active_only = inputs.active_only
    raw_key = NextCourseRawKey(
        selected_inputs=selected_inputs,
        completed_inputs=completed_inputs,
        basis=normalized_basis,
        mode=normalized_mode,
        display_language=display_language,
        include_inferred=include_inferred,
        active_only=active_only,
    )
    if report_cache is not None:
        retained = report_cache.get_raw(raw_key)
        if retained is not None:
            return retained
    with _database_context(database_settings, factory=session_factory) as factory:
        curriculum = CurriculumRepository(factory)
        resolver = CourseResolver(curriculum, projection=projection)
        resolved = resolver.resolve_courses((*selected_inputs, *completed_inputs))
        selected_slice = resolved[: len(selected_inputs)]
        completed_slice = resolved[len(selected_inputs) :]
        canonical_selected = tuple(sorted({record.summary.group_id for record in selected_slice}))
        canonical_completed = tuple(sorted({record.summary.group_id for record in completed_slice}))
        if selected_inputs:
            offenders = sorted(set(canonical_completed) - set(canonical_selected))
            if offenders:
                raise ValueError(f"completed courses must be selected: {', '.join(offenders)}")
            effective_selected = canonical_selected
        else:
            effective_selected = canonical_completed
        chosen = (
            effective_selected
            if normalized_basis is PrerequisiteCalculationBasis.SELECTED
            else canonical_completed
        )
        report_key = (
            None
            if report_cache is None
            else NextCourseReportKey(
                selected_group_ids=effective_selected,
                completed_group_ids=canonical_completed,
                basis=normalized_basis,
                mode=normalized_mode,
                display_language=display_language,
                include_inferred=include_inferred,
                active_only=active_only,
            )
        )
        if report_cache is not None:
            cached = report_cache.get(report_key)
            if cached is not None:
                return cached
        results: tuple[NextCourseResult, ...] = ()
        if chosen:
            inferred_sets = InferredPrerequisiteRepository(factory)
            equivalence_groups = InferredEquivalenceRepository(factory)
            from course_explorer.prerequisite import native_compiler, native_handle

            compiler = PrerequisiteGraphCompiler(
                native_handle=native_handle.worker_handle(database_settings)
            )
            source_ids = set(chosen)
            if include_inferred:
                basis_equivalence = equivalence_groups.read_for_members(chosen)
                for member_group_id in chosen:
                    for group in basis_equivalence[member_group_id]:
                        for member in group.members:
                            source_ids.add(member.course_group_id)
            source_ids.update(curriculum.get_substitution_source_group_ids(source_ids))
            candidate_ids = set(
                curriculum.get_prerequisite_candidate_group_ids(source_ids, active_only=active_only)
            )
            if include_inferred:
                candidate_ids |= set(inferred_sets.find_candidate_group_ids(source_ids))
            candidate_ids -= set(chosen)
            first_pass = compiler.compile_direct_many(
                candidate_ids,
                include_inferred=include_inferred,
                active_only=active_only,
                retained_group_ids=chosen,
            )
            try:
                first_pass_outcomes = evaluate_next_course_outcomes(
                    first_pass, chosen, mode=normalized_mode
                )
                if include_inferred:
                    eligible_ids = eligible_next_course_group_ids(
                        first_pass,
                        chosen,
                        mode=normalized_mode,
                        candidate_outcomes=first_pass_outcomes,
                    )
                    official_pass = compiler.compile_direct_many(
                        eligible_ids,
                        include_inferred=False,
                        active_only=active_only,
                        retained_group_ids=chosen,
                    )
                    try:
                        results = next_courses_from_compilations(
                            first_pass,
                            chosen,
                            mode=normalized_mode,
                            display_language=display_language,
                            official_compilations=official_pass,
                            candidate_outcomes=first_pass_outcomes,
                        )
                    finally:
                        native_compiler.close_compilations(official_pass)
                else:
                    results = next_courses_from_compilations(
                        first_pass,
                        chosen,
                        mode=normalized_mode,
                        display_language=display_language,
                        candidate_outcomes=first_pass_outcomes,
                    )
            finally:
                native_compiler.close_compilations(first_pass)
    report = NextCoursesReport(
        selected_group_ids=effective_selected,
        completed_group_ids=canonical_completed,
        basis=normalized_basis,
        mode=normalized_mode,
        display_language=display_language,
        include_inferred=include_inferred,
        active_only=active_only,
        results=results,
    )
    if report_cache is not None:
        report_cache.put_raw(raw_key, report_key, report)
    return report
