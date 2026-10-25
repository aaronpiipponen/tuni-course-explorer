"""Next-course result-service contracts over the direct compiler."""

from __future__ import annotations

import pytest

from course_explorer.curriculum import CatalogueCurriculumPeriod
from course_explorer.enums import ModuleRuleType, PrerequisiteRequirementKind
from course_explorer.next_courses.service import (
    NextCourseMode,
    evaluate_next_course_outcomes,
    next_courses_from_compilations,
)
from course_explorer.prerequisite.graph import PrerequisiteGraphCompiler
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    current_result,
    equivalence_group,
    ignored_parts,
    inferred_course,
    module_rule,
    module_version,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
    root_summary,
    substitution_option,
)

COMPULSORY = PrerequisiteRequirementKind.COMPULSORY
RECOMMENDED = PrerequisiteRequirementKind.RECOMMENDED
BASIS = ("base",)
_EQUIVALENCE_GROUP_ID = "00000000-0000-0000-0000-0000000000aa"


def _courses():
    """Build one coherent basket of candidate DTOs over the shared fixture builders."""
    return (
        catalogue_course("base"),
        catalogue_course(
            "best",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    COMPULSORY,
                    prerequisite_course_member(0, "base"),
                    prerequisite_course_member(1, "x"),
                ),
                prerequisite_option(1, COMPULSORY, prerequisite_course_member(0, "base")),
            ),
        ),
        catalogue_course(
            "partial",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    COMPULSORY,
                    prerequisite_course_member(0, "base"),
                    prerequisite_course_member(1, "x"),
                ),
            ),
        ),
        catalogue_course(
            "recdep",
            prerequisite_options=(
                prerequisite_option(0, RECOMMENDED, prerequisite_course_member(0, "base")),
            ),
        ),
        catalogue_course(
            "otherdep",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "other")),
            ),
        ),
        catalogue_course("nopre"),
        catalogue_course(
            "inactive",
            is_active=False,
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "base")),
            ),
        ),
        catalogue_course(
            "inactive-dep",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "inactive")),
            ),
        ),
        catalogue_course(
            "sub",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "orig")),
            ),
        ),
        catalogue_course("orig", substitution_options=(substitution_option(0, ("base", None)),)),
        catalogue_course(
            "subpartial",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "orig2")),
            ),
        ),
        catalogue_course(
            "orig2",
            substitution_options=(substitution_option(0, ("base", None), ("sub2", None)),),
        ),
        catalogue_course("sub2"),
        catalogue_course(
            "deepdep",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "deep")),
            ),
        ),
        catalogue_course(
            "deep",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "deep-ancestor")),
            ),
        ),
        catalogue_course("deep-ancestor"),
        catalogue_course(
            "equiv",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_course_member(0, "orig3")),
            ),
        ),
        catalogue_course("orig3"),
        catalogue_course("inferredonly"),
        catalogue_course("x"),
        catalogue_course("other"),
        catalogue_course(
            "freechoice",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_module_member(0, "module-free")),
            ),
        ),
        catalogue_course(
            "missingalt",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_module_member(0, "module-absent")),
                prerequisite_option(1, COMPULSORY, prerequisite_course_member(0, "base")),
            ),
        ),
        catalogue_course(
            "nearest",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_module_member(0, "module-nearest")),
            ),
        ),
        catalogue_course(
            "freeonly",
            prerequisite_options=(
                prerequisite_option(
                    0, COMPULSORY, prerequisite_module_member(0, "module-freeonly")
                ),
            ),
        ),
        catalogue_course(
            "emptyonly",
            prerequisite_options=(prerequisite_option(0, COMPULSORY),),
        ),
        catalogue_course(
            "opaqueonly",
            prerequisite_options=(
                prerequisite_option(0, COMPULSORY, prerequisite_module_member(0, "module-opaque")),
            ),
        ),
        catalogue_course(
            "opaquebasis",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    COMPULSORY,
                    prerequisite_course_member(0, "base"),
                    prerequisite_module_member(1, "module-opaque"),
                ),
            ),
        ),
    )


def _modules():
    """Build module fixtures for free choice, missing alternatives and the nearest fallback."""
    return (
        catalogue_module(
            "module-free",
            (
                module_version(
                    "module-free-v1",
                    rule=module_rule(
                        ModuleRuleType.COMPOSITE_RULE,
                        all_mandatory=True,
                        children=(
                            module_rule(
                                ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="base"
                            ),
                            module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE, sibling_position=1),
                        ),
                    ),
                    curriculum_periods=(
                        CatalogueCurriculumPeriod(id="p2026", academic_year_start=2026),
                    ),
                ),
            ),
        ),
        catalogue_module(
            "module-nearest",
            (
                module_version(
                    "module-nearest-v2027",
                    rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="base"),
                    curriculum_periods=(
                        CatalogueCurriculumPeriod(id="p2027", academic_year_start=2027),
                    ),
                ),
            ),
        ),
        catalogue_module(
            "module-freeonly",
            (
                module_version(
                    "module-freeonly-v1",
                    rule=module_rule(ModuleRuleType.ANY_MODULE_RULE),
                    curriculum_periods=(
                        CatalogueCurriculumPeriod(id="p2026b", academic_year_start=2026),
                    ),
                ),
            ),
        ),
        catalogue_module(
            "module-opaque",
            (
                module_version(
                    "module-opaque-v1",
                    rule=None,
                    curriculum_periods=(
                        CatalogueCurriculumPeriod(id="p2026c", academic_year_start=2026),
                    ),
                    target_credits_min="10",
                ),
            ),
        ),
    )


def _inferred_results():
    """Return one published inferred-only route naming the basis course."""
    return {"inferredonly": current_result("inferredonly", expression=inferred_course("base"))}


def _equivalence_groups():
    """Return one accepted group making the basis course an equivalent of a required source."""
    return {"orig3": (equivalence_group(_EQUIVALENCE_GROUP_ID, "base", "orig3"),)}


def _compile_all(
    courses,
    *,
    include_inferred: bool,
    active_only: bool,
    retained: tuple[str, ...] = (),
    modules=(),
):
    """Compile every supplied candidate through the real direct compiler."""
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, modules),
        RecordingInferredSetRead(_inferred_results()),
        RecordingEquivalenceGroupRead(_equivalence_groups()),
    )
    return compiler.compile_direct_many(
        tuple(course.group_id for course in courses),
        include_inferred=include_inferred,
        active_only=active_only,
        retained_group_ids=retained,
    )


def _discovery_passes(*, active_only: bool = True, retained: tuple[str, ...] = ()):
    """Build the real direct compilations shared by independent discovery proofs."""
    courses = _courses()
    modules = _modules()
    first = _compile_all(
        courses, include_inferred=True, active_only=active_only, retained=retained, modules=modules
    )
    official = _compile_all(
        courses, include_inferred=False, active_only=active_only, retained=retained, modules=modules
    )
    return courses, modules, first, official


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            NextCourseMode.ALL,
            [
                "best",
                "equiv",
                "freechoice",
                "inferredonly",
                "missingalt",
                "nearest",
                "recdep",
                "sub",
            ],
        ),
        (
            NextCourseMode.AT_LEAST_ONE,
            [
                "best",
                "equiv",
                "freechoice",
                "inferredonly",
                "missingalt",
                "nearest",
                "opaquebasis",
                "sub",
                "partial",
                "recdep",
            ],
        ),
    ],
)
def test_next_course_modes_order_eligible_candidates(mode, expected) -> None:
    """Both modes return their ordered candidate identities."""
    _, _, first_pass, official_pass = _discovery_passes()
    results = next_courses_from_compilations(
        first_pass,
        BASIS,
        mode=mode,
        display_language="en",
        official_compilations=official_pass,
    )
    assert [result.course.group_id for result in results] == expected


@pytest.mark.parametrize("mode", [NextCourseMode.ALL, NextCourseMode.AT_LEAST_ONE])
def test_supplied_next_course_outcomes_preserve_results(mode) -> None:
    """A same-input supplied map preserves the result without changing official attribution."""
    _, _, first_pass, official_pass = _discovery_passes()
    results = next_courses_from_compilations(
        first_pass,
        BASIS,
        mode=mode,
        display_language="en",
        official_compilations=official_pass,
    )
    outcomes = evaluate_next_course_outcomes(first_pass, BASIS, mode=mode)
    with_outcomes = next_courses_from_compilations(
        first_pass,
        BASIS,
        mode=mode,
        display_language="en",
        official_compilations=official_pass,
        candidate_outcomes=outcomes,
    )
    assert with_outcomes == results


@pytest.mark.parametrize("mode", [NextCourseMode.ALL, NextCourseMode.AT_LEAST_ONE])
@pytest.mark.parametrize(
    ("group_id", "required", "recommended", "inferred"),
    [
        ("best", 1.0, None, False),
        ("recdep", None, 1.0, False),
        ("sub", 1.0, None, False),
        ("equiv", 1.0, None, True),
        ("inferredonly", 1.0, None, True),
    ],
)
def test_next_course_coverage_and_official_wins_attribution(
    mode, group_id, required, recommended, inferred
) -> None:
    """Required/recommended coverage and relation-local official precedence stay distinct."""
    _, _, first_pass, official_pass = _discovery_passes()
    results = next_courses_from_compilations(
        first_pass,
        BASIS,
        mode=mode,
        display_language="en",
        official_compilations=official_pass,
    )
    by_id = {result.course.group_id: result for result in results}
    assert by_id[group_id].required_coverage == required
    assert by_id[group_id].recommended_coverage == recommended
    assert by_id[group_id].depends_on_inferred is inferred


@pytest.mark.parametrize(
    ("group_id", "ignored_kind"),
    [
        ("freechoice", "free_choice"),
        ("missingalt", "missing_module_alternative"),
        ("nearest", "module_version_fallback"),
    ],
)
def test_next_course_source_shape_slots_preserve_coverage(group_id, ignored_kind) -> None:
    """Free choice, missing module, and nearest-version handling retain real course slots."""
    _, _, first_pass, _ = _discovery_passes()
    results = next_courses_from_compilations(
        first_pass, BASIS, mode=NextCourseMode.ALL, display_language="en"
    )
    by_id = {result.course.group_id: result for result in results}
    assert by_id[group_id].required_coverage == 1.0
    assert by_id[group_id].depends_on_inferred is False
    compilation = next(
        entry for entry in first_pass if root_summary(entry.solver).group_id == group_id
    )
    assert [part.kind for part in ignored_parts(compilation.solver)] == [ignored_kind]


@pytest.mark.parametrize("mode", [NextCourseMode.ALL, NextCourseMode.AT_LEAST_ONE])
def test_next_course_basis_and_uncovered_candidates_are_omitted(mode) -> None:
    """Basis courses and candidates without a satisfiable real prerequisite slot are absent."""
    _, _, first_pass, official_pass = _discovery_passes()
    results = next_courses_from_compilations(
        first_pass,
        BASIS,
        mode=mode,
        display_language="en",
        official_compilations=official_pass,
    )
    proposed = {result.course.group_id for result in results}
    assert {
        "base",
        "nopre",
        "otherdep",
        "orig",
        "orig2",
        "orig3",
        "freeonly",
        "emptyonly",
        "opaqueonly",
    } & proposed == set()
    opaque_only = next(
        entry for entry in first_pass if root_summary(entry.solver).group_id == "opaqueonly"
    )
    assert opaque_only.required_use_id is not None
    if mode is NextCourseMode.AT_LEAST_ONE:
        by_id = {result.course.group_id: result for result in results}
        assert by_id["opaquebasis"].required_coverage == 1.0
        assert by_id["opaquebasis"].depends_on_inferred is False
    else:
        assert "opaquebasis" not in proposed


def test_partial_required_option_qualifies_only_at_least_one() -> None:
    """Partial coverage is eligible only in the at-least-one mode."""
    _, _, first_pass, _ = _discovery_passes()
    results = next_courses_from_compilations(
        first_pass, BASIS, mode=NextCourseMode.AT_LEAST_ONE, display_language="en"
    )
    by_id = {result.course.group_id: result for result in results}
    assert by_id["partial"].required_coverage == 0.5


def test_multi_course_substitution_requires_every_member() -> None:
    """One directional substitution option is covered only when its full AND is satisfied."""
    _, _, first_pass, official_pass = _discovery_passes()
    partial = next_courses_from_compilations(
        first_pass,
        BASIS,
        mode=NextCourseMode.AT_LEAST_ONE,
        display_language="en",
        official_compilations=official_pass,
    )
    assert "subpartial" not in {result.course.group_id for result in partial}
    complete = next_courses_from_compilations(
        first_pass,
        ("base", "sub2"),
        mode=NextCourseMode.AT_LEAST_ONE,
        display_language="en",
        official_compilations=official_pass,
    )
    by_id = {result.course.group_id: result for result in complete}
    assert by_id["subpartial"].required_coverage == 1.0


def test_discovery_basis_does_not_require_ancestor_completion() -> None:
    """An explicitly chosen one-course basis satisfies direct knowledge, not its ancestors."""
    _, _, first_pass, _ = _discovery_passes()
    deep = next_courses_from_compilations(
        first_pass, ("base", "deep"), mode=NextCourseMode.ALL, display_language="en"
    )
    by_id = {result.course.group_id: result for result in deep}
    assert by_id["deepdep"].required_coverage == 1.0
    assert "deep-ancestor" not in by_id


def test_discovery_activity_scope_controls_inactive_candidates() -> None:
    """Active-only omits inactive candidates while all-courses labels them inactive."""
    _, _, active, _ = _discovery_passes()
    _, _, all_courses_first, _ = _discovery_passes(active_only=False)
    active_results = next_courses_from_compilations(
        active, BASIS, mode=NextCourseMode.ALL, display_language="en"
    )
    all_results = next_courses_from_compilations(
        all_courses_first, BASIS, mode=NextCourseMode.ALL, display_language="en"
    )
    assert "inactive" not in {result.course.group_id for result in active_results}
    all_by_id = {result.course.group_id: result for result in all_results}
    assert all_by_id["inactive"].course.is_active is False


def test_inactive_basis_is_retained_and_never_proposed() -> None:
    """An inactive selected foundation satisfies its dependents and is not returned."""
    _, _, retained_first, _ = _discovery_passes(retained=("inactive",))
    retained = next_courses_from_compilations(
        retained_first, ("inactive",), mode=NextCourseMode.ALL, display_language="en"
    )
    retained_ids = {result.course.group_id for result in retained}
    assert "inactive-dep" in retained_ids
    assert "inactive" not in retained_ids
