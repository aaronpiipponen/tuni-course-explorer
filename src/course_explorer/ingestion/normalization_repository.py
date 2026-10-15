"""Transactional persistence for normalized official curriculum DTOs.

The repository is the sole writer for normalized curriculum tables. It applies one complete
normalization batch through one transaction, retaining immutable capture provenance and replacing
only exact versions whose source hash changed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from itertools import batched
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.curriculum import is_within_activity_window
from course_explorer.curriculum_repository import select_representative_source_ids
from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
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
from course_explorer.enums import IngestionRunStatus, ModuleRuleType, SourceObjectType
from course_explorer.ingestion.normalization import (
    NormalizationBatch,
    NormalizationPersistence,
    NormalizationReport,
    NormalizedCourseVersion,
    NormalizedModuleRule,
    NormalizedModuleVersion,
    NormalizedPeriod,
    SnapshotProvenance,
    walk_normalized_rule,
)

_SNAPSHOT_QUERY_CHUNK_SIZE = 10_000


class NormalizationRepository(NormalizationPersistence):
    """Apply normalized source DTOs atomically and report exact rerun classifications."""

    def __init__(self, factory: sessionmaker[Session]):
        self._factory = factory

    def apply(
        self,
        batch: NormalizationBatch,
        *,
        current_academic_year_start: int,
        activity_window_years: int,
    ) -> NormalizationReport:
        """Validate provenance, reconcile versions, and commit one all-or-nothing batch."""
        if current_academic_year_start <= 0:
            raise ValueError("current academic year start must be positive")
        if activity_window_years <= 0:
            raise ValueError("activity window years must be positive")

        course_groups = {course.group_id for course in batch.courses}
        excluded_course_source_ids = {
            exclusion.source_object_id for exclusion in batch.excluded_null_code_course_versions
        }
        excluded_course_groups = {
            exclusion.source_group_id for exclusion in batch.excluded_null_code_course_versions
        }
        affected_course_groups = course_groups | excluded_course_groups
        module_groups = {module.group_id for module in batch.modules}
        course_source_ids = {course.provenance.source_object_id for course in batch.courses}
        course_source_ids |= excluded_course_source_ids
        module_source_ids = {module.provenance.source_object_id for module in batch.modules}
        input_provenance = {
            (
                course.provenance.response_path,
                course.provenance.response_item_index,
            ): course.provenance
            for course in batch.courses
        }
        input_provenance.update(
            {
                (
                    module.provenance.response_path,
                    module.provenance.response_item_index,
                ): module.provenance
                for module in batch.modules
            }
        )
        input_provenance.update(
            {
                (
                    exclusion.response_path,
                    exclusion.response_item_index,
                ): exclusion
                for exclusion in batch.excluded_null_code_course_versions
            }
        )

        with session_scope(self._factory) as session:
            run = session.get(IngestionRun, batch.run_id)
            if run is None or run.status is not IngestionRunStatus.COMPLETED:
                raise ValueError("normalization requires a completed ingestion run")

            snapshots = self._load_snapshots(session, batch.run_id, input_provenance)
            periods = self._load_periods(session, {period.id for period in batch.periods})
            courses = self._load_courses(session, affected_course_groups)
            modules = self._load_modules(session, module_groups)
            existing_course_versions = self._load_course_versions(session, course_source_ids)
            existing_module_versions = self._load_module_versions(session, module_source_ids)

            before_representatives = select_representative_source_ids(
                session,
                affected_course_groups,
                current_academic_year_start=current_academic_year_start,
                activity_window_years=activity_window_years,
            )

            self._prepare_periods(session, batch.periods, periods)
            self._ensure_owners(
                session,
                courses=courses,
                modules=modules,
                course_groups=course_groups,
                module_groups=module_groups,
                current_academic_year_start=current_academic_year_start,
                activity_window_years=activity_window_years,
            )
            session.flush()

            course_statuses = self._apply_versions(
                session,
                object_type=SourceObjectType.COURSE_UNIT,
                versions=batch.courses,
                owners=courses,
                existing=existing_course_versions,
                snapshots=snapshots,
            )
            module_statuses = self._apply_versions(
                session,
                object_type=SourceObjectType.MODULE,
                versions=batch.modules,
                owners=modules,
                existing=existing_module_versions,
                snapshots=snapshots,
            )
            session.flush()

            self._remove_excluded_null_code_versions(
                session, batch, existing_course_versions, courses
            )

            affected_courses = self._recalculate_courses(
                session,
                affected_course_groups,
                current_academic_year_start=current_academic_year_start,
                activity_window_years=activity_window_years,
            )
            after_representatives = select_representative_source_ids(
                session,
                affected_course_groups,
                current_academic_year_start=current_academic_year_start,
                activity_window_years=activity_window_years,
            )

            unrestricted_rule_count = sum(
                1
                for module in batch.modules
                if module.rule is not None
                for node in walk_normalized_rule(module.rule)
                if node.node_type
                in {ModuleRuleType.ANY_COURSE_UNIT_RULE, ModuleRuleType.ANY_MODULE_RULE}
            )
            return NormalizationReport(
                run_id=batch.run_id,
                period_count=len(batch.periods),
                canonical_course_count=len(course_groups),
                active_course_count=sum(
                    1
                    for course in affected_courses
                    if course.group_id in course_groups and course.is_active
                ),
                canonical_module_count=len(module_groups),
                course_version_count=len(batch.courses),
                excluded_null_code_course_versions=batch.excluded_null_code_course_versions,
                new_course_version_count=course_statuses["new"],
                changed_course_version_count=course_statuses["changed"],
                unchanged_course_version_count=course_statuses["unchanged"],
                module_version_count=len(batch.modules),
                new_module_version_count=module_statuses["new"],
                changed_module_version_count=module_statuses["changed"],
                unchanged_module_version_count=module_statuses["unchanged"],
                representative_changed_course_count=sum(
                    before_representatives.get(group_id) != after_representatives.get(group_id)
                    for group_id in affected_course_groups
                ),
                unresolved_course_group_count=len(batch.unresolved_course_group_ids),
                unresolved_module_group_count=len(batch.unresolved_module_group_ids),
                unrestricted_rule_count=unrestricted_rule_count,
            )

    @staticmethod
    def _prepare_periods(
        session: Session,
        period_values: Sequence[NormalizedPeriod],
        periods: dict[str, CurriculumPeriod],
    ) -> None:
        """Create or update the canonical curriculum-period rows for one batch."""
        for period in period_values:
            current = periods.get(period.id)
            if current is None:
                current = CurriculumPeriod(
                    id=period.id, academic_year_start=period.academic_year_start
                )
                session.add(current)
                periods[period.id] = current
            else:
                current.academic_year_start = period.academic_year_start

    @staticmethod
    def _ensure_owners(
        session: Session,
        *,
        courses: dict[str, Course],
        modules: dict[str, Module],
        course_groups: set[str],
        module_groups: set[str],
        current_academic_year_start: int,
        activity_window_years: int,
    ) -> None:
        """Create the missing canonical course and module containers for one batch."""
        for group_id in course_groups:
            if group_id in courses:
                continue
            courses[group_id] = Course(
                id=uuid4(),
                group_id=group_id,
                first_listed_academic_year_start=None,
                last_listed_academic_year_start=None,
                is_active=False,
                activity_as_of_academic_year_start=current_academic_year_start,
                activity_window_years=activity_window_years,
            )
            session.add(courses[group_id])
        for group_id in module_groups:
            if group_id in modules:
                continue
            modules[group_id] = Module(id=uuid4(), group_id=group_id)
            session.add(modules[group_id])

    @staticmethod
    def _remove_excluded_null_code_versions(
        session: Session,
        batch: NormalizationBatch,
        existing_course_versions: dict[str, tuple[CourseVersion, Course, SourceSnapshot]],
        courses: dict[str, Course],
    ) -> None:
        """Remove null-code exact versions and any canonical course left with no versions."""
        excluded_course_groups = {
            exclusion.source_group_id for exclusion in batch.excluded_null_code_course_versions
        }
        for exclusion in batch.excluded_null_code_course_versions:
            current = existing_course_versions.get(exclusion.source_object_id)
            if current is None:
                continue
            version, current_course, _ = current
            if current_course.group_id != exclusion.source_group_id:
                raise ValueError("exact source version is linked to a different canonical group")
            session.delete(version)
        session.flush()

        remaining_groups = set(
            session.scalars(
                select(Course.group_id)
                .join(CourseVersion, CourseVersion.course_id == Course.id)
                .where(Course.group_id.in_(excluded_course_groups))
            )
        )
        for group_id in excluded_course_groups - remaining_groups:
            course = courses.get(group_id)
            if course is not None:
                session.delete(course)
        session.flush()

    @staticmethod
    def _load_snapshots(
        session: Session,
        run_id: UUID,
        provenance: dict[tuple[str, int], SnapshotProvenance],
    ) -> dict[tuple[str, int], SourceSnapshot]:
        if not provenance:
            return {}
        indexed: dict[tuple[str, int], SourceSnapshot] = {}
        response_paths = tuple(dict.fromkeys(path for path, _ in provenance))
        for paths in batched(response_paths, _SNAPSHOT_QUERY_CHUNK_SIZE):
            rows = tuple(
                session.scalars(
                    select(SourceSnapshot).where(
                        SourceSnapshot.ingestion_run_id == run_id,
                        SourceSnapshot.response_path.in_(paths),
                    )
                )
            )
            indexed.update({(row.response_path, row.response_item_index): row for row in rows})
        if not set(provenance).issubset(indexed):
            raise ValueError("normalization provenance snapshot is missing")
        for key, expected in provenance.items():
            actual = indexed[key]
            if (
                actual.ingestion_run_id != run_id
                or actual.object_type is not expected.object_type
                or actual.source_object_id != expected.source_object_id
                or actual.source_group_id != expected.source_group_id
                or actual.source_hash != expected.source_hash
            ):
                raise ValueError("normalization provenance snapshot conflicts with source evidence")
        return indexed

    @staticmethod
    def _load_periods(session: Session, ids: set[str]) -> dict[str, CurriculumPeriod]:
        if not ids:
            return {}
        return {
            period.id: period
            for period in session.scalars(
                select(CurriculumPeriod).where(CurriculumPeriod.id.in_(ids))
            )
        }

    @staticmethod
    def _load_courses(session: Session, groups: set[str]) -> dict[str, Course]:
        if not groups:
            return {}
        return {
            course.group_id: course
            for course in session.scalars(select(Course).where(Course.group_id.in_(groups)))
        }

    @staticmethod
    def _load_modules(session: Session, groups: set[str]) -> dict[str, Module]:
        if not groups:
            return {}
        return {
            module.group_id: module
            for module in session.scalars(select(Module).where(Module.group_id.in_(groups)))
        }

    @staticmethod
    def _load_course_versions(
        session: Session, source_ids: set[str]
    ) -> dict[str, tuple[CourseVersion, Course, SourceSnapshot]]:
        if not source_ids:
            return {}
        rows = session.execute(
            select(CourseVersion, Course, SourceSnapshot)
            .join(Course, Course.id == CourseVersion.course_id)
            .join(SourceSnapshot, SourceSnapshot.id == CourseVersion.source_snapshot_id)
            .where(CourseVersion.sisu_course_unit_id.in_(source_ids))
        )
        return {
            version.sisu_course_unit_id: (version, course, snapshot)
            for version, course, snapshot in rows
        }

    @staticmethod
    def _load_module_versions(
        session: Session, source_ids: set[str]
    ) -> dict[str, tuple[ModuleVersion, Module, SourceSnapshot]]:
        if not source_ids:
            return {}
        rows = session.execute(
            select(ModuleVersion, Module, SourceSnapshot)
            .join(Module, Module.id == ModuleVersion.module_id)
            .join(SourceSnapshot, SourceSnapshot.id == ModuleVersion.source_snapshot_id)
            .where(ModuleVersion.sisu_module_id.in_(source_ids))
        )
        return {
            version.sisu_module_id: (version, module, snapshot)
            for version, module, snapshot in rows
        }

    @staticmethod
    def _version_values(
        version: NormalizedCourseVersion | NormalizedModuleVersion,
        *,
        owner_id: UUID,
        snapshot_id: UUID,
        object_type: SourceObjectType,
    ) -> dict[str, Any]:
        """Map one normalized version's shared fields plus its type-specific owner columns."""
        values: dict[str, Any] = {
            "code": version.code,
            "name_fi": version.name_fi,
            "name_en": version.name_en,
            "document_state": version.document_state,
            "validity_start": version.validity_start,
            "validity_end": version.validity_end,
            "source_revision": version.source_revision,
            "source_modification_ordinal": version.source_modification_ordinal,
            "source_snapshot_id": snapshot_id,
        }
        if object_type is SourceObjectType.COURSE_UNIT:
            values.update(
                {
                    "course_id": owner_id,
                    "sisu_course_unit_id": version.provenance.source_object_id,
                    "credits_min": version.credits_min,
                    "credits_max": version.credits_max,
                    "official_url": version.official_url,
                }
            )
        else:
            values.update(
                {
                    "module_id": owner_id,
                    "sisu_module_id": version.provenance.source_object_id,
                    "module_type": version.module_type,
                    "target_credits_min": version.target_credits_min,
                    "target_credits_max": version.target_credits_max,
                }
            )
        return values

    def _apply_versions(
        self,
        session: Session,
        *,
        object_type: SourceObjectType,
        versions: tuple[NormalizedCourseVersion, ...] | tuple[NormalizedModuleVersion, ...],
        owners: dict[str, Any],
        existing: dict[str, tuple[Any, Any, SourceSnapshot]],
        snapshots: dict[tuple[str, int], SourceSnapshot],
    ) -> dict[str, int]:
        """Reconcile one object type's versions: reuse, replace in place, or create rows."""
        row_type = CourseVersion if object_type is SourceObjectType.COURSE_UNIT else ModuleVersion
        counts = {"new": 0, "changed": 0, "unchanged": 0}
        payloads: list[tuple[Any, Any]] = []
        for normalized in versions:
            source_id = normalized.provenance.source_object_id
            snapshot = snapshots[_provenance_key(normalized.provenance)]
            current = existing.get(source_id)
            if current is not None:
                version, current_owner, current_snapshot = current
                if current_owner.group_id != normalized.group_id:
                    raise ValueError(
                        "exact source version is linked to a different canonical group"
                    )
                if current_snapshot.source_hash == normalized.provenance.source_hash:
                    counts["unchanged"] += 1
                    continue
                counts["changed"] += 1
                self._delete_version_payload(session, object_type, version.id)
                for field, value in self._version_values(
                    normalized,
                    owner_id=current_owner.id,
                    snapshot_id=snapshot.id,
                    object_type=object_type,
                ).items():
                    setattr(version, field, value)
            else:
                counts["new"] += 1
                version = row_type(
                    id=uuid4(),
                    **self._version_values(
                        normalized,
                        owner_id=owners[normalized.group_id].id,
                        snapshot_id=snapshot.id,
                        object_type=object_type,
                    ),
                )
                session.add(version)
            payloads.append((version, normalized))
        session.flush()
        for version, normalized in payloads:
            self._insert_version_payload(session, object_type, version, normalized)
        return counts

    @staticmethod
    def _delete_version_payload(
        session: Session, object_type: SourceObjectType, version_id: UUID
    ) -> None:
        """Delete the two payload shapes for one exact version being removed."""
        if object_type is SourceObjectType.COURSE_UNIT:
            prerequisite_ids = select(OfficialPrerequisiteOption.id).where(
                OfficialPrerequisiteOption.target_course_version_id == version_id
            )
            substitution_ids = select(OfficialSubstitutionOption.id).where(
                OfficialSubstitutionOption.source_course_version_id == version_id
            )
            session.execute(
                delete(OfficialPrerequisiteOptionMember).where(
                    OfficialPrerequisiteOptionMember.prerequisite_option_id.in_(prerequisite_ids)
                )
            )
            session.execute(
                delete(OfficialPrerequisiteOption).where(
                    OfficialPrerequisiteOption.target_course_version_id == version_id
                )
            )
            session.execute(
                delete(OfficialSubstitutionOptionMember).where(
                    OfficialSubstitutionOptionMember.substitution_option_id.in_(substitution_ids)
                )
            )
            session.execute(
                delete(OfficialSubstitutionOption).where(
                    OfficialSubstitutionOption.source_course_version_id == version_id
                )
            )
            session.execute(delete(CourseText).where(CourseText.course_version_id == version_id))
            session.execute(
                delete(CourseVersionCurriculumPeriod).where(
                    CourseVersionCurriculumPeriod.course_version_id == version_id
                )
            )
        else:
            session.execute(
                delete(ModuleRuleNode).where(ModuleRuleNode.module_version_id == version_id)
            )
            session.execute(
                delete(ModuleVersionCurriculumPeriod).where(
                    ModuleVersionCurriculumPeriod.module_version_id == version_id
                )
            )

    @staticmethod
    def _insert_period_memberships(
        session: Session,
        object_type: SourceObjectType,
        version_id: UUID,
        period_ids: tuple[str, ...],
    ) -> None:
        """Insert the type-specific period-membership rows for one exact version."""
        if object_type is SourceObjectType.COURSE_UNIT:
            for period_id in period_ids:
                session.add(
                    CourseVersionCurriculumPeriod(
                        course_version_id=version_id, curriculum_period_id=period_id
                    )
                )
        else:
            for period_id in period_ids:
                session.add(
                    ModuleVersionCurriculumPeriod(
                        module_version_id=version_id, curriculum_period_id=period_id
                    )
                )

    @staticmethod
    def _insert_version_payload(
        session: Session,
        object_type: SourceObjectType,
        version: Any,
        normalized: NormalizedCourseVersion | NormalizedModuleVersion,
    ) -> None:
        """Insert the two necessary payload shapes for one added or changed exact version."""
        if object_type is SourceObjectType.MODULE:
            NormalizationRepository._insert_period_memberships(
                session, object_type, version.id, normalized.curriculum_period_ids
            )
            if normalized.rule is not None:
                _insert_rule_tree(session, version.id, normalized.rule, None)
            return
        session.add(
            CourseText(
                course_version_id=version.id,
                content_fi=normalized.content_fi,
                content_en=normalized.content_en,
                outcomes_fi=normalized.outcomes_fi,
                outcomes_en=normalized.outcomes_en,
                prerequisite_text_fi=normalized.prerequisite_text_fi,
                prerequisite_text_en=normalized.prerequisite_text_en,
                additional_info_fi=normalized.additional_info_fi,
                additional_info_en=normalized.additional_info_en,
            )
        )
        NormalizationRepository._insert_period_memberships(
            session, object_type, version.id, normalized.curriculum_period_ids
        )
        for option in normalized.prerequisite_options:
            option_row = OfficialPrerequisiteOption(
                id=uuid4(),
                target_course_version_id=version.id,
                option_index=option.option_index,
                requirement_kind=option.requirement_kind,
            )
            session.add(option_row)
            for member in option.members:
                session.add(
                    OfficialPrerequisiteOptionMember(
                        id=uuid4(),
                        prerequisite_option_id=option_row.id,
                        member_index=member.member_index,
                        member_type=member.member_type,
                        referenced_group_id=member.referenced_group_id,
                    )
                )
        for option in normalized.substitution_options:
            option_row = OfficialSubstitutionOption(
                id=uuid4(), source_course_version_id=version.id, option_index=option.option_index
            )
            session.add(option_row)
            for member in option.members:
                session.add(
                    OfficialSubstitutionOptionMember(
                        id=uuid4(),
                        substitution_option_id=option_row.id,
                        member_index=member.member_index,
                        course_group_id=member.course_group_id,
                        credits=member.credits,
                    )
                )

    @staticmethod
    def _recalculate_courses(
        session: Session,
        group_ids: set[str],
        *,
        current_academic_year_start: int,
        activity_window_years: int,
    ) -> tuple[Course, ...]:
        if not group_ids:
            return ()
        courses = tuple(session.scalars(select(Course).where(Course.group_id.in_(group_ids))))
        years_by_group: dict[str, list[int]] = defaultdict(list)
        rows = session.execute(
            select(Course.group_id, CurriculumPeriod.academic_year_start)
            .join(CourseVersion, CourseVersion.course_id == Course.id)
            .join(
                CourseVersionCurriculumPeriod,
                CourseVersionCurriculumPeriod.course_version_id == CourseVersion.id,
            )
            .join(
                CurriculumPeriod,
                CurriculumPeriod.id == CourseVersionCurriculumPeriod.curriculum_period_id,
            )
            .where(Course.group_id.in_(group_ids))
        )
        for group_id, year in rows:
            years_by_group[group_id].append(year)
        for course in courses:
            years = years_by_group.get(course.group_id, [])
            course.first_listed_academic_year_start = min(years) if years else None
            course.last_listed_academic_year_start = max(years) if years else None
            course.is_active = any(
                is_within_activity_window(
                    year,
                    current_academic_year_start=current_academic_year_start,
                    activity_window_years=activity_window_years,
                )
                for year in years
            )
            course.activity_as_of_academic_year_start = current_academic_year_start
            course.activity_window_years = activity_window_years
        return courses


def _provenance_key(provenance: SnapshotProvenance) -> tuple[str, int]:
    return provenance.response_path, provenance.response_item_index


def _insert_rule_tree(
    session: Session,
    module_version_id: UUID,
    rule: NormalizedModuleRule,
    parent_node_id: UUID | None,
) -> None:
    node_id = uuid4()
    session.add(
        ModuleRuleNode(
            id=node_id,
            module_version_id=module_version_id,
            parent_node_id=parent_node_id,
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
    )
    session.flush()
    for child in rule.children:
        _insert_rule_tree(session, module_version_id, child, node_id)
