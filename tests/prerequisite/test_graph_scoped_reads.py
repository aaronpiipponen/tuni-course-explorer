"""Scoped closure reads and parity with full-catalogue compilation."""

from __future__ import annotations

import pytest

from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
)
from course_explorer.enums import (
    ModuleRuleType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.graph import (
    DirectPrerequisiteReadContext,
    PrerequisiteGraphCompiler,
    PrerequisiteIgnoredPartKind,
)
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    FullCatalogueFakeCurriculum,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    ignored_parts,
    module_rule,
    module_version,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
    root_summary,
)


def test_compiler_reads_only_the_target_retained_and_referenced_closure() -> None:
    """Compilation requests the target, retained, and transitively referenced identities only."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    root_options = (
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "child"),
            prerequisite_module_member(1, "module-referenced"),
        ),
        prerequisite_option(
            1,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "child"),
            prerequisite_course_member(1, "missing-child"),
            prerequisite_module_member(2, "missing-module"),
        ),
    )
    module = catalogue_module(
        "module-referenced",
        (
            module_version(
                "module-referenced-v1",
                rule=module_rule(
                    ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="module-leaf"
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    retained = catalogue_course(
        "retained",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "retained-child"),
            ),
        ),
    )
    courses = (
        catalogue_course("root", prerequisite_options=root_options),
        catalogue_course("child"),
        catalogue_course("module-leaf"),
        retained,
        catalogue_course("retained-child"),
        # An unrelated canonical course must never be requested or loaded.
        catalogue_course("unrelated"),
    )
    curriculum = FakeCurriculumRead(courses, (module,))
    compilation = PrerequisiteGraphCompiler(
        curriculum, RecordingInferredSetRead(), RecordingEquivalenceGroupRead()
    ).compile("root", retained_group_ids=("retained",))

    # The target, retained, and sibling references load in scoped batches.
    requested_courses = {group_id for batch in curriculum.course_reads for group_id in batch}
    assert requested_courses == {"root", "retained", "child", "module-leaf", "missing-child"}
    assert "unrelated" not in requested_courses
    # A retained course is a compile-time retention input, not a dependency root: it loads for
    # validation but its own prerequisites never enter the closure unless referenced.
    assert "retained-child" not in requested_courses
    assert {summary.group_id for summary in compilation.solver.courses} == {
        "root",
        "child",
        "module-leaf",
    }
    assert tuple(part.kind for part in ignored_parts(compilation.solver)) == (
        PrerequisiteIgnoredPartKind.MISSING_MODULE_ALTERNATIVE,
    )
    assert ignored_parts(compilation.solver)[0].referenced_group_ids == (
        "child",
        "missing-child",
        "missing-module",
    )

    # Only the referenced module is requested. An unrelated module is unread.
    requested_modules = {group_id for batch in curriculum.module_reads for group_id in batch}
    assert requested_modules == {"module-referenced", "missing-module"}
    assert sum("missing-child" in batch for batch in curriculum.course_reads) == 1
    assert sum("missing-module" in batch for batch in curriculum.module_reads) == 1

    # Warmed and on-demand referenced reads produce byte-identical trees/graphs to a full preloaded read.
    preloaded = PrerequisiteGraphCompiler(
        FullCatalogueFakeCurriculum(courses, (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root", retained_group_ids=("retained",))
    assert compilation == preloaded

    with pytest.raises(ValueError):
        PrerequisiteGraphCompiler(
            FakeCurriculumRead(courses, (module,)),
            RecordingInferredSetRead(),
            RecordingEquivalenceGroupRead(),
        ).compile("root", retained_group_ids=("absent",))

    # Direct-many over the same root/module fixture plus one shared-target sibling stops ordinary
    # course ancestors, keeps unrelated catalogue unread, and reads a shared identity once across
    # roots.
    direct_courses = (
        *courses,
        catalogue_course(
            "direct-root",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "child"),
                    prerequisite_course_member(1, "direct-child"),
                ),
            ),
        ),
        catalogue_course(
            "direct-child",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "direct-ancestor"),
                ),
            ),
        ),
        catalogue_course("direct-ancestor"),
    )
    direct_curriculum = FakeCurriculumRead(direct_courses, (module,))
    direct_compiler = PrerequisiteGraphCompiler(
        direct_curriculum, RecordingInferredSetRead(), RecordingEquivalenceGroupRead()
    )
    read_context = DirectPrerequisiteReadContext()
    first_pass = direct_compiler.compile_direct_many(
        ("root", "direct-root"), include_inferred=True, read_context=read_context
    )
    official_pass = direct_compiler.compile_direct_many(
        ("root", "direct-root"), include_inferred=False, read_context=read_context
    )
    assert [root_summary(entry.solver).group_id for entry in first_pass] == ["direct-root", "root"]
    assert [root_summary(entry.solver).group_id for entry in official_pass] == [
        "direct-root",
        "root",
    ]

    # The shared-context inference-on and official-only passes are byte-identical to independent
    # compiles of the same fixture, so no compiled state leaked through the shared raw reads.
    fresh_first = PrerequisiteGraphCompiler(
        FakeCurriculumRead(direct_courses, (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile_direct_many(("root", "direct-root"), include_inferred=True)
    fresh_official = PrerequisiteGraphCompiler(
        FakeCurriculumRead(direct_courses, (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile_direct_many(("root", "direct-root"), include_inferred=False)
    assert first_pass == fresh_first
    assert official_pass == fresh_official

    requested_direct = {group_id for batch in direct_curriculum.course_reads for group_id in batch}
    assert "direct-ancestor" not in requested_direct
    assert "unrelated" not in requested_direct
    assert sum(1 for batch in direct_curriculum.course_reads if "child" in batch) == 1
    assert sum("missing-child" in batch for batch in direct_curriculum.course_reads) == 1
    assert sum("missing-module" in batch for batch in direct_curriculum.module_reads) == 1
    root_direct = next(
        entry for entry in official_pass if root_summary(entry.solver).group_id == "root"
    )
    assert {course.group_id for course in root_direct.solver.courses} == {
        "root",
        "child",
        "module-leaf",
    }
    direct_root_entry = next(
        entry for entry in official_pass if root_summary(entry.solver).group_id == "direct-root"
    )
    assert {course.group_id for course in direct_root_entry.solver.courses} == {
        "direct-root",
        "child",
        "direct-child",
    }


def test_compiler_builds_repeated_source_dependencies_without_expanding_paths() -> None:
    """Layered shared bodies intern once and repeated source slots share one use."""
    root_options = (
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "a"),
            prerequisite_course_member(1, "b"),
            prerequisite_course_member(2, "repeat"),
        ),
    )

    def requires(*group_ids: str):
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

    courses = (
        catalogue_course("root", prerequisite_options=root_options),
        catalogue_course("a", prerequisite_options=requires("c", "d")),
        catalogue_course("b", prerequisite_options=requires("c", "d")),
        catalogue_course("repeat", prerequisite_options=requires("c", "c")),
        catalogue_course("c", prerequisite_options=requires("e")),
        catalogue_course("d", prerequisite_options=requires("e")),
        catalogue_course("e", prerequisite_options=requires("c")),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")
    structure = compilation.solver
    pieces = {piece.piece_id: piece for piece in structure.pieces}
    uses = {use.use_id: use for use in structure.uses}
    e_pieces = [
        piece
        for piece in structure.pieces
        if piece.kind == "course" and piece.course_group_id == "e"
    ]
    normal_e = [piece for piece in e_pieces if not piece.cycle_closing]
    assert len(normal_e) == 1
    e_uses = [use for use in structure.uses if use.piece_id == normal_e[0].piece_id]
    # One source-local E occurrence is shared by every acyclic prefix. The opposite cycle entry
    # keeps its own closing E variant, never replacing the normal one.
    assert len(e_uses) == 1
    # The shared cycle-containing C suffix is one fragment: the closing C leaf is one piece and one
    # source use, reached identically through a, b and both repeated repeat slots.
    c_pieces = [
        piece
        for piece in structure.pieces
        if piece.kind == "course" and piece.course_group_id == "c"
    ]
    closing_c = [piece for piece in c_pieces if piece.cycle_closing]
    normal_c = [piece for piece in c_pieces if not piece.cycle_closing]
    assert len(c_pieces) == 2
    assert len(closing_c) == 1
    assert len(normal_c) == 1
    assert len([use for use in structure.uses if use.piece_id == closing_c[0].piece_id]) == 1
    assert len([use for use in structure.uses if use.piece_id == normal_c[0].piece_id]) == 1
    expanded_by_head = {
        pieces[uses[use.children[0]].piece_id].course_group_id: use
        for use in structure.uses
        if pieces[use.piece_id].kind == "expanded_course"
        and pieces[uses[use.children[0]].piece_id].kind == "course"
    }
    repeat_expanded = expanded_by_head["repeat"]
    repeat_children = uses[repeat_expanded.children[1]].children
    assert len(repeat_children) == 2
    assert repeat_children[0] == repeat_children[1]
    # A and B share the same C/D body uses even though their own heads differ.
    a_body = uses[expanded_by_head["a"].children[1]].children
    b_body = uses[expanded_by_head["b"].children[1]].children
    assert a_body == b_body
    c_expanded_use = a_body[0]
    assert pieces[uses[c_expanded_use].piece_id].kind == "expanded_course"
    assert pieces[uses[uses[c_expanded_use].children[0]].piece_id].course_group_id == "c"
