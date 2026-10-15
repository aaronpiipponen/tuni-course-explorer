"""Read-only repository for detached official curriculum catalogue DTOs.

It owns the bulk catalogue reads, one projected represented-summary read, and the scoped
identity getters graph compilation uses. Every read shares a private loader with the bulk
variant and differs only by projection or identity filter.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Sequence
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueCourseActivity,
    CatalogueCourseVersion,
    CatalogueCurriculumPeriod,
    CatalogueModule,
    CatalogueModuleLookup,
    CatalogueModuleRule,
    CatalogueModuleVersion,
    CatalogueModuleVersionIdentity,
    CataloguePrerequisiteMember,
    CataloguePrerequisiteOption,
    CatalogueRepresentativeTeachingText,
    CatalogueSubstitutionMember,
    CatalogueSubstitutionOption,
    CatalogueSummary,
    CatalogueTeachingCourse,
    CatalogueTeachingCourseVersion,
    CatalogueTeachingText,
    CatalogueTeachingTextInput,
    CourseSummary,
    CurriculumDiscoveryRead,
    CurriculumRead,
    CurriculumStructureRead,
    RepresentedCourseSummary,
    course_summary_from_fields,
    is_within_activity_window,
)
from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
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
from course_explorer.enums import ModuleRuleType, PrerequisiteMemberType


def _require_representative_versions(
    representative_ids: Collection[str], found_ids: Collection[str]
) -> None:
    """Fail loudly when a selected representative has no persisted version row.

    Both course reads resolve a representative identity before loading any version data, so this one
    guard keeps their identical missing-representative error in a single place.
    """
    missing = set(representative_ids) - set(found_ids)
    if missing:
        raise ValueError(f"representative course versions are missing: {sorted(missing)}")


def select_representative_source_ids(
    session: Session,
    group_ids: Collection[str],
    *,
    current_academic_year_start: int,
    activity_window_years: int,
) -> dict[str, str | None]:
    """Rank each version's eligible membership by year, retaining one best candidate per course."""
    result = {group_id: None for group_id in group_ids}
    if not group_ids:
        return result
    rows = session.execute(
        select(
            Course.group_id,
            CourseVersion.sisu_course_unit_id,
            CourseVersion.source_modification_ordinal,
            func.max(CurriculumPeriod.academic_year_start),
        )
        .join(CourseVersion, CourseVersion.course_id == Course.id)
        .join(
            CourseVersionCurriculumPeriod,
            CourseVersionCurriculumPeriod.course_version_id == CourseVersion.id,
        )
        .join(
            CurriculumPeriod,
            CurriculumPeriod.id == CourseVersionCurriculumPeriod.curriculum_period_id,
        )
        .where(
            Course.group_id.in_(group_ids),
            CurriculumPeriod.academic_year_start <= current_academic_year_start,
        )
        .group_by(
            Course.group_id,
            CourseVersion.sisu_course_unit_id,
            CourseVersion.source_modification_ordinal,
        )
    )
    best_by_group: dict[str, tuple[tuple[int, int], int, str]] = {}
    for group_id, source_id, ordinal, year in rows:
        if year == current_academic_year_start:
            rank = (2, year)
        elif is_within_activity_window(
            year,
            current_academic_year_start=current_academic_year_start,
            activity_window_years=activity_window_years,
        ):
            rank = (1, year)
        else:
            rank = (0, year)
        candidate = (rank, -1 if ordinal is None else ordinal, source_id)
        previous = best_by_group.get(group_id)
        if previous is None or candidate > previous:
            best_by_group[group_id] = candidate
            result[group_id] = source_id
    return result


class _RepresentativeActivityContext(Protocol):
    """The three canonical columns the shared representative selector actually consumes."""

    group_id: str
    activity_as_of_academic_year_start: int
    activity_window_years: int


def _representative_teaching_texts(
    session: Session,
    selected_ids: Collection[str],
    *,
    include_identity: bool = False,
) -> dict[str, CatalogueRepresentativeTeachingText | CatalogueTeachingCourseVersion]:
    """Load official representative identity/teaching text for exact selected source IDs.

    This is the one selected-source projection shared by every representative teaching read. The
    default read selects only the requested source IDs' identity, name, and official
    content/outcomes columns. ``include_identity`` adds the selected representative's source hash
    and code through the snapshot join for consumers that compare those identities. A selected
    representative with no persisted version row fails loudly.
    """
    source_ids = tuple(dict.fromkeys(selected_ids))
    if not source_ids:
        return {}
    columns: list[Any] = [
        CourseVersion.sisu_course_unit_id,
        CourseVersion.name_fi,
        CourseVersion.name_en,
        CourseText.content_fi,
        CourseText.content_en,
        CourseText.outcomes_fi,
        CourseText.outcomes_en,
    ]
    if include_identity:
        columns[1:1] = [SourceSnapshot.source_hash, CourseVersion.code]
    statement = (
        select(*columns)
        .outerjoin(CourseText, CourseText.course_version_id == CourseVersion.id)
        .where(CourseVersion.sisu_course_unit_id.in_(source_ids))
        .order_by(CourseVersion.sisu_course_unit_id)
    )
    if include_identity:
        statement = statement.join(
            SourceSnapshot, SourceSnapshot.id == CourseVersion.source_snapshot_id
        )
    by_source_id: dict[
        str, CatalogueRepresentativeTeachingText | CatalogueTeachingCourseVersion
    ] = {}
    for row in session.execute(statement):
        common = {
            "sisu_course_unit_id": row.sisu_course_unit_id,
            "name_fi": row.name_fi,
            "name_en": row.name_en,
            "teaching_text": CatalogueTeachingText(
                content_fi=row.content_fi,
                content_en=row.content_en,
                outcomes_fi=row.outcomes_fi,
                outcomes_en=row.outcomes_en,
            ),
        }
        if include_identity:
            by_source_id[row.sisu_course_unit_id] = CatalogueTeachingCourseVersion(
                **common, source_hash=row.source_hash, code=row.code
            )
        else:
            by_source_id[row.sisu_course_unit_id] = CatalogueRepresentativeTeachingText(**common)
    _require_representative_versions(source_ids, by_source_id)
    return by_source_id


class CurriculumRepository(CurriculumRead, CurriculumStructureRead, CurriculumDiscoveryRead):
    """Load canonical official curriculum data through fixed, shared-loader read queries only."""

    def __init__(self, factory: sessionmaker[Session]):
        self._factory = factory

    def list_courses(self, *, active_only: bool | None = None) -> tuple[CatalogueCourse, ...]:
        """Return detached canonical courses and computed official representatives."""
        with self._factory() as session:
            return self._load_courses(session, active_only=active_only, group_ids=None)

    def list_teaching_courses(
        self, *, active_only: bool | None = None
    ) -> tuple[CatalogueTeachingCourse, ...]:
        """Return canonical activity context with each selected representative's teaching text."""
        with self._factory() as session:
            return self._load_courses(
                session, active_only=active_only, group_ids=None, teaching_only=True
            )

    def get_courses(self, group_ids: Collection[str]) -> tuple[CatalogueCourse, ...]:
        """Return only the requested canonical courses and their selected representatives."""
        if not group_ids:
            return ()
        with self._factory() as session:
            return self._load_courses(session, active_only=None, group_ids=group_ids)

    def get_substitution_source_group_ids(
        self, member_group_ids: Collection[str]
    ) -> tuple[str, ...]:
        """Return canonical sources whose substitution option names a requested member course.

        One bounded reverse read over the stored official substitution rows: a source course is
        selected when any of its options' member `course_group_id` values is requested. This is a
        candidate superset across stored versions, not completion state: the compiler decides
        whether a substitution actually satisfies the original requirement.
        """
        requested = {group_id for group_id in member_group_ids if group_id}
        if not requested:
            return ()
        with self._factory() as session:
            return tuple(
                session.scalars(
                    select(Course.group_id)
                    .join(CourseVersion, CourseVersion.course_id == Course.id)
                    .join(
                        OfficialSubstitutionOption,
                        OfficialSubstitutionOption.source_course_version_id == CourseVersion.id,
                    )
                    .join(
                        OfficialSubstitutionOptionMember,
                        OfficialSubstitutionOptionMember.substitution_option_id
                        == OfficialSubstitutionOption.id,
                    )
                    .where(OfficialSubstitutionOptionMember.course_group_id.in_(requested))
                    .distinct()
                    .order_by(Course.group_id)
                )
            )

    def get_prerequisite_candidate_group_ids(
        self, source_group_ids: Collection[str], *, active_only: bool
    ) -> tuple[str, ...]:
        """Return canonical targets whose official prerequisite option references a source.

        A target is selected when its stored option has a course member naming one of the requested
        source identities, or a module member naming a module that can contain one. The module
        membership superset is one recursive CTE seeded from course-unit rule references and closed
        over containing module-rule references with `UNION` (distinct), so cycles terminate. Stored
        versions may overselect. The current compiler alone decides real eligibility.
        """
        requested = {group_id for group_id in source_group_ids if group_id}
        if not requested:
            return ()
        with self._factory() as session:
            module_scope = (
                select(Module.group_id.label("group_id"))
                .join(ModuleVersion, ModuleVersion.module_id == Module.id)
                .join(ModuleRuleNode, ModuleRuleNode.module_version_id == ModuleVersion.id)
                .where(
                    ModuleRuleNode.node_type == ModuleRuleType.COURSE_UNIT_RULE,
                    ModuleRuleNode.referenced_group_id.in_(requested),
                )
                .cte("module_scope", recursive=True)
            )
            containing = (
                select(Module.group_id.label("group_id"))
                .join(ModuleVersion, ModuleVersion.module_id == Module.id)
                .join(ModuleRuleNode, ModuleRuleNode.module_version_id == ModuleVersion.id)
                .where(
                    ModuleRuleNode.node_type == ModuleRuleType.MODULE_RULE,
                    ModuleRuleNode.referenced_group_id == module_scope.c.group_id,
                )
            )
            module_scope = module_scope.union(containing)
            statement = (
                select(Course.group_id)
                .join(CourseVersion, CourseVersion.course_id == Course.id)
                .join(
                    OfficialPrerequisiteOption,
                    OfficialPrerequisiteOption.target_course_version_id == CourseVersion.id,
                )
                .join(
                    OfficialPrerequisiteOptionMember,
                    OfficialPrerequisiteOptionMember.prerequisite_option_id
                    == OfficialPrerequisiteOption.id,
                )
                .where(
                    or_(
                        (
                            OfficialPrerequisiteOptionMember.member_type
                            == PrerequisiteMemberType.COURSE
                        )
                        & (OfficialPrerequisiteOptionMember.referenced_group_id.in_(requested)),
                        (
                            OfficialPrerequisiteOptionMember.member_type
                            == PrerequisiteMemberType.MODULE
                        )
                        & (
                            OfficialPrerequisiteOptionMember.referenced_group_id.in_(
                                select(module_scope.c.group_id)
                            )
                        ),
                    )
                )
                .distinct()
                .order_by(Course.group_id)
            )
            if active_only:
                statement = statement.where(Course.is_active.is_(True))
            return tuple(session.scalars(statement))

    def get_course_activities(
        self, group_ids: Collection[str]
    ) -> tuple[CatalogueCourseActivity, ...]:
        """Return only the four activity columns for the requested canonical courses.

        Publication and group reconciliation need canonical identity, active state, and the live
        activity context, so this read projects exactly those columns instead of
        materializing full courses and representatives. Requested identities absent from the
        database are omitted and the caller validates the resulting coverage.
        """
        requested = {group_id for group_id in group_ids if group_id}
        if not requested:
            return ()
        with self._factory() as session:
            return self._scoped_courses(
                session, active_only=None, group_ids=requested, teaching_only=True
            )

    def _scoped_courses(
        self,
        session: Session,
        *,
        active_only: bool | None,
        group_ids: Collection[str] | None,
        teaching_only: bool = False,
    ) -> tuple[Course, ...] | tuple[CatalogueCourseActivity, ...]:
        """Select canonical course rows under the one shared activity and identity scope.

        The full read selects whole canonical rows. ``teaching_only`` selects the four
        activity/identity columns a teaching-text consumer needs, keeping one filter/order builder.
        """
        if teaching_only:
            statement = select(
                Course.group_id,
                Course.is_active,
                Course.activity_as_of_academic_year_start,
                Course.activity_window_years,
            )
        else:
            statement = select(Course)
        statement = statement.order_by(Course.group_id)
        if active_only is not None:
            statement = statement.where(Course.is_active == active_only)
        if group_ids is not None:
            statement = statement.where(Course.group_id.in_(group_ids))
        if teaching_only:
            return tuple(
                CatalogueCourseActivity(
                    group_id=group_id,
                    is_active=is_active,
                    activity_as_of_academic_year_start=year,
                    activity_window_years=window,
                )
                for group_id, is_active, year, window in session.execute(statement)
            )
        return tuple(session.scalars(statement))

    def _load_courses(
        self,
        session: Session,
        *,
        active_only: bool | None,
        group_ids: Collection[str] | None,
        teaching_only: bool = False,
    ) -> tuple[CatalogueCourse, ...] | tuple[CatalogueTeachingCourse, ...]:
        """Assemble detached canonical courses under an optional activity and identity scope.

        The full read returns every official structure. ``teaching_only`` returns the
        activity context plus the selected representative's identity/hash/code/names/teaching text
        through the shared selector and the selected-source projection.
        """
        courses = self._scoped_courses(
            session, active_only=active_only, group_ids=group_ids, teaching_only=teaching_only
        )
        representatives = self._representative_source_ids(session, courses)
        representative_ids = tuple(
            source_id for source_id in representatives.values() if source_id is not None
        )
        if teaching_only:
            versions = (
                _representative_teaching_texts(session, representative_ids, include_identity=True)
                if representative_ids
                else {}
            )
            return tuple(
                CatalogueTeachingCourse(
                    group_id=course.group_id,
                    is_active=course.is_active,
                    activity_as_of_academic_year_start=course.activity_as_of_academic_year_start,
                    activity_window_years=course.activity_window_years,
                    representative=(
                        None
                        if representatives[course.group_id] is None
                        else versions[representatives[course.group_id]]
                    ),
                )
                for course in courses
            )
        return self._assemble_full_courses(session, courses, representatives, representative_ids)

    def _assemble_full_courses(
        self,
        session: Session,
        courses: Sequence[Course],
        representatives: dict[str, str | None],
        representative_ids: tuple[str, ...],
    ) -> tuple[CatalogueCourse, ...]:
        """Assemble full canonical courses, all official structures included."""
        if not representative_ids:
            return tuple(
                CatalogueCourse(
                    group_id=course.group_id,
                    first_listed_academic_year_start=course.first_listed_academic_year_start,
                    last_listed_academic_year_start=course.last_listed_academic_year_start,
                    is_active=course.is_active,
                    activity_as_of_academic_year_start=course.activity_as_of_academic_year_start,
                    activity_window_years=course.activity_window_years,
                    representative=None,
                )
                for course in courses
            )

        version_rows = tuple(
            session.execute(
                select(CourseVersion, SourceSnapshot, CourseText)
                .join(SourceSnapshot, SourceSnapshot.id == CourseVersion.source_snapshot_id)
                .outerjoin(CourseText, CourseText.course_version_id == CourseVersion.id)
                .where(CourseVersion.sisu_course_unit_id.in_(representative_ids))
                .order_by(CourseVersion.sisu_course_unit_id)
            )
        )
        versions_by_source: dict[str, tuple[CourseVersion, SourceSnapshot, CourseText | None]] = {
            version.sisu_course_unit_id: (version, snapshot, text)
            for version, snapshot, text in version_rows
        }
        _require_representative_versions(representative_ids, versions_by_source)
        version_ids = tuple(version.id for version, _, _ in version_rows)

        period_rows = tuple(
            session.scalars(
                select(CourseVersionCurriculumPeriod)
                .where(CourseVersionCurriculumPeriod.course_version_id.in_(version_ids))
                .order_by(
                    CourseVersionCurriculumPeriod.course_version_id,
                    CourseVersionCurriculumPeriod.curriculum_period_id,
                )
            )
        )
        periods_by_version: dict[UUID, list[str]] = defaultdict(list)
        for row in period_rows:
            periods_by_version[row.course_version_id].append(row.curriculum_period_id)

        prerequisite_rows = tuple(
            session.execute(
                select(OfficialPrerequisiteOption, OfficialPrerequisiteOptionMember)
                .outerjoin(
                    OfficialPrerequisiteOptionMember,
                    OfficialPrerequisiteOptionMember.prerequisite_option_id
                    == OfficialPrerequisiteOption.id,
                )
                .where(OfficialPrerequisiteOption.target_course_version_id.in_(version_ids))
                .order_by(
                    OfficialPrerequisiteOption.target_course_version_id,
                    OfficialPrerequisiteOption.requirement_kind,
                    OfficialPrerequisiteOption.option_index,
                    OfficialPrerequisiteOptionMember.member_index,
                )
            )
        )
        prerequisite_by_version = _group_prerequisites(prerequisite_rows)

        substitution_rows = tuple(
            session.execute(
                select(OfficialSubstitutionOption, OfficialSubstitutionOptionMember)
                .outerjoin(
                    OfficialSubstitutionOptionMember,
                    OfficialSubstitutionOptionMember.substitution_option_id
                    == OfficialSubstitutionOption.id,
                )
                .where(OfficialSubstitutionOption.source_course_version_id.in_(version_ids))
                .order_by(
                    OfficialSubstitutionOption.source_course_version_id,
                    OfficialSubstitutionOption.option_index,
                    OfficialSubstitutionOptionMember.member_index,
                )
            )
        )
        substitution_by_version = _group_substitutions(substitution_rows)

        version_dtos = {
            source_id: _course_version_dto(
                version,
                snapshot,
                text,
                tuple(periods_by_version[version.id]),
                tuple(prerequisite_by_version.get(version.id, ())),
                tuple(substitution_by_version.get(version.id, ())),
            )
            for source_id, (version, snapshot, text) in versions_by_source.items()
        }
        return tuple(
            CatalogueCourse(
                group_id=course.group_id,
                first_listed_academic_year_start=course.first_listed_academic_year_start,
                last_listed_academic_year_start=course.last_listed_academic_year_start,
                is_active=course.is_active,
                activity_as_of_academic_year_start=course.activity_as_of_academic_year_start,
                activity_window_years=course.activity_window_years,
                representative=(
                    None
                    if representatives[course.group_id] is None
                    else version_dtos[representatives[course.group_id]]
                ),
            )
            for course in courses
        )

    def list_represented_summaries(
        self, *, active_only: bool | None = None
    ) -> tuple[RepresentedCourseSummary, ...]:
        """Return one shared summary plus exact representative identity per represented course."""
        with self._factory() as session:
            return self._load_course_summaries(
                session, active_only=active_only, group_ids=None, include_identity=True
            )

    def get_represented_summaries(
        self, group_ids: Collection[str], *, active_only: bool | None = None
    ) -> tuple[RepresentedCourseSummary, ...]:
        """Return represented summaries for exactly the requested canonical courses.

        The scoped variant of `list_represented_summaries`: it shares the one summary loader,
        applies the optional activity scope, omits unknown and unrepresented identities, and
        returns empty before any I/O for an empty scope. It is the read the id-or-code resolver uses
        for a few requested identities.
        """
        requested = {group_id for group_id in group_ids if group_id}
        if not requested:
            return ()
        with self._factory() as session:
            return self._load_course_summaries(
                session, active_only=active_only, group_ids=requested, include_identity=True
            )

    def list_course_code_identities(
        self, *, active_only: bool | None = None
    ) -> tuple[tuple[str, str], ...]:
        """Return distinct `(group_id, code)` pairs across every stored course version.

        This is a whole-catalogue two-column projection used only to preserve the exact Python
        Unicode matcher cheaply: it includes non-representative stored versions as a
        candidate superset and carries no summary, representative, text or prerequisite payload.
        The resolver decides the current representative code through its scoped summary read,
        so a historical code never resolves on its own. `active_only` filters the canonical course
        activity only when explicitly supplied.
        """
        with self._factory() as session:
            statement = (
                select(Course.group_id, CourseVersion.code)
                .join(CourseVersion, CourseVersion.course_id == Course.id)
                .distinct()
                .order_by(Course.group_id, CourseVersion.code)
            )
            if active_only is not None:
                statement = statement.where(Course.is_active == active_only)
            return tuple((row.group_id, row.code) for row in session.execute(statement).all())

    def get_course_summaries(self, group_ids: Collection[str]) -> tuple[CourseSummary, ...]:
        """Return the shared official summary for exactly the requested represented courses.

        Structure projection references canonical course identities discovered while walking one
        rule tree, so this scoped read omits unknown and unrepresented identities, applies no
        activity filter, and returns the same shared summary in canonical `group_id` order. It reads
        only the summary columns plus the selected source identity, never a source hash, snapshot
        join, full version, text or prerequisite structure.
        """
        requested = {group_id for group_id in group_ids if group_id}
        if not requested:
            return ()
        with self._factory() as session:
            return self._load_course_summaries(
                session, active_only=None, group_ids=requested, include_identity=False
            )

    def _load_course_summaries(
        self,
        session: Session,
        *,
        active_only: bool | None,
        group_ids: Collection[str] | None,
        include_identity: bool,
    ) -> tuple[CourseSummary, ...] | tuple[RepresentedCourseSummary, ...]:
        """Assemble shared summaries under the one shared activity/identity/representative scope.

        Both public summary reads share this loader and differ only by identity scope and projection:
        the represented-summary read adds the selected representative's source hash/code through the
        snapshot join, while the structure-only read selects the shared summary columns plus the
        selected source identity needed to join and order.
        """
        courses = self._scoped_courses(
            session, active_only=active_only, group_ids=group_ids, teaching_only=True
        )
        representatives = self._representative_source_ids(session, courses)
        selected = {
            group_id: source_id
            for group_id, source_id in representatives.items()
            if source_id is not None
        }
        if not selected:
            return ()
        columns: list[Any] = [
            Course.group_id,
            Course.is_active,
            CourseVersion.sisu_course_unit_id,
        ]
        if include_identity:
            columns.append(SourceSnapshot.source_hash)
        columns.extend(
            (
                CourseVersion.name_fi,
                CourseVersion.name_en,
                CourseVersion.code,
                CourseVersion.credits_min,
                CourseVersion.credits_max,
                CourseVersion.official_url,
            )
        )
        statement = (
            select(*columns)
            .join(CourseVersion, CourseVersion.course_id == Course.id)
            .where(CourseVersion.sisu_course_unit_id.in_(tuple(selected.values())))
            .order_by(Course.group_id)
        )
        if include_identity:
            statement = statement.join(
                SourceSnapshot, SourceSnapshot.id == CourseVersion.source_snapshot_id
            )
        summaries_by_source: dict[str, CourseSummary | RepresentedCourseSummary] = {}
        for row in session.execute(statement):
            summary = course_summary_from_fields(
                group_id=row.group_id,
                is_active=row.is_active,
                name_fi=row.name_fi,
                name_en=row.name_en,
                code=row.code,
                credits_min=row.credits_min,
                credits_max=row.credits_max,
                official_url=row.official_url,
            )
            if include_identity:
                summaries_by_source[row.sisu_course_unit_id] = RepresentedCourseSummary(
                    summary=summary,
                    sisu_course_unit_id=row.sisu_course_unit_id,
                    source_hash=row.source_hash,
                )
            else:
                summaries_by_source[row.sisu_course_unit_id] = summary
        _require_representative_versions(selected.values(), summaries_by_source)
        return tuple(summaries_by_source[selected[group_id]] for group_id in sorted(selected))

    def get_representative_teaching_texts(
        self, sisu_course_unit_ids: Collection[str]
    ) -> tuple[CatalogueRepresentativeTeachingText, ...]:
        """Return selected representatives' official identity and teaching text for exact source IDs.

        Only groups owning one of the requested source IDs are read, and only requested source IDs
        that the shared persisted-activity rule selected are returned. A requested but non-selected
        version of an affected group is therefore absent, and the caller rejects it as not a
        selected representative.
        """
        source_ids = tuple(dict.fromkeys(sisu_course_unit_ids))
        if not source_ids:
            return ()
        with self._factory() as session:
            affected_group_ids = tuple(
                session.scalars(
                    select(Course.group_id)
                    .join(CourseVersion, CourseVersion.course_id == Course.id)
                    .where(CourseVersion.sisu_course_unit_id.in_(source_ids))
                    .distinct()
                )
            )
            if not affected_group_ids:
                return ()
            courses = self._scoped_courses(
                session, active_only=None, group_ids=affected_group_ids, teaching_only=True
            )
            representatives = self._representative_source_ids(session, courses)
            requested = set(source_ids)
            selected_ids = tuple(
                source_id
                for source_id in representatives.values()
                if source_id is not None and source_id in requested
            )
            if not selected_ids:
                return ()
            by_source_id = _representative_teaching_texts(session, selected_ids)
            return tuple(by_source_id[source_id] for source_id in sorted(selected_ids))

    def list_teaching_text_inputs(self) -> tuple[CatalogueTeachingTextInput, ...]:
        """Return every canonical course's group ID and its official representative text, if any.

        It reads only the course identity/activity columns needed for the shared representative
        rule and then the selected representatives' official identity and text through the one
        shared selected-source projection. No full course, prerequisite, substitution, source hash,
        or unrelated text column is materialized. Unrepresented courses are preserved with a null
        representative and the result is sorted by canonical group ID.
        """
        with self._factory() as session:
            contexts = self._scoped_courses(
                session, active_only=None, group_ids=None, teaching_only=True
            )
            representatives = self._representative_source_ids(session, contexts)
            selected_ids = tuple(
                source_id for source_id in representatives.values() if source_id is not None
            )
            by_source_id = _representative_teaching_texts(session, selected_ids)
            return tuple(
                CatalogueTeachingTextInput(
                    group_id=course.group_id,
                    representative=(
                        None
                        if representatives[course.group_id] is None
                        else by_source_id[representatives[course.group_id]]
                    ),
                )
                for course in contexts
            )

    def _representative_source_ids(
        self, session: Session, courses: Sequence[_RepresentativeActivityContext]
    ) -> dict[str, str | None]:
        """Choose the official representative per canonical course for its own activity context."""
        contexts: dict[tuple[int, int], list[_RepresentativeActivityContext]] = defaultdict(list)
        for course in courses:
            contexts[
                (
                    course.activity_as_of_academic_year_start,
                    course.activity_window_years,
                )
            ].append(course)

        representatives: dict[str, str | None] = {}
        for (current_year, window), context_courses in contexts.items():
            representatives.update(
                select_representative_source_ids(
                    session,
                    tuple(course.group_id for course in context_courses),
                    current_academic_year_start=current_year,
                    activity_window_years=window,
                )
            )
        return representatives

    def list_modules(self) -> tuple[CatalogueModule, ...]:
        """Return detached canonical modules with all exact versions and rule trees."""
        with self._factory() as session:
            return self._load_modules(session, group_ids=None)

    def list_module_lookup(self) -> tuple[CatalogueModuleLookup, ...]:
        """Return canonical module identity with only the projected versions a name lookup needs.

        It shares `_load_modules`' identity filter, version ordering and membership loader, but
        projects only the consumed module-version columns and never reads a rule node or snapshot.
        """
        with self._factory() as session:
            return self._load_modules(session, group_ids=None, lookup_only=True)

    def get_modules(self, group_ids: Collection[str]) -> tuple[CatalogueModule, ...]:
        """Return only the requested canonical modules with their exact versions and rules."""
        if not group_ids:
            return ()
        with self._factory() as session:
            return self._load_modules(session, group_ids=group_ids)

    def _load_modules(
        self,
        session: Session,
        *,
        group_ids: Collection[str] | None,
        lookup_only: bool = False,
    ) -> tuple[CatalogueModule, ...] | tuple[CatalogueModuleLookup, ...]:
        """Assemble detached canonical modules under an optional identity scope.

        The default full read returns every exact version, membership and typed rule tree. The
        ``lookup_only`` projection shares the same identity filter, version ordering and membership
        loader but returns only the module-version identity fields, so it never materializes a
        `ModuleVersion`/`SourceSnapshot` ORM row or queries `ModuleRuleNode`.
        """
        statement = select(Module.id, Module.group_id).order_by(Module.group_id)
        if group_ids is not None:
            statement = statement.where(Module.group_id.in_(group_ids))
        modules = tuple(session.execute(statement))
        module_ids = tuple(module_id for module_id, _ in modules)
        if not module_ids:
            return ()

        version_rows = self._module_version_rows(
            session, module_ids=module_ids, lookup_only=lookup_only
        )
        if lookup_only:
            version_ids = tuple(row.id for row in version_rows)
        else:
            version_ids = tuple(version.id for version, _ in version_rows)
        periods_by_version = self._module_periods_by_version(session, version_ids=version_ids)
        if lookup_only:
            identities_by_module = _assemble_module_version_identities(
                version_rows, periods_by_version
            )
            return tuple(
                CatalogueModuleLookup(
                    group_id=group_id,
                    versions=tuple(identities_by_module[module_id]),
                )
                for module_id, group_id in modules
            )

        rules_by_version = _build_rules(
            tuple(
                session.scalars(
                    select(ModuleRuleNode)
                    .where(ModuleRuleNode.module_version_id.in_(version_ids))
                    .order_by(
                        ModuleRuleNode.module_version_id,
                        ModuleRuleNode.parent_node_id.asc().nulls_first(),
                        ModuleRuleNode.sibling_position,
                    )
                )
            )
        )
        versions_by_module = _assemble_module_versions(
            version_rows, periods_by_version, rules_by_version
        )
        return tuple(
            CatalogueModule(
                group_id=group_id,
                versions=tuple(versions_by_module[module_id]),
            )
            for module_id, group_id in modules
        )

    def _module_version_rows(
        self,
        session: Session,
        *,
        module_ids: Collection[UUID],
        lookup_only: bool,
    ) -> tuple[Any, ...]:
        """Select exact module versions under the one shared module-ID filter and order.

        The full read selects whole versions plus their source snapshots. ``lookup_only`` projects
        only the identity, type, name and validity columns the substring lookup consumes, with no
        snapshot join or full ORM entity.
        """
        if lookup_only:
            statement = select(
                ModuleVersion.id,
                ModuleVersion.module_id,
                ModuleVersion.sisu_module_id,
                ModuleVersion.module_type,
                ModuleVersion.code,
                ModuleVersion.name_fi,
                ModuleVersion.name_en,
                ModuleVersion.validity_start,
                ModuleVersion.validity_end,
            )
        else:
            statement = select(ModuleVersion, SourceSnapshot).join(
                SourceSnapshot, SourceSnapshot.id == ModuleVersion.source_snapshot_id
            )
        return tuple(
            session.execute(
                statement.where(ModuleVersion.module_id.in_(module_ids)).order_by(
                    ModuleVersion.module_id, ModuleVersion.sisu_module_id
                )
            )
        )

    def _module_periods_by_version(
        self, session: Session, *, version_ids: Collection[UUID]
    ) -> dict[UUID, list[CatalogueCurriculumPeriod]]:
        """Project the common module membership read into detached period DTOs per version."""
        period_rows = tuple(
            session.execute(
                select(
                    ModuleVersionCurriculumPeriod.module_version_id,
                    CurriculumPeriod.id,
                    CurriculumPeriod.academic_year_start,
                )
                .join(
                    CurriculumPeriod,
                    CurriculumPeriod.id == ModuleVersionCurriculumPeriod.curriculum_period_id,
                )
                .where(ModuleVersionCurriculumPeriod.module_version_id.in_(version_ids))
                .order_by(
                    ModuleVersionCurriculumPeriod.module_version_id,
                    CurriculumPeriod.academic_year_start,
                    ModuleVersionCurriculumPeriod.curriculum_period_id,
                )
            )
        )
        periods_by_version: dict[UUID, list[CatalogueCurriculumPeriod]] = defaultdict(list)
        periods_by_id: dict[str, CatalogueCurriculumPeriod] = {}
        for version_id, period_id, academic_year_start in period_rows:
            period = periods_by_id.get(period_id)
            if period is None:
                period = CatalogueCurriculumPeriod(
                    id=period_id, academic_year_start=academic_year_start
                )
                periods_by_id[period_id] = period
            periods_by_version[version_id].append(period)
        return periods_by_version

    def summary(self) -> CatalogueSummary:
        """Return counts directly from migration-owned normalized tables."""
        with self._factory() as session:
            return CatalogueSummary(
                curriculum_period_count=session.scalar(
                    select(func.count()).select_from(CurriculumPeriod)
                ),
                canonical_course_count=session.scalar(select(func.count()).select_from(Course)),
                active_course_count=session.scalar(
                    select(func.count()).select_from(Course).where(Course.is_active)
                ),
                course_version_count=session.scalar(
                    select(func.count()).select_from(CourseVersion)
                ),
                canonical_module_count=session.scalar(select(func.count()).select_from(Module)),
                module_version_count=session.scalar(
                    select(func.count()).select_from(ModuleVersion)
                ),
            )


def _course_version_dto(
    version: CourseVersion,
    snapshot: SourceSnapshot,
    text: CourseText | None,
    period_ids: tuple[str, ...],
    prerequisite_options: tuple[CataloguePrerequisiteOption, ...],
    substitution_options: tuple[CatalogueSubstitutionOption, ...],
) -> CatalogueCourseVersion:
    """Map one bulk-loaded course row and its ordered child DTOs."""
    return CatalogueCourseVersion(
        sisu_course_unit_id=version.sisu_course_unit_id,
        source_hash=snapshot.source_hash,
        code=version.code,
        name_fi=version.name_fi,
        name_en=version.name_en,
        credits_min=version.credits_min,
        credits_max=version.credits_max,
        official_url=version.official_url,
        document_state=version.document_state,
        validity_start=version.validity_start,
        validity_end=version.validity_end,
        curriculum_period_ids=period_ids,
        teaching_text=CatalogueTeachingText(
            content_fi=None if text is None else text.content_fi,
            content_en=None if text is None else text.content_en,
            outcomes_fi=None if text is None else text.outcomes_fi,
            outcomes_en=None if text is None else text.outcomes_en,
        ),
        prerequisite_text_fi=None if text is None else text.prerequisite_text_fi,
        prerequisite_text_en=None if text is None else text.prerequisite_text_en,
        additional_info_fi=None if text is None else text.additional_info_fi,
        additional_info_en=None if text is None else text.additional_info_en,
        prerequisite_options=prerequisite_options,
        substitution_options=substitution_options,
    )


def _group_ordered_options(
    rows,
    *,
    owner_id: Callable[[Any], UUID],
    build_option: Callable[[Any], Any],
    build_member: Callable[[Any], Any],
) -> dict[UUID, tuple[Any, ...]]:
    """Accumulate ordered options and their ordered members under one owner id.

    Course prerequisites/substitutions share this shape. The caller supplies the owner id, the
    option DTO, and the member DTO so only the type-specific mapping differs. Option and member
    order follow the ordered SQL rows, preserving AND members and OR options.
    """
    grouped: dict[UUID, dict[UUID, tuple[Any, list[Any]]]] = {}
    for option, member in rows:
        options = grouped.setdefault(owner_id(option), {})
        entry = options.get(option.id)
        if entry is None:
            entry = (build_option(option), [])
            options[option.id] = entry
        if member is not None:
            entry[1].append(build_member(member))
    return {
        version_id: tuple(
            option.model_copy(update={"members": tuple(members)})
            for option, members in options.values()
        )
        for version_id, options in grouped.items()
    }


def _group_prerequisites(rows):
    return _group_ordered_options(
        rows,
        owner_id=lambda option: option.target_course_version_id,
        build_option=lambda option: CataloguePrerequisiteOption(
            option_index=option.option_index,
            requirement_kind=option.requirement_kind,
            members=(),
        ),
        build_member=lambda member: CataloguePrerequisiteMember(
            member_index=member.member_index,
            member_type=member.member_type,
            referenced_group_id=member.referenced_group_id,
        ),
    )


def _group_substitutions(rows):
    return _group_ordered_options(
        rows,
        owner_id=lambda option: option.source_course_version_id,
        build_option=lambda option: CatalogueSubstitutionOption(
            option_index=option.option_index, members=()
        ),
        build_member=lambda member: CatalogueSubstitutionMember(
            member_index=member.member_index,
            course_group_id=member.course_group_id,
            credits=member.credits,
        ),
    )


def _assemble_module_versions(
    version_rows: Sequence[tuple[ModuleVersion, SourceSnapshot]],
    periods_by_version: dict[UUID, list[CatalogueCurriculumPeriod]],
    rules_by_version: dict[UUID, CatalogueModuleRule],
) -> dict[UUID, list[CatalogueModuleVersion]]:
    """Map each exact module-version row into its ordered detached DTO."""
    versions_by_module: dict[UUID, list[CatalogueModuleVersion]] = defaultdict(list)
    for version, snapshot in version_rows:
        versions_by_module[version.module_id].append(
            CatalogueModuleVersion(
                sisu_module_id=version.sisu_module_id,
                source_hash=snapshot.source_hash,
                module_type=version.module_type,
                code=version.code,
                name_fi=version.name_fi,
                name_en=version.name_en,
                target_credits_min=version.target_credits_min,
                target_credits_max=version.target_credits_max,
                document_state=version.document_state,
                validity_start=version.validity_start,
                validity_end=version.validity_end,
                curriculum_periods=tuple(periods_by_version[version.id]),
                rule=rules_by_version.get(version.id),
            )
        )
    return versions_by_module


def _assemble_module_version_identities(
    version_rows: Sequence[tuple[Any, ...]],
    periods_by_version: dict[UUID, list[CatalogueCurriculumPeriod]],
) -> dict[UUID, list[CatalogueModuleVersionIdentity]]:
    """Map each module-version projection row into its ordered detached identity DTO."""
    versions_by_module: dict[UUID, list[CatalogueModuleVersionIdentity]] = defaultdict(list)
    for (
        version_id,
        module_id,
        sisu_module_id,
        module_type,
        code,
        name_fi,
        name_en,
        validity_start,
        validity_end,
    ) in version_rows:
        versions_by_module[module_id].append(
            CatalogueModuleVersionIdentity(
                sisu_module_id=sisu_module_id,
                module_type=module_type,
                code=code,
                name_fi=name_fi,
                name_en=name_en,
                validity_start=validity_start,
                validity_end=validity_end,
                curriculum_periods=tuple(periods_by_version[version_id]),
            )
        )
    return versions_by_module


def _build_rules(rows: tuple[ModuleRuleNode, ...]) -> dict[UUID, CatalogueModuleRule]:
    by_version: dict[UUID, list[ModuleRuleNode]] = defaultdict(list)
    for row in rows:
        by_version[row.module_version_id].append(row)
    result: dict[UUID, CatalogueModuleRule] = {}
    for version_id, version_rows in by_version.items():
        children: dict[UUID, list[ModuleRuleNode]] = defaultdict(list)
        roots = []
        for row in version_rows:
            if row.parent_node_id is None:
                roots.append(row)
            else:
                children[row.parent_node_id].append(row)
        if len(roots) != 1:
            raise ValueError("module version rule tree must have exactly one root")

        def build(row: ModuleRuleNode) -> CatalogueModuleRule:
            child_rows = sorted(children.get(row.id, ()), key=lambda child: child.sibling_position)
            return CatalogueModuleRule(
                node_type=row.node_type,
                sibling_position=row.sibling_position,
                local_id=row.local_id,
                require_min=row.require_min,
                require_max=row.require_max,
                all_mandatory=row.all_mandatory,
                description=None if row.description is None else dict(row.description),
                credits_min=row.credits_min,
                credits_max=row.credits_max,
                count_min=row.count_min,
                count_max=row.count_max,
                referenced_group_id=row.referenced_group_id,
                children=tuple(build(child) for child in child_rows),
            )

        result[version_id] = build(roots[0])
    return result
