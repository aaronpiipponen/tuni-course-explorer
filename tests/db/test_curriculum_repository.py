"""Opt-in PostgreSQL proofs for the detached curriculum read seam and module graph."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from course_explorer.config import NormalizationSettings, SearchSettings
from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
    course_summary,
)
from course_explorer.curriculum_repository import CurriculumRepository
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
    OfficialSubstitutionOption,
    SourceSnapshot,
)
from course_explorer.enums import ModuleRuleType, ModuleType
from course_explorer.ingestion.normalization import normalize_curriculum
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.prerequisite import commands as prerequisite_command_module
from course_explorer.prerequisite.domain import (
    CardinalityRequirement,
    CourseCountRequirement,
    CreditRequirement,
    ModuleBlockRequirement,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from course_explorer.prerequisite.path import (
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionState,
    evaluate_prerequisite_expression,
    evaluate_prerequisite_satisfaction,
)
from course_explorer.search import lookup_commands as lookup_command_module
from course_explorer.search.lookup import CourseLookupService
from course_explorer.study_structure import commands as study_structure_command_module
from tests.ingestion._normalization_repository_support import (
    GUIDE_URL,
    _NoEquivalenceGroupRead,
    _NoInferredSetRead,
    build_completed_fixture_store,
    fixture_bytes,
)
from tests.support import settings_factory

pytestmark = [
    pytest.mark.integration,
]


def test_curriculum_repository_reads_representatives_text_and_official_structures(
    database: tuple[object, object], tmp_path: Path
) -> None:
    """The read seam returns detached representatives and preserves typed module rules."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    store = build_completed_fixture_store(tmp_path, capture_repository)
    normalize_curriculum(
        store,
        NormalizationRepository(factory),
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )

    repository = CurriculumRepository(factory)
    courses = repository.list_courses()
    assert [course.group_id for course in courses] == [
        "course-group-a",
        "course-group-future",
        "course-group-inactive",
        "course-group-tie",
    ]
    course_a = courses[0]
    assert course_a.representative is not None
    assert course_a.representative.sisu_course_unit_id == "course-a-v2"
    assert course_a.representative.teaching_text.content_en == "Revised content"
    assert not hasattr(course_a.representative.teaching_text, "prerequisite_text_en")
    assert repository.list_courses(active_only=True) == (course_a,)
    assert [course.group_id for course in repository.list_courses(active_only=False)] == [
        "course-group-future",
        "course-group-inactive",
        "course-group-tie",
    ]
    assert courses[1].representative is None

    modules = repository.list_modules()
    assert [module.group_id for module in modules] == [
        "module-group-degree",
        "module-group-grouping",
        "module-group-study",
    ]
    grouping = modules[1].versions[0]
    assert grouping.sisu_module_id == "module-group-grouping-v1"
    assert grouping.curriculum_periods == (
        CatalogueCurriculumPeriod(id="period-2027", academic_year_start=2027),
    )
    assert modules[2].versions[0].curriculum_periods == (
        CatalogueCurriculumPeriod(id="period-2025", academic_year_start=2025),
        CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),
    )
    assert grouping.rule is not None
    assert [child.node_type.value for child in grouping.rule.children] == [
        "CreditsRule",
        "ModuleRule",
        "AnyCourseUnitRule",
        "AnyModuleRule",
    ]
    assert grouping.rule.children[1].referenced_group_id == "module-group-study"


@pytest.fixture
def normalized_curriculum(
    database: tuple[object, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, object, CurriculumRepository]:
    """Normalize the real fixture catalogue and provide the owning SQL read seam."""
    engine, factory = database
    capture_repository = CaptureRepository(factory)
    store = build_completed_fixture_store(tmp_path, capture_repository)
    normalize_curriculum(
        store,
        NormalizationRepository(factory),
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )

    monkeypatch.setattr(
        lookup_command_module,
        "load_search_settings",
        lambda: settings_factory(SearchSettings),
    )
    monkeypatch.setattr(
        lookup_command_module,
        "load_normalization_settings",
        lambda: settings_factory(NormalizationSettings),
    )
    return engine, factory, CurriculumRepository(factory)


def test_represented_summary_projection_matches_full_read(normalized_curriculum) -> None:
    """Represented summary records equal each full course's selected official version."""
    _, _, repository = normalized_curriculum
    courses = repository.list_courses()
    summaries = repository.list_represented_summaries()
    expected = tuple(
        (
            course_summary(course),
            course.representative.sisu_course_unit_id,
            course.representative.source_hash,
        )
        for course in courses
        if course.representative is not None
    )
    assert [
        (record.summary, record.sisu_course_unit_id, record.source_hash) for record in summaries
    ] == list(expected)
    assert [record.summary.group_id for record in summaries] == sorted(
        record.summary.group_id for record in summaries
    )
    assert repository.list_represented_summaries(active_only=True) == tuple(
        record for record in summaries if record.summary.is_active
    )
    # A course without a selected representative never appears in the summary read.
    assert "course-group-future" in {course.group_id for course in courses}
    assert "course-group-future" not in {record.summary.group_id for record in summaries}
    assert repository.list_represented_summaries(active_only=True) != ()


def test_scoped_course_summaries_omit_unknown_and_unrepresented(normalized_curriculum) -> None:
    """Scoped summary reads return requested represented cards and omit absent identities."""
    _, _, repository = normalized_curriculum
    summaries = repository.list_represented_summaries()

    # The scoped summary getter returns the same shared summaries for exactly the requested
    # represented identities, including inactive ones, and omits unrepresented and unknown IDs.
    requested_summary_ids = tuple(record.summary.group_id for record in summaries) + (
        "course-group-future",
        "course-group-absent",
    )
    assert repository.get_course_summaries(requested_summary_ids) == tuple(
        record.summary for record in summaries
    )
    assert repository.get_course_summaries(()) == ()


def test_scoped_represented_records_match_bulk_and_activity_scope(normalized_curriculum) -> None:
    """Scoped represented reads preserve bulk records and honor the active-only projection."""
    _, _, repository = normalized_curriculum
    summaries = repository.list_represented_summaries()
    requested = tuple(record.summary.group_id for record in summaries) + (
        "course-group-future",
        "course-group-absent",
    )

    # The scoped represented getter returns the same shared records as the bulk read for exactly
    # the requested represented identities, omits unrepresented and unknown IDs, honors the activity
    # scope, and returns empty before I/O for an empty scope.
    scoped_represented = repository.get_represented_summaries(requested)
    assert scoped_represented == summaries
    assert repository.get_represented_summaries(()) == ()
    assert repository.get_represented_summaries(("course-group-absent",)) == ()
    assert repository.get_represented_summaries(requested, active_only=True) == tuple(
        record for record in summaries if record.summary.is_active
    )


def test_course_code_identity_projection_includes_all_stored_versions(
    normalized_curriculum,
) -> None:
    """The two-column identity projection includes historical and unrepresented stored versions."""
    _, _, repository = normalized_curriculum

    # The whole-catalogue two-column code projection matches the authoritative distinct stored
    # `(group_id, code)` pairs, including non-representative versions, and orders by group/code.
    code_identities = repository.list_course_code_identities()
    assert set(code_identities) == {
        ("course-group-a", "CS.A1"),
        ("course-group-a", "CS.A2"),
        ("course-group-inactive", "CS.I1"),
        ("course-group-future", "CS.F1"),
        ("course-group-tie", "TIE.A"),
        ("course-group-tie", "TIE.B"),
    }
    assert code_identities == tuple(sorted(code_identities))
    assert repository.list_course_code_identities(active_only=True) == (
        ("course-group-a", "CS.A1"),
        ("course-group-a", "CS.A2"),
    )


def test_scoped_courses_match_full_read(normalized_curriculum) -> None:
    """Scoped full-catalogue course reads agree with their corresponding bulk rows."""
    _, _, repository = normalized_curriculum
    courses = repository.list_courses()
    scoped_courses = repository.get_courses(("course-group-a", "course-group-tie"))
    assert [course.group_id for course in scoped_courses] == ["course-group-a", "course-group-tie"]
    by_group = {course.group_id: course for course in courses}
    assert all(course == by_group[course.group_id] for course in scoped_courses)
    assert repository.get_courses(()) == ()
    assert repository.get_courses(("course-group-absent",)) == ()


def test_activity_projection_matches_canonical_context(normalized_curriculum) -> None:
    """Scoped activity records retain only the canonical activity context and omit absent IDs."""
    _, _, repository = normalized_curriculum
    courses = repository.list_courses()
    by_group = {course.group_id: course for course in courses}

    # The scoped activity projection returns only identity plus the live four-column context.
    activities = repository.get_course_activities(
        ("course-group-a", "course-group-tie", "course-group-absent")
    )
    assert [activity.group_id for activity in activities] == [
        "course-group-a",
        "course-group-tie",
    ]
    for activity in activities:
        canonical = by_group[activity.group_id]
        assert activity.is_active is canonical.is_active
        assert (
            activity.activity_as_of_academic_year_start
            == canonical.activity_as_of_academic_year_start
        )
        assert activity.activity_window_years == canonical.activity_window_years
    inactive_activity = repository.get_course_activities(("course-group-inactive",))
    assert len(inactive_activity) == 1
    assert inactive_activity[0].is_active is False
    assert repository.get_course_activities(()) == ()


def test_scoped_modules_match_full_read(normalized_curriculum) -> None:
    """Scoped module reads equal the corresponding records in the official full read."""
    _, _, repository = normalized_curriculum
    modules = repository.list_modules()
    scoped_modules = repository.get_modules(("module-group-study", "module-group-degree"))
    assert [module.group_id for module in scoped_modules] == [
        "module-group-degree",
        "module-group-study",
    ]
    assert scoped_modules == tuple(
        module
        for module in modules
        if module.group_id in {"module-group-degree", "module-group-study"}
    )
    assert repository.get_modules(()) == ()


def test_module_lookup_identity_projection_matches_full_versions(normalized_curriculum) -> None:
    """The projected module identity read preserves all selected-version fields."""
    _, _, repository = normalized_curriculum
    modules = repository.list_modules()

    # The projected module lookup read returns the same canonical module identities and all
    # version identity/membership fields as the full read, including the grouping module's
    # 2027-only version (candidate selection happens in the service, not the repository).
    module_lookup = repository.list_module_lookup()
    assert [module.group_id for module in module_lookup] == [module.group_id for module in modules]
    modules_by_group = {module.group_id: module for module in modules}
    for projected in module_lookup:
        full = modules_by_group[projected.group_id]
        assert [version.sisu_module_id for version in projected.versions] == [
            version.sisu_module_id for version in full.versions
        ]
        for projected_version, full_version in zip(projected.versions, full.versions, strict=True):
            assert projected_version.module_type == full_version.module_type
            assert projected_version.code == full_version.code
            assert projected_version.name_fi == full_version.name_fi
            assert projected_version.name_en == full_version.name_en
            assert projected_version.validity_start == full_version.validity_start
            assert projected_version.validity_end == full_version.validity_end
            assert projected_version.curriculum_periods == full_version.curriculum_periods


def test_teaching_inputs_match_scoped_representative_texts(normalized_curriculum) -> None:
    """Teaching inputs carry selected official text only for represented identities."""
    _, _, repository = normalized_curriculum
    courses = repository.list_courses()

    # The projected teaching-text input equals the selected official data plus unrepresented IDs
    # while carrying the representative projection, never a full version/prerequisite ORM row.
    inputs = repository.list_teaching_text_inputs()
    assert [entry.group_id for entry in inputs] == sorted(course.group_id for course in courses)
    represented_by_source = {
        entry.representative.sisu_course_unit_id: entry.representative
        for entry in inputs
        if entry.representative is not None
    }
    assert represented_by_source == {
        representative.sisu_course_unit_id: representative
        for representative in repository.get_representative_teaching_texts(
            tuple(represented_by_source)
        )
    }
    assert {entry.group_id for entry in inputs if entry.representative is not None} == {
        course.group_id for course in courses if course.representative is not None
    }
    assert "course-group-future" not in {
        entry.group_id for entry in inputs if entry.representative is not None
    }


def test_projected_reads_avoid_full_orm_and_prerequisite_payloads(normalized_curriculum) -> None:
    """Projected reads match the full reads without loading entities or prerequisite payloads."""
    engine, _, repository = normalized_curriculum
    summaries = repository.list_represented_summaries()
    requested_summary_ids = tuple(record.summary.group_id for record in summaries) + (
        "course-group-future",
        "course-group-absent",
    )
    inputs = repository.list_teaching_text_inputs()
    represented_by_source = {
        entry.representative.sisu_course_unit_id: entry.representative
        for entry in inputs
        if entry.representative is not None
    }
    activities = repository.get_course_activities(
        ("course-group-a", "course-group-tie", "course-group-absent")
    )
    module_lookup = repository.list_module_lookup()
    code_identities = repository.list_course_code_identities()

    # Every shared projected read matches the full read exactly over its selected columns. The shared
    # representative selector's necessary membership/period joins are allowed.
    loaded_full: list[object] = []

    def _record_full(session: Session, instance: object) -> None:
        if isinstance(
            instance,
            (
                Course,
                CourseVersion,
                CourseVersionCurriculumPeriod,
                CourseText,
                Module,
                ModuleRuleNode,
                ModuleVersion,
                ModuleVersionCurriculumPeriod,
                SourceSnapshot,
                OfficialPrerequisiteOption,
                OfficialSubstitutionOption,
            ),
        ):
            loaded_full.append(instance)

    statements: list[str] = []

    def _capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(Session, "loaded_as_persistent", _record_full)
    event.listen(engine, "before_cursor_execute", _capture_sql)
    try:
        repository.list_teaching_courses()
        summaries_window = repository.list_represented_summaries()
        activities_window = repository.get_course_activities(
            ("course-group-a", "course-group-tie", "course-group-absent")
        )
        inputs_window = repository.list_teaching_text_inputs()
        teaching_texts_window = repository.get_representative_teaching_texts(
            tuple(represented_by_source)
        )
        lookup_window = repository.list_module_lookup()
        summary_getter_window = repository.get_course_summaries(requested_summary_ids)
        represented_getter_window = repository.get_represented_summaries(requested_summary_ids)
        code_identity_window = repository.list_course_code_identities()
    finally:
        event.remove(Session, "loaded_as_persistent", _record_full)
        event.remove(engine, "before_cursor_execute", _capture_sql)
    assert loaded_full == []
    assert not any(
        "official_prerequisite" in statement or "official_substitution" in statement
        for statement in statements
    )
    # The projected module lookup never queries rule nodes and loads no module ORM entity.
    assert not any("module_rule" in statement for statement in statements)
    # Each shared projected read returns the same result as before with no full ORM load.
    assert summaries_window == summaries
    assert activities_window == activities
    assert inputs_window == inputs
    assert lookup_window == module_lookup
    assert summary_getter_window == tuple(record.summary for record in summaries)
    assert represented_getter_window == summaries
    assert code_identity_window == code_identities
    assert teaching_texts_window == tuple(
        represented_by_source[source_id] for source_id in sorted(represented_by_source)
    )


def test_teaching_course_projection_matches_full_read_and_activity(normalized_curriculum) -> None:
    """Teaching-course projections retain complete representative parity in both activity scopes."""
    _, _, repository = normalized_curriculum
    courses = repository.list_courses()
    inputs = repository.list_teaching_text_inputs()
    teaching = repository.list_teaching_courses()

    by_group = {course.group_id: course for course in courses}
    text_inputs_by_group = {entry.group_id: entry.representative for entry in inputs}
    assert [course.group_id for course in teaching] == [course.group_id for course in courses]
    for projected in teaching:
        full = by_group[projected.group_id]
        text_input = text_inputs_by_group[projected.group_id]
        assert projected.is_active is full.is_active
        assert (
            projected.activity_as_of_academic_year_start == full.activity_as_of_academic_year_start
        )
        assert projected.activity_window_years == full.activity_window_years
        if full.representative is None:
            assert projected.representative is None
            assert text_input is None
            continue
        assert projected.representative is not None
        assert text_input is not None
        assert (
            projected.representative.sisu_course_unit_id == full.representative.sisu_course_unit_id
        )
        assert projected.representative.source_hash == full.representative.source_hash
        assert projected.representative.code == full.representative.code
        assert projected.representative.name_fi == full.representative.name_fi
        assert projected.representative.name_en == full.representative.name_en
        assert projected.representative.teaching_text == full.representative.teaching_text
        # The coverage/import projection and the teaching-course projection share one
        # loader, so their identity, names, and teaching text agree exactly.
        assert text_input.sisu_course_unit_id == projected.representative.sisu_course_unit_id
        assert text_input.name_fi == projected.representative.name_fi
        assert text_input.name_en == projected.representative.name_en
        assert text_input.teaching_text == projected.representative.teaching_text
    assert [course.group_id for course in repository.list_teaching_courses(active_only=True)] == [
        course.group_id for course in repository.list_courses(active_only=True)
    ]
    assert [course.group_id for course in repository.list_teaching_courses(active_only=False)] == [
        course.group_id for course in repository.list_courses(active_only=False)
    ]
    assert "course-group-inactive" in {course.group_id for course in teaching}
    assert "course-group-future" in {course.group_id for course in teaching}


def test_course_lookup_command_uses_real_summary_projection(
    normalized_curriculum,
) -> None:
    """The course lookup command consumes the actual normalized summary projection."""
    course_report = lookup_command_module.run_course_lookup_command("cs.", display_language="fi")
    assert course_report.query == "cs."
    assert course_report.display_language == "fi"
    assert course_report.include_inactive is True
    assert [summary.group_id for summary in course_report.results] == [
        "course-group-a",
        "course-group-inactive",
    ]
    assert [summary.is_active for summary in course_report.results] == [True, False]
    active_report = lookup_command_module.run_course_lookup_command(
        "cs.", display_language="fi", include_inactive=False
    )
    assert active_report.include_inactive is False
    assert [summary.group_id for summary in active_report.results] == ["course-group-a"]


def test_module_lookup_command_uses_real_identity_projection(
    normalized_curriculum,
) -> None:
    """The module lookup command selects current module identities from the real repository."""
    module_report = lookup_command_module.run_module_lookup_command("DP.A", display_language="en")
    assert module_report.academic_year_start == 2026
    assert module_report.display_language == "en"
    assert [(summary.group_id, summary.sisu_module_id) for summary in module_report.results] == [
        ("module-group-degree", "module-group-degree-v1")
    ]
    assert module_report.results[0].module_type.value == "DegreeProgramme"
    assert module_report.results[0].code == "DP.A"
    assert module_report.results[0].name_en == "Degree"
    assert [
        summary.group_id
        for summary in lookup_command_module.run_module_lookup_command(
            "study", display_language="en"
        ).results
    ] == ["module-group-study"]
    # The grouping module's only version is tied to 2027, so it has no eligible 2026 candidate.
    assert (
        lookup_command_module.run_module_lookup_command("grouping", display_language="en").results
        == ()
    )


def test_catalogue_summary_matches_sql_aggregates(normalized_curriculum) -> None:
    """Catalogue summary counts equal direct SQL aggregates over the normalized database."""
    _, factory, repository = normalized_curriculum

    # The summary fields equal direct SQL counts rather than fixture assumptions.
    summary = repository.summary()
    with factory.begin() as session:
        assert summary.curriculum_period_count == session.scalar(
            select(func.count()).select_from(CurriculumPeriod)
        )
        assert summary.canonical_course_count == session.scalar(
            select(func.count()).select_from(Course)
        )
        assert summary.active_course_count == session.scalar(
            select(func.count()).select_from(Course).where(Course.is_active)
        )
        assert summary.course_version_count == session.scalar(
            select(func.count()).select_from(CourseVersion)
        )
        assert summary.canonical_module_count == session.scalar(
            select(func.count()).select_from(Module)
        )
        assert summary.module_version_count == session.scalar(
            select(func.count()).select_from(ModuleVersion)
        )


def test_resolver_rejects_historical_and_unrepresented_codes(normalized_curriculum) -> None:
    """The code resolver accepts current representatives and rejects historical/absent versions."""
    _, factory, repository = normalized_curriculum

    # Change one nonrepresentative stored version's code in the test DB. The id-or-code resolver
    # must ignore that stored code while admitting the selected representative's code:
    # the two-column projection collects the candidate group, but only the current representative
    # code resolves.
    with factory.begin() as session:
        session.execute(
            update(CourseVersion)
            .where(CourseVersion.sisu_course_unit_id == "course-a-z1")
            .values(code="CS.AOLD")
        )
    lookup = CourseLookupService(repository, settings_factory(SearchSettings))
    representative_resolved = lookup.resolve_courses(("CS.A2",))
    assert [record.summary.group_id for record in representative_resolved] == ["course-group-a"]
    with pytest.raises(ValueError):
        lookup.resolve_courses(("CS.AOLD",))
    # An unrepresented stored code is a projection candidate but has no current representative code,
    # so it is an explicit unknown rather than a crash or a fabricated card.
    with pytest.raises(ValueError):
        lookup.resolve_courses(("CS.F1",))
    historical_projection = repository.list_course_code_identities()
    assert ("course-group-a", "CS.AOLD") in historical_projection
    assert ("course-group-a", "CS.A1") not in historical_projection


def test_prerequisite_graph_expands_normalized_module_rules(
    database: tuple[object, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source-shaped stored module prerequisite draws one identified module node."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    courses = json.loads(fixture_bytes("courses.json"))
    course_a_v2 = next(course for course in courses if course["id"] == "course-a-v2")
    course_a_v2["compulsoryFormalPrerequisites"] = [
        {"prerequisites": [{"type": "Module", "moduleGroupId": "module-group-grouping"}]}
    ]
    modules = json.loads(fixture_bytes("modules.json"))
    grouping = next(module for module in modules if module["id"] == "module-group-grouping-v1")
    grouping["curriculumPeriodIds"] = ["period-2026"]
    degree = next(module for module in modules if module["id"] == "module-group-degree-v1")
    degree["rule"] = {
        "type": "CompositeRule",
        "localId": "degree-root",
        "allMandatory": True,
        "rules": [
            {
                "type": "ModuleRule",
                "localId": "degree-grouping",
                "moduleGroupId": "module-group-grouping",
            }
        ],
    }
    store = build_completed_fixture_store(
        tmp_path,
        capture_repository,
        courses_body=json.dumps(courses, sort_keys=True, separators=(",", ":")).encode(),
        modules_body=json.dumps(modules, sort_keys=True, separators=(",", ":")).encode(),
    )
    normalize_curriculum(
        store,
        NormalizationRepository(factory),
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )

    compiler = PrerequisiteGraphCompiler(
        CurriculumRepository(factory), _NoInferredSetRead(), _NoEquivalenceGroupRead()
    )
    compilation = compiler.compile(
        "course-group-a", include_recommended=False, include_inferred=False
    )
    tree = compilation.tree
    # The root's persisted activity context selects the period-2026 grouping-version membership.
    assert tree.academic_year_start == 2026
    assert "course-group-inactive" in {course.group_id for course in tree.courses}

    # The numeric and unrestricted rule structure is the calculation authority. It is reached
    # through the module boundary, where the module node stands in for the drawing subtree.
    boundary = tree.requirements
    assert isinstance(boundary, ModuleBlockRequirement)
    requirements = boundary.child
    assert isinstance(requirements, CardinalityRequirement)
    assert (requirements.require_min, requirements.require_max) == (1, 3)
    credits = requirements.children[0]
    assert isinstance(credits, CreditRequirement)
    assert (credits.credits_min, credits.credits_max) == (Decimal("5"), None)
    count = credits.child
    assert isinstance(count, CourseCountRequirement)
    assert (count.count_min, count.count_max) == (1, 2)
    # The two unrestricted source rules are ignored in calculation and disclosed, never free positions.
    assert [part.kind.value for part in tree.ignored_parts] == ["free_choice", "free_choice"]

    # The grouping module is one identified module node. Its inactive course-unit member is a card,
    # not a standalone graph node, and the persisted study module's self CourseUnitRule is dropped.
    assert [(occ.occurrence_id, occ.module.group_id) for occ in tree.module_occurrences] == [
        ("r", "module-group-grouping")
    ]
    occurrence = tree.module_occurrences[0]
    assert occurrence.module.sisu_module_id == "module-group-grouping-v1"
    assert occurrence.module.module_type is ModuleType.GROUPING_MODULE
    assert occurrence.module.name_fi == "Ryhmä"
    assert occurrence.module.name_en == "Grouping"
    assert occurrence.member_group_ids == ("course-group-inactive",)
    graph = compilation.graph
    assert [node.course.group_id for node in graph.course_nodes] == ["course-group-a"]
    assert graph.connector_nodes == ()
    assert [node.node_id for node in graph.module_nodes] == ["module:r"]
    assert graph.module_nodes[0].module.group_id == "module-group-grouping"
    assert [card.group_id for card in graph.module_nodes[0].member_courses] == [
        "course-group-inactive"
    ]
    base_edges = [
        (edge.source_node_id, edge.target_node_id)
        for edge in graph.edges
        if not edge.target_node_id.startswith("ignored:")
    ]
    assert base_edges == [("course:course-group-a", "module:r")]
    # The two free-choice leaves are disclosed once and drawn as ignored annotations on the module.
    assert [part.kind.value for part in tree.ignored_parts] == ["free_choice", "free_choice"]
    assert [node.node_id for node in graph.ignored_nodes] == [
        part.part_id for part in tree.ignored_parts
    ]
    assert all(
        edge.source_node_id == "module:r"
        for edge in graph.edges
        if edge.target_node_id.startswith("ignored:")
    )

    # The persisted study module's CourseUnitRule references the immediate owning root course, so
    # its occurrence is dropped before any cycle issue or graph edge: the seeded root holds and no
    # requirement edge targets it.
    assert tree.issues == ()
    assert not any(edge.target_node_id == "course:course-group-a" for edge in graph.edges)

    # The real normalized module tree is unsatisfied: the surviving 5-credit numeric child exceeds the
    # inactive 3-credit member under all-courses scope, so ignoring the unrestricted positions is
    # a no-solution rather than a fabricated zero-cost satisfaction.
    evaluation = evaluate_prerequisite_satisfaction(compilation.tree, [])
    assert evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    # Direct-many associates the same separate category roots on the real module fixture: the
    # compulsory module-rule cardinality is the only enabled pool.
    direct = compiler.compile_direct_many(("course-group-a",), active_only=False)
    assert [entry.tree.root.group_id for entry in direct] == ["course-group-a"]
    direct_entry = direct[0]
    assert direct_entry.required == boundary
    assert direct_entry.recommended is None
    assert (
        evaluate_prerequisite_expression(direct_entry.tree, direct_entry.required, [])
        is PrerequisiteSatisfactionState.UNSATISFIED
    )
    # The inactive 3-credit module member cannot satisfy the stored 5-credit numeric child, so the
    # numeric known-child route is unsatisfied rather than being reported satisfied.
    numeric_child = direct_entry.required.child.children[0]
    assert isinstance(numeric_child, CreditRequirement)
    assert (
        evaluate_prerequisite_expression(
            direct_entry.tree,
            numeric_child,
            ["course-group-inactive"],
        )
        is PrerequisiteSatisfactionState.UNSATISFIED
    )

    # Pathing returns a no-solution for the impossible surviving numeric position and fabricates
    # no course.
    path_result = calculate_minimum_new_credits(compilation.tree, [])
    assert path_result.state is PrerequisitePathState.NO_SOLUTION
    assert path_result.new_courses == ()
    assert path_result.total_new_credits is None
    assert path_result.blockers == ()
    assert path_result.shortfalls == ()

    # The real command composes the same tree and normalized drawing over the real repositories and
    # serializes the module identity/list without any extra report shape.
    monkeypatch.setattr(
        prerequisite_command_module,
        "load_search_settings",
        lambda: settings_factory(SearchSettings),
    )
    report = prerequisite_command_module.run_prerequisite_command("CS.A2")
    assert report.compilation.tree == tree
    command_graph = report.compilation.graph
    assert command_graph.node_states
    assert command_graph.connector_nodes == graph.connector_nodes
    assert command_graph.edges == graph.edges
    assert command_graph.course_nodes == graph.course_nodes
    assert command_graph.module_nodes == graph.module_nodes
    assert "path" not in type(report).model_fields
    payload = json.loads(report.model_dump_json())
    module_payload = payload["compilation"]["graph"]["module_nodes"]
    assert [
        (node["module"]["group_id"], node["module"]["sisu_module_id"]) for node in module_payload
    ] == [("module-group-grouping", "module-group-grouping-v1")]
    assert [card["group_id"] for card in module_payload[0]["member_courses"]] == [
        "course-group-inactive"
    ]
    ignored_payload = payload["compilation"]["tree"]["ignored_parts"]
    assert [part["kind"] for part in ignored_payload] == ["free_choice", "free_choice"]
    assert [node["node_id"] for node in payload["compilation"]["graph"]["ignored_nodes"]] == [
        part["part_id"] for part in ignored_payload
    ]
    assert "path" not in payload

    # The separate explicit route operation returns the same authoritative no-solution result without
    # returning or projecting any second drawing.
    route = prerequisite_command_module.run_minimum_route_command("CS.A2")
    assert route == path_result
    assert route.state is PrerequisitePathState.NO_SOLUTION
    assert route.new_courses == ()
    assert route.total_new_credits is None

    # The structure command reads the same stored degree version over the real repository and
    # projects its official containers, rule kinds and course cards without any graph traversal.
    monkeypatch.setattr(
        study_structure_command_module,
        "load_normalization_settings",
        lambda: settings_factory(NormalizationSettings),
    )
    structure = study_structure_command_module.run_study_structure_command("module-group-degree")
    repository = CurriculumRepository(factory)
    assert structure.academic_year_start == 2026
    degree_root = structure.root
    assert (degree_root.module.group_id, degree_root.module.sisu_module_id) == (
        "module-group-degree",
        "module-group-degree-v1",
    )
    assert degree_root.module.module_type is ModuleType.DEGREE_PROGRAMME
    assert degree_root.target_credits_min == Decimal("180")
    assert degree_root.rule.node_type is ModuleRuleType.COMPOSITE_RULE
    assert degree_root.rule.local_id == "degree-root"
    assert degree_root.rule.all_mandatory is True
    assert len(degree_root.rule.children) == 1
    wrapper = degree_root.rule.children[0]
    assert wrapper.node_type is ModuleRuleType.MODULE_RULE
    assert wrapper.local_id == "degree-grouping"
    assert wrapper.referenced_group_id == "module-group-grouping"
    assert wrapper.module is not None
    grouping_structure = wrapper.module
    assert (grouping_structure.module.group_id, grouping_structure.module.sisu_module_id) == (
        "module-group-grouping",
        "module-group-grouping-v1",
    )
    assert grouping_structure.module.module_type is ModuleType.GROUPING_MODULE
    assert [child.node_type for child in grouping_structure.rule.children] == [
        ModuleRuleType.CREDITS_RULE,
        ModuleRuleType.MODULE_RULE,
        ModuleRuleType.ANY_COURSE_UNIT_RULE,
        ModuleRuleType.ANY_MODULE_RULE,
    ]
    assert (grouping_structure.rule.require_min, grouping_structure.rule.require_max) == (1, 3)
    # The localized official description is not projected into the report.
    assert "description" not in grouping_structure.rule.model_dump()
    credits_node, nested_module, any_course, any_module = grouping_structure.rule.children
    assert (credits_node.credits_min, credits_node.credits_max) == (Decimal("5"), None)
    count_node = credits_node.children[0]
    assert count_node.node_type is ModuleRuleType.COURSE_UNIT_COUNT_RULE
    assert (count_node.count_min, count_node.count_max) == (1, 2)
    inactive_course_node = count_node.children[0]
    assert inactive_course_node.node_type is ModuleRuleType.COURSE_UNIT_RULE
    assert inactive_course_node.course is not None
    assert inactive_course_node.course.group_id == "course-group-inactive"
    assert inactive_course_node.course.is_active is False
    study_structure = nested_module.module
    assert study_structure is not None
    assert study_structure.module.group_id == "module-group-study"
    assert study_structure.rule.node_type is ModuleRuleType.COURSE_UNIT_RULE
    assert study_structure.rule.course is not None
    assert study_structure.rule.course.group_id == "course-group-a"
    assert study_structure.rule.course.is_active is True
    assert any_course.node_type is ModuleRuleType.ANY_COURSE_UNIT_RULE
    assert any_course.unresolved is None
    assert any_module.node_type is ModuleRuleType.ANY_MODULE_RULE
    assert any_module.unresolved is None
    # The member course cards equal the real scoped repository summary projection, in canonical order.
    assert repository.get_course_summaries(("course-group-a", "course-group-inactive")) == (
        study_structure.rule.course,
        inactive_course_node.course,
    )
    assert (
        study_structure_command_module.StudyStructureReport.model_validate_json(
            structure.model_dump_json()
        )
        == structure
    )

    # A bare module root projects the same stored rule directly, with no wrapper degree.
    grouping_report = study_structure_command_module.run_study_structure_command(
        "module-group-grouping"
    )
    assert grouping_report.root.module.group_id == "module-group-grouping"
    assert grouping_report.root.rule.node_type is ModuleRuleType.COMPOSITE_RULE
    assert [child.node_type for child in grouping_report.root.rule.children] == [
        ModuleRuleType.CREDITS_RULE,
        ModuleRuleType.MODULE_RULE,
        ModuleRuleType.ANY_COURSE_UNIT_RULE,
        ModuleRuleType.ANY_MODULE_RULE,
    ]
    bare_study = grouping_report.root.rule.children[1].module
    assert bare_study is not None
    assert bare_study.module.group_id == "module-group-study"
    assert bare_study.rule.course is not None
    assert bare_study.rule.course.group_id == "course-group-a"
