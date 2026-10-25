"""Global inferred equivalence composition as flat alternatives with ordinary path cost."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.enums import PrerequisiteRequirementKind
from course_explorer.prerequisite.domain import (
    InferredPrerequisiteCategory,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from course_explorer.prerequisite.projection import PrerequisiteGraphCompilation
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
    child_uses,
    current_result,
    equivalence_group,
    fact_of,
    inferred_course,
    leaf_group_ids,
    piece_of,
    prerequisite_course_member,
    prerequisite_option,
    substitution_option,
)
from tests.prerequisite._path_support import solve_route


def test_compiler_composes_global_equivalence_as_flat_non_transitive_alternatives() -> None:
    """Exact equivalence groups add flat inferred alternatives with ordinary prerequisite cost."""
    # A has official substitution options and two ordinary prerequisites. B and C are distinct
    # equivalents of A with their own prerequisites and substitutions. Groups A-B, A-C and
    # overlapping B-D are exact and non-transitive.
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
    equivalence_read = RecordingEquivalenceGroupRead(
        {
            "a": (group_b, group_c),
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
    disabled_root = disabled.solver.root_use_id
    assert disabled_root is not None
    assert piece_of(disabled.solver, disabled_root).kind == "course_alternatives"
    disabled_children = child_uses(disabled.solver, disabled_root)
    assert [piece_of(disabled.solver, use).kind for use in disabled_children] == [
        "expanded_course",
        "course",
    ]
    original_disabled, substitution_disabled = disabled_children
    assert fact_of(disabled.solver, disabled_root).origin is PrerequisiteOrigin.COMPOSED
    original_children = child_uses(disabled.solver, original_disabled)
    assert piece_of(disabled.solver, original_children[0]).course_group_id == "a"
    substitution_piece = piece_of(disabled.solver, substitution_disabled)
    substitution_fact = fact_of(disabled.solver, substitution_disabled)
    assert substitution_piece.course_group_id == "a-sub"
    assert substitution_fact.official_kind is OfficialPrerequisiteKind.SUBSTITUTION

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

    enabled_root = enabled.solver.root_use_id
    assert enabled_root is not None
    requirements_piece = piece_of(enabled.solver, enabled_root)
    assert requirements_piece.kind == "course_alternatives"
    assert fact_of(enabled.solver, enabled_root).origin is PrerequisiteOrigin.COMPOSED
    # One flat OR: head branch, official substitution branch, then inferred equivalents in
    # group UUID and member order. A's own branch keeps its own ordinary prerequisite.
    (
        original,
        substitution,
        equivalent_b,
        equivalent_c,
    ) = child_uses(enabled.solver, enabled_root)
    assert piece_of(enabled.solver, original).kind == "expanded_course"
    original_children = child_uses(enabled.solver, original)
    assert piece_of(enabled.solver, original_children[0]).course_group_id == "a"
    assert leaf_group_ids(enabled.solver, original_children[1]) == {"a-prereq"}
    assert piece_of(enabled.solver, substitution).course_group_id == "a-sub"
    assert (
        fact_of(enabled.solver, substitution).official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    )
    leaves = leaf_group_ids(enabled.solver, enabled_root)
    # D's transitive closure is absent.
    assert "d" not in leaves
    # Equivalent heads expand their ordinary prerequisites but never chain their own substitutions
    # or groups: B's b-sub and D are absent, C has no group of its own.
    assert piece_of(enabled.solver, equivalent_b).kind == "expanded_course"
    equivalent_b_children = child_uses(enabled.solver, equivalent_b)
    b_head = piece_of(enabled.solver, equivalent_b_children[0])
    assert b_head.course_group_id == "b"
    assert leaf_group_ids(enabled.solver, equivalent_b_children[1]) == {"b-prereq"}
    assert "b-sub" not in leaves
    c_piece = piece_of(enabled.solver, equivalent_c)
    assert c_piece.kind == "course" and c_piece.course_group_id == "c"

    # Category derivation: a required represented occurrence yields required equivalents.
    assert fact_of(enabled.solver, equivalent_b_children[0]).inferred_category is (
        InferredPrerequisiteCategory.REQUIRED
    )
    assert fact_of(enabled.solver, equivalent_c).inferred_category is (
        InferredPrerequisiteCategory.REQUIRED
    )

    # Provenance is distinct: equivalents are inferred with the group's evidence, the official
    # substitution keeps official provenance, and overlapping groups never merge.
    b_head_fact = fact_of(enabled.solver, equivalent_b_children[0])
    assert b_head_fact.origin is PrerequisiteOrigin.INFERRED
    assert b_head_fact.inference == INFERENCE_METADATA
    assert fact_of(enabled.solver, equivalent_c).inference == INFERENCE_METADATA
    substitution_fact = fact_of(enabled.solver, substitution)
    assert substitution_fact.origin is PrerequisiteOrigin.OFFICIAL
    assert substitution_fact.official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    assert b_head_fact.official_kind is None

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
    recommended_root = recommended.solver.root_use_id
    assert recommended_root is not None
    assert piece_of(recommended.solver, recommended_root).kind == "course_alternatives"
    recommended_children = child_uses(recommended.solver, recommended_root)
    assert len(recommended_children) == 2
    recommended_equivalent = recommended_children[1]
    recommended_piece = piece_of(recommended.solver, recommended_equivalent)
    recommended_fact = fact_of(recommended.solver, recommended_equivalent)
    assert recommended_piece.course_group_id == "recommended-b"
    assert recommended_fact.inferred_category is InferredPrerequisiteCategory.RECOMMENDED

    # Real satisfaction: a basis containing an offered equivalent satisfies A's requirement.
    satisfied_by_b = evaluate_prerequisite_satisfaction(enabled.solver, ["b"])
    assert satisfied_by_b.requirements_state is PrerequisiteSatisfactionState.SATISFIED


def test_compiler_equivalence_alternatives_carry_their_ordinary_path_cost(
    solver_bundle: None,
) -> None:
    """One equivalent's ordinary closure is context-sensitive, so its cost is exact."""
    group = equivalence_group("00000000-0000-0000-0000-000000000010", "a", "d")

    def requires(*group_ids: str) -> tuple:
        return (
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                *(
                    prerequisite_course_member(index, group_id)
                    for index, group_id in enumerate(group_ids)
                ),
            ),
        )

    def build(
        order: tuple[str, str], *, excluded_group_ids: tuple[str, ...] = ()
    ) -> tuple[PrerequisiteGraphCompiler, PrerequisiteGraphCompilation]:
        courses = (
            catalogue_course(
                "root",
                prerequisite_options=(
                    prerequisite_option(
                        0,
                        PrerequisiteRequirementKind.COMPULSORY,
                        prerequisite_course_member(0, order[0]),
                        prerequisite_course_member(1, order[1]),
                    ),
                ),
            ),
            catalogue_course("a", prerequisite_options=requires("c", "z")),
            catalogue_course("b", prerequisite_options=requires("c")),
            catalogue_course("c", prerequisite_options=requires("d")),
            catalogue_course("d"),
            catalogue_course("z"),
        )
        inferred_read = RecordingInferredSetRead(
            {group_id: current_result(group_id) for group_id in ("root", "a", "b", "c", "d", "z")}
        )
        compiler = PrerequisiteGraphCompiler(
            FakeCurriculumRead(courses),
            inferred_read,
            RecordingEquivalenceGroupRead({"a": (group,), "d": (group,)}),
        )
        return compiler, compiler.compile(
            "root", include_inferred=True, excluded_group_ids=excluded_group_ids
        )

    for order in (("a", "b"), ("b", "a")):
        compiler, compilation = build(order)
        solver = compilation.solver
        root_use = solver.root_use_id
        assert root_use is not None

        # The equivalent d covers a's requirements at zero cost, while b pays for c.
        covered = solve_route(solver, ["a"])
        assert covered["state"] == "exact"
        assert [entry["course"]["group_id"] for entry in covered["new_courses"]] == ["b", "c"]
        assert Decimal(covered["total_new_credits"]) == Decimal("10")

        # Without that basis the equivalent's closure holds a viable cycle, so no exact
        # alternative is fabricated from the d branch alone.
        for basis in ((), ("d",)):
            unresolved = solve_route(solver, list(basis))
            assert unresolved["state"] == "unresolved"
            assert unresolved["total_new_credits"] is None
            assert unresolved["new_courses"] == []

        # An excluded basis cannot cover the equivalent, so d is bought instead.
        _, excluded = build(order, excluded_group_ids=("a",))
        excluded_result = solve_route(excluded.solver, ["a"])
        assert excluded_result["state"] == "exact"
        assert [entry["course"]["group_id"] for entry in excluded_result["new_courses"]] == [
            "b",
            "c",
            "d",
        ]
        assert Decimal(excluded_result["total_new_credits"]) == Decimal("15")

        # The a occurrence is the first branch of its alternatives. Its body is the compulsory
        # option over c and z. c is a bare leaf because the mandatory-position rule
        # already forces the one shared c closure through b, so no d alternative is offered here.
        branches = {}
        for root_child in child_uses(solver, root_use):
            branch = (
                child_uses(solver, root_child)[0]
                if piece_of(solver, root_child).kind == "course_alternatives"
                else root_child
            )
            head = piece_of(solver, child_uses(solver, branch)[0])
            branches[head.course_group_id] = branch
        a_body = child_uses(solver, branches["a"])[1]
        c_position = child_uses(solver, a_body)[0]
        assert piece_of(solver, c_position).kind == "course"
        assert piece_of(solver, c_position).course_group_id == "c"

        # On the b branch the same c body offers d's alternatives. The equivalent a
        # branch is inferred, expands a's own ordinary c and z closure, and closes the cycle on c.
        b_body = child_uses(solver, branches["b"])[1]
        c_occurrence = (
            b_body
            if piece_of(solver, b_body).kind == "expanded_course"
            else child_uses(solver, b_body)[0]
        )
        d_alternatives = child_uses(solver, c_occurrence)[1]
        assert piece_of(solver, d_alternatives).kind == "course_alternatives"
        d_alternatives_children = child_uses(solver, d_alternatives)
        assert piece_of(solver, d_alternatives_children[0]).course_group_id == "d"
        inferred_a = d_alternatives_children[1]
        assert piece_of(solver, inferred_a).kind == "expanded_course"
        inferred_a_head = child_uses(solver, inferred_a)[0]
        assert fact_of(solver, inferred_a_head).origin is PrerequisiteOrigin.INFERRED
        assert piece_of(solver, inferred_a_head).course_group_id == "a"
        assert {"c", "z"} <= leaf_group_ids(solver, inferred_a)
        subtree_uses: list[str] = []
        stack = [inferred_a]
        while stack:
            current = stack.pop()
            subtree_uses.append(current)
            stack.extend(child_uses(solver, current))
        assert any(
            piece_of(solver, use).kind == "course"
            and piece_of(solver, use).course_group_id == "c"
            and piece_of(solver, use).cycle_closing
            for use in subtree_uses
        )


def test_compiler_drops_an_equivalent_of_an_ancestor_only_when_inference_is_enabled() -> None:
    """An occurrence equivalent to an ancestor disappears, and inference off reads no group."""

    def requires(group_id: str):
        return (
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, group_id),
            ),
        )

    # root -> a -> p -> e, with a and e in one equivalence group.
    courses = (
        catalogue_course("root", prerequisite_options=requires("a")),
        catalogue_course("a", prerequisite_options=requires("p")),
        catalogue_course("p", prerequisite_options=requires("e")),
        catalogue_course("e"),
    )
    group = equivalence_group("00000000-0000-0000-0000-000000000020", "a", "e")
    equivalence_read = RecordingEquivalenceGroupRead({"a": (group,), "e": (group,)})
    inferred_results = {group_id: current_result(group_id) for group_id in ("root", "a", "p", "e")}
    shared = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        RecordingInferredSetRead(inferred_results),
        equivalence_read,
    )

    enabled = shared.compile("root", include_inferred=True).solver
    equivalence_read.reads.clear()
    equivalence_read.bulk_reads.clear()
    disabled = shared.compile("root").solver

    # e is offered beside a, so a's requirement p keeps its head but drops its own requirement e.
    enabled_root = enabled.root_use_id
    assert enabled_root is not None
    assert piece_of(enabled, enabled_root).kind == "course_alternatives"
    original, equivalent = child_uses(enabled, enabled_root)
    assert piece_of(enabled, equivalent).kind == "course"
    assert piece_of(enabled, equivalent).course_group_id == "e"
    p_position = child_uses(enabled, original)[1]
    assert piece_of(enabled, p_position).kind == "course"
    assert piece_of(enabled, p_position).course_group_id == "p"

    # Inference off: no equivalence read, the same structure as a fresh compiler, and e stays
    # required below p.
    assert equivalence_read.reads == []
    assert equivalence_read.bulk_reads == []
    fresh = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        RecordingInferredSetRead(inferred_results),
        RecordingEquivalenceGroupRead({"a": (group,), "e": (group,)}),
    )
    assert disabled == fresh.compile("root").solver
    disabled_root = disabled.root_use_id
    assert disabled_root is not None
    a_body = child_uses(disabled, disabled_root)[1]
    assert piece_of(disabled, a_body).kind == "expanded_course"
    assert leaf_group_ids(disabled, a_body) == {"p", "e"}
