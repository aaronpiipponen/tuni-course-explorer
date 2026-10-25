"""Shared fakes, builders, and constants for the prerequisite graph compiler tests."""

from __future__ import annotations

import functools
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueCourseVersion,
    CatalogueCurriculumPeriod,
    CatalogueModule,
    CatalogueModuleRule,
    CatalogueModuleVersion,
    CataloguePrerequisiteMember,
    CataloguePrerequisiteOption,
    CatalogueSubstitutionMember,
    CatalogueSubstitutionOption,
    CatalogueTeachingText,
    CourseSummary,
)
from course_explorer.enums import (
    InferredCoverageState,
    InferredProducerKind,
    ModuleRuleType,
    ModuleType,
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    CurrentEquivalenceGroup,
    EquivalenceGroupMember,
    InferenceNodeMetadata,
    InferredReadState,
    InferredSetCoverage,
    InferredSetReadResult,
    PrerequisiteExpression,
)
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure
from tests.prerequisite._expression_support import (
    course_summary as course_summary,
)
from tests.prerequisite._expression_support import (
    fixture_structure as _fixture_structure,
)
from tests.prerequisite._expression_support import (
    inferred_course as _shared_inferred_course,
)
from tests.prerequisite._expression_support import (
    official_course as official_course,
)

GENERATED_AT = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
INFERENCE_METADATA = InferenceNodeMetadata(confidence=Decimal("0.9"), requirement_ids=("R1",))
EMPTY_COVERAGE = InferredSetCoverage(
    eligible_source_count=0, processed_source_count=0, accepted_source_count=0
)


def course_version(
    *,
    code: str | None = None,
    credits_min: str = "5",
    credits_max: str | None = None,
    prerequisite_options: tuple[CataloguePrerequisiteOption, ...] = (),
    substitution_options: tuple[CatalogueSubstitutionOption, ...] = (),
) -> CatalogueCourseVersion:
    """Build one official course version with exactly the options under test."""
    return CatalogueCourseVersion(
        sisu_course_unit_id=f"source-{code}",
        source_hash="c" * 64,
        code=code or "TEST-100",
        name_fi=f"Kurssi {code or 'TEST-100'}",
        name_en=f"Course {code or 'TEST-100'}",
        credits_min=Decimal(credits_min),
        credits_max=None if credits_max is None else Decimal(credits_max),
        official_url=f"https://example.invalid/{code or 'TEST-100'}",
        document_state="ACTIVE",
        curriculum_period_ids=("2026-2027",),
        teaching_text=CatalogueTeachingText(),
        prerequisite_options=prerequisite_options,
        substitution_options=substitution_options,
    )


def catalogue_course(
    group_id: str,
    *,
    is_active: bool = True,
    representative: CatalogueCourseVersion | None | object = ...,
    prerequisite_options: tuple[CataloguePrerequisiteOption, ...] = (),
    substitution_options: tuple[CatalogueSubstitutionOption, ...] = (),
) -> CatalogueCourse:
    """Build one canonical course DTO, defaulting to a valid representative."""
    if representative is ...:
        representative = course_version(
            code=group_id.upper(),
            prerequisite_options=prerequisite_options,
            substitution_options=substitution_options,
        )
    return CatalogueCourse(
        group_id=group_id,
        is_active=is_active,
        activity_as_of_academic_year_start=2026,
        activity_window_years=3,
        representative=representative,
    )


def prerequisite_course_member(
    member_index: int, referenced_group_id: str
) -> CataloguePrerequisiteMember:
    """Build one course-typed official prerequisite member."""
    return CataloguePrerequisiteMember(
        member_index=member_index,
        member_type=PrerequisiteMemberType.COURSE,
        referenced_group_id=referenced_group_id,
    )


def prerequisite_module_member(
    member_index: int, referenced_group_id: str
) -> CataloguePrerequisiteMember:
    """Build one module-typed official prerequisite member."""
    return CataloguePrerequisiteMember(
        member_index=member_index,
        member_type=PrerequisiteMemberType.MODULE,
        referenced_group_id=referenced_group_id,
    )


def prerequisite_option(
    option_index: int,
    requirement_kind: PrerequisiteRequirementKind,
    *members: CataloguePrerequisiteMember,
) -> CataloguePrerequisiteOption:
    """Build one ordered official prerequisite option."""
    return CataloguePrerequisiteOption(
        option_index=option_index, requirement_kind=requirement_kind, members=members
    )


def substitution_option(
    option_index: int, *members: tuple[str, str | None]
) -> CatalogueSubstitutionOption:
    """Build one ordered directional substitution option from (group_id, credits) pairs."""
    return CatalogueSubstitutionOption(
        option_index=option_index,
        members=tuple(
            CatalogueSubstitutionMember(
                member_index=index,
                course_group_id=group_id,
                credits=None if credits is None else Decimal(credits),
            )
            for index, (group_id, credits) in enumerate(members)
        ),
    )


def module_rule(
    node_type: ModuleRuleType,
    *,
    sibling_position: int = 0,
    local_id: str | None = None,
    require_min: int | None = None,
    require_max: int | None = None,
    all_mandatory: bool | None = None,
    credits_min: str | None = None,
    credits_max: str | None = None,
    count_min: int | None = None,
    count_max: int | None = None,
    referenced_group_id: str | None = None,
    children: tuple[CatalogueModuleRule, ...] = (),
) -> CatalogueModuleRule:
    """Build one typed official module-rule node with exactly the fields under test."""
    return CatalogueModuleRule(
        node_type=node_type,
        sibling_position=sibling_position,
        local_id=local_id,
        require_min=require_min,
        require_max=require_max,
        all_mandatory=all_mandatory,
        credits_min=None if credits_min is None else Decimal(credits_min),
        credits_max=None if credits_max is None else Decimal(credits_max),
        count_min=count_min,
        count_max=count_max,
        referenced_group_id=referenced_group_id,
        children=children,
    )


def module_version(
    sisu_module_id: str,
    *,
    rule: CatalogueModuleRule | None = None,
    curriculum_periods: tuple[CatalogueCurriculumPeriod, ...] = (),
    validity_start: date | None = None,
    validity_end: date | None = None,
    module_type: ModuleType = ModuleType.STUDY_MODULE,
    target_credits_min: str | None = None,
    target_credits_max: str | None = None,
) -> CatalogueModuleVersion:
    """Build one exact official module version with explicit membership years."""
    return CatalogueModuleVersion(
        sisu_module_id=sisu_module_id,
        source_hash="d" * 64,
        module_type=module_type,
        code=None,
        name_en=f"Module {sisu_module_id}",
        document_state="ACTIVE",
        validity_start=validity_start,
        validity_end=validity_end,
        curriculum_periods=curriculum_periods,
        rule=rule,
        target_credits_min=None if target_credits_min is None else Decimal(target_credits_min),
        target_credits_max=None if target_credits_max is None else Decimal(target_credits_max),
    )


def catalogue_module(
    group_id: str, versions: tuple[CatalogueModuleVersion, ...]
) -> CatalogueModule:
    """Build one canonical module DTO sorted by exact source ID like the read seam."""
    ordered = tuple(sorted(versions, key=lambda version: version.sisu_module_id))
    return CatalogueModule(group_id=group_id, versions=ordered)


class FakeCurriculumRead:
    """Scoped `CurriculumGraphRead` implementation returning supplied DTOs and recording reads.

    The graph read requests one canonical identity per lookup, so this fake records every requested
    batch and returns only the matching supplied DTOs.
    """

    def __init__(
        self, courses: tuple[CatalogueCourse, ...], modules: tuple[CatalogueModule, ...] = ()
    ):
        self._courses = tuple(sorted(courses, key=lambda course: course.group_id))
        self._modules = modules
        self.course_reads: list[tuple[str, ...]] = []
        self.module_reads: list[tuple[str, ...]] = []

    def get_courses(self, group_ids) -> tuple[CatalogueCourse, ...]:
        """Return only the requested supplied courses, in canonical group order."""
        self.course_reads.append(tuple(group_ids))
        wanted = set(group_ids)
        return tuple(course for course in self._courses if course.group_id in wanted)

    def get_modules(self, group_ids) -> tuple[CatalogueModule, ...]:
        """Return only the requested supplied modules, in canonical group order."""
        self.module_reads.append(tuple(group_ids))
        wanted = set(group_ids)
        return tuple(module for module in self._modules if module.group_id in wanted)


class FullCatalogueFakeCurriculum(FakeCurriculumRead):
    """Scoped-read fake that answers every request with the whole catalogue.

    It exists only to prove that on-demand caching of referenced identities produces the same
    compilation as having every canonical identity preloaded.
    """

    def get_courses(self, group_ids) -> tuple[CatalogueCourse, ...]:
        """Return the whole course catalogue regardless of the requested identities."""
        self.course_reads.append(tuple(group_ids))
        return self._courses

    def get_modules(self, group_ids) -> tuple[CatalogueModule, ...]:
        """Return the whole module catalogue regardless of the requested identities."""
        self.module_reads.append(tuple(group_ids))
        return self._modules


class RecordingInferredSetRead:
    """Recording `InferredSetRead` returning configured per-target results."""

    def __init__(self, results: dict[str, InferredSetReadResult] | None = None):
        self.reads: list[str] = []
        self._results = dict(results or {})

    def read(self, target_group_id: str) -> InferredSetReadResult:
        """Record and return the configured result, defaulting to unavailable."""
        self.reads.append(target_group_id)
        return self._results.get(
            target_group_id,
            InferredSetReadResult(
                target_group_id=target_group_id, state=InferredReadState.UNAVAILABLE
            ),
        )


class RecordingEquivalenceGroupRead:
    """Recording `EquivalenceGroupRead` returning configured per-member group tuples."""

    def __init__(
        self, groups: dict[str, tuple[CurrentEquivalenceGroup, ...]] | None = None
    ) -> None:
        self.reads: list[str] = []
        self.bulk_reads: list[tuple[str, ...]] = []
        self._groups = dict(groups or {})

    def read_for_member(self, member_group_id: str) -> tuple[CurrentEquivalenceGroup, ...]:
        """Record and return the configured sorted group tuple, defaulting to empty."""
        self.reads.append(member_group_id)
        return self._groups.get(member_group_id, ())

    def read_for_members(self, member_group_ids) -> dict[str, tuple[CurrentEquivalenceGroup, ...]]:
        """Record and return only the requested keys from the configured map."""
        requested = tuple(sorted(set(member_group_ids)))
        self.bulk_reads.append(requested)
        return {group_id: self._groups.get(group_id, ()) for group_id in requested}


def equivalence_group(
    group_id: str,
    *member_group_ids: str,
    inference: InferenceNodeMetadata = INFERENCE_METADATA,
) -> CurrentEquivalenceGroup:
    """Build one stored group over sorted unique members with deterministic evidence."""
    return CurrentEquivalenceGroup(
        group_id=UUID(group_id),
        members=tuple(
            EquivalenceGroupMember(
                course_group_id=member,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
            )
            for member in sorted(member_group_ids)
        ),
        producer_kind=InferredProducerKind.TEST,
        producer_name="test-fixture",
        producer_version="1",
        input_hash="a" * 64,
        inference=inference,
        generated_at=GENERATED_AT,
        payload_hash="b" * 64,
        published_at=GENERATED_AT,
    )


def current_result(
    target_group_id: str,
    *,
    expression=None,
    coverage_state: InferredCoverageState = InferredCoverageState.COMPLETE,
    coverage: InferredSetCoverage = EMPTY_COVERAGE,
) -> InferredSetReadResult:
    """Build one current inferred read result with an explicit stored payload."""
    from course_explorer.prerequisite.domain import CurrentInferredSet

    return InferredSetReadResult(
        target_group_id=target_group_id,
        state=InferredReadState.CURRENT,
        current_set=CurrentInferredSet(
            set_id=uuid4(),
            target_group_id=target_group_id,
            activity_as_of_academic_year_start=2026,
            activity_window_years=3,
            producer_kind=InferredProducerKind.TEST,
            producer_name="test-fixture",
            producer_version="1",
            input_hash="a" * 64,
            coverage_state=coverage_state,
            coverage=coverage,
            expression=expression,
            generated_at=GENERATED_AT,
            payload_hash="b" * 64,
            published_at=GENERATED_AT,
        ),
    )


inferred_course = functools.partial(_shared_inferred_course, inference=INFERENCE_METADATA)


def make_structure(
    root: CourseSummary,
    requirements: PrerequisiteExpression | None,
    courses: tuple[CourseSummary, ...],
    *,
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    excluded_group_ids: tuple[str, ...] = (),
    completed_node_keys: tuple[str, ...] = (),
    excluded_node_keys: tuple[str, ...] = (),
    cycle_group_ids: tuple[str, ...] = (),
    coverage: tuple[object, ...] = (),
) -> PrerequisiteSolverStructure:
    """Build one native fixture structure with projector-installed bindings."""
    return _fixture_structure(
        requirements,
        root=root,
        courses=courses,
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        active_only=active_only,
        excluded_group_ids=excluded_group_ids,
        completed_node_keys=completed_node_keys,
        excluded_node_keys=excluded_node_keys,
        cycle_group_ids=cycle_group_ids,
        coverage=coverage,
    )


def piece_of(structure: PrerequisiteSolverStructure, use_id: str):
    """Return the native piece one use evaluates."""
    return next(
        piece
        for piece in structure.pieces
        if piece.piece_id == next(use.piece_id for use in structure.uses if use.use_id == use_id)
    )


def fact_of(structure: PrerequisiteSolverStructure, use_id: str):
    """Return the provenance fact one use carries."""
    fact_id = next(use.fact_id for use in structure.uses if use.use_id == use_id)
    return next(fact for fact in structure.facts if fact.fact_id == fact_id)


def child_uses(structure: PrerequisiteSolverStructure, use_id: str) -> tuple[str, ...]:
    """Return one use's ordered child use IDs."""
    return next(use.children for use in structure.uses if use.use_id == use_id)


def leaf_group_ids(structure: PrerequisiteSolverStructure, use_id: str | None) -> set[str]:
    """Return every canonical course leaf one use subtree represents."""
    leaves: set[str] = set()
    if use_id is None:
        return leaves
    stack = [use_id]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        piece = piece_of(structure, current)
        if piece.kind == "course" and piece.course_group_id is not None:
            leaves.add(piece.course_group_id)
        stack.extend(child_uses(structure, current))
    return leaves


def course_node_ids(display) -> set[str]:
    """Return every drawn canonical course group ID."""
    return {
        node.course_group_id
        for node in display.nodes
        if node.kind == "course" and node.course_group_id is not None
    }


def root_summary(structure: PrerequisiteSolverStructure) -> CourseSummary:
    """Return one structure's root course summary."""
    return next(
        course for course in structure.courses if course.group_id == structure.root_group_id
    )


def ignored_parts(structure: PrerequisiteSolverStructure):
    """Return every ignored-source diagnostic of one structure."""
    return tuple(
        diagnostic
        for diagnostic in structure.diagnostics
        if diagnostic.kind not in ("course_cycle", "module_cycle")
    )


def issues(structure: PrerequisiteSolverStructure):
    """Return every cycle diagnostic of one structure."""
    return tuple(
        diagnostic
        for diagnostic in structure.diagnostics
        if diagnostic.kind in ("course_cycle", "module_cycle")
    )


def course_nodes(display):
    """Return every drawn course node."""
    return tuple(node for node in display.nodes if node.kind == "course")


def connector_nodes(display):
    """Return every drawn connector node."""
    return tuple(node for node in display.nodes if node.kind not in ("course", "module", "ignored"))


def module_nodes(display):
    """Return every drawn module node."""
    return tuple(node for node in display.nodes if node.kind == "module")


def ignored_nodes(display):
    """Return every drawn ignored annotation."""
    return tuple(node for node in display.nodes if node.kind == "ignored")
