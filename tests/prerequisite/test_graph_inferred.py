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
    ComposedAndRole,
    ComposedOrRole,
    CreditRequirement,
    InferredPrerequisiteCategory,
    InferredReadState,
    InferredSetCoverage,
    InferredSetReadResult,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
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
    current_result,
    inferred_course,
    module_rule,
    module_version,
    official_course,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
)


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
        return {node.course.group_id for node in compilation.graph.course_nodes}

    # Inference disabled: nothing is read or compiled even when recommended is enabled.
    inferred_read.reads.clear()
    disabled = compiler.compile("root", include_recommended=True)
    assert inferred_read.reads == []
    assert disabled.tree.requirements is None
    assert disabled.tree.inferred_coverage == ()
    assert course_ids(disabled) == {"root"}

    # Inferred only: the required route is read and compiled. Both recommended occurrences are
    # pruned before course expansion, descendant compilation, inferred reads, or issue creation.
    inferred_read.reads.clear()
    inferred_only = compiler.compile("root", include_inferred=True)
    assert inferred_read.reads == ["root", "required-core"]
    assert inferred_only.tree.include_inferred is True
    assert inferred_only.tree.include_recommended is False
    assert inferred_only.tree.requirements == inferred_course("required-core")
    assert course_ids(inferred_only) == {"root", "required-core"}
    assert inferred_only.tree.issues == ()
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
    assert inferred_read.reads == [
        "root",
        "required-core",
        "recommended-only-desc",
        "recommended-parent",
        "recommended-inferred-desc",
    ]
    assert course_ids(both) == {
        "root",
        "required-core",
        "recommended-parent",
        "recommended-only-desc",
        "recommended-inferred-desc",
    }
    assert both.tree.issues == ()


def test_compiler_composes_current_inferred_expressions_and_reports_coverage() -> None:
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
    assert disabled.tree.inferred_coverage == ()
    assert disabled.tree.requirements is None

    enabled = compiler.compile("root", include_inferred=True)
    # Each distinct active expanded target is read exactly once.
    assert inferred_read.reads == ["root", "s", "t"]
    tree = enabled.tree
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
    unavailable_tree = unavailable.compile("root", include_inferred=True).tree
    assert unavailable_tree.requirements is None
    assert unavailable_tree.inferred_coverage == ()
    assert unavailable_tree.issues == ()

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
    stale_tree = stale.compile("root", include_inferred=True).tree
    assert stale_tree.requirements is None
    assert stale_tree.inferred_coverage == ()
    assert stale_tree.issues == ()

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
    assert absent_compilation.tree.requirements is not None
    coverage_targets = {
        record.target_group_id for record in absent_compilation.tree.inferred_coverage
    }
    assert coverage_targets == {"absent-root", "a", "b"}
    assert "absent" not in coverage_targets
    assert absent_compilation.tree.issues == ()
    assert absent_read.reads.count("absent") == 1
    path = calculate_minimum_new_credits(absent_compilation.tree, [], completed_group_ids=[])
    assert path.state is PrerequisitePathState.EXACT
    assert {entry.course.group_id for entry in path.new_courses} in (
        {"a", "absent"},
        {"b", "absent"},
    )


def test_compiler_pools_complete_official_and_inferred_options_by_category() -> None:
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
    assert official_only.tree.requirements == AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.COMPULSORY,
                children=(official_course("a"), official_course("b")),
            ),
            official_course("r", OfficialPrerequisiteKind.RECOMMENDED),
        ),
    )

    compilation = compiler.compile("root", include_recommended=True, include_inferred=True)
    requirements = compilation.tree.requirements
    # Required and recommended remain separate categories joined by one composed logical AND.
    assert isinstance(requirements, AndRequirement)
    assert requirements.origin is PrerequisiteOrigin.COMPOSED
    assert requirements.composed_role is ComposedAndRole.LOGICAL
    required_pool, recommended_pool = requirements.children

    # Required: official AND(A,B) and inferred AND(A,C) are two complete OR alternatives.
    assert isinstance(required_pool, OrRequirement)
    assert required_pool.origin is PrerequisiteOrigin.COMPOSED
    assert required_pool.composed_role is ComposedOrRole.LOGICAL
    official_required, inferred_required = required_pool.children
    assert isinstance(official_required, AndRequirement)
    assert official_required.origin is PrerequisiteOrigin.OFFICIAL
    assert official_required.official_kind is OfficialPrerequisiteKind.COMPULSORY
    assert official_required.children == (official_course("a"), official_course("b"))
    assert isinstance(inferred_required, AndRequirement)
    assert inferred_required.origin is PrerequisiteOrigin.COMPOSED
    assert inferred_required.composed_role is ComposedAndRole.LOGICAL
    assert inferred_required.children == (inferred_course("a"), inferred_course("c"))

    # Recommended: official R and inferred AND(D,E) share one independent composed OR.
    assert isinstance(recommended_pool, OrRequirement)
    assert recommended_pool.origin is PrerequisiteOrigin.COMPOSED
    assert recommended_pool.composed_role is ComposedOrRole.LOGICAL
    official_recommended, inferred_recommended = recommended_pool.children
    assert official_recommended == official_course("r", OfficialPrerequisiteKind.RECOMMENDED)
    assert isinstance(inferred_recommended, AndRequirement)
    assert inferred_recommended.origin is PrerequisiteOrigin.COMPOSED
    assert inferred_recommended.children == (
        inferred_course("d", InferredPrerequisiteCategory.RECOMMENDED),
        inferred_course("e", InferredPrerequisiteCategory.RECOMMENDED),
    )

    # The pool is one alternative per category, not a conjunction of every source option.
    satisfied = evaluate_prerequisite_satisfaction(
        compilation.tree, ["a", "b", "r"], completed_group_ids=["a", "b", "r"]
    )
    assert satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    missing_recommended = evaluate_prerequisite_satisfaction(
        compilation.tree, ["a", "b"], completed_group_ids=["a", "b"]
    )
    assert missing_recommended.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED
    path = calculate_minimum_new_credits(compilation.tree, [], completed_group_ids=[])
    assert path.state is PrerequisitePathState.EXACT
    assert [entry.course.group_id for entry in path.new_courses] == ["a", "b", "r"]
    assert path.total_new_credits == Decimal("15")


def test_compiler_inferred_option_bypasses_official_module_rule() -> None:
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
    official_requirements = official.tree.requirements
    assert isinstance(official_requirements, OrRequirement)
    assert official_requirements.origin is PrerequisiteOrigin.OFFICIAL
    assert official_requirements.official_kind is OfficialPrerequisiteKind.COMPULSORY
    numeric_branch, unresolved_branch = official_requirements.children
    assert isinstance(numeric_branch, ModuleBlockRequirement)
    assert isinstance(numeric_branch.child, CreditRequirement)
    assert isinstance(unresolved_branch, ModuleBlockRequirement)
    assert isinstance(unresolved_branch.child, UnresolvedRequirement)
    assert unresolved_branch.child.reason is UnresolvedPrerequisiteReason.MALFORMED_RULE
    numeric_satisfied = evaluate_prerequisite_satisfaction(
        official.tree, ["a", "b"], completed_group_ids=["a", "b"]
    )
    assert numeric_satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED

    # With inference the complete inferred option joins the same required OR pool, so it bypasses
    # the official numeric branch while the separate malformed official option is explicit.
    enabled = compiler.compile("root", include_inferred=True)
    requirements = enabled.tree.requirements
    assert isinstance(requirements, OrRequirement)
    assert requirements.origin is PrerequisiteOrigin.COMPOSED
    assert requirements.composed_role is ComposedOrRole.LOGICAL
    enabled_numeric, enabled_unresolved, inferred_c = requirements.children
    assert isinstance(enabled_numeric, ModuleBlockRequirement)
    assert isinstance(enabled_numeric.child, CreditRequirement)
    assert isinstance(enabled_unresolved, ModuleBlockRequirement)
    assert isinstance(enabled_unresolved.child, UnresolvedRequirement)
    assert enabled_unresolved.child.reason is UnresolvedPrerequisiteReason.MALFORMED_RULE
    assert inferred_c == inferred_course("c")

    # Completed C alone satisfies the category even though the official route is unknown, but
    # minimum-new-credit with a positive-cost C is unresolved because that unknown route could
    # be cheaper. No fabricated exact answer is returned.
    satisfied = evaluate_prerequisite_satisfaction(enabled.tree, ["c"], completed_group_ids=["c"])
    assert satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    unresolved = calculate_minimum_new_credits(enabled.tree, [], completed_group_ids=[])
    assert unresolved.state is PrerequisitePathState.UNRESOLVED
    assert unresolved.new_courses == ()
    assert any(
        blocker.reason is UnresolvedPrerequisiteReason.MALFORMED_RULE
        for blocker in unresolved.blockers
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
    official_only_requirements = official_only_missing.tree.requirements
    assert isinstance(official_only_requirements, UnresolvedRequirement)
    assert official_only_requirements.reason is UnresolvedPrerequisiteReason.MISSING_MODULE
    assert official_only_missing.tree.ignored_parts == ()
    enabled_missing = missing_compiler.compile("missing-root", include_inferred=True)
    assert enabled_missing.tree.requirements == inferred_course("d")
    assert [part.kind.value for part in enabled_missing.tree.ignored_parts] == [
        "missing_module_alternative"
    ]
