"""Seed synthetic catalogue DTOs into the disposable database for native compiler tests.

The native prerequisite compiler reads its facts through libpq. These helpers translate the test DTO
builders into the owning normalized tables, so a contract test exercises the native loader, compiler
and materializer.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select

from course_explorer.config import load_database_settings
from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueModule,
    CatalogueModuleRule,
)
from course_explorer.db.models import (
    Course,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    InferredEquivalenceGroup,
    InferredEquivalenceGroupMember,
    InferredPrerequisiteSet,
    IngestionRun,
    Module,
    ModuleRuleNode,
    ModuleVersion,
    ModuleVersionCurriculumPeriod,
    OfficialPrerequisiteOption,
    OfficialPrerequisiteOptionMember,
    OfficialSubstitutionOption,
    OfficialSubstitutionOptionMember,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import IngestionRunStatus, SourceObjectType
from course_explorer.prerequisite import native_compiler, native_handle
from course_explorer.prerequisite.domain import (
    CurrentEquivalenceGroup,
    InferredReadState,
    InferredSetReadResult,
)
from course_explorer.prerequisite.graph import PrerequisiteGraphCompiler
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
)


def _period_year(period_id: str) -> int:
    """Return the academic year a fixture period ID names, defaulting to the fixture year."""
    prefix = period_id.split("-", 1)[0]
    return int(prefix) if prefix.isdigit() else 2026


def _ensure_period(session, period_id: str, year: int) -> None:
    """Insert one curriculum period identity when the fixture has not created it."""
    if session.get(CurriculumPeriod, period_id) is None:
        session.add(CurriculumPeriod(id=period_id, academic_year_start=year))


def _snapshot(session, object_type: SourceObjectType, ordinal: int) -> SourceSnapshot:
    """Insert one provenance snapshot required by a version row."""
    run = session.scalar(select(IngestionRun).limit(1))
    if run is None:
        run = IngestionRun(
            status=IngestionRunStatus.COMPLETED,
            raw_root_path="/tmp/native-fixture",
            manifest_path="/tmp/native-fixture/manifest.json",
        )
        session.add(run)
        session.flush()
    identity = uuid4()
    snapshot = SourceSnapshot(
        ingestion_run_id=run.id,
        object_type=object_type,
        source_object_id=f"fixture-{object_type.value}-{identity}",
        response_path=f"/fixture/{object_type.value}/{identity}",
        response_item_index=0,
        source_hash=f"{ordinal:064x}",
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _clear_course(session, group_id: str) -> None:
    """Delete one canonical course and its version and official structures."""
    course = session.scalar(select(Course).where(Course.group_id == group_id))
    if course is None:
        return
    session.execute(delete(CourseVersion).where(CourseVersion.course_id == course.id))
    session.execute(delete(Course).where(Course.id == course.id))


def _clear_module(session, group_id: str) -> None:
    """Delete one canonical module and its versions, periods and rule nodes."""
    module = session.scalar(select(Module).where(Module.group_id == group_id))
    if module is None:
        return
    session.execute(delete(ModuleVersion).where(ModuleVersion.module_id == module.id))
    session.execute(delete(Module).where(Module.id == module.id))


def _seed_course(session, course: CatalogueCourse, ordinal: int) -> None:
    """Insert one canonical course, its representative and its official structures."""
    _clear_course(session, course.group_id)
    row = Course(
        group_id=course.group_id,
        first_listed_academic_year_start=course.first_listed_academic_year_start,
        last_listed_academic_year_start=course.last_listed_academic_year_start,
        is_active=course.is_active,
        activity_as_of_academic_year_start=course.activity_as_of_academic_year_start,
        activity_window_years=course.activity_window_years,
    )
    session.add(row)
    session.flush()
    version = course.representative
    if version is None:
        return
    period_ids = version.curriculum_period_ids or ("2026-2027",)
    for period_id in period_ids:
        _ensure_period(session, period_id, _period_year(period_id))
    snapshot = _snapshot(session, SourceObjectType.COURSE_UNIT, ordinal)
    version_row = CourseVersion(
        course_id=row.id,
        sisu_course_unit_id=version.sisu_course_unit_id,
        code=version.code,
        name_fi=version.name_fi,
        name_en=version.name_en,
        credits_min=version.credits_min,
        credits_max=version.credits_max,
        official_url=version.official_url,
        document_state=version.document_state,
        validity_start=version.validity_start,
        validity_end=version.validity_end,
        source_snapshot_id=snapshot.id,
    )
    session.add(version_row)
    session.flush()
    for period_id in period_ids:
        session.add(
            CourseVersionCurriculumPeriod(
                course_version_id=version_row.id, curriculum_period_id=period_id
            )
        )
    for option in version.prerequisite_options:
        option_row = OfficialPrerequisiteOption(
            target_course_version_id=version_row.id,
            option_index=option.option_index,
            requirement_kind=option.requirement_kind,
        )
        session.add(option_row)
        session.flush()
        for member in option.members:
            session.add(
                OfficialPrerequisiteOptionMember(
                    prerequisite_option_id=option_row.id,
                    member_index=member.member_index,
                    member_type=member.member_type,
                    referenced_group_id=member.referenced_group_id,
                )
            )
    for option in version.substitution_options:
        option_row = OfficialSubstitutionOption(
            source_course_version_id=version_row.id,
            option_index=option.option_index,
        )
        session.add(option_row)
        session.flush()
        for member in option.members:
            session.add(
                OfficialSubstitutionOptionMember(
                    substitution_option_id=option_row.id,
                    member_index=member.member_index,
                    course_group_id=member.course_group_id,
                    credits=member.credits,
                )
            )


def _seed_rule(session, version_id, rule: CatalogueModuleRule, parent_id, ordinal: int) -> None:
    """Insert one module rule tree under an exact module version."""
    row = ModuleRuleNode(
        module_version_id=version_id,
        parent_node_id=parent_id,
        sibling_position=rule.sibling_position,
        local_id=rule.local_id,
        node_type=rule.node_type,
        require_min=rule.require_min,
        require_max=rule.require_max,
        all_mandatory=rule.all_mandatory,
        description=rule.description,
        credits_min=rule.credits_min,
        credits_max=rule.credits_max,
        count_min=rule.count_min,
        count_max=rule.count_max,
        referenced_group_id=rule.referenced_group_id,
    )
    session.add(row)
    session.flush()
    for child in rule.children:
        _seed_rule(session, version_id, child, row.id, ordinal)


def _seed_module(session, module: CatalogueModule, ordinal: int) -> None:
    """Insert one canonical module, its versions, periods and rule trees."""
    _clear_module(session, module.group_id)
    row = Module(group_id=module.group_id)
    session.add(row)
    session.flush()
    for version in module.versions:
        for period in version.curriculum_periods:
            _ensure_period(session, period.id, period.academic_year_start)
        snapshot = _snapshot(session, SourceObjectType.MODULE, ordinal)
        version_row = ModuleVersion(
            module_id=row.id,
            sisu_module_id=version.sisu_module_id,
            module_type=version.module_type,
            code=version.code,
            name_fi=version.name_fi,
            name_en=version.name_en,
            target_credits_min=version.target_credits_min,
            target_credits_max=version.target_credits_max,
            document_state=version.document_state,
            validity_start=version.validity_start,
            validity_end=version.validity_end,
            source_snapshot_id=snapshot.id,
        )
        session.add(version_row)
        session.flush()
        for period in version.curriculum_periods:
            session.add(
                ModuleVersionCurriculumPeriod(
                    module_version_id=version_row.id, curriculum_period_id=period.id
                )
            )
        if version.rule is not None:
            _seed_rule(session, version_row.id, version.rule, None, ordinal)
        ordinal += 1


def _seed_inferred(session, results: dict[str, InferredSetReadResult]) -> None:
    """Insert every current inferred set the fixture supplies."""
    for result in results.values():
        if result.state is not InferredReadState.CURRENT or result.current_set is None:
            continue
        current = result.current_set
        target = session.scalar(select(Course).where(Course.group_id == result.target_group_id))
        if target is None:
            target = Course(
                group_id=result.target_group_id,
                is_active=True,
                activity_as_of_academic_year_start=current.activity_as_of_academic_year_start,
                activity_window_years=current.activity_window_years,
            )
            session.add(target)
            session.flush()
        if (
            session.scalar(
                select(InferredPrerequisiteSet).where(
                    InferredPrerequisiteSet.target_course_id == target.id
                )
            )
            is not None
        ):
            continue
        expression = (
            None if current.expression is None else current.expression.model_dump(mode="json")
        )
        eligible = current.coverage.eligible_source_count
        processed = current.coverage.processed_source_count
        accepted = current.coverage.accepted_source_count
        if expression is not None:
            accepted = max(accepted, 1)
            processed = max(processed, accepted)
            eligible = max(eligible, processed)
        session.add(
            InferredPrerequisiteSet(
                target_course_id=target.id,
                activity_as_of_academic_year_start=current.activity_as_of_academic_year_start,
                activity_window_years=current.activity_window_years,
                coverage_state=current.coverage_state,
                eligible_source_count=eligible,
                processed_source_count=processed,
                accepted_source_count=accepted,
                producer_kind=current.producer_kind,
                producer_name=current.producer_name,
                producer_version=current.producer_version,
                input_hash=current.input_hash,
                payload_hash=current.payload_hash,
                expression=expression,
                generated_at=current.generated_at,
                published_at=current.published_at,
            )
        )


def _seed_equivalence(session, groups: dict[str, tuple[CurrentEquivalenceGroup, ...]]) -> None:
    """Insert every current inferred equivalence group the fixture supplies."""
    for member_groups in groups.values():
        for group in member_groups:
            if session.get(InferredEquivalenceGroup, group.group_id) is not None:
                continue
            session.add(
                InferredEquivalenceGroup(
                    id=group.group_id,
                    producer_kind=group.producer_kind,
                    producer_name=group.producer_name,
                    producer_version=group.producer_version,
                    input_hash=group.input_hash,
                    payload_hash=group.payload_hash,
                    inference=group.inference.model_dump(mode="json"),
                    generated_at=group.generated_at,
                    published_at=group.published_at,
                )
            )
            session.flush()
            for member in group.members:
                course = session.scalar(
                    select(Course).where(Course.group_id == member.course_group_id)
                )
                if course is None:
                    course = Course(
                        group_id=member.course_group_id,
                        is_active=True,
                        activity_as_of_academic_year_start=(
                            member.activity_as_of_academic_year_start
                        ),
                        activity_window_years=member.activity_window_years,
                    )
                    session.add(course)
                    session.flush()
                session.add(
                    InferredEquivalenceGroupMember(
                        equivalence_group_id=group.group_id,
                        course_id=course.id,
                        activity_as_of_academic_year_start=(
                            member.activity_as_of_academic_year_start
                        ),
                        activity_window_years=member.activity_window_years,
                    )
                )


def seed_native_facts(
    factory: object,
    curriculum: FakeCurriculumRead,
    inferred: RecordingInferredSetRead | None = None,
    equivalence: RecordingEquivalenceGroupRead | None = None,
) -> None:
    """Insert one fixture catalogue and its inferred facts into the disposable database."""
    with session_scope(factory) as session:
        session.execute(delete(InferredPrerequisiteSet))
        session.execute(delete(InferredEquivalenceGroup))
        ordinal = 1
        for course in sorted(curriculum.courses, key=lambda item: item.group_id):
            _seed_course(session, course, ordinal)
            ordinal += 1
        for module in curriculum.modules:
            _seed_module(session, module, ordinal)
            ordinal += 1
        if inferred is not None:
            _seed_inferred(session, inferred.results)
        if equivalence is not None:
            _seed_equivalence(session, equivalence.groups)


def reset_worker_handle() -> None:
    """Close and forget this process's cached fact handle after a seeded database changes."""
    native_handle.reset_worker_handle()


def open_native_compiler(factory: object) -> PrerequisiteGraphCompiler:
    """Open one compiler handle against the configured disposable database."""
    settings = load_database_settings()
    if not settings.postgres_db.endswith("_test"):
        raise ValueError("native compiler tests require a _test database")
    handle = native_handle.open_database(native_handle.database_conninfo(settings))
    return PrerequisiteGraphCompiler(native_handle=handle)


def close_native_compiler(compiler: PrerequisiteGraphCompiler) -> None:
    """Close one compiler's database fact handle."""
    handle = getattr(compiler, "_native_handle", None)
    if handle is not None:
        native_handle.close_database(handle)


def native_compiler_for(
    factory: object,
    curriculum: FakeCurriculumRead,
    inferred: RecordingInferredSetRead | None = None,
    equivalence: RecordingEquivalenceGroupRead | None = None,
) -> PrerequisiteGraphCompiler:
    """Seed one fixture catalogue and return a compiler over the native fact loader."""
    seed_native_facts(factory, curriculum, inferred, equivalence)
    return open_native_compiler(factory)


def native_requirement_state(
    compiler: PrerequisiteGraphCompiler,
    target_group_id: str,
    basis_group_ids: tuple[str, ...],
    *,
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    retained_group_ids: tuple[str, ...] = (),
) -> str:
    """Return one full structure's native eligibility state for a fixed basis."""
    handle = getattr(compiler, "_native_handle")
    bundle = native_compiler._compile(
        handle,
        (target_group_id,),
        retained_group_ids,
        active_only=active_only,
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        direct_only=False,
        excluded=(),
        completed=(),
        excluded_keys=(),
    )
    try:
        solver = bundle.structures[0].solver
        if solver.root_use_id is None:
            return "satisfied"
        outcome = bundle.evaluate(tuple(basis_group_ids), mode=0)[0]
        return "satisfied" if outcome.has_outcome else "unsatisfied"
    finally:
        bundle.close()
