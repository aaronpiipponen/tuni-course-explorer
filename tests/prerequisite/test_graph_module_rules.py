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
    AndRequirement,
    CardinalityRequirement,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
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
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    contains_module_requirement,
    module_rule,
    module_version,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
)


def test_compiler_expands_all_seven_module_rule_kinds_without_module_nodes() -> None:
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
                ModuleRuleType.ANY_COURSE_UNIT_RULE,
                sibling_position=3,
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
    tree = compilation.tree
    # Root year comes from the persisted activity context, not a parsed period ID.
    assert tree.academic_year_start == 2026
    # The singleton root option collapses to its single module member, so the whole requirement is
    # the module boundary wrapping the inlined rule: an official AND with source child order kept,
    # minus the two unrestricted rules ignored in calculation.
    wrapped = tree.requirements
    assert isinstance(wrapped, ModuleBlockRequirement)
    assert wrapped.module_group_id == "module-all"
    assert wrapped.official_kind is OfficialPrerequisiteKind.COMPULSORY
    inlined = wrapped.child
    assert isinstance(inlined, AndRequirement)
    assert inlined.origin is PrerequisiteOrigin.OFFICIAL
    assert inlined.official_kind is OfficialPrerequisiteKind.MODULE_RULE
    assert len(inlined.children) == 3
    course_one, credits, nested = inlined.children
    assert isinstance(course_one, CourseRequirement)
    assert course_one.course_group_id == "c1"
    assert course_one.official_kind is OfficialPrerequisiteKind.MODULE_RULE

    # CreditsRule wraps the recursively compiled CourseUnitCountRule and keeps both bounds.
    assert isinstance(credits, CreditRequirement)
    assert credits.credits_min == Decimal("5")
    assert credits.credits_max == Decimal("10")
    assert credits.official_kind is OfficialPrerequisiteKind.MODULE_RULE
    assert isinstance(credits.child, CourseCountRequirement)
    assert credits.child.count_min == 1
    assert credits.child.count_max == 2
    count_leaf = credits.child.child
    assert isinstance(count_leaf, CourseRequirement)
    assert count_leaf.course_group_id == "c2"
    assert count_leaf.official_kind is OfficialPrerequisiteKind.MODULE_RULE

    # Nested ModuleRule inlines through the same compiler as its own module boundary wrapping a
    # cardinality connector.
    assert isinstance(nested, ModuleBlockRequirement)
    assert nested.module_group_id == "module-nested"
    nested_body = nested.child
    assert isinstance(nested_body, CardinalityRequirement)
    assert nested_body.require_min == 1
    assert nested_body.require_max == 2
    assert [expression_course_leaf_group_ids(child) for child in nested_body.children] == [
        {"shared"},
        {"nested-only"},
    ]

    # The one generic course-leaf traversal exposes every canonical course leaf, including the
    # nested numeric credit/count wrapper around c2. Module/unresolved nodes add no leaf.
    assert expression_course_leaf_group_ids(tree.requirements) == {
        "c1",
        "c2",
        "shared",
        "nested-only",
    }

    # Unrestricted rules are ignored fully: they add no calculation node and are disclosed as
    # ignored parts, never an invented concrete course or a successful zero-credit alternative.
    assert [part.kind.value for part in tree.ignored_parts] == [
        "free_choice",
        "free_choice",
        "all_mandatory_bounds",
    ]

    # The selected module's identity lives only in the request-local display metadata beside the
    # inlined rule.
    assert not contains_module_requirement(tree.requirements)
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
    # module's, sorted and unique.
    assert [(occ.occurrence_id, occ.module.group_id) for occ in tree.module_occurrences] == [
        ("r", "module-all"),
        ("r.0.2", "module-nested"),
    ]
    outer, nested = tree.module_occurrences
    assert outer.official_kind is OfficialPrerequisiteKind.COMPULSORY
    assert outer.module.sisu_module_id == "module-all-v1"
    assert outer.module.module_type is ModuleType.STUDY_MODULE
    assert outer.module.name_en == "Module module-all-v1"
    assert outer.member_group_ids == ("c1", "c2", "nested-only", "shared")
    assert nested.official_kind is OfficialPrerequisiteKind.MODULE_RULE
    assert nested.module.sisu_module_id == "module-nested-v1"
    assert nested.member_group_ids == ("nested-only", "shared")

    # Ignored free choice and all-mandatory bounds add no witness. Known numeric requirements are
    # met, so shared satisfaction and PATH are exact zero.
    satisfied = evaluate_prerequisite_satisfaction(compilation.tree, ["c1", "c2", "shared"])
    assert satisfied.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    exact = calculate_minimum_new_credits(compilation.tree, ["c1", "c2", "shared"])
    assert exact.state is PrerequisitePathState.EXACT
    assert exact.total_new_credits == Decimal("0")

    # The drawing graph compacts the whole inlined module subtree into one node with member cards.
    assert [node.course.group_id for node in compilation.graph.course_nodes] == ["root"]
    assert compilation.graph.connector_nodes == ()
    assert [(node.node_id, node.occurrence_id) for node in compilation.graph.module_nodes] == [
        ("module:r", "r")
    ]
    module_node = compilation.graph.module_nodes[0]
    assert module_node.module.group_id == "module-all"
    assert [card.group_id for card in module_node.member_courses] == [
        "c1",
        "c2",
        "nested-only",
        "shared",
    ]
    base_edges = [
        (edge.source_node_id, edge.target_node_id)
        for edge in compilation.graph.edges
        if not edge.target_node_id.startswith("ignored:")
    ]
    assert base_edges == [("course:root", "module:r")]
    # Every disclosure is drawn as one ignored annotation around the same compact module, with no
    # standalone member course card.
    assert [node.node_id for node in compilation.graph.ignored_nodes] == [
        part.part_id for part in tree.ignored_parts
    ]
    assert len(tree.ignored_parts) == 3
    ignored_edges = [
        edge for edge in compilation.graph.edges if edge.target_node_id.startswith("ignored:")
    ]
    assert len(ignored_edges) == 3
    assert all(edge.source_node_id == "module:r" for edge in ignored_edges)
    assert all(
        member.origin is PrerequisiteOrigin.OFFICIAL
        for edge in ignored_edges
        for member in edge.relationships
    )
    assert [part.kind.value for part in tree.ignored_parts] == [
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

    def inlined(compilation) -> object:
        requirements = compilation.tree.requirements
        if isinstance(requirements, ModuleBlockRequirement):
            return requirements.child
        return requirements

    # A version tied only to the 2027 period is the nearest fallback: the requested year 2026 has no
    # strict candidate, so the single nearest year is selected and disclosed with its actual identity.
    other_year = module_version(
        "module-select-v2027",
        rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="selected-leaf"),
        curriculum_periods=(CatalogueCurriculumPeriod(id="period-2027", academic_year_start=2027),),
    )
    missing_year = compile_with_versions(other_year)
    result = inlined(missing_year)
    assert isinstance(result, CourseRequirement)
    assert result.course_group_id == "selected-leaf"
    assert [
        (occ.occurrence_id, occ.module.sisu_module_id)
        for occ in missing_year.tree.module_occurrences
    ] == [("r", "module-select-v2027")]
    assert [part.kind.value for part in missing_year.tree.ignored_parts] == [
        "module_version_fallback"
    ]
    assert missing_year.tree.ignored_parts[0].detail == (
        "requested year 2026; selected module-select-v2027"
    )

    # No versions at all resolves MISSING_MODULE too.
    no_versions = compile_with_versions()
    result = inlined(no_versions)
    assert isinstance(result, UnresolvedRequirement)
    assert result.reason is UnresolvedPrerequisiteReason.MISSING_MODULE
    assert no_versions.tree.module_occurrences == ()

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
    result = inlined(selected)
    assert isinstance(result, CourseRequirement)
    assert result.course_group_id == "selected-leaf"
    assert len(selected.tree.module_occurrences) == 1
    occurrence = selected.tree.module_occurrences[0]
    assert occurrence.occurrence_id == "r"
    assert occurrence.module.group_id == "module-select"
    assert occurrence.module.sisu_module_id == "module-select-v2026"
    assert occurrence.module.module_type is ModuleType.STUDY_MODULE
    assert occurrence.module.name_en == "Module module-select-v2026"
    assert occurrence.module.code is None
    assert occurrence.member_group_ids == ("selected-leaf",)

    # A membership-free version whose validity covers 2026 is usable when nothing matches exactly.
    # Its unrestricted rule is ignored in calculation, disclosed, and leaves no requirement node.
    validity_only_compilation = compile_with_versions(validity_only)
    assert inlined(validity_only_compilation) is None
    assert [part.kind.value for part in validity_only_compilation.tree.ignored_parts] == [
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
    assert inlined(expired_compilation) is None
    # The ignored module leaves no calculation node, so no boundary occurrence holds. The
    # fallback is attributed to its actual selected version in the disclosure.
    assert expired_compilation.tree.module_occurrences == ()
    assert [part.kind.value for part in expired_compilation.tree.ignored_parts] == [
        "module_version_fallback",
        "free_choice",
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
    assert inlined(ruleless_compilation) is None
    assert ruleless_compilation.tree.module_occurrences == ()
    assert [part.kind.value for part in ruleless_compilation.tree.ignored_parts] == [
        "unexpandable_content"
    ]
    ruleless_part = ruleless_compilation.tree.ignored_parts[0]
    assert ruleless_part.module is not None
    assert ruleless_part.module.sisu_module_id == "module-select-vruleless"
    assert [node.node_id for node in ruleless_compilation.graph.module_nodes] == [
        f"module:{ruleless_part.part_id}"
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
    assert earlier_selected.tree.module_occurrences[0].module.sisu_module_id == (
        "module-select-v2024"
    )
    later_only = module_version(
        "module-select-v2027b",
        rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="selected-leaf"),
        curriculum_periods=(
            CatalogueCurriculumPeriod(id="period-2027b", academic_year_start=2027),
        ),
    )
    later_only_selected = compile_with_versions(later_only, later)
    assert later_only_selected.tree.module_occurrences[0].module.sisu_module_id == (
        "module-select-v2027b"
    )

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
    result = inlined(ambiguous)
    assert isinstance(result, UnresolvedRequirement)
    assert result.reason is UnresolvedPrerequisiteReason.AMBIGUOUS_MODULE_VERSION
    assert result.referenced_group_id == "module-select"
    assert ambiguous.tree.module_occurrences == ()

    # Direct-many reuses the same nearest fallback and attributes the actual selected version.
    direct = PrerequisiteGraphCompiler(
        FakeCurriculumRead((root, course), (catalogue_module("module-select", (other_year,)),)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile_direct_many(("root",))
    assert [entry.tree.root.group_id for entry in direct] == ["root"]
    assert [
        (occ.occurrence_id, occ.module.sisu_module_id) for occ in direct[0].tree.module_occurrences
    ] == [("r", "module-select-v2027")]

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
    alternative_requirements = alternative.tree.requirements
    assert isinstance(alternative_requirements, CourseRequirement)
    assert alternative_requirements.course_group_id == "valid-leaf"
    assert [part.kind.value for part in alternative.tree.ignored_parts] == [
        "missing_module_alternative"
    ]
    assert alternative.tree.ignored_parts[0].referenced_group_ids == ("module-absent",)


def test_module_rule_malformed_shapes_become_explicit_unresolved_nodes() -> None:
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
        requirements = compilation.tree.requirements
        if isinstance(requirements, ModuleBlockRequirement):
            return requirements.child
        return requirements

    # A blank all-mandatory composite is an unexpandable block: it contributes nothing and
    # is disclosed, never a vacuous true AND or a malformed node.
    blank = compile_rule(module_rule(ModuleRuleType.COMPOSITE_RULE, all_mandatory=True))
    assert blank.tree.requirements is None
    assert [part.kind.value for part in blank.tree.ignored_parts] == ["unexpandable_content"]

    # A stored version with no rule tree is the same whole-module unexpandable shape, not a malformed
    # rule: with whole-module target credits it is one childless opaque obligation. With no credits it
    # is absent from calculation, disclosed, and kept as a childless display module.
    empty_credits = compile_rule(None, target_credits_min="35")
    empty_inlined = inlined(None, target_credits_min="35")
    assert isinstance(empty_inlined, OpaqueCreditRequirement)
    assert empty_inlined.credits_min == Decimal("35")
    assert [part.kind.value for part in empty_credits.tree.ignored_parts] == [
        "unexpandable_content"
    ]
    assert empty_credits.tree.ignored_parts[0].module is None
    assert [node.node_id for node in empty_credits.graph.module_nodes] == ["module:r"]
    assert len(empty_credits.graph.module_nodes) == 1
    empty_no_credits = compile_rule(None)
    assert empty_no_credits.tree.requirements is None
    assert [part.kind.value for part in empty_no_credits.tree.ignored_parts] == [
        "unexpandable_content"
    ]
    display_part = empty_no_credits.tree.ignored_parts[0]
    assert display_part.module is not None
    assert display_part.module.group_id == "module-malformed"
    assert [node.node_id for node in empty_no_credits.graph.module_nodes] == [
        f"module:{display_part.part_id}"
    ]
    assert empty_no_credits.graph.module_nodes[0].member_courses == ()
    assert empty_no_credits.graph.module_nodes[0].action_key == "module:module-malformed"

    # A credit wrapper whose only content is the immediate owning course is a direct self
    # occurrence: it contributes nothing and creates no credit obligation.
    self_credit = compile_rule(
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="5",
            children=(module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="root"),),
        )
    )
    assert self_credit.tree.requirements is None

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
    assert isinstance(malformed, UnresolvedRequirement)
    assert malformed.reason is UnresolvedPrerequisiteReason.MALFORMED_RULE
    assert malformed.official_kind is OfficialPrerequisiteKind.MODULE_RULE

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
    assert isinstance(surviving_impossible, CardinalityRequirement)
    assert surviving_impossible.require_min == 2
    assert len(surviving_impossible.children) == 1

    # Valid shapes referencing absent canonical entities become the specific missing reason.
    missing_course = inlined(
        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="absent-course")
    )
    assert isinstance(missing_course, UnresolvedRequirement)
    assert missing_course.reason is UnresolvedPrerequisiteReason.MISSING_COURSE
    assert missing_course.referenced_group_id == "absent-course"

    missing_module = inlined(
        module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="absent-module")
    )
    assert isinstance(missing_module, UnresolvedRequirement)
    assert missing_module.reason is UnresolvedPrerequisiteReason.MISSING_MODULE
    assert missing_module.referenced_group_id == "absent-module"

    # A genuinely empty official source option is dropped with an EMPTY_OPTION disclosure rather
    # than a vacuous true AND or a fabricated branch. The whole requirement is None and PATH is
    # exact zero.
    empty_option_root = catalogue_course(
        "empty-option-root",
        prerequisite_options=(prerequisite_option(0, PrerequisiteRequirementKind.COMPULSORY),),
    )
    empty_option = PrerequisiteGraphCompiler(
        FakeCurriculumRead((empty_option_root,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("empty-option-root")
    assert empty_option.tree.requirements is None
    assert [part.kind.value for part in empty_option.tree.ignored_parts] == ["empty_option"]
    empty_path = calculate_minimum_new_credits(empty_option.tree, [])
    assert empty_path.state is PrerequisitePathState.EXACT
    assert empty_path.total_new_credits == Decimal("0")
