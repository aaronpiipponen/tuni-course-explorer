"""Global inferred equivalence composition as flat alternatives with ordinary path cost."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.enums import PrerequisiteRequirementKind
from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedAndRole,
    ComposedOrRole,
    InferredPrerequisiteCategory,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    expression_course_leaf_group_ids,
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
    INFERENCE_METADATA,
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    course_version,
    current_result,
    equivalence_group,
    inferred_course,
    official_course,
    prerequisite_course_member,
    prerequisite_option,
    substitution_option,
)


def test_compiler_composes_global_equivalence_as_flat_non_transitive_alternatives() -> None:
    """Exact equivalence groups add flat inferred alternatives with ordinary prerequisite cost."""
    # A has official substitution options and two ordinary prerequisites. B and C are distinct
    # equivalents of A with their own prerequisites and substitutions. Groups A-B, A-C and
    # overlapping B-D are exact and non-transitive. A fourth group holds the selected root.
    courses = (
        catalogue_course(
            "root",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "a"),
                ),
            ),
        ),
        catalogue_course(
            "a",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "a-prereq"),
                ),
            ),
            substitution_options=(substitution_option(0, ("a-sub", None)),),
        ),
        catalogue_course(
            "b",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "b-prereq"),
                ),
            ),
            substitution_options=(substitution_option(0, ("b-sub", None)),),
        ),
        catalogue_course("c"),
        catalogue_course("d"),
        catalogue_course("a-prereq"),
        catalogue_course("a-sub"),
        catalogue_course("b-prereq"),
        catalogue_course("b-sub"),
    )
    group_b = equivalence_group("00000000-0000-0000-0000-00000000000b", "a", "b")
    group_c = equivalence_group("00000000-0000-0000-0000-00000000000c", "a", "c")
    group_d = equivalence_group("00000000-0000-0000-0000-00000000000d", "b", "d")
    group_root = equivalence_group("00000000-0000-0000-0000-00000000000e", "a", "root")
    equivalence_read = RecordingEquivalenceGroupRead(
        {
            "a": (group_b, group_c, group_root),
            "b": (group_b, group_d),
        }
    )
    inferred_read = RecordingInferredSetRead(
        {
            "root": current_result("root"),
            "a": current_result("a"),
            "b": current_result("b"),
            "c": current_result("c"),
            "a-prereq": current_result("a-prereq"),
            "a-sub": current_result("a-sub"),
            "b-prereq": current_result("b-prereq"),
        }
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), inferred_read, equivalence_read
    )

    # Inference disabled: the compiler reads the official catalogue and produces the
    # official/substitution output.
    disabled = compiler.compile("root")
    assert equivalence_read.reads == []
    assert inferred_read.reads == []
    disabled_requirements = disabled.tree.requirements
    assert isinstance(disabled_requirements, OrRequirement)
    assert disabled_requirements.origin is PrerequisiteOrigin.COMPOSED
    assert disabled_requirements.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    original_disabled, substitution_disabled = disabled_requirements.children
    assert isinstance(original_disabled, AndRequirement)
    assert substitution_disabled == official_course("a-sub", OfficialPrerequisiteKind.SUBSTITUTION)

    # Inference enabled: every distinct represented course occurrence is read exactly once through
    # the per-compilation cache, and the offered equivalent heads never recurse into their own
    # groups. The selected root's own prerequisites are compiled first step, so it is not read here.
    equivalence_read.reads.clear()
    enabled = compiler.compile("root", include_inferred=True)
    equivalence_requests = [
        *equivalence_read.reads,
        *(group_id for batch in equivalence_read.bulk_reads for group_id in batch),
    ]
    assert sorted(equivalence_requests) == ["a", "a-prereq", "a-sub", "b-prereq"]
    assert len(set(equivalence_requests)) == len(equivalence_requests)
    for absent in ("root", "b", "c", "d"):
        assert absent not in equivalence_requests

    requirements = enabled.tree.requirements
    assert isinstance(requirements, OrRequirement)
    assert requirements.origin is PrerequisiteOrigin.COMPOSED
    assert requirements.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    # One flat OR: head branch, official substitution branch, then inferred equivalents in
    # group UUID and member order. A's own branch keeps its own ordinary prerequisite.
    original, substitution, equivalent_b, equivalent_c = requirements.children
    assert isinstance(original, AndRequirement)
    assert original.composed_role is ComposedAndRole.EXPANDED_COURSE
    assert original.children[0] == official_course("a")
    assert original.children[1] == official_course("a-prereq")
    assert substitution == official_course("a-sub", OfficialPrerequisiteKind.SUBSTITUTION)
    # The selected-root alternative and D's transitive closure are absent.
    assert "root" not in expression_course_leaf_group_ids(requirements)
    assert "d" not in expression_course_leaf_group_ids(requirements)
    # Equivalent heads expand their ordinary prerequisites but never chain their own substitutions
    # or groups: B's b-sub and D are absent, C has no group of its own.
    assert isinstance(equivalent_b, AndRequirement)
    assert equivalent_b.composed_role is ComposedAndRole.EXPANDED_COURSE
    assert equivalent_b.children[0] == inferred_course("b")
    assert equivalent_b.children[1] == official_course("b-prereq")
    assert "b-sub" not in expression_course_leaf_group_ids(requirements)
    assert equivalent_c == inferred_course("c")

    # Category derivation: a required represented occurrence yields required equivalents.
    assert equivalent_b.children[0].inferred_category is InferredPrerequisiteCategory.REQUIRED
    assert equivalent_c.inferred_category is InferredPrerequisiteCategory.REQUIRED

    # Provenance is distinct: equivalents are inferred with the group's evidence, the official
    # substitution keeps official provenance, and overlapping groups never merge.
    assert equivalent_b.children[0].origin is PrerequisiteOrigin.INFERRED
    assert equivalent_b.children[0].inference == INFERENCE_METADATA
    assert equivalent_c.inference == INFERENCE_METADATA
    assert substitution.origin is PrerequisiteOrigin.OFFICIAL
    assert substitution.official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    assert equivalent_b.children[0].official_kind is None

    # Category derivation from a recommended represented occurrence flows to equivalents.
    recommended_read = RecordingInferredSetRead(
        {
            "recommended-root": current_result(
                "recommended-root",
                expression=inferred_course(
                    "recommended-a", InferredPrerequisiteCategory.RECOMMENDED
                ),
            ),
            "recommended-a": current_result("recommended-a"),
            "recommended-b": current_result("recommended-b"),
        }
    )
    recommended_compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                catalogue_course("recommended-root"),
                catalogue_course("recommended-a"),
                catalogue_course("recommended-b"),
            )
        ),
        recommended_read,
        RecordingEquivalenceGroupRead(
            {
                "recommended-a": (
                    equivalence_group(
                        "00000000-0000-0000-0000-00000000000f",
                        "recommended-a",
                        "recommended-b",
                    ),
                )
            }
        ),
    )
    recommended = recommended_compiler.compile(
        "recommended-root", include_recommended=True, include_inferred=True
    )
    recommended_requirements = recommended.tree.requirements
    assert isinstance(recommended_requirements, OrRequirement)
    recommended_equivalent = recommended_requirements.children[1]
    assert recommended_equivalent == inferred_course(
        "recommended-b", InferredPrerequisiteCategory.RECOMMENDED
    )

    # Real satisfaction: a basis containing an offered equivalent satisfies A's requirement.
    satisfied_by_b = evaluate_prerequisite_satisfaction(
        enabled.tree, ["b"], completed_group_ids=["b"]
    )
    assert satisfied_by_b.requirements_state is PrerequisiteSatisfactionState.SATISFIED


def test_compiler_equivalence_alternatives_carry_their_ordinary_path_cost() -> None:
    """Each equivalent head carries its own prerequisite path cost."""
    courses = (
        catalogue_course(
            "root",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "a"),
                ),
            ),
        ),
        # The A branch is dear because of its own ordinary prerequisite.
        catalogue_course(
            "a",
            representative=course_version(
                code="A",
                credits_min="10",
                prerequisite_options=(
                    prerequisite_option(
                        0,
                        PrerequisiteRequirementKind.COMPULSORY,
                        prerequisite_course_member(0, "a-prereq"),
                    ),
                ),
            ),
        ),
        catalogue_course(
            "a-prereq", representative=course_version(code="A-PREQ", credits_min="10")
        ),
        # Equivalent B costs one credit but needs its own two-credit prerequisite.
        catalogue_course(
            "b",
            representative=course_version(
                code="B",
                credits_min="1",
                prerequisite_options=(
                    prerequisite_option(
                        0,
                        PrerequisiteRequirementKind.COMPULSORY,
                        prerequisite_course_member(0, "b-prereq"),
                    ),
                ),
            ),
        ),
        catalogue_course("b-prereq", representative=course_version(code="B-PREQ", credits_min="2")),
    )
    inferred_read = RecordingInferredSetRead(
        {
            "root": current_result("root"),
            "a": current_result("a"),
            "a-prereq": current_result("a-prereq"),
            "b": current_result("b"),
            "b-prereq": current_result("b-prereq"),
        }
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        inferred_read,
        RecordingEquivalenceGroupRead(
            {
                "a": (equivalence_group("00000000-0000-0000-0000-000000000010", "a", "b"),),
            }
        ),
    )
    compilation = compiler.compile("root", include_inferred=True)
    requirements = compilation.tree.requirements
    assert isinstance(requirements, OrRequirement)
    assert requirements.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    original, equivalent = requirements.children
    # The equivalent branch expands B's ordinary prerequisite, so that prerequisite is required.
    assert isinstance(equivalent, AndRequirement)
    assert equivalent.children == (inferred_course("b"), official_course("b-prereq"))
    assert "a-prereq" in expression_course_leaf_group_ids(original)

    # The globally cheapest route is the equivalent branch, paying B plus B's own prerequisite.
    result = calculate_minimum_new_credits(compilation.tree, [], completed_group_ids=[])
    assert result.state is PrerequisitePathState.EXACT
    assert [entry.course.group_id for entry in result.new_courses] == ["b", "b-prereq"]
    assert result.total_new_credits == Decimal("3")

    # A basis containing the equivalent satisfies the occurrence at zero cost, exactly like any
    # completed prerequisite course, without charging B's own historical prerequisite twice.
    partial = calculate_minimum_new_credits(compilation.tree, ["b"], completed_group_ids=["b"])
    assert partial.state is PrerequisitePathState.EXACT
    assert partial.new_courses == ()
    assert partial.total_new_credits == Decimal("0")

    # Excluding the cheap equivalent member forces the dear head route through its own
    # prerequisite rather than charging the excluded course.
    excluded = compiler.compile("root", include_inferred=True, excluded_group_ids=("b",))
    excluded_result = calculate_minimum_new_credits(excluded.tree, [], completed_group_ids=[])
    assert excluded_result.state is PrerequisitePathState.EXACT
    assert [entry.course.group_id for entry in excluded_result.new_courses] == ["a", "a-prereq"]
    assert excluded_result.total_new_credits == Decimal("20")
    assert excluded_result.blocked_excluded_group_ids == ("b",)
