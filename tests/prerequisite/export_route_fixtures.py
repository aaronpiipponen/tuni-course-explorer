"""Write the solver structures the TypeScript route tests read."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from course_explorer.curriculum import CatalogueCurriculumPeriod
from course_explorer.enums import (
    InferredCoverageState,
    ModuleRuleType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedAndRole,
    ComposedOrRole,
    CourseCountRequirement,
    CreditRequirement,
    InferredSetCoverage,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import (
    InferredCoverageRecord,
    PrerequisiteGraphCompiler,
)
from course_explorer.prerequisite.projection import PrerequisiteGraphCompilation
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    course_version,
    module_rule,
    module_version,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
)
from tests.prerequisite._path_support import (
    course_summary,
    expanded_course,
    inferred_course,
    make_compilation,
    module_and,
    module_cardinality,
    module_course,
    module_credits,
    official_and,
    official_course,
    official_or,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "web/src/solver/fixtures"
ACTIVITY_PATH = FIXTURE_DIR / "route-activity.json"
APPROXIMATION_PATH = FIXTURE_DIR / "route-approximation.json"
CONTRACTS_PATH = FIXTURE_DIR / "route-contracts.json"
MINIMUM_PATH = FIXTURE_DIR / "route-minimum.json"
MODULE_FAILURES_PATH = FIXTURE_DIR / "route-module-failures.json"
MODULE_SHORTFALL_PATH = FIXTURE_DIR / "route-module-shortfall.json"
_OPAQUE_YEAR = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)


def entry(
    compilation: PrerequisiteGraphCompilation, *, include_display: bool = False
) -> dict[str, object]:
    """Return one fixture entry for a compilation's solver structure and its opted-in display."""
    return {
        "solver": compilation.solver.model_dump(mode="json"),
        "display": _display(compilation) if include_display else None,
    }


def variant(
    structure: PrerequisiteSolverStructure,
    compilation: PrerequisiteGraphCompilation,
    *,
    include_display: bool = False,
) -> dict[str, object]:
    """Return one fixture entry for a copied structure, with its source compilation's display."""
    return {
        "solver": structure.model_dump(mode="json"),
        "display": _display(compilation) if include_display else None,
    }


def _display(compilation: PrerequisiteGraphCompilation) -> dict[str, object] | None:
    """Return the compilation's drawn display as JSON data, when it has one."""
    return None if compilation.display is None else compilation.display.model_dump(mode="json")


def _compile_opaque_root(root, modules, courses=(), completed_node_keys=()):
    """Compile one real graph fixture used by the opaque-source-work path contracts."""
    return PrerequisiteGraphCompiler(
        FakeCurriculumRead((root, *courses), modules),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile(root.group_id, completed_node_keys=completed_node_keys)


def _opaque_module(group_id: str, rule, *, credits: str | None = None):
    """Build one module fixture with one version in the opaque test year."""
    return catalogue_module(
        group_id,
        (
            module_version(
                f"{group_id}-v1",
                rule=rule,
                curriculum_periods=_OPAQUE_YEAR,
                target_credits_min=credits,
            ),
        ),
    )


def _opaque_course_root(root_id: str, *members):
    """Build one course whose only prerequisite option holds the supplied members."""
    return catalogue_course(
        root_id,
        prerequisite_options=(
            prerequisite_option(0, PrerequisiteRequirementKind.COMPULSORY, *members),
        ),
    )


def build_active_only_path_excludes_inactive_non_basis_candidates_and_uses_eligible_alternatives() -> (
    dict[str, object]
):
    """Build the four structures of the active-only eligibility test."""
    root = course_summary("root")

    required_inactive = make_compilation(
        root,
        official_and("inactive-leaf"),
        (course_summary("inactive-leaf", credits_min="4", is_active=False),),
        active_only=True,
    )

    alternative = make_compilation(
        root,
        official_or("inactive-leaf", "active-alt"),
        (
            course_summary("inactive-leaf", credits_min="1", is_active=False),
            course_summary("active-alt", credits_min="3"),
        ),
        active_only=True,
    )

    retained_basis = make_compilation(
        root,
        official_and("inactive-leaf"),
        (course_summary("inactive-leaf", credits_min="4", is_active=False),),
        active_only=True,
    )

    all_courses = make_compilation(
        root,
        official_and("inactive-leaf"),
        (course_summary("inactive-leaf", credits_min="4", is_active=False),),
    )

    prefix = (
        "active_only_path_excludes_inactive_non_basis_candidates_and_uses_eligible_alternatives"
    )
    return {
        f"{prefix}.required_inactive": entry(required_inactive),
        f"{prefix}.alternative": entry(alternative),
        f"{prefix}.retained_basis": entry(retained_basis),
        f"{prefix}.all_courses": entry(all_courses),
    }


def build_exclusion_selects_other_or_else_no_solution() -> dict[str, object]:
    """Build the two structures of the excluded-OR test."""
    root = course_summary("root")

    alternative = make_compilation(
        root,
        official_or("excluded", "alt"),
        (course_summary("excluded", credits_min="1"), course_summary("alt", credits_min="3")),
        excluded_group_ids=("excluded",),
    )

    only = make_compilation(
        root,
        official_and("excluded"),
        (course_summary("excluded", credits_min="1"),),
        excluded_group_ids=("excluded",),
    )

    prefix = "exclusion_selects_other_or_else_no_solution"
    return {
        f"{prefix}.alternative": entry(alternative),
        f"{prefix}.only": entry(only),
    }


def build_excluded_substitution_option_requires_every_member() -> dict[str, object]:
    """Build the structure of the excluded substitution member test."""
    root = course_summary("root")
    substitution = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(official_course("s1"), official_course("s2")),
    )
    other = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(official_course("other"),),
    )
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.COURSE_ALTERNATIVES,
        children=(official_course("a"), substitution, other),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("a", credits_min="6"),
            course_summary("s1", credits_min="2"),
            course_summary("s2", credits_min="2"),
            course_summary("other", credits_min="8"),
        ),
        excluded_group_ids=("s1",),
    )
    return {"excluded_substitution_option_requires_every_member.compilation": entry(compilation)}


def build_excluded_course_does_not_poison_descendant_on_another_route() -> dict[str, object]:
    """Build the structure of the shared descendant route test."""
    root = course_summary("root")
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            expanded_course("x", official_course("shared")),
            expanded_course("y", official_course("shared")),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("x", credits_min="2"),
            course_summary("y", credits_min="3"),
            course_summary("shared", credits_min="4"),
        ),
        excluded_group_ids=("x",),
    )
    return {
        "excluded_course_does_not_poison_descendant_on_another_route.compilation": entry(
            compilation
        )
    }


def build_shared_problem_locations_retain_every_provenance_fact() -> dict[str, object]:
    """Build the structure of the shared problem location test."""
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            official_course("shared"),
            inferred_course("shared"),
            official_course("keep"),
        ),
    )
    root = course_summary("root")
    compilation = make_compilation(
        root,
        requirements,
        (course_summary("shared"), course_summary("keep")),
        include_inferred=True,
        excluded_group_ids=("shared",),
    )
    return {
        "shared_problem_locations_retain_every_provenance_fact.compilation": entry(
            compilation, include_display=True
        )
    }


def build_minimum_path_preserves_coverage_and_deterministic_ties() -> dict[str, object]:
    """Build the five structures of the coverage and deterministic ties test."""
    root = course_summary("root")

    coverage = (
        InferredCoverageRecord(
            target_group_id="root",
            coverage_state=InferredCoverageState.PARTIAL,
            coverage=InferredSetCoverage(
                eligible_source_count=3,
                processed_source_count=1,
                accepted_source_count=1,
            ),
        ),
    )
    inferred_compilation = make_compilation(
        root,
        inferred_course("z"),
        (course_summary("z", credits_min="2"),),
        include_inferred=True,
        coverage=coverage,
    )

    tie = make_compilation(
        root,
        official_or("a", "b"),
        (
            course_summary("a", credits_min="5", is_active=False),
            course_summary("b", credits_min="5"),
        ),
    )

    stable = make_compilation(
        root,
        official_or("a", "b"),
        (course_summary("a", credits_min="5"), course_summary("b", credits_min="5")),
    )

    opaque = OpaqueCreditRequirement(
        type="opaque_credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        work_key="opaque",
        credits_min=Decimal("5"),
    )
    mixed = make_compilation(
        root,
        OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(official_course("a"), opaque),
        ),
        (course_summary("a", credits_min="5"),),
    )

    shared_work = OpaqueCreditRequirement(
        type="opaque_credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        work_key="shared-work",
        credits_min=Decimal("5"),
    )
    manual_module = ModuleBlockRequirement(
        type="module_block",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        module_group_id="manual",
        child=official_course("member"),
    )
    witness_tie = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(
                shared_work,
                CreditRequirement(
                    type="credits",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    credits_min=Decimal("5"),
                    credits_max=Decimal("5"),
                    child=OrRequirement(
                        type="or",
                        origin=PrerequisiteOrigin.OFFICIAL,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        children=(manual_module, shared_work),
                    ),
                ),
            ),
        ),
        (course_summary("member"),),
    )
    witness_tie_tree = witness_tie.solver.model_copy(
        update={
            "completed_node_keys": (
                next(
                    node.node_id
                    for node in witness_tie.display.nodes
                    if node.kind == "module" and node.module_group_id == "manual"
                ),
            ),
            "pieces": tuple(
                piece.model_copy(update={"manual_credits_min": Decimal("5")})
                if piece.kind == "module_block" and piece.module_group_id == "manual"
                else piece
                for piece in witness_tie.solver.pieces
            ),
        }
    )

    prefix = "minimum_path_preserves_coverage_and_deterministic_ties"
    return {
        f"{prefix}.inferred_compilation": entry(inferred_compilation),
        f"{prefix}.tie": entry(tie),
        f"{prefix}.stable": entry(stable),
        f"{prefix}.mixed": entry(mixed),
        f"{prefix}.witness_tie_tree": variant(witness_tie_tree, witness_tie, include_display=True),
    }


def build_basis_head_satisfies_its_expanded_prerequisites_at_zero_cost() -> dict[str, object]:
    """Build the three structures of the basis head test."""
    root = course_summary("root")
    plain = make_compilation(
        root,
        expanded_course("a", official_course("e")),
        (course_summary("a", credits_min="2"), course_summary("e", credits_min="3")),
    )
    excluded = plain.solver.model_copy(update={"excluded_group_ids": ("root",)})
    shared_tree = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(
                expanded_course("a", official_course("shared")),
                expanded_course("b", official_course("shared")),
            ),
        ),
        (
            course_summary("a", credits_min="2"),
            course_summary("b", credits_min="3"),
            course_summary("shared", credits_min="4"),
        ),
    )
    prefix = "basis_head_satisfies_its_expanded_prerequisites_at_zero_cost"
    return {
        f"{prefix}.plain": entry(plain),
        f"{prefix}.excluded": variant(excluded, plain),
        f"{prefix}.shared_tree": entry(shared_tree),
    }


def build_minimum_path_zero_credit_ties_ignore_tree_variable_order(
    required: str, optional: str
) -> dict[str, object]:
    """Build the two structures of one zero-credit tie parameter."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            OpaqueCreditRequirement(
                type="opaque_credits",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                work_key="mandatory-opaque",
                credits_min=Decimal("2"),
            ),
            official_course(required),
            module_cardinality(0, 1, optional),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary(required, credits_min="1"),
            course_summary(optional, credits_min="0"),
        ),
    )
    reversed_source = make_compilation(
        root,
        requirements.model_copy(update={"children": tuple(reversed(requirements.children))}),
        compilation.solver.courses,
    )
    prefix = "minimum_path_zero_credit_ties_ignore_tree_variable_order"
    suffix = f"[required={required},optional={optional}]"
    return {
        f"{prefix}.compilation{suffix}": entry(compilation),
        f"{prefix}.reversed_source{suffix}": entry(reversed_source),
    }


def build_minimum_path_reconstructs_only_feasible_projected_evidence() -> dict[str, object]:
    """Build the structure of the projected evidence test."""
    root = course_summary("root")
    count_node = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                official_and("shared", "extra"),
                official_course("shared"),
                official_and("shared", "shared"),
            ),
        ),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            expanded_course("head", count_node),
            official_course("shared"),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("head", credits_min="2"),
            course_summary("shared", credits_min="1"),
            course_summary("extra", credits_min="0"),
        ),
    )
    return {
        "minimum_path_reconstructs_only_feasible_projected_evidence.compilation": entry(compilation)
    }


def build_minimum_path_uses_global_union_and_new_credits_not_local_course_count() -> dict[
    str, object
]:
    """Build the three structures of the global union test."""
    root = course_summary("root")

    cheap = official_and("a", "b", "c")
    dear = official_and("d")
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(cheap, dear),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("a", credits_min="1"),
            course_summary("b", credits_min="1"),
            course_summary("c", credits_min="1"),
            course_summary("d", credits_min="10"),
        ),
    )

    overlapping = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_or("a", "b"), official_or("a", "c")),
    )
    overlap_compilation = make_compilation(
        root,
        overlapping,
        (
            course_summary("a", credits_min="2"),
            course_summary("b", credits_min="5"),
            course_summary("c", credits_min="5"),
        ),
    )

    repeated = official_and("a", "a", "b")
    repeated_compilation = make_compilation(
        root,
        repeated,
        (course_summary("a", credits_min="2"), course_summary("b", credits_min="4")),
    )

    prefix = "minimum_path_uses_global_union_and_new_credits_not_local_course_count"
    return {
        f"{prefix}.compilation": entry(compilation),
        f"{prefix}.overlap_compilation": entry(overlap_compilation),
        f"{prefix}.repeated_compilation": entry(repeated_compilation),
    }


def build_minimum_path_expands_new_courses_and_directional_substitutions() -> dict[str, object]:
    """Build the structure of the directional substitution test."""
    root = course_summary("root")

    original_branch = expanded_course("a", official_course("e"))
    option_one = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(
            expanded_course("a1", official_course("e1")),
            official_course("a2", OfficialPrerequisiteKind.SUBSTITUTION),
        ),
    )
    option_two = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(official_course("a3", OfficialPrerequisiteKind.SUBSTITUTION),),
    )
    substitution = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.COURSE_ALTERNATIVES,
        children=(original_branch, option_one, option_two),
    )
    substitution_compilation = make_compilation(
        root,
        substitution,
        (
            course_summary("a", credits_min="10"),
            course_summary("e", credits_min="10"),
            course_summary("a1", credits_min="1"),
            course_summary("e1", credits_min="1"),
            course_summary("a2", credits_min="1"),
            course_summary("a3", credits_min="50"),
        ),
    )
    return {
        "minimum_path_expands_new_courses_and_directional_substitutions.substitution_compilation": entry(
            substitution_compilation
        )
    }


def build_logical_composed_and_charges_every_incomplete_child() -> dict[str, object]:
    """Build the structure of the logical composed AND test."""
    root = course_summary("root")
    logical_and = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(official_course("a"), official_course("b")),
    )
    compilation = make_compilation(
        root,
        logical_and,
        (course_summary("a", credits_min="3"), course_summary("b", credits_min="4")),
    )
    return {"logical_composed_and_charges_every_incomplete_child.compilation": entry(compilation)}


def build_minimum_path_solves_cardinality_credit_and_course_count_on_witnesses() -> dict[
    str, object
]:
    """Build the five structures of the numeric wrapper test."""
    root = course_summary("root")
    cardinality = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=1,
        require_max=2,
        children=(official_course("a"), official_course("b"), official_course("c")),
    )
    cardinality_compilation = make_compilation(
        root,
        cardinality,
        (
            course_summary("a", credits_min="1"),
            course_summary("b", credits_min="2"),
            course_summary("c", credits_min="5"),
        ),
    )

    overlap = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=2,
        require_max=2,
        children=(official_course("a"), official_course("a"), official_course("b")),
    )
    overlap_compilation = make_compilation(
        root,
        overlap,
        (course_summary("a", credits_min="1"), course_summary("b", credits_min="4")),
    )

    neutral = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=0,
        require_max=1,
        children=(official_course("a"),),
    )
    neutral_compilation = make_compilation(root, neutral, (course_summary("a"),))

    credit = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("1"),
        credits_max=Decimal("1"),
        child=expanded_course("a", official_course("e")),
    )
    credit_compilation = make_compilation(
        root,
        credit,
        (
            course_summary("a", credits_min="1", credits_max="99"),
            course_summary("e", credits_min="100", credits_max="999"),
        ),
    )

    count = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=official_or("a", "b"),
    )
    count_compilation = make_compilation(
        root,
        count,
        (course_summary("a", credits_min="3"), course_summary("b", credits_min="2")),
    )

    prefix = "minimum_path_solves_cardinality_credit_and_course_count_on_witnesses"
    return {
        f"{prefix}.cardinality_compilation": entry(cardinality_compilation),
        f"{prefix}.overlap_compilation": entry(overlap_compilation),
        f"{prefix}.neutral_compilation": entry(neutral_compilation),
        f"{prefix}.credit_compilation": entry(credit_compilation),
        f"{prefix}.count_compilation": entry(count_compilation),
    }


def build_minimum_path_reports_unresolved_cycles_and_no_solution() -> dict[str, object]:
    """Build the four structures of the unresolved and no-solution test."""
    root = course_summary("root")

    zero_opaque = make_compilation(
        root,
        OpaqueCreditRequirement(
            type="opaque_credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            work_key="w-zero",
            credits_min=Decimal("0"),
        ),
        (),
    )

    mixed = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            official_course("a"),
            UnresolvedRequirement(
                type="unresolved",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
            ),
        ),
    )
    mixed_compilation = make_compilation(root, mixed, (course_summary("a", credits_min="5"),))

    cycle_compilation = make_compilation(
        root,
        official_and("a", "a"),
        (course_summary("a", credits_min="2"),),
        cycle_group_ids=("a",),
    )

    impossible = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
        child=official_course("a"),
    )
    impossible_compilation = make_compilation(
        root, impossible, (course_summary("a", credits_min="5"),)
    )

    prefix = "minimum_path_reports_unresolved_cycles_and_no_solution"
    return {
        f"{prefix}.zero_opaque": entry(zero_opaque),
        f"{prefix}.mixed_compilation": entry(mixed_compilation),
        f"{prefix}.cycle_compilation": entry(cycle_compilation),
        f"{prefix}.impossible_compilation": entry(impossible_compilation),
    }


def build_minimum_path_handles_large_nested_choice_rules_exactly() -> dict[str, object]:
    """Build the structure of the 27-way nested choice test."""
    root = course_summary("root")
    choice_ids = tuple(f"choice-{index:02d}" for index in range(27))
    requirements = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("3"),
        credits_max=Decimal("3"),
        child=CourseCountRequirement(
            type="course_count",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            count_min=3,
            count_max=3,
            child=module_cardinality(1, None, *choice_ids),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        tuple(course_summary(group_id, credits_min="1") for group_id in choice_ids),
    )
    return {
        "minimum_path_handles_large_nested_choice_rules_exactly.compilation": entry(compilation)
    }


def build_repeated_unexpandable_module_work_is_charged_once() -> dict[str, object]:
    """Build the structure of the repeated unexpandable module test."""
    blank = _opaque_module("module-blank", module_rule(ModuleRuleType.COMPOSITE_RULE), credits="35")
    root = _opaque_course_root(
        "blank-root",
        prerequisite_module_member(0, "module-blank"),
        prerequisite_module_member(1, "module-blank"),
    )
    compilation = _compile_opaque_root(root, (blank,))
    return {"repeated_unexpandable_module_work_is_charged_once.compilation": entry(compilation)}


def build_repeated_bounded_work_keeps_intrinsic_identity_and_occurrences() -> dict[str, object]:
    """Build the structure of the repeated bounded work test."""
    rule = module_rule(
        ModuleRuleType.CREDITS_RULE,
        credits_min="10",
        children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
    )
    module = _opaque_module("module-bounded", rule)
    root = _opaque_course_root(
        "bounded-root",
        prerequisite_module_member(0, "module-bounded"),
        prerequisite_module_member(1, "module-bounded"),
    )
    compilation = _compile_opaque_root(root, (module,))
    return {
        "repeated_bounded_work_keeps_intrinsic_identity_and_occurrences.compilation": entry(
            compilation
        )
    }


def build_distinct_opaque_siblings_are_charged_separately() -> dict[str, object]:
    """Build the structure of the distinct opaque siblings test."""
    rule = module_rule(
        ModuleRuleType.COMPOSITE_RULE,
        all_mandatory=True,
        children=(
            module_rule(
                ModuleRuleType.CREDITS_RULE,
                credits_min="10",
                children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
            ),
            module_rule(
                ModuleRuleType.CREDITS_RULE,
                sibling_position=1,
                credits_min="10",
                children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
            ),
        ),
    )
    module = _opaque_module("module-siblings", rule)
    root = _opaque_course_root("sibling-root", prerequisite_module_member(0, "module-siblings"))
    compilation = _compile_opaque_root(root, (module,))
    return {"distinct_opaque_siblings_are_charged_separately.compilation": entry(compilation)}


def build_resolved_members_cost_courses_not_module_target() -> dict[str, object]:
    """Build the structure of the resolved module member test."""
    module = _opaque_module(
        "module-member",
        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
        credits="35",
    )
    root = _opaque_course_root("member-root", prerequisite_module_member(0, "module-member"))
    compilation = _compile_opaque_root(root, (module,), (catalogue_course("member"),))
    return {"resolved_members_cost_courses_not_module_target.compilation": entry(compilation)}


def build_unknown_course_count_never_fabricates_courses() -> dict[str, object]:
    """Build the structure of the unknown course count test."""
    module = _opaque_module(
        "module-unknown",
        module_rule(
            ModuleRuleType.COURSE_UNIT_COUNT_RULE,
            count_min=1,
            children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
        ),
    )
    root = _opaque_course_root("unknown-root", prerequisite_module_member(0, "module-unknown"))
    compilation = _compile_opaque_root(root, (module,))
    return {"unknown_course_count_never_fabricates_courses.compilation": entry(compilation)}


def build_completed_unknown_extent_fails_positive_credit_bound() -> dict[str, object]:
    """Build the completed unknown extent structure of the bounded completion test."""
    outer = _opaque_module(
        "module-outer",
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="10",
            children=(
                module_rule(
                    ModuleRuleType.CREDITS_RULE,
                    sibling_position=0,
                    credits_min="5",
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
                    ),
                ),
            ),
        ),
    )
    root = _opaque_course_root("outer-root", prerequisite_module_member(0, "module-outer"))
    prepared = _compile_opaque_root(root, (outer,), (catalogue_course("member"),))
    completed_key = next(
        node.node_id
        for node in prepared.display.nodes
        if node.kind == "credits" and node.credits_min == Decimal("5")
    )
    tree = _compile_opaque_root(
        root,
        (outer,),
        (catalogue_course("member"),),
        completed_node_keys=(completed_key,),
    )
    return {"completed_unknown_extent_fails_positive_credit_bound.tree": entry(tree)}


def build_bounded_unknown_extent_with_unpaid_sibling_is_unresolved() -> dict[str, object]:
    """Build the bounded unknown extent structure of the unpaid sibling test."""
    bounded = _opaque_module(
        "module-trivial",
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="5",
            children=(
                module_rule(
                    ModuleRuleType.CREDITS_RULE,
                    sibling_position=0,
                    credits_min="5",
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
                    ),
                ),
            ),
        ),
    )
    root = _opaque_course_root(
        "trivial-root",
        prerequisite_module_member(0, "module-trivial"),
        prerequisite_course_member(1, "unpaid"),
    )
    prepared = _compile_opaque_root(
        root, (bounded,), (catalogue_course("member"), catalogue_course("unpaid"))
    )
    credits_ids = {node.node_id for node in prepared.display.nodes if node.kind == "credits"}
    nested_ids = {
        edge.target_node_id
        for edge in prepared.display.edges
        if edge.source_node_id in credits_ids and edge.target_node_id in credits_ids
    }
    completed_key = next(iter(nested_ids))
    tree = _compile_opaque_root(
        root,
        (bounded,),
        (catalogue_course("member"), catalogue_course("unpaid")),
        completed_node_keys=(completed_key,),
    )
    return {"bounded_unknown_extent_with_unpaid_sibling_is_unresolved.tree": entry(tree)}


def build_known_alternative_survives_unknown_count_option() -> dict[str, object]:
    """Build the structure of the known alternative test."""
    unknown = _opaque_module(
        "module-unknown",
        module_rule(
            ModuleRuleType.COURSE_UNIT_COUNT_RULE,
            count_min=1,
            children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
        ),
    )
    root = catalogue_course(
        "unknown-alt-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "known-alt"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-unknown"),
            ),
        ),
    )
    compilation = _compile_opaque_root(root, (unknown,), (catalogue_course("known-alt"),))
    return {"known_alternative_survives_unknown_count_option.compilation": entry(compilation)}


def build_duplicate_recommended_occurrence_route_matches_a_fixture_without_the_duplicate() -> dict[
    str, object
]:
    """Build both structures of the duplicate recommended occurrence test."""
    duplicated_root = catalogue_course(
        "duplicated-root",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                2, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    without_duplicate_root = catalogue_course(
        "plain-root",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    head = catalogue_course(
        "head",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "head-prereq"),
            ),
        ),
    )
    courses = (duplicated_root, without_duplicate_root, head, catalogue_course("head-prereq"))
    duplicated_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("duplicated-root", include_recommended=True)
    without_duplicate_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("plain-root", include_recommended=True)
    prefix = "duplicate_recommended_occurrence_route_matches_a_fixture_without_the_duplicate"
    return {
        f"{prefix}.duplicated_compilation": entry(duplicated_compilation),
        f"{prefix}.without_duplicate_compilation": entry(without_duplicate_compilation),
    }


def build_path_below_size_limit_preserves_complete_exact_bytes() -> dict[str, object]:
    """Build the structure of the size-limit byte comparison test."""
    root = course_summary("root")
    small = make_compilation(root, official_course("small"), (course_summary("small"),))
    return {"path_below_size_limit_preserves_complete_exact_bytes.small": entry(small)}


def build_scalar_greedy_route_deduplicates_shared_prerequisites_and_opaque_work(
    overlapping_option: bool,
) -> dict[str, object]:
    """Build the structure of one shared-prerequisite greedy parameter."""
    root = course_summary("root")
    heads = tuple(f"head-{index:02d}" for index in range(40))
    choices = []
    for head in heads:
        original = expanded_course(head, official_course("shared"))
        if overlapping_option:
            bait = expanded_course(
                f"bait-{head}",
                AndRequirement(
                    type="and",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.COMPULSORY,
                    children=(official_course("shared"), official_course("shared")),
                ),
            )
            choices.append(
                OrRequirement(
                    type="or",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.COMPULSORY,
                    children=(original, bait),
                )
            )
        else:
            choices.append(original)
    pick = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=20,
        require_max=None,
        children=tuple(choices),
    )
    repeated_opaque = OpaqueCreditRequirement(
        type="opaque_credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        work_key="same-work",
        credits_min=Decimal("5"),
    )
    compilation = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(official_course("shared"), repeated_opaque, repeated_opaque, pick),
        ),
        (
            course_summary("shared", credits_min="3"),
            *(course_summary(head, credits_min="1") for head in heads),
            *(course_summary(f"bait-{head}", credits_min="0.5") for head in heads),
        ),
    )
    prefix = "scalar_greedy_route_deduplicates_shared_prerequisites_and_opaque_work"
    return {f"{prefix}.tree[{overlapping_option}]": entry(compilation)}


def build_path_approximation_extends_greedy_prefixes_for_numeric_bounds(
    pick_minimum: int, duplicate_position: bool
) -> dict[str, object]:
    """Build the structure of one numeric-bound greedy parameter."""
    root = course_summary("root")
    choices = tuple(f"choice-{index:02d}" for index in range(27))
    pick = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=pick_minimum,
        require_max=None,
        children=tuple(
            official_course(choice)
            for choice in (
                (choices[0], choices[0], *choices[1:]) if duplicate_position else choices
            )
        ),
    )
    requirements = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("3"),
        credits_max=Decimal("3"),
        child=CourseCountRequirement(
            type="course_count",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            count_min=3,
            count_max=3,
            child=pick,
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        tuple(course_summary(choice, credits_min="1") for choice in choices),
    )
    prefix = "path_approximation_extends_greedy_prefixes_for_numeric_bounds"
    return {f"{prefix}.tree[{pick_minimum}-{duplicate_position}]": entry(compilation)}


def build_path_approximation_failure_reports_search_too_large_without_a_route(
    limit: int,
) -> dict[str, object]:
    """Build the structure of one approximation-failure limit parameter."""
    root = course_summary("root")
    wide = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=20,
        require_max=20,
        children=tuple(official_course(f"wide-{index:02d}") for index in range(40)),
    )
    numeric_choice = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("3"),
        credits_max=Decimal("3"),
        child=CardinalityRequirement(
            type="cardinality",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            require_min=1,
            require_max=1,
            children=(official_course("cheap"), official_course("dear")),
        ),
    )
    compilation = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(wide, numeric_choice),
        ),
        tuple(course_summary(f"wide-{index:02d}", credits_min="1") for index in range(40))
        + (course_summary("cheap", credits_min="1"), course_summary("dear", credits_min="3")),
    )
    prefix = "path_approximation_failure_reports_search_too_large_without_a_route"
    return {f"{prefix}.tree[{limit}]": entry(compilation)}


def build_scalar_greedy_expanded_head_stops_at_the_basis() -> dict[str, object]:
    """Build the structure of the basis-head greedy test."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(expanded_course("head", official_course("history")), official_course("sibling")),
    )
    compilation = make_compilation(
        root,
        requirements,
        tuple(course_summary(group_id) for group_id in ("head", "history", "sibling")),
    )
    tree = compilation.solver.model_copy(
        update={"completed_node_keys": (), "excluded_node_keys": ()}
    )
    return {"scalar_greedy_expanded_head_stops_at_the_basis.tree": variant(tree, compilation)}


def build_scalar_greedy_route_rejects_unavailable_alternatives(
    denial: str,
) -> dict[str, object]:
    """Build the structure of one unavailable-alternative greedy parameter."""
    root = course_summary("root")
    cheap = (
        ModuleBlockRequirement(
            type="module_block",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            module_group_id="module-cheap",
            child=official_course("cheap"),
        )
        if denial == "excluded_module"
        else official_course("cheap")
    )
    requirements = official_or("dear")
    requirements = requirements.model_copy(update={"children": (cheap, official_course("dear"))})
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("cheap", credits_min="1", is_active=denial != "inactive_course"),
            course_summary("dear", credits_min="4"),
        ),
        active_only=denial == "inactive_course",
    )
    module_key = (
        next(node.node_id for node in compilation.display.nodes if node.kind == "module")
        if denial == "excluded_module"
        else None
    )
    tree = compilation.solver.model_copy(
        update={
            "excluded_group_ids": ("cheap",) if denial == "excluded_course" else (),
            "completed_node_keys": (module_key,) if module_key is not None else (),
            "excluded_node_keys": (module_key,) if module_key is not None else (),
        }
    )
    prefix = "scalar_greedy_route_rejects_unavailable_alternatives"
    return {f"{prefix}.tree[{denial}]": variant(tree, compilation)}


def build_active_module_shortfall_is_activity_only_and_preserves_strict_failures() -> dict[
    str, object
]:
    """Build every structure of the activity-only module failure test."""
    root = course_summary("root")
    inactive_child = course_summary("inactive-b", credits_min="9", is_active=False)
    active_child = course_summary("active-a", credits_min="3")
    all_courses = make_compilation(
        root,
        module_and("active-a", "inactive-b"),
        (active_child, inactive_child),
    )
    ordinary = make_compilation(
        root,
        official_and("inactive-b"),
        (inactive_child,),
        active_only=True,
    )
    impossible = make_compilation(
        root,
        module_credits("60", None, "active-a"),
        (active_child,),
        active_only=True,
    )
    too_high = make_compilation(
        root,
        CourseCountRequirement(
            type="course_count",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            count_min=1,
            count_max=1,
            child=module_and("active-a", "active-b"),
        ),
        (
            course_summary("active-a", credits_min="1"),
            course_summary("active-b", credits_min="1"),
        ),
        active_only=True,
    )
    module_with_unresolved = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                module_course("active-a"),
                UnresolvedRequirement(
                    type="unresolved",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
                ),
            ),
        ),
        (active_child,),
        active_only=True,
    )
    cyclic = make_compilation(
        root,
        module_and("active-a"),
        (active_child,),
        active_only=True,
        cycle_group_ids=("active-a",),
    )
    nested_ordinary = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                expanded_course("active-head", official_course("inactive-tail")),
                module_course("inactive-sibling"),
            ),
        ),
        (
            course_summary("active-head", credits_min="4"),
            course_summary("inactive-tail", credits_min="1", is_active=False),
            course_summary("inactive-sibling", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    numeric_compilation = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("2"),
            credits_max=None,
            child=expanded_course("active-head", official_course("inactive-tail")),
        ),
        (
            course_summary("active-head", credits_min="4"),
            course_summary("inactive-tail", credits_min="1", is_active=False),
            course_summary("inactive-other", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    ordinary_in_module = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        children=(official_course("inactive-b"),),
    )
    outer_credit = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("2"),
            credits_max=None,
            child=ordinary_in_module,
        ),
        (course_summary("inactive-b", credits_min="4", is_active=False),),
        active_only=True,
    )
    exact_wins = make_compilation(
        root,
        OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(
                module_and("inactive-b"),
                official_course("active-a"),
            ),
        ),
        (active_child, inactive_child),
        active_only=True,
    )
    excluded = make_compilation(
        root,
        module_course("module-unit"),
        (course_summary("module-unit", credits_min="4"),),
        active_only=True,
        excluded_group_ids=("module-unit",),
    )
    prefix = "active_module_shortfall_is_activity_only_and_preserves_strict_failures"
    return {
        f"{prefix}.all_courses": entry(all_courses),
        f"{prefix}.ordinary": entry(ordinary),
        f"{prefix}.impossible": entry(impossible),
        f"{prefix}.too_high": entry(too_high),
        f"{prefix}.module_with_unresolved": entry(module_with_unresolved),
        f"{prefix}.cyclic": entry(cyclic),
        f"{prefix}.nested_ordinary": entry(nested_ordinary),
        f"{prefix}.numeric_compilation": entry(numeric_compilation),
        f"{prefix}.outer_credit": entry(outer_credit),
        f"{prefix}.exact_wins": entry(exact_wins),
        f"{prefix}.excluded": entry(excluded),
    }


def build_active_module_shortfall_returns_maximum_for_all_rule_families() -> dict[str, object]:
    """Build every structure of the module shortfall maximum test."""
    root = course_summary("root")
    bare = make_compilation(
        root,
        module_course("inactive-unit"),
        (course_summary("inactive-unit", credits_min="4", is_active=False),),
        active_only=True,
    )
    all_mandatory = make_compilation(
        root,
        module_and("active-a", "inactive-b"),
        (
            course_summary("active-a", credits_min="3"),
            course_summary("inactive-b", credits_min="9", is_active=False),
        ),
        active_only=True,
    )
    nested = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=2,
        require_max=2,
        children=(module_course("active-nested"), module_course("inactive-nested")),
    )
    mixed = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(nested, module_course("inactive-sibling")),
        ),
        (
            course_summary("active-nested", credits_min="4"),
            course_summary("inactive-nested", credits_min="6", is_active=False),
            course_summary("inactive-sibling", credits_min="7", is_active=False),
        ),
        active_only=True,
    )
    nested_only = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                CardinalityRequirement(
                    type="cardinality",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    require_min=2,
                    require_max=2,
                    children=(
                        module_course("active-nested"),
                        module_course("inactive-nested"),
                    ),
                ),
                module_course("active-ok"),
            ),
        ),
        (
            course_summary("active-nested", credits_min="4"),
            course_summary("inactive-nested", credits_min="6", is_active=False),
            course_summary("active-ok", credits_min="2"),
        ),
        active_only=True,
    )
    cardinality = make_compilation(
        root,
        module_cardinality(2, 3, "active-a", "inactive-b", "inactive-c"),
        (
            course_summary("active-a", credits_min="5"),
            course_summary("inactive-b", credits_min="2", is_active=False),
            course_summary("inactive-c", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    credits = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("10"),
            credits_max=None,
            child=OrRequirement(
                type="or",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                children=(
                    expanded_course("active-head", module_course("deep-tail")),
                    module_course("inactive-big"),
                ),
            ),
        ),
        (
            course_summary("active-head", credits_min="4"),
            course_summary("deep-tail", credits_min="100"),
            course_summary("inactive-big", credits_min="12", is_active=False),
        ),
        active_only=True,
    )
    mixed_credit = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("5"),
            credits_max=Decimal("10"),
            child=module_cardinality(1, 1, "credit-low", "credit-high", "credit-fit-inactive"),
        ),
        (
            course_summary("credit-low", credits_min="3"),
            course_summary("credit-high", credits_min="12"),
            course_summary("credit-fit-inactive", credits_min="6", is_active=False),
        ),
        active_only=True,
    )
    course_count = make_compilation(
        root,
        CourseCountRequirement(
            type="course_count",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            count_min=3,
            count_max=None,
            child=AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                children=(
                    module_course("active-a"),
                    module_course("active-b"),
                    module_course("inactive-c"),
                ),
            ),
        ),
        (
            course_summary("active-a", credits_min="2"),
            course_summary("active-b", credits_min="3"),
            course_summary("inactive-c", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    prefix = "active_module_shortfall_returns_maximum_for_all_rule_families"
    return {
        f"{prefix}.bare": entry(bare),
        f"{prefix}.all_mandatory": entry(all_mandatory),
        f"{prefix}.mixed": entry(mixed),
        f"{prefix}.nested_only": entry(nested_only),
        f"{prefix}.cardinality": entry(cardinality),
        f"{prefix}.credits": entry(credits),
        f"{prefix}.mixed_credit": entry(mixed_credit),
        f"{prefix}.course_count": entry(course_count),
    }


def build_zero_minimum_module_bound_preserves_child_activity_shortfall(
    node_type: ModuleRuleType,
) -> dict[str, object]:
    """Build the structure of one zero-minimum module bound parameter."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    numeric_fields = (
        {"credits_min": "0"} if node_type is ModuleRuleType.CREDITS_RULE else {"count_min": 0}
    )
    module = catalogue_module(
        "module-zero",
        (
            module_version(
                "module-zero-v1",
                rule=module_rule(
                    node_type,
                    **numeric_fields,
                    children=(
                        module_rule(
                            ModuleRuleType.COMPOSITE_RULE,
                            require_min=1,
                            require_max=1,
                            children=(
                                module_rule(
                                    ModuleRuleType.COURSE_UNIT_RULE,
                                    referenced_group_id="inactive",
                                ),
                            ),
                        ),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-zero"),
            ),
        ),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((root, catalogue_course("inactive", is_active=False)), (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root", active_only=True, retained_group_ids=("inactive",))
    prefix = "zero_minimum_module_bound_preserves_child_activity_shortfall"
    return {f"{prefix}.compilation[{node_type.value}]": entry(compilation)}


def build_route_activity_tie_counts_only_distinct_new_courses(
    max_compact_nodes: int | None,
) -> dict[str, object]:
    """Build the structures of one route activity tie parameter."""
    root = course_summary("root")

    def solve(requirements, courses):
        return make_compilation(root, requirements, courses)

    cheap = solve(
        official_or("inactive-cheap", "active-dear"),
        (
            course_summary("inactive-cheap", credits_min="1", is_active=False),
            course_summary("active-dear", credits_min="5"),
        ),
    )
    head = expanded_course("head", official_course("inactive-shared"))
    extra = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            expanded_course("head", official_course("inactive-shared")),
            official_course("inactive-extra"),
        ),
    )
    activity_tie = solve(
        OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(head, extra),
        ),
        (
            course_summary("head", credits_min="5"),
            course_summary("inactive-shared", credits_min="5", is_active=False),
            course_summary("inactive-extra", credits_min="0", is_active=False),
        ),
    )
    basis_compilation = make_compilation(
        root,
        official_or("inactive-covered", "active-alternative"),
        (
            course_summary("inactive-covered", credits_min="5", is_active=False),
            course_summary("active-alternative", credits_min="5"),
        ),
    )
    prefix = "route_activity_tie_counts_only_distinct_new_courses"
    suffix = f"[{max_compact_nodes}]"
    return {
        f"{prefix}.compilation{suffix}": entry(cheap),
        f"{prefix}.compilation{suffix}#2": entry(activity_tie),
        f"{prefix}.basis_compilation{suffix}": entry(basis_compilation),
    }


def build_zero_bound_unknown_extent_wrappers_preserve_unpaid_sibling(
    wrapper: str,
) -> dict[str, object]:
    """Build the structure of one zero-bound unknown-extent wrapper parameter."""
    bound_child = module_rule(
        ModuleRuleType.CREDITS_RULE,
        sibling_position=0,
        credits_min="5",
        children=(module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),),
    )
    bound = (
        module_rule(ModuleRuleType.CREDITS_RULE, credits_min="0", children=(bound_child,))
        if wrapper == "credits"
        else module_rule(
            ModuleRuleType.COURSE_UNIT_COUNT_RULE, count_min=0, children=(bound_child,)
        )
    )
    trivial = _opaque_module("module-trivial", bound)
    root = _opaque_course_root(
        "trivial-root",
        prerequisite_module_member(0, "module-trivial"),
        prerequisite_course_member(1, "unpaid"),
    )
    prepared = _compile_opaque_root(
        root, (trivial,), (catalogue_course("member"), catalogue_course("unpaid"))
    )
    completed_key = next(
        node.node_id
        for node in prepared.display.nodes
        if node.kind == "credits" and node.credits_min == Decimal("5")
    )
    tree = _compile_opaque_root(
        root,
        (trivial,),
        (catalogue_course("member"), catalogue_course("unpaid")),
        completed_node_keys=(completed_key,),
    )
    prefix = "zero_bound_unknown_extent_wrappers_preserve_unpaid_sibling"
    return {f"{prefix}.tree[{wrapper}]": entry(tree)}


def build_known_completed_extent_satisfies_credit_bound_without_member_courses(
    completed_kind: str,
) -> dict[str, object]:
    """Build the structure of one known completed extent parameter."""
    inner = _opaque_module(
        "module-known",
        (
            module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member")
            if completed_kind == "module"
            else module_rule(
                ModuleRuleType.CREDITS_RULE,
                credits_min="10",
                children=(
                    module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
                ),
            )
        ),
        credits="10",
    )
    outer = _opaque_module(
        "module-known-outer",
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="10",
            children=(module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-known"),),
        ),
        credits="10",
    )
    root = _opaque_course_root(
        "known-root",
        prerequisite_module_member(0, "module-known-outer"),
        prerequisite_course_member(1, "unpaid"),
    )
    compilation = _compile_opaque_root(
        root,
        (inner, outer),
        (catalogue_course("member"), catalogue_course("unpaid")),
    )
    module_node_id = next(
        node.node_id
        for node in compilation.display.nodes
        if node.kind == "module" and node.module_group_id == "module-known-outer"
    )
    if completed_kind == "module":
        completed_key = module_node_id
    else:
        module_edges = {
            (edge.source_node_id, edge.target_node_id)
            for edge in compilation.display.edges
            if edge.source_node_id == module_node_id
        }
        completed_key = next(
            node.node_id
            for node in compilation.display.nodes
            if node.kind == "credits" and (module_node_id, node.node_id) in module_edges
        )
    tree = _compile_opaque_root(
        root,
        (inner, outer),
        (catalogue_course("member"), catalogue_course("unpaid")),
        completed_node_keys=(completed_key,),
    )
    prefix = "known_completed_extent_satisfies_credit_bound_without_member_courses"
    return {f"{prefix}.tree[{completed_kind}]": entry(tree)}


def build_route_nodes_follow_selected_members() -> dict[str, object]:
    """Build the structure whose two modules share a hidden member with one external prerequisite."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module_m1 = catalogue_module(
        "M1",
        (
            module_version(
                "M1-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="P"),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    module_m2 = catalogue_module(
        "M2",
        (
            module_version(
                "M2-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="P"),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=1,
                            referenced_group_id="R",
                        ),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "M1"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "M2"),
            ),
        ),
    )
    member_p = catalogue_course(
        "P",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "Q"),
            ),
        ),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (root, member_p, catalogue_course("Q"), catalogue_course("R")),
            (module_m1, module_m2),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")
    return {
        "route_nodes_follow_selected_members.compilation": entry(compilation, include_display=True)
    }


def build_coherent_route_occurrences() -> dict[str, object]:
    """Build the equal-cost and module-local structures of the coherent occurrence tests."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)

    def module_with_body(group_id: str, body):
        return catalogue_module(
            group_id,
            (
                module_version(
                    f"{group_id}-v1",
                    rule=module_rule(
                        ModuleRuleType.COMPOSITE_RULE,
                        all_mandatory=True,
                        children=body,
                    ),
                    curriculum_periods=year_period,
                ),
            ),
        )

    equal_p = catalogue_course(
        "P",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "Q"),
            ),
        ),
    )
    equal_root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "M1"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "M2"),
            ),
        ),
    )
    equal_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (equal_root, equal_p, catalogue_course("Q")),
            (
                module_with_body(
                    "M1",
                    (module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="P"),),
                ),
                module_with_body(
                    "M2",
                    (module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="P"),),
                ),
            ),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")

    pick = module_rule(
        ModuleRuleType.COMPOSITE_RULE,
        require_min=1,
        require_max=1,
        children=(
            module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="P"),
            module_rule(
                ModuleRuleType.COURSE_UNIT_RULE,
                sibling_position=1,
                referenced_group_id="Q",
            ),
        ),
    )
    local_root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "M1"),
                prerequisite_module_member(1, "M2"),
            ),
        ),
    )
    local_p = catalogue_course(
        "P",
        representative=course_version(
            code="P",
            credits_min="3",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "X"),
                ),
            ),
        ),
    )
    local_q = catalogue_course(
        "Q",
        representative=course_version(
            code="Q",
            credits_min="5",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "Y"),
                ),
            ),
        ),
    )
    local_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (local_root, local_p, local_q, catalogue_course("X"), catalogue_course("Y")),
            (
                module_with_body(
                    "M1",
                    (
                        module_rule(
                            ModuleRuleType.CREDITS_RULE,
                            credits_min="3",
                            credits_max="4",
                            children=(pick,),
                        ),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=1,
                            referenced_group_id="X",
                        ),
                    ),
                ),
                module_with_body(
                    "M2",
                    (
                        module_rule(
                            ModuleRuleType.CREDITS_RULE,
                            credits_min="5",
                            children=(pick,),
                        ),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=1,
                            referenced_group_id="Y",
                        ),
                    ),
                ),
            ),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")

    return {
        "coherent_route_occurrences.equal": entry(equal_compilation, include_display=True),
        "coherent_route_occurrences.local": entry(local_compilation, include_display=True),
    }


def activity_structures() -> dict[str, object]:
    """Build every structure of the activity, exclusion and shared problem tests."""
    structures: dict[str, object] = {}
    for build in (
        build_active_only_path_excludes_inactive_non_basis_candidates_and_uses_eligible_alternatives,
        build_exclusion_selects_other_or_else_no_solution,
        build_excluded_substitution_option_requires_every_member,
        build_excluded_course_does_not_poison_descendant_on_another_route,
        build_shared_problem_locations_retain_every_provenance_fact,
    ):
        structures.update(build())
    return structures


def contract_structures() -> dict[str, object]:
    """Build every structure of the coverage, tie and evidence contract tests."""
    structures: dict[str, object] = {}
    for build in (
        build_minimum_path_preserves_coverage_and_deterministic_ties,
        build_basis_head_satisfies_its_expanded_prerequisites_at_zero_cost,
        build_minimum_path_reconstructs_only_feasible_projected_evidence,
        build_route_nodes_follow_selected_members,
        build_coherent_route_occurrences,
    ):
        structures.update(build())
    for required, optional, _expected in (("z", "a", ("a", "z")), ("a", "z", ("a",))):
        structures.update(
            build_minimum_path_zero_credit_ties_ignore_tree_variable_order(required, optional)
        )
    for max_compact_nodes in (None, 1):
        structures.update(
            build_route_activity_tie_counts_only_distinct_new_courses(max_compact_nodes)
        )
    return structures


def minimum_structures() -> dict[str, object]:
    """Build every structure of the minimum route tests."""
    structures: dict[str, object] = {}
    for build in (
        build_minimum_path_uses_global_union_and_new_credits_not_local_course_count,
        build_minimum_path_expands_new_courses_and_directional_substitutions,
        build_logical_composed_and_charges_every_incomplete_child,
        build_minimum_path_solves_cardinality_credit_and_course_count_on_witnesses,
        build_minimum_path_reports_unresolved_cycles_and_no_solution,
        build_minimum_path_handles_large_nested_choice_rules_exactly,
        build_repeated_unexpandable_module_work_is_charged_once,
        build_repeated_bounded_work_keeps_intrinsic_identity_and_occurrences,
        build_distinct_opaque_siblings_are_charged_separately,
        build_resolved_members_cost_courses_not_module_target,
        build_unknown_course_count_never_fabricates_courses,
        build_completed_unknown_extent_fails_positive_credit_bound,
        build_bounded_unknown_extent_with_unpaid_sibling_is_unresolved,
        build_known_alternative_survives_unknown_count_option,
        build_duplicate_recommended_occurrence_route_matches_a_fixture_without_the_duplicate,
    ):
        structures.update(build())
    for wrapper in ("credits", "count"):
        structures.update(build_zero_bound_unknown_extent_wrappers_preserve_unpaid_sibling(wrapper))
    for completed_kind in ("module", "credit_rule"):
        structures.update(
            build_known_completed_extent_satisfies_credit_bound_without_member_courses(
                completed_kind
            )
        )
    return structures


def approximation_structures() -> dict[str, object]:
    """Build every structure of the approximation and greedy tests."""
    structures: dict[str, object] = {}
    structures.update(build_path_below_size_limit_preserves_complete_exact_bytes())
    for overlapping_option in (False, True):
        structures.update(
            build_scalar_greedy_route_deduplicates_shared_prerequisites_and_opaque_work(
                overlapping_option
            )
        )
    for pick_minimum, duplicate_position in ((0, False), (1, False), (1, True)):
        structures.update(
            build_path_approximation_extends_greedy_prefixes_for_numeric_bounds(
                pick_minimum, duplicate_position
            )
        )
    for limit in (1, 10000):
        structures.update(
            build_path_approximation_failure_reports_search_too_large_without_a_route(limit)
        )
    structures.update(build_scalar_greedy_expanded_head_stops_at_the_basis())
    for denial in ("excluded_course", "excluded_module", "inactive_course"):
        structures.update(build_scalar_greedy_route_rejects_unavailable_alternatives(denial))
    return structures


def module_failure_structures() -> dict[str, object]:
    """Build the structures of the activity-only module failure test."""
    return build_active_module_shortfall_is_activity_only_and_preserves_strict_failures()


def module_shortfall_structures() -> dict[str, object]:
    """Build every structure of the module shortfall tests."""
    structures = build_active_module_shortfall_returns_maximum_for_all_rule_families()
    for node_type in (
        ModuleRuleType.CREDITS_RULE,
        ModuleRuleType.COURSE_UNIT_COUNT_RULE,
    ):
        structures.update(
            build_zero_minimum_module_bound_preserves_child_activity_shortfall(node_type)
        )
    return structures


def write_payload(path: Path, payload: dict[str, object]) -> None:
    """Write one fixture file as sorted, indented JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    """Write the fixture files the TypeScript route tests import."""
    write_payload(ACTIVITY_PATH, activity_structures())
    write_payload(APPROXIMATION_PATH, approximation_structures())
    write_payload(CONTRACTS_PATH, contract_structures())
    write_payload(MINIMUM_PATH, minimum_structures())
    write_payload(MODULE_FAILURES_PATH, module_failure_structures())
    write_payload(MODULE_SHORTFALL_PATH, module_shortfall_structures())


if __name__ == "__main__":
    main()
