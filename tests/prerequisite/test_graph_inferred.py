"""Inferred prerequisite compilation, coverage composition, and category pooling."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
)
from course_explorer.enums import (
    InferredCoverageState,
    ModuleRuleType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    InferredPrerequisiteCategory,
    InferredReadState,
    InferredSetCoverage,
    InferredSetReadResult,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionState,
    evaluate_prerequisite_satisfaction,
)
from tests.prerequisite._graph_support import (
    EMPTY_COVERAGE,
    INFERENCE_METADATA,
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    child_uses,
    course_nodes,
    current_result,
    fact_of,
    ignored_parts,
    inferred_course,
    issues,
    module_rule,
    module_version,
    piece_of,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
)
from tests.prerequisite._path_support import solve_route


def test_compiler_filters_inferred_recommended_occurrences_before_descendant_traversal() -> None:
    """An inferred recommended occurrence needs both toggles and is pruned whole when disabled."""
    root_inferred = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=INFERENCE_METADATA,
        children=(
            inferred_course("required-core"),
            # The same canonical course as a recommended occurrence: the two relationships must
            # stay separate and the shared course node must aggregate both path categories.
            inferred_course("required-core", InferredPrerequisiteCategory.RECOMMENDED),
            inferred_course("recommended-parent", InferredPrerequisiteCategory.RECOMMENDED),
        ),
    )
    recommended_parent_inferred = inferred_course("recommended-inferred-desc")
    courses = (
        catalogue_course("root"),
        catalogue_course("required-core"),
        catalogue_course(
            "recommended-parent",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "recommended-only-desc"),
                ),
            ),
        ),
        catalogue_course("recommended-only-desc"),
        catalogue_course("recommended-inferred-desc"),
    )
    inferred_read = RecordingInferredSetRead(
        {
            "root": current_result("root", expression=root_inferred),
            "required-core": current_result("required-core"),
            "recommended-parent": current_result(
                "recommended-parent", expression=recommended_parent_inferred
            ),
            "recommended-only-desc": current_result("recommended-only-desc"),
            "recommended-inferred-desc": current_result("recommended-inferred-desc"),
        }
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), inferred_read, RecordingEquivalenceGroupRead()
    )

    def course_ids(compilation) -> set[str]:
        return {node.course_group_id for node in course_nodes(compilation.display)}

    # Inference disabled: nothing is read or compiled even when recommended is enabled.
    inferred_read.reads.clear()
    disabled = compiler.compile("root", include_recommended=True)
    assert inferred_read.reads == []
    assert disabled.solver.root_use_id is None
    assert disabled.solver.inferred_coverage == ()
    assert course_ids(disabled) == {"root"}

    # Inferred only: the required route is read and compiled. Both recommended occurrences are
    # pruned before course expansion, descendant compilation, inferred reads, or issue creation.
    inferred_read.reads.clear()
    inferred_only = compiler.compile("root", include_inferred=True)
    assert inferred_read.reads == ["root", "required-core"]
    assert inferred_only.solver.include_inferred is True
    assert inferred_only.solver.include_recommended is False
    inferred_root = inferred_only.solver.root_use_id
    assert inferred_root is not None
    inferred_root_piece = piece_of(inferred_only.solver, inferred_root)
    assert inferred_root_piece.kind == "course"
    assert inferred_root_piece.course_group_id == "required-core"
    assert course_ids(inferred_only) == {"root", "required-core"}
    assert issues(inferred_only.solver) == ()
    for hidden in (
        "recommended-parent",
        "recommended-only-desc",
        "recommended-inferred-desc",
    ):
        assert hidden not in inferred_read.reads
        assert hidden not in course_ids(inferred_only)

    # Both toggles: recommended routes and their official/inferred descendants are included.
    inferred_read.reads.clear()
    both = compiler.compile("root", include_recommended=True, include_inferred=True)
    assert sorted(inferred_read.reads) == [
        "recommended-inferred-desc",
        "recommended-only-desc",
        "recommended-parent",
        "required-core",
        "root",
    ]
    assert course_ids(both) == {
        "root",
        "required-core",
        "recommended-parent",
        "recommended-only-desc",
        "recommended-inferred-desc",
    }
    assert issues(both.solver) == ()


def test_compiler_composes_current_inferred_expressions_and_reports_coverage(
    solver_bundle: None,
) -> None:
    """Current contributions keep coverage. Unavailable, stale and absent inputs invent nothing."""
    inferred_expression = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=INFERENCE_METADATA,
        children=(
            AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                inference=INFERENCE_METADATA,
                children=(inferred_course("s"), inferred_course("t")),
            ),
            inferred_course("s"),
        ),
    )
    root_coverage = InferredSetCoverage(
        eligible_source_count=5, processed_source_count=3, accepted_source_count=2
    )
    inferred_read = RecordingInferredSetRead(
        {
            "root": current_result(
                "root",
                expression=inferred_expression,
                coverage_state=InferredCoverageState.PARTIAL,
                coverage=root_coverage,
            ),
            "s": current_result("s"),
            "t": current_result("t"),
        }
    )
    courses = (catalogue_course("root"), catalogue_course("s"), catalogue_course("t"))
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), inferred_read, RecordingEquivalenceGroupRead()
    )

    # Disabled mode performs zero inferred reads and reports empty coverage.
    disabled = compiler.compile("root")
    assert inferred_read.reads == []
    assert disabled.solver.inferred_coverage == ()
    assert disabled.solver.root_use_id is None

    enabled = compiler.compile("root", include_inferred=True)
    # Each distinct active expanded target is read exactly once, in source-index discovery order.
    assert sorted(inferred_read.reads) == ["root", "s", "t"]
    tree = enabled.solver
    assert tree.include_inferred is True
    assert "s" in {summary.group_id for summary in tree.courses}
    assert "t" in {summary.group_id for summary in tree.courses}

    # Coverage is per target: partial root, complete-empty expanded leaves, sorted by ID.
    coverage_by_target = {record.target_group_id: record for record in tree.inferred_coverage}
    assert coverage_by_target["root"].coverage_state is InferredCoverageState.PARTIAL
    assert coverage_by_target["root"].coverage == root_coverage
    assert coverage_by_target["s"].coverage_state is InferredCoverageState.COMPLETE
    assert coverage_by_target["s"].coverage == EMPTY_COVERAGE
    assert coverage_by_target["t"].coverage == EMPTY_COVERAGE
    assert [record.target_group_id for record in tree.inferred_coverage] == ["root", "s", "t"]

    # An unavailable or stale inferred set contributes nothing: no expression, coverage, issue, or
    # fabricated complete-empty record, and the official-only graph compiles.
    unavailable = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), RecordingInferredSetRead(), RecordingEquivalenceGroupRead()
    )
    unavailable_tree = unavailable.compile("root", include_inferred=True).solver
    assert unavailable_tree.root_use_id is None
    assert unavailable_tree.inferred_coverage == ()
    assert issues(unavailable_tree) == ()

    stale_read = RecordingInferredSetRead(
        {
            "root": InferredSetReadResult(
                target_group_id="root",
                state=InferredReadState.STALE_ACTIVITY_CONTEXT,
                stored_activity_as_of_academic_year_start=2025,
                stored_activity_window_years=2,
            )
        }
    )
    stale = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), stale_read, RecordingEquivalenceGroupRead()
    )
    stale_tree = stale.compile("root", include_inferred=True).solver
    assert stale_tree.root_use_id is None
    assert stale_tree.inferred_coverage == ()
    assert issues(stale_tree) == ()

    # A covered root whose two official alternatives share one absent child contributes nothing for
    # the absent child: it is read exactly once, adds no coverage record or issue, and the ordinary
    # official path is exact.
    absent_root_options = (
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "a"),
        ),
        prerequisite_option(
            1,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "b"),
        ),
    )
    absent_child_options = (
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "absent"),
        ),
    )
    absent_courses = (
        catalogue_course("absent-root", prerequisite_options=absent_root_options),
        catalogue_course("a", prerequisite_options=absent_child_options),
        catalogue_course("b", prerequisite_options=absent_child_options),
        catalogue_course("absent"),
    )
    absent_read = RecordingInferredSetRead(
        {
            "absent-root": current_result("absent-root", expression=inferred_course("a")),
            "a": current_result("a"),
            "b": current_result("b"),
        }
    )
    absent_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(absent_courses), absent_read, RecordingEquivalenceGroupRead()
    ).compile("absent-root", include_inferred=True)
    assert absent_compilation.solver.root_use_id is not None
    coverage_targets = {
        record.target_group_id for record in absent_compilation.solver.inferred_coverage
    }
    assert coverage_targets == {"absent-root", "a", "b"}
    assert "absent" not in coverage_targets
    assert issues(absent_compilation.solver) == ()
    assert absent_read.reads.count("absent") == 1
    path = solve_route(absent_compilation.solver, [])
    assert path["state"] == "exact"
    assert {entry["course"]["group_id"] for entry in path["new_courses"]} in (
        {"a", "absent"},
        {"b", "absent"},
    )


def test_compiler_pools_complete_official_and_inferred_options_by_category(
    solver_bundle: None,
) -> None:
    """Same-category official and inferred complete options share one flat OR pool."""
    root_options = (
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "a"),
            prerequisite_course_member(1, "b"),
        ),
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.RECOMMENDED,
            prerequisite_course_member(0, "r"),
        ),
    )
    # The stored root carries both categories: required AND(A,C) and recommended AND(D,E).
    root_inferred = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=INFERENCE_METADATA,
        children=(
            inferred_course("a"),
            inferred_course("c"),
            inferred_course("d", InferredPrerequisiteCategory.RECOMMENDED),
            inferred_course("e", InferredPrerequisiteCategory.RECOMMENDED),
        ),
    )
    courses = (
        catalogue_course("root", prerequisite_options=root_options),
        catalogue_course("a"),
        catalogue_course("b"),
        catalogue_course("c"),
        catalogue_course("r"),
        catalogue_course("d"),
        catalogue_course("e"),
    )
    inferred_read = RecordingInferredSetRead(
        {"root": current_result("root", expression=root_inferred)}
        | {group_id: current_result(group_id) for group_id in ("a", "b", "c", "r", "d", "e")}
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), inferred_read, RecordingEquivalenceGroupRead()
    )

    # Inference disabled keeps the official-only composed AND join.
    official_only = compiler.compile("root", include_recommended=True)
    official_only_root = official_only.solver.root_use_id
    assert official_only_root is not None
    assert piece_of(official_only.solver, official_only_root).kind == "and"
    assert fact_of(official_only.solver, official_only_root).origin is PrerequisiteOrigin.COMPOSED
    official_group, official_recommended_use = child_uses(official_only.solver, official_only_root)
    assert piece_of(official_only.solver, official_group).kind == "and"
    assert (
        fact_of(official_only.solver, official_group).official_kind
        is OfficialPrerequisiteKind.COMPULSORY
    )
    assert [
        piece_of(official_only.solver, use).course_group_id
        for use in child_uses(official_only.solver, official_group)
    ] == ["a", "b"]
    assert (
        fact_of(official_only.solver, official_recommended_use).official_kind
        is OfficialPrerequisiteKind.RECOMMENDED
    )

    compilation = compiler.compile("root", include_recommended=True, include_inferred=True)
    requirements_use = compilation.solver.root_use_id
    assert requirements_use is not None
    assert piece_of(compilation.solver, requirements_use).kind == "and"
    assert fact_of(compilation.solver, requirements_use).origin is PrerequisiteOrigin.COMPOSED
    required_pool, recommended_pool = child_uses(compilation.solver, requirements_use)

    # Required: official AND(A,B) and inferred AND(A,C) are two complete OR alternatives.
    assert piece_of(compilation.solver, required_pool).kind == "or"
    assert fact_of(compilation.solver, required_pool).origin is PrerequisiteOrigin.COMPOSED
    official_required, inferred_required = child_uses(compilation.solver, required_pool)
    assert piece_of(compilation.solver, official_required).kind == "and"
    official_required_fact = fact_of(compilation.solver, official_required)
    assert official_required_fact.origin is PrerequisiteOrigin.OFFICIAL
    assert official_required_fact.official_kind is OfficialPrerequisiteKind.COMPULSORY
    assert [
        piece_of(compilation.solver, use).course_group_id
        for use in child_uses(compilation.solver, official_required)
    ] == ["a", "b"]
    assert piece_of(compilation.solver, inferred_required).kind == "and"
    assert [
        (
            piece_of(compilation.solver, use).course_group_id,
            fact_of(compilation.solver, use).origin,
            fact_of(compilation.solver, use).inferred_category,
        )
        for use in child_uses(compilation.solver, inferred_required)
    ] == [
        ("a", PrerequisiteOrigin.INFERRED, InferredPrerequisiteCategory.REQUIRED),
        ("c", PrerequisiteOrigin.INFERRED, InferredPrerequisiteCategory.REQUIRED),
    ]

    # Recommended: official R and inferred AND(D,E) share one independent composed OR.
    assert piece_of(compilation.solver, recommended_pool).kind == "or"
    assert fact_of(compilation.solver, recommended_pool).origin is PrerequisiteOrigin.COMPOSED
    official_recommended, inferred_recommended = child_uses(compilation.solver, recommended_pool)
    official_recommended_piece = piece_of(compilation.solver, official_recommended)
    assert official_recommended_piece.kind == "course"
    assert official_recommended_piece.course_group_id == "r"
    assert (
        fact_of(compilation.solver, official_recommended).official_kind
        is OfficialPrerequisiteKind.RECOMMENDED
    )
    assert piece_of(compilation.solver, inferred_recommended).kind == "and"
    assert [
        (
            piece_of(compilation.solver, use).course_group_id,
            fact_of(compilation.solver, use).origin,
            fact_of(compilation.solver, use).inferred_category,
        )
        for use in child_uses(compilation.solver, inferred_recommended)
    ] == [
        ("d", PrerequisiteOrigin.INFERRED, InferredPrerequisiteCategory.RECOMMENDED),
        ("e", PrerequisiteOrigin.INFERRED, InferredPrerequisiteCategory.RECOMMENDED),
    ]

    # The pool is one alternative per category, not a conjunction of every source option.
    satisfied = evaluate_prerequisite_satisfaction(compilation.solver, ["a", "b", "r"])
    assert satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    missing_recommended = evaluate_prerequisite_satisfaction(compilation.solver, ["a", "b"])
    assert missing_recommended.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED
    path = solve_route(compilation.solver, [])
    assert path["state"] == "exact"
    assert [entry["course"]["group_id"] for entry in path["new_courses"]] == ["a", "b", "r"]
    assert Decimal(path["total_new_credits"]) == Decimal("15")


def test_compiler_inferred_option_bypasses_official_module_rule(solver_bundle: None) -> None:
    """An inferred option is a complete alternative to an unresolved/numeric official module rule."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-credits"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-unknown"),
            ),
        ),
    )
    modules = (
        catalogue_module(
            "module-credits",
            (
                module_version(
                    "module-credits-v1",
                    rule=module_rule(
                        ModuleRuleType.CREDITS_RULE,
                        credits_min="10",
                        children=(
                            module_rule(
                                ModuleRuleType.COMPOSITE_RULE,
                                all_mandatory=True,
                                children=(
                                    module_rule(
                                        ModuleRuleType.COURSE_UNIT_RULE,
                                        referenced_group_id="a",
                                    ),
                                    module_rule(
                                        ModuleRuleType.COURSE_UNIT_RULE,
                                        sibling_position=1,
                                        referenced_group_id="b",
                                    ),
                                ),
                            ),
                        ),
                    ),
                    curriculum_periods=year_period,
                ),
            ),
        ),
        catalogue_module(
            "module-unknown",
            (
                module_version(
                    "module-unknown-v1",
                    rule=module_rule(
                        ModuleRuleType.COMPOSITE_RULE,
                        require_min=2,
                        require_max=2,
                        children=(
                            module_rule(
                                ModuleRuleType.COURSE_UNIT_RULE,
                                referenced_group_id="c",
                            ),
                        ),
                    ),
                    curriculum_periods=year_period,
                ),
            ),
        ),
    )
    courses = (root, catalogue_course("a"), catalogue_course("b"), catalogue_course("c"))
    inferred_read = RecordingInferredSetRead(
        {
            "root": current_result("root", expression=inferred_course("c")),
            "a": current_result("a"),
            "b": current_result("b"),
            "c": current_result("c"),
        }
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, modules), inferred_read, RecordingEquivalenceGroupRead()
    )

    # Without inference the official numeric and malformed-module options are identical, and A+B
    # satisfies the numeric credit rule exactly.
    official = compiler.compile("root")
    official_requirements = official.solver.root_use_id
    assert official_requirements is not None
    official_piece = piece_of(official.solver, official_requirements)
    official_fact = fact_of(official.solver, official_requirements)
    assert official_piece.kind == "or"
    assert official_fact.origin is PrerequisiteOrigin.OFFICIAL
    assert official_fact.official_kind is OfficialPrerequisiteKind.COMPULSORY
    numeric_branch, unresolved_branch = child_uses(official.solver, official_requirements)
    assert piece_of(official.solver, numeric_branch).kind == "module_block"
    numeric_child = child_uses(official.solver, numeric_branch)[0]
    assert piece_of(official.solver, numeric_child).kind == "credits"
    assert piece_of(official.solver, unresolved_branch).kind == "module_block"
    unresolved_child = child_uses(official.solver, unresolved_branch)[0]
    unresolved_piece = piece_of(official.solver, unresolved_child)
    assert unresolved_piece.kind == "unresolved"
    assert unresolved_piece.reason is UnresolvedPrerequisiteReason.MALFORMED_RULE.value
    numeric_satisfied = evaluate_prerequisite_satisfaction(official.solver, ["a", "b"])
    assert numeric_satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED

    # With inference the complete inferred option joins the same required OR pool, so it bypasses
    # the official numeric branch while the separate malformed official option is explicit.
    enabled = compiler.compile("root", include_inferred=True)
    enabled_requirements = enabled.solver.root_use_id
    assert enabled_requirements is not None
    enabled_piece = piece_of(enabled.solver, enabled_requirements)
    enabled_fact = fact_of(enabled.solver, enabled_requirements)
    assert enabled_piece.kind == "or"
    assert enabled_fact.origin is PrerequisiteOrigin.COMPOSED
    enabled_numeric, enabled_unresolved, inferred_c = child_uses(
        enabled.solver, enabled_requirements
    )
    assert piece_of(enabled.solver, enabled_numeric).kind == "module_block"
    enabled_numeric_child = child_uses(enabled.solver, enabled_numeric)[0]
    assert piece_of(enabled.solver, enabled_numeric_child).kind == "credits"
    assert piece_of(enabled.solver, enabled_unresolved).kind == "module_block"
    enabled_unresolved_child = child_uses(enabled.solver, enabled_unresolved)[0]
    enabled_unresolved_piece = piece_of(enabled.solver, enabled_unresolved_child)
    assert enabled_unresolved_piece.kind == "unresolved"
    assert enabled_unresolved_piece.reason is UnresolvedPrerequisiteReason.MALFORMED_RULE.value
    inferred_c_piece = piece_of(enabled.solver, inferred_c)
    assert inferred_c_piece.kind == "course" and inferred_c_piece.course_group_id == "c"
    assert fact_of(enabled.solver, inferred_c).origin is PrerequisiteOrigin.INFERRED

    # Completed C alone satisfies the category even though the official route is unknown, but
    # minimum-new-credit with a positive-cost C is unresolved because that unknown route could
    # be cheaper. No fabricated exact answer is returned.
    satisfied = evaluate_prerequisite_satisfaction(enabled.solver, ["c"])
    assert satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    unresolved = solve_route(enabled.solver, [])
    assert unresolved["state"] == "unresolved"
    assert unresolved["new_courses"] == []
    assert any(
        blocker["reason"] == UnresolvedPrerequisiteReason.MALFORMED_RULE.value
        for blocker in unresolved["blockers"]
    )

    # An enabled inferred alternative permits dropping a genuinely missing official module, while
    # inference disabled with no usable alternative is unresolved.
    missing_root = catalogue_course(
        "missing-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-absent"),
            ),
        ),
    )
    missing_inferred = RecordingInferredSetRead(
        {
            "missing-root": current_result("missing-root", expression=inferred_course("d")),
            "d": current_result("d"),
        }
    )
    missing_compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead((missing_root, catalogue_course("d")), modules),
        missing_inferred,
        RecordingEquivalenceGroupRead(),
    )
    official_only_missing = missing_compiler.compile("missing-root")
    official_only_root = official_only_missing.solver.root_use_id
    assert official_only_root is not None
    official_only_piece = piece_of(official_only_missing.solver, official_only_root)
    assert official_only_piece.kind == "unresolved"
    assert official_only_piece.reason is UnresolvedPrerequisiteReason.MISSING_MODULE.value
    assert ignored_parts(official_only_missing.solver) == ()
    enabled_missing = missing_compiler.compile("missing-root", include_inferred=True)
    enabled_missing_root = enabled_missing.solver.root_use_id
    assert enabled_missing_root is not None
    enabled_missing_piece = piece_of(enabled_missing.solver, enabled_missing_root)
    assert enabled_missing_piece.kind == "course"
    assert enabled_missing_piece.course_group_id == "d"
    assert fact_of(enabled_missing.solver, enabled_missing_root).origin is (
        PrerequisiteOrigin.INFERRED
    )
    assert [part.kind for part in ignored_parts(enabled_missing.solver)] == [
        "missing_module_alternative"
    ]
