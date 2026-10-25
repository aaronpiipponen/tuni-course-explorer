"""Write the solver structures the TypeScript solver tests read."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedAndRole,
    CourseCountRequirement,
    CreditRequirement,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure
from tests.prerequisite._path_support import (
    course_summary,
    fixture_structure,
    inferred_course,
    make_compilation,
    module_cardinality,
    official_and,
    official_course,
)

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "web/src/solver/fixtures/satisfaction.json"


def canonical_structures() -> dict[str, PrerequisiteSolverStructure]:
    """Build the three structures of the canonical completion identity test."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("a"), official_course("b")),
    )
    compilation = make_compilation(
        root,
        requirements,
        (course_summary("a"), course_summary("b")),
    )
    exact_count_two = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=requirements,
    )
    exact_count_three = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=3,
        count_max=3,
        child=requirements,
    )
    exact_ten_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
        child=requirements,
    )
    wrappers = fixture_structure(
        requirements,
        root=root,
        courses=(course_summary("a"), course_summary("b")),
        extra_requirements=(exact_count_two, exact_count_three, exact_ten_credits),
    )
    positions = module_cardinality(2, 2, "a", "a")
    exact_one_course = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=positions,
    )
    exact_two_courses = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=positions,
    )
    positions_structure = fixture_structure(
        positions,
        root=root,
        courses=(course_summary("a"),),
        extra_requirements=(exact_one_course, exact_two_courses),
    )
    return {
        "canonical.compilation": compilation.solver,
        "canonical.wrappers": wrappers,
        "canonical.positions": positions_structure,
    }


def logical_structures() -> dict[str, PrerequisiteSolverStructure]:
    """Build the seven structures of the already filtered logical states test."""
    root = course_summary("root")
    rootless = make_compilation(root, None, ())
    and_tree = make_compilation(
        root,
        official_and("a", "b"),
        (course_summary("a"), course_summary("b")),
    )
    or_requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("b")),
    )
    or_tree = make_compilation(
        root,
        or_requirements,
        (course_summary("a"), course_summary("b")),
    )
    recommended_tree = make_compilation(
        root,
        official_course("recommended", OfficialPrerequisiteKind.RECOMMENDED),
        (course_summary("recommended"),),
        include_recommended=True,
    )
    inferred_tree = make_compilation(
        root,
        inferred_course("inferred"),
        (course_summary("inferred"),),
        include_inferred=True,
    )
    unresolved_requirement = UnresolvedRequirement(
        type="unresolved",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
    )
    subtree_structure = fixture_structure(
        official_and("a", "b"),
        root=root,
        courses=(course_summary("a"), course_summary("b")),
        extra_requirements=(unresolved_requirement,),
    )
    leaves = tuple(f"leaf-{index:02d}" for index in range(27))
    cardinality = module_cardinality(1, None, *leaves)
    exact_count_two = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=cardinality,
    )
    exact_ten_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
        child=exact_count_two,
    )
    exact_twelve_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("12"),
        credits_max=Decimal("12"),
        child=cardinality,
    )
    cardinality_structure = fixture_structure(
        cardinality,
        root=root,
        courses=tuple(course_summary(group_id) for group_id in leaves),
        extra_requirements=(exact_count_two, exact_ten_credits, exact_twelve_credits),
    )
    return {
        "logical.rootless": rootless.solver,
        "logical.and": and_tree.solver,
        "logical.or": or_tree.solver,
        "logical.recommended": recommended_tree.solver,
        "logical.inferred": inferred_tree.solver,
        "logical.subtree": subtree_structure,
        "logical.cardinality": cardinality_structure,
    }


def composed_structures() -> dict[str, PrerequisiteSolverStructure]:
    """Build the structure of the composed logical AND test."""
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
        (course_summary("a"), course_summary("b")),
    )
    return {"composed.logical_and": compilation.solver}


def expanded_structures() -> dict[str, PrerequisiteSolverStructure]:
    """Build the two structures of the expanded course satisfaction test."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(official_course("a"), official_course("e")),
    )
    compilation = make_compilation(
        root,
        requirements,
        (course_summary("a"), course_summary("e")),
    )
    exact_one = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=requirements,
    )
    exact_two = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=requirements,
    )
    expanded_structure = fixture_structure(
        requirements,
        root=root,
        courses=(course_summary("a"), course_summary("e")),
        extra_requirements=(exact_one, exact_two),
    )
    return {
        "expanded.compilation": compilation.solver,
        "expanded.wrappers": expanded_structure,
    }


def excluded_structures() -> dict[str, PrerequisiteSolverStructure]:
    """Build the structure of the excluded completed and selected basis test."""
    root = course_summary("root")
    expanded = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(official_course("head"), official_course("head-child")),
    )
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("leaf"), expanded, official_course("keep")),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("leaf"),
            course_summary("head"),
            course_summary("head-child"),
            course_summary("keep"),
        ),
        excluded_group_ids=("head", "leaf"),
    )
    return {"excluded.compilation": compilation.solver}


def node_state_case() -> dict[str, object]:
    """Build the neutral solver structure and display the box-state test reads."""
    compilation = make_compilation(
        course_summary("root"),
        official_and("a", "b"),
        (course_summary("a"), course_summary("b")),
    )
    if compilation.display is None:
        raise ValueError("the node-state fixture compilation carries no display")
    return {
        "solver": compilation.solver.model_dump(mode="json"),
        "display": compilation.display.model_dump(mode="json"),
    }


def main() -> None:
    """Write the fixture file the TypeScript satisfaction test imports."""
    structures: dict[str, PrerequisiteSolverStructure] = {}
    for build in (
        canonical_structures,
        logical_structures,
        composed_structures,
        expanded_structures,
        excluded_structures,
    ):
        structures.update(build())
    payload = {
        "structures": {
            label: structure.model_dump(mode="json") for label, structure in structures.items()
        },
        "nodeStates": node_state_case(),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
