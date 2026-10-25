"""Module rule expansion, version selection, and malformed-shape handling."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
    CatalogueModuleRule,
    CatalogueModuleVersion,
)
from course_explorer.enums import (
    ModuleRuleType,
    ModuleType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    OfficialPrerequisiteKind,
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
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    child_uses,
    course_nodes,
    fact_of,
    ignored_nodes,
    ignored_parts,
    leaf_group_ids,
    module_nodes,
    module_rule,
    module_version,
    piece_of,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
    root_summary,
)
from tests.prerequisite._path_support import solve_route


def test_compiler_expands_all_seven_module_rule_kinds_without_module_nodes(
    solver_bundle: None,
) -> None:
    """Compiler calculation keeps inlined module rules. The drawing graph shows one module node."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    nested_rule = module_rule(
        ModuleRuleType.COMPOSITE_RULE,
        require_min=1,
        require_max=2,
        children=(
            module_rule(
                ModuleRuleType.COURSE_UNIT_RULE,
                referenced_group_id="shared",
            ),
            module_rule(
                ModuleRuleType.COURSE_UNIT_RULE,
                sibling_position=1,
                referenced_group_id="nested-only",
            ),
            module_rule(
                ModuleRuleType.ANY_COURSE_UNIT_RULE,
                sibling_position=2,
            ),
        ),
    )
    all_kinds_rule = module_rule(
        ModuleRuleType.COMPOSITE_RULE,
        local_id="root",
        all_mandatory=True,
        require_min=1,
        require_max=3,
        children=(
            module_rule(
                ModuleRuleType.COURSE_UNIT_RULE,
                local_id="course-one",
                referenced_group_id="c1",
            ),
            module_rule(
                ModuleRuleType.CREDITS_RULE,
                sibling_position=1,
                credits_min="5",
                credits_max="10",
                children=(
                    module_rule(
                        ModuleRuleType.COURSE_UNIT_COUNT_RULE,
                        count_min=1,
                        count_max=2,
                        children=(
                            module_rule(
                                ModuleRuleType.COURSE_UNIT_RULE,
                                referenced_group_id="c2",
                            ),
                        ),
                    ),
                ),
            ),
            module_rule(
                ModuleRuleType.MODULE_RULE,
                sibling_position=2,
                referenced_group_id="module-nested",
            ),
            module_rule(
                ModuleRuleType.ANY_MODULE_RULE,
                sibling_position=4,
            ),
        ),
    )
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-all"),
            ),
        ),
    )
    modules = (
        catalogue_module(
            "module-all",
            (
                module_version(
                    "module-all-v1",
                    rule=all_kinds_rule,
                    curriculum_periods=year_period,
                ),
            ),
        ),
        catalogue_module(
            "module-nested",
            (
                module_version(
                    "module-nested-v1",
                    rule=nested_rule,
                    curriculum_periods=year_period,
                ),
            ),
        ),
    )
    courses = (
        root,
        catalogue_course("c1"),
        catalogue_course("c2"),
        catalogue_course("shared"),
        catalogue_course("nested-only"),
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, modules),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    )

    compilation = compiler.compile("root")
    tree = compilation.solver
    # Root year comes from the persisted activity context, not a parsed period ID.
    assert tree.academic_year_start == 2026
    # The singleton root option collapses to its single module member, so the whole requirement is
    # the module boundary wrapping the inlined rule: an official AND with source child order kept,
    # minus the two unrestricted rules ignored in calculation.
    wrapped_use = tree.root_use_id
    assert wrapped_use is not None
    wrapped = piece_of(tree, wrapped_use)
    assert wrapped.kind == "module_block"
    assert wrapped.module_group_id == "module-all"
    assert fact_of(tree, wrapped_use).official_kind is OfficialPrerequisiteKind.COMPULSORY
    inlined_use = child_uses(tree, wrapped_use)[0]
    inlined = piece_of(tree, inlined_use)
    assert inlined.kind == "and"
    inlined_fact = fact_of(tree, inlined_use)
    assert inlined_fact.origin is PrerequisiteOrigin.OFFICIAL
    assert inlined_fact.official_kind is OfficialPrerequisiteKind.MODULE_RULE
    inlined_children = child_uses(tree, inlined_use)
    assert len(inlined_children) == 3
    course_one_use, credits_use, nested_use = inlined_children
    course_one = piece_of(tree, course_one_use)
    assert course_one.kind == "course"
    assert course_one.course_group_id == "c1"
    assert course_one.module_rule is True
    assert fact_of(tree, course_one_use).official_kind is OfficialPrerequisiteKind.MODULE_RULE

    # CreditsRule wraps the recursively compiled CourseUnitCountRule and keeps both bounds.
    credits = piece_of(tree, credits_use)
    assert credits.kind == "credits"
    assert credits.credits_min == Decimal("5")
    assert credits.credits_max == Decimal("10")
    assert fact_of(tree, credits_use).official_kind is OfficialPrerequisiteKind.MODULE_RULE
    count_use = child_uses(tree, credits_use)[0]
    credits_count = piece_of(tree, count_use)
    assert credits_count.kind == "course_count"
    assert credits_count.count_min == 1
    assert credits_count.count_max == 2
    count_leaf = piece_of(tree, child_uses(tree, count_use)[0])
    assert count_leaf.kind == "course"
    assert count_leaf.course_group_id == "c2"
    assert count_leaf.module_rule is True

    # Nested ModuleRule inlines through the same compiler as its own module boundary wrapping a
    # cardinality connector.
    nested = piece_of(tree, nested_use)
    assert nested.kind == "module_block"
    assert nested.module_group_id == "module-nested"
    nested_body_use = child_uses(tree, nested_use)[0]
    nested_body = piece_of(tree, nested_body_use)
    assert nested_body.kind == "cardinality"
    assert nested_body.require_min == 1
    assert nested_body.require_max == 2
    assert [leaf_group_ids(tree, child) for child in child_uses(tree, nested_body_use)] == [
        {"shared"},
        {"nested-only"},
    ]

    # The native course-leaf traversal exposes every canonical course leaf, including the nested
    # numeric credit/count wrapper around c2. Module/unresolved nodes add no leaf.
    assert leaf_group_ids(tree, wrapped_use) == {
        "c1",
        "c2",
        "shared",
        "nested-only",
    }

    # Unrestricted rules are ignored fully: they add no calculation node and are disclosed as
    # ignored parts, never an invented concrete course or a successful zero-credit alternative.
    assert [part.kind for part in ignored_parts(tree)] == [
        "free_choice",
        "free_choice",
        "all_mandatory_bounds",
    ]

    # The selected module's identity lives only in the native module boundaries and display metadata.
    assert [piece.kind for piece in tree.pieces].count("module_block") == 2
    assert "module-all" not in {summary.group_id for summary in tree.courses}
    assert "module-nested" not in {summary.group_id for summary in tree.courses}
    assert {summary.group_id for summary in tree.courses} == {
        "root",
        "c1",
        "c2",
        "shared",
        "nested-only",
    }

    # Both selected module boundaries survive at their surviving expression occurrences, the outer
    # module first. The members are the explicit official course-unit members including the nested
    # module's, sorted and unique. The nested module is structural content of the outer drawn
    # module, so only the outer module node is drawn.
    modules = {module.group_id: module for module in compilation.solver.modules}
    module_display = {node.module_group_id: node for node in module_nodes(compilation.display)}
    assert set(module_display) == {"module-all"}
    assert {module.group_id for module in compilation.solver.modules} == {
        "module-all",
        "module-nested",
    }
    assert modules["module-all"].sisu_module_id == "module-all-v1"
    assert modules["module-all"].module_type is ModuleType.STUDY_MODULE
    assert modules["module-all"].name_en == "Module module-all-v1"
    assert module_display["module-all"].member_group_ids == (
        "c1",
        "c2",
        "nested-only",
        "shared",
    )
    assert modules["module-nested"].sisu_module_id == "module-nested-v1"

    # Ignored free choice and all-mandatory bounds add no witness. Known numeric requirements are
    # met, so satisfaction holds and the route is exact at zero credits.
    satisfied = evaluate_prerequisite_satisfaction(compilation.solver, ["c1", "c2", "shared"])
    assert satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    exact = solve_route(compilation.solver, ["c1", "c2", "shared"])
    assert exact["state"] == "exact"
    assert Decimal(exact["total_new_credits"]) == Decimal("0")

    # The drawing graph compacts the whole inlined module subtree into one outer module node with
    # member cards, while the structurally nested module contributes no box of its own.
    assert [node.course_group_id for node in course_nodes(compilation.display)] == ["root"]
    assert {node.module_group_id for node in module_nodes(compilation.display)} == {"module-all"}
    module_node = module_display["module-all"]
    assert module_node.module_group_id == "module-all"
    assert module_node.member_group_ids == ("c1", "c2", "nested-only", "shared")
    base_edges = [
        (edge.source_node_id, edge.target_node_id)
        for edge in compilation.display.edges
        if not edge.target_node_id.startswith("ignored:")
    ]
    assert ("course:root", module_node.node_id) in base_edges
    # Every disclosure is drawn as one ignored annotation around the same compact module, with no
    # standalone member course card.
    assert len(ignored_nodes(compilation.display)) == len(ignored_parts(tree))
    assert {part.diagnostic_id for part in ignored_parts(tree)} <= {
        diagnostic_id
        for node in ignored_nodes(compilation.display)
        for diagnostic_id in node.diagnostic_ids
    }
    assert len(ignored_parts(tree)) == 3
    ignored_ids = {node.node_id for node in ignored_nodes(compilation.display)}
    ignored_edges = [
        edge for edge in compilation.display.edges if edge.target_node_id in ignored_ids
    ]
    assert len(ignored_edges) == 3

    facts = {fact.fact_id: fact for fact in compilation.solver.facts}
    members = {member.member_id: member for member in compilation.solver.members}
    assert all(
        facts[members[member_id].fact_id].origin is PrerequisiteOrigin.OFFICIAL
        for edge in ignored_edges
        for member_id in edge.member_ids
    )
    assert [part.kind for part in ignored_parts(tree)] == [
        "free_choice",
        "free_choice",
        "all_mandatory_bounds",
    ]


def test_module_version_selection_uses_root_year_and_reports_missing_or_ambiguous() -> None:
    """Exact-year membership wins, validity is the fallback, and ties are never silently picked."""
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-select"),
            ),
        ),
    )
    course = catalogue_course("selected-leaf")

    def compile_with_versions(*versions: CatalogueModuleVersion):
        module = catalogue_module("module-select", versions)
        return PrerequisiteGraphCompiler(
            FakeCurriculumRead((root, course), (module,)),
            RecordingInferredSetRead(),
            RecordingEquivalenceGroupRead(),
        ).compile("root")

    def inlined_use(compilation) -> str | None:
        root_use = compilation.solver.root_use_id
        if root_use is None:
            return None
        if piece_of(compilation.solver, root_use).kind == "module_block":
            return child_uses(compilation.solver, root_use)[0]
        return root_use

    # A version tied only to the 2027 period is the nearest fallback: the requested year 2026 has no
    # strict candidate, so the single nearest year is selected and disclosed with its actual identity.
    other_year = module_version(
        "module-select-v2027",
        rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="selected-leaf"),
        curriculum_periods=(CatalogueCurriculumPeriod(id="period-2027", academic_year_start=2027),),
    )
    missing_year = compile_with_versions(other_year)
    result_use = inlined_use(missing_year)
    assert result_use is not None
    result = piece_of(missing_year.solver, result_use)
    assert result.kind == "course"
    assert result.course_group_id == "selected-leaf"
    missing_modules = {module.group_id: module for module in missing_year.solver.modules}
    assert missing_modules["module-select"].sisu_module_id == "module-select-v2027"
    assert [part.kind for part in ignored_parts(missing_year.solver)] == ["module_version_fallback"]
    assert ignored_parts(missing_year.solver)[0].detail == (
        "requested year 2026; selected module-select-v2027"
    )

    # No versions at all resolves MISSING_MODULE too.
    no_versions = compile_with_versions()
    no_versions_use = inlined_use(no_versions)
    assert no_versions_use is not None
    result = piece_of(no_versions.solver, no_versions_use)
    assert result.kind == "unresolved"
    assert result.reason is UnresolvedPrerequisiteReason.MISSING_MODULE.value
    assert module_nodes(no_versions.display) == ()

    # An exact-year membership wins over a membership-free validity match, and the selected exact
    # version carries its official identity, type, and name.
    exact_year = module_version(
        "module-select-v2026",
        rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="selected-leaf"),
        curriculum_periods=(CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),),
    )
    validity_only = module_version(
        "module-select-vvalidity",
        rule=module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),
        validity_start=date(2026, 1, 1),
        validity_end=None,
    )
    selected = compile_with_versions(validity_only, exact_year)
    selected_use = inlined_use(selected)
    assert selected_use is not None
    result = piece_of(selected.solver, selected_use)
    assert result.kind == "course"
    assert result.course_group_id == "selected-leaf"
    selected_nodes = module_nodes(selected.display)
    assert len(selected_nodes) == 1
    selected_module = {module.group_id: module for module in selected.solver.modules}[
        "module-select"
    ]
    assert selected_module.sisu_module_id == "module-select-v2026"
    assert selected_module.module_type is ModuleType.STUDY_MODULE
    assert selected_module.name_en == "Module module-select-v2026"
    assert selected_module.code is None
    assert selected_nodes[0].member_group_ids == ("selected-leaf",)

    # A membership-free version whose validity covers 2026 is usable when nothing matches exactly.
    # Its unrestricted rule is ignored in calculation, disclosed, and leaves no requirement node.
    validity_only_compilation = compile_with_versions(validity_only)
    assert inlined_use(validity_only_compilation) is None
    assert [part.kind for part in ignored_parts(validity_only_compilation.solver)] == [
        "free_choice"
    ]

    # A validity window that ended before the root year is the nearest fallback, disclosed with its
    # actual selected version.
    expired = module_version(
        "module-select-vexpired",
        rule=module_rule(ModuleRuleType.ANY_MODULE_RULE),
        validity_start=date(2020, 1, 1),
        validity_end=date(2021, 12, 31),
    )
    expired_compilation = compile_with_versions(expired)
    assert inlined_use(expired_compilation) is None
    # The ignored module leaves no calculation node, so no boundary occurrence holds. The
    # fallback is attributed to its actual selected version in the disclosure.
    assert [node.module_group_id for node in module_nodes(expired_compilation.display)] == [
        "module-select"
    ]
    assert sorted(part.kind for part in ignored_parts(expired_compilation.solver)) == [
        "free_choice",
        "module_version_fallback",
    ]

    # A selected version with no stored rule tree is a disappeared selected module: it records no
    # calculation occurrence but keeps a childless display module with its selected identity.
    ruleless = module_version(
        "module-select-vruleless",
        rule=None,
        curriculum_periods=(
            CatalogueCurriculumPeriod(id="period-2026-ruleless", academic_year_start=2026),
        ),
    )
    ruleless_compilation = compile_with_versions(ruleless)
    assert inlined_use(ruleless_compilation) is None
    assert [node.module_group_id for node in module_nodes(ruleless_compilation.display)] == [
        "module-select"
    ]
    assert [part.kind for part in ignored_parts(ruleless_compilation.solver)] == [
        "unexpandable_content"
    ]
    ruleless_module = {module.group_id: module for module in ruleless_compilation.solver.modules}[
        "module-select"
    ]
    assert ruleless_module.sisu_module_id == "module-select-vruleless"
    assert [node.module_group_id for node in module_nodes(ruleless_compilation.display)] == [
        "module-select"
    ]

    # The greatest preceding year wins over a following one. A following-only set takes the least following year.
    earlier = module_version(
        "module-select-v2024",
        rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="selected-leaf"),
        curriculum_periods=(CatalogueCurriculumPeriod(id="period-2024", academic_year_start=2024),),
    )
    later = module_version(
        "module-select-v2028",
        rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="selected-leaf"),
        curriculum_periods=(CatalogueCurriculumPeriod(id="period-2028", academic_year_start=2028),),
    )
    earlier_selected = compile_with_versions(earlier, later)
    assert {module.sisu_module_id for module in earlier_selected.solver.modules} == {
        "module-select-v2024"
    }
    later_only = module_version(
        "module-select-v2027b",
        rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="selected-leaf"),
        curriculum_periods=(
            CatalogueCurriculumPeriod(id="period-2027b", academic_year_start=2027),
        ),
    )
    later_only_selected = compile_with_versions(later_only, later)
    assert {module.sisu_module_id for module in later_only_selected.solver.modules} == {
        "module-select-v2027b"
    }

    # Two exact-year candidates are ambiguous even though source-ID order could break the tie. An
    # ambiguous version has no selected identity and therefore no module summary.
    duplicate_a = module_version(
        "module-select-v1a",
        rule=module_rule(ModuleRuleType.ANY_MODULE_RULE),
        curriculum_periods=(
            CatalogueCurriculumPeriod(id="period-2026-a", academic_year_start=2026),
        ),
    )
    duplicate_b = module_version(
        "module-select-v1b",
        rule=module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),
        curriculum_periods=(
            CatalogueCurriculumPeriod(id="period-2026-b", academic_year_start=2026),
        ),
    )
    ambiguous = compile_with_versions(duplicate_a, duplicate_b)
    ambiguous_use = inlined_use(ambiguous)
    assert ambiguous_use is not None
    result = piece_of(ambiguous.solver, ambiguous_use)
    assert result.kind == "unresolved"
    assert result.reason is UnresolvedPrerequisiteReason.AMBIGUOUS_MODULE_VERSION.value
    assert result.referenced_group_id == "module-select"
    assert module_nodes(ambiguous.display) == ()

    # Direct-many reuses the same nearest fallback and attributes the actual selected version.
    direct = PrerequisiteGraphCompiler(
        FakeCurriculumRead((root, course), (catalogue_module("module-select", (other_year,)),)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile_direct_many(("root",))
    assert [root_summary(entry.solver).group_id for entry in direct] == ["root"]
    assert [(module.group_id, module.sisu_module_id) for module in direct[0].solver.modules] == [
        ("module-select", "module-select-v2027")
    ]

    # A missing-module official alternative beside a valid option is dropped whole and disclosed,
    # rather than turning a mandatory member into a weaker requirement.
    alternative_root = catalogue_course(
        "alternative-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "valid-leaf"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-absent"),
            ),
        ),
    )
    alternative = PrerequisiteGraphCompiler(
        FakeCurriculumRead((alternative_root, catalogue_course("valid-leaf"))),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("alternative-root")
    alternative_root = alternative.solver.root_use_id
    assert alternative_root is not None
    alternative_requirements = piece_of(alternative.solver, alternative_root)
    assert alternative_requirements.kind == "course"
    assert alternative_requirements.course_group_id == "valid-leaf"
    assert [part.kind for part in ignored_parts(alternative.solver)] == [
        "missing_module_alternative"
    ]
    assert ignored_parts(alternative.solver)[0].referenced_group_ids == ("module-absent",)


def test_module_rule_malformed_shapes_become_explicit_unresolved_nodes(solver_bundle: None) -> None:
    """Malformed source rule shapes and missing references yield explicit nodes."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-malformed"),
            ),
        ),
    )

    def compile_rule(
        rule: CatalogueModuleRule | None,
        *,
        courses=(),
        modules=(),
        target_credits_min: str | None = None,
    ):
        module = catalogue_module(
            "module-malformed",
            (
                module_version(
                    "module-malformed-v1",
                    rule=rule,
                    curriculum_periods=year_period,
                    target_credits_min=target_credits_min,
                ),
            ),
        )
        return PrerequisiteGraphCompiler(
            FakeCurriculumRead((root, *courses), (module, *modules)),
            RecordingInferredSetRead(),
            RecordingEquivalenceGroupRead(),
        ).compile("root")

    def inlined(rule: CatalogueModuleRule | None, **kwargs):
        compilation = compile_rule(rule, **kwargs)
        root_use = compilation.solver.root_use_id
        if root_use is None:
            return None
        if piece_of(compilation.solver, root_use).kind == "module_block":
            return piece_of(compilation.solver, child_uses(compilation.solver, root_use)[0])
        return piece_of(compilation.solver, root_use)

    # A blank all-mandatory composite is an unexpandable block: it contributes nothing and
    # is disclosed, never a vacuous true AND or a malformed node.
    blank = compile_rule(module_rule(ModuleRuleType.COMPOSITE_RULE, all_mandatory=True))
    assert blank.solver.root_use_id is None
    assert [part.kind for part in ignored_parts(blank.solver)] == ["unexpandable_content"]

    # A stored version with no rule tree is the same whole-module unexpandable shape, not a malformed
    # rule: with whole-module target credits it is one childless opaque obligation. With no credits it
    # is absent from calculation, disclosed, and kept as a childless display module.
    empty_credits = compile_rule(None, target_credits_min="35")
    empty_inlined = inlined(None, target_credits_min="35")
    assert empty_inlined.kind == "opaque_credits"
    assert empty_inlined.credits_min == Decimal("35")
    assert [part.kind for part in ignored_parts(empty_credits.solver)] == ["unexpandable_content"]
    assert ignored_parts(empty_credits.solver)[0].module_group_id is not None
    assert len(module_nodes(empty_credits.display)) == 1
    empty_no_credits = compile_rule(None)
    assert empty_no_credits.solver.root_use_id is None
    assert [part.kind for part in ignored_parts(empty_no_credits.solver)] == [
        "unexpandable_content"
    ]
    display_part = ignored_parts(empty_no_credits.solver)[0]
    assert display_part.module_group_id == "module-malformed"
    assert [node.module_group_id for node in module_nodes(empty_no_credits.display)] == [
        "module-malformed"
    ]
    assert module_nodes(empty_no_credits.display)[0].member_group_ids == ()

    # A credit wrapper whose only content is the immediate owning course is a direct self
    # occurrence: it contributes nothing and creates no credit obligation.
    self_credit = compile_rule(
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="5",
            children=(module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="root"),),
        )
    )
    assert self_credit.solver.root_use_id is None

    # A malformed source range (a pick-N minimum above the child count) is an
    # explicit unresolved MALFORMED_RULE node. Only positions dropped from a valid source survive.
    malformed = inlined(
        module_rule(
            ModuleRuleType.COMPOSITE_RULE,
            require_min=2,
            require_max=2,
            children=(module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="solo"),),
        )
    )
    assert malformed.kind == "unresolved"
    assert malformed.reason is UnresolvedPrerequisiteReason.MALFORMED_RULE.value
    assert malformed.module_rule is True

    # A surviving pick-N rule whose ignored positions leave fewer than its positive minimum keeps its
    # source minimum as a located cardinality node, so the fold returns no-solution rather than a
    # compiler error or a lowered N.
    surviving_impossible = inlined(
        module_rule(
            ModuleRuleType.COMPOSITE_RULE,
            require_min=2,
            require_max=3,
            children=(
                module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="solo"),
                module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE, sibling_position=1),
                module_rule(ModuleRuleType.ANY_MODULE_RULE, sibling_position=2),
            ),
        )
    )
    assert surviving_impossible.kind == "cardinality"
    assert surviving_impossible.require_min == 2
    assert len(surviving_impossible.children) == 1

    # Valid shapes referencing absent canonical entities become the specific missing reason.
    missing_course = inlined(
        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="absent-course")
    )
    assert missing_course.kind == "unresolved"
    assert missing_course.reason is UnresolvedPrerequisiteReason.MISSING_COURSE.value
    assert missing_course.referenced_group_id == "absent-course"

    missing_module = inlined(
        module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="absent-module")
    )
    assert missing_module.kind == "unresolved"
    assert missing_module.reason is UnresolvedPrerequisiteReason.MISSING_MODULE.value
    assert missing_module.referenced_group_id == "absent-module"

    # A genuinely empty official source option is dropped with an EMPTY_OPTION disclosure rather
    # than a vacuous true AND or a fabricated branch. The root use is None and the route is exact
    # at zero credits.
    empty_option_root = catalogue_course(
        "empty-option-root",
        prerequisite_options=(prerequisite_option(0, PrerequisiteRequirementKind.COMPULSORY),),
    )
    empty_option = PrerequisiteGraphCompiler(
        FakeCurriculumRead((empty_option_root,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("empty-option-root")
    assert empty_option.solver.root_use_id is None
    assert [part.kind for part in ignored_parts(empty_option.solver)] == ["empty_option"]
    empty_path = solve_route(empty_option.solver, [])
    assert empty_path["state"] == "exact"
    assert Decimal(empty_path["total_new_credits"]) == Decimal("0")
