"""Native drawing projection: sharing, marks, members and display identity."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.curriculum import CatalogueCurriculumPeriod
from course_explorer.enums import (
    ModuleRuleType,
    ModuleType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedAndRole,
    ComposedOrRole,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import PrerequisiteGraphCompiler
from course_explorer.prerequisite.projection import project_prerequisite_graph
from course_explorer.prerequisite.structure import support_id
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    child_uses,
    course_version,
    current_result,
    fact_of,
    ignored_parts,
    leaf_group_ids,
    module_rule,
    module_version,
    piece_of,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
    substitution_option,
)
from tests.prerequisite._path_support import (
    course_summary,
    expanded_course,
    inferred_course,
    make_compilation,
    module_cardinality,
    official_and,
    official_course,
    official_or,
    solve_route,
)


def _module(group_id: str, child) -> ModuleBlockRequirement:
    """Build one official module boundary over a compiled child shape."""
    return ModuleBlockRequirement(
        type="module_block",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        module_group_id=group_id,
        child=child,
    )


def _reachable_node_ids(display) -> set[str]:
    """Return every display node reachable from the root course."""
    adjacency: dict[str, set[str]] = {}
    for edge in display.edges:
        adjacency.setdefault(edge.source_node_id, set()).add(edge.target_node_id)
    root = next(node.node_id for node in display.nodes if node.is_root)
    seen = {root}
    stack = [root]
    while stack:
        current = stack.pop()
        for target in adjacency.get(current, ()):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def _endpoint_pairs(display) -> list[tuple[str, str]]:
    """Return every directed endpoint pair in display order."""
    return [(edge.source_node_id, edge.target_node_id) for edge in display.edges]


def _expanded_head_groups(structure, use_id: str | None) -> list[str]:
    """Return every expanded-course head occurrence through ordered child slots."""
    if use_id is None:
        return []
    groups: list[str] = []

    def walk(current: str, path: frozenset[str]) -> None:
        if current in path:
            return
        piece = piece_of(structure, current)
        if piece.kind == "expanded_course":
            head = piece_of(structure, child_uses(structure, current)[0])
            groups.append(head.course_group_id or "")
        next_path = path | {current}
        for child in child_uses(structure, current):
            walk(child, next_path)

    walk(use_id, frozenset())
    return groups


def _nodes(display, kind: str):
    """Return every display node of one kind."""
    return [node for node in display.nodes if node.kind == kind]


def _root_piece(structure):
    """Return the primary root piece, or `None` for a rootless structure."""
    if structure.root_use_id is None:
        return None
    return piece_of(structure, structure.root_use_id)


def test_projection_deduplicates_canonical_courses_and_exact_edges_only() -> None:
    """A canonical course is one node and one endpoint pair is one connection."""
    root = course_summary("root")
    requirements = official_and("a", "b", "a")
    compilation = make_compilation(root, requirements, (course_summary("a"), course_summary("b")))
    display = compilation.display
    assert display is not None
    course_ids = [node.node_id for node in display.nodes if node.kind == "course"]
    assert sorted(course_ids) == ["course:a", "course:b", "course:root"]
    endpoint_pairs = _endpoint_pairs(display)
    assert len(endpoint_pairs) == len(set(endpoint_pairs))
    assert len(display.edges) == 3
    assert _reachable_node_ids(display) == {node.node_id for node in display.nodes}


def test_projection_shares_identical_logical_subtrees_independent_of_provenance() -> None:
    """Reversed official and inferred OR children share one drawn box."""
    metadata = InferenceNodeMetadata(confidence=Decimal("0.9"))
    first = official_or("a", "b")
    second = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=metadata,
        children=(
            inferred_course("b", inference=metadata),
            inferred_course("a", inference=metadata),
        ),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(first, second),
    )
    compilation = make_compilation(
        course_summary("root"),
        requirements,
        (course_summary("a"), course_summary("b")),
        include_inferred=True,
    )
    display = compilation.display
    assert display is not None
    assert len(display.nodes) == 4
    or_nodes = [node for node in display.nodes if node.kind == "or"]
    assert len(or_nodes) == 1
    shared_or = or_nodes[0]
    assert shared_or.via_inferred is True
    assert shared_or.markable is False
    # Both ordered parent slots draw the same OR, so the parent AND collapses into that one box.
    assert [node for node in display.nodes if node.kind == "and"] == []
    assert set(_endpoint_pairs(display)) == {
        ("course:root", shared_or.node_id),
        (shared_or.node_id, "course:a"),
        (shared_or.node_id, "course:b"),
    }
    assert len(_endpoint_pairs(display)) == 3
    # The calculation holds the AND with its two ordered, distinct child pieces.
    root_use = compilation.solver.root_use_id
    assert root_use is not None
    assert piece_of(compilation.solver, root_use).kind == "and"
    root_children = child_uses(compilation.solver, root_use)
    assert len(root_children) == 2
    root_piece_ids = [piece_of(compilation.solver, use).piece_id for use in root_children]
    assert root_piece_ids[0] != root_piece_ids[1]
    # The one drawn box binds both ordered pieces, and its a connection holds both origins.
    assert {
        binding.piece_id
        for binding in compilation.solver.bindings
        if shared_or.node_id in binding.node_ids
    } == set(root_piece_ids)
    a_edge = next(edge for edge in display.edges if edge.target_node_id == "course:a")
    a_member_fact_ids = {
        member.fact_id
        for member in compilation.solver.members
        if member.member_id in a_edge.member_ids
    }
    assert {
        fact.origin for fact in compilation.solver.facts if fact.fact_id in a_member_fact_ids
    } == {PrerequisiteOrigin.OFFICIAL, PrerequisiteOrigin.INFERRED}


def test_projection_shares_identical_numeric_subtrees_with_all_source_marks(
    solver_bundle: None,
) -> None:
    """Two module parents share one numeric drawing backed by distinct ordered slots."""
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            # The same drawn set in a different order is a distinct ordered calculation slot.
            _module("m1", module_cardinality(2, 2, "p", "q", "r")),
            _module("m2", module_cardinality(2, 2, "r", "q", "p")),
        ),
    )
    compilation = make_compilation(
        course_summary("root"),
        requirements,
        (course_summary("p"), course_summary("q"), course_summary("r")),
    )
    display = compilation.display
    assert display is not None
    numeric = [node for node in display.nodes if node.kind == "cardinality"]
    assert len(numeric) == 1
    box = numeric[0]
    assert box.markable is True
    bindings = [
        binding for binding in compilation.solver.bindings if box.node_id in binding.mark_node_ids
    ]
    assert len({binding.piece_id for binding in bindings}) == 2
    assert sum(len(binding.use_ids) for binding in bindings) >= 2
    modules = [node for node in display.nodes if node.kind == "module"]
    assert len(modules) == 2
    assert len({node.node_id for node in modules}) == 2
    assert all(node.member_group_ids == ("p", "q", "r") for node in modules)

    # Actual satisfaction reaches every bound piece: p and q fulfill both modules at zero cost.
    satisfied = solve_route(compilation.solver, ["p", "q"])
    assert satisfied["state"] == "exact"
    assert satisfied["new_courses"] == []
    assert Decimal(satisfied["total_new_credits"]) == Decimal("0")

    # Completing the one shared numeric box manually fulfills both modules without completing members.
    manual_structure = compilation.solver.model_copy(
        update={
            "completed_node_keys": (box.node_id,),
            "bindings": tuple(
                binding.model_copy(
                    update={
                        "mark_node_ids": tuple(
                            node_id for node_id in binding.mark_node_ids if node_id == box.node_id
                        )
                    }
                )
                for binding in compilation.solver.bindings
            ),
        }
    )
    manual = solve_route(manual_structure, [])
    assert manual["state"] == "exact"
    assert Decimal(manual["total_new_credits"]) == Decimal("0")

    # Excluding the shared box denies both module rules.
    excluded_structure = compilation.solver.model_copy(
        update={"excluded_node_keys": (box.node_id,)}
    )
    excluded = solve_route(excluded_structure, [])
    assert excluded["state"] == "no_solution"

    # Equal rules under different expanded-course owners stay distinct drawings.
    independent = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            expanded_course("a", _module("m", module_cardinality(2, 2, "p", "q"))),
            expanded_course("b", _module("m", module_cardinality(2, 2, "p", "q"))),
        ),
    )
    independent_compilation = make_compilation(
        course_summary("root"),
        independent,
        (course_summary("a"), course_summary("b"), course_summary("p"), course_summary("q")),
    )
    independent_numeric = [
        node for node in independent_compilation.display.nodes if node.kind == "cardinality"
    ]
    assert len(independent_numeric) == 2
    assert {node.owner_group_id for node in independent_numeric} == {"a", "b"}


def test_saved_module_box_key_fulfils_its_calculation_support(solver_bundle: None) -> None:
    """A saved box key is scoped to its display identity and never converted."""
    requirements = _module("m", module_cardinality(2, 2, "p", "q"))
    first = make_compilation(
        course_summary("root"),
        requirements,
        (course_summary("p"), course_summary("q")),
    )
    box = next(node for node in first.display.nodes if node.markable)
    orphan = "s:root:d:" + "0" * 24
    marked = make_compilation(
        course_summary("root"),
        requirements,
        (course_summary("p"), course_summary("q")),
        completed_node_keys=(box.node_id, orphan),
    )
    assert marked.solver.completed_node_keys == tuple(sorted((box.node_id, orphan)))
    binding = next(value for value in marked.solver.bindings if box.node_id in value.mark_node_ids)
    assert binding.owner_group_id == "root"
    assert support_id(owner_group_id="root", piece_id=binding.piece_id) == binding.support_id

    # The saved box key fulfils its calculation support automatically, without completing the members.
    manual = solve_route(marked.solver, [])
    assert manual["state"] == "exact"
    assert manual["new_courses"] == []
    assert Decimal(manual["total_new_credits"]) == Decimal("0")
    selected = solve_route(first.solver, ["p", "q"])
    assert selected["state"] == "exact"
    assert Decimal(selected["total_new_credits"]) == Decimal("0")
    missing = solve_route(first.solver, [])
    assert missing["state"] == "exact"
    assert {entry["course"]["group_id"] for entry in missing["new_courses"]} == {"p", "q"}


def test_projection_groups_visible_connections_without_losing_relationship_evidence(
    solver_bundle: None,
) -> None:
    """One drawn connection keeps its compulsory and recommended occurrence members apart."""
    direct = official_course("a")
    first = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"),),
    )
    second = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.RECOMMENDED,
        children=(official_course("a", OfficialPrerequisiteKind.RECOMMENDED),),
    )
    # One independent sibling makes the root OR a drawn box, so the alternatives to `a` are
    # distinct drawn relationships under it.
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(direct, first, second, official_course("c")),
    )
    compilation = make_compilation(
        course_summary("root"), requirements, (course_summary("a"), course_summary("c"))
    )
    edges = [edge for edge in compilation.display.edges if edge.target_node_id == "course:a"]
    assert len(edges) == 1
    assert len(edges[0].member_ids) == 2
    members = [
        member for member in compilation.solver.members if member.member_id in edges[0].member_ids
    ]
    assert len({member.fact_id for member in members}) == 2
    compulsory = next(
        member
        for member in members
        if next(fact for fact in compilation.solver.facts if fact.fact_id == member.fact_id).origin
        is PrerequisiteOrigin.OFFICIAL
        and next(
            fact for fact in compilation.solver.facts if fact.fact_id == member.fact_id
        ).official_kind
        is OfficialPrerequisiteKind.COMPULSORY
    )
    recommended = next(member for member in members if member.member_id != compulsory.member_id)
    course_c_edge = next(
        edge for edge in compilation.display.edges if edge.target_node_id == "course:c"
    )

    path = solve_route(compilation.solver, [])
    assert path["state"] == "exact"
    assert [entry["course"]["group_id"] for entry in path["new_courses"]] == ["a"]
    assert Decimal(path["total_new_credits"]) == Decimal("5")
    lit = set(path["lit_members"])
    assert compulsory.member_id in lit
    assert recommended.member_id not in lit
    assert not lit & set(course_c_edge.member_ids)


def test_returned_category_roots_reference_the_native_structure() -> None:
    """Direct compilation returns category roots that resolve in its own use table."""
    courses = (
        catalogue_course(
            "root",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "a"),
                ),
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.RECOMMENDED,
                    prerequisite_course_member(0, "b"),
                ),
            ),
        ),
        catalogue_course("a"),
        catalogue_course("b"),
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    )
    direct = compiler.compile_direct_many(("root",))
    entry = direct[0]
    assert entry.required_use_id is not None
    assert entry.recommended_use_id is not None
    uses = {use.use_id: use for use in entry.solver.uses}
    assert entry.required_use_id in uses
    assert entry.recommended_use_id in uses
    required = piece_of(entry.solver, entry.required_use_id)
    recommended = piece_of(entry.solver, entry.recommended_use_id)
    assert required.kind == "course" and required.course_group_id == "a"
    assert recommended.kind == "course" and recommended.course_group_id == "b"


def test_module_cards_hide_member_closure_without_relabeling_independent_occurrences(
    solver_bundle: None,
) -> None:
    """A hidden official member head neither draws nor relabels an independently inferred course."""
    metadata = InferenceNodeMetadata(confidence=Decimal("0.9"))
    member_rule = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        children=(official_course("p", OfficialPrerequisiteKind.MODULE_RULE),),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            _module("m", member_rule),
            inferred_course("p", inference=metadata),
        ),
    )
    compilation = make_compilation(
        course_summary("root"),
        requirements,
        (course_summary("p"),),
        include_inferred=True,
    )
    display = compilation.display
    assert display is not None
    p_nodes = [
        node for node in display.nodes if node.kind == "course" and node.course_group_id == "p"
    ]
    assert len(p_nodes) == 1
    independent_p = p_nodes[0]
    assert independent_p.display_as_inferred is True
    assert independent_p.has_inferred_provenance is True
    assert independent_p.has_official_provenance is False
    incoming_p = [edge for edge in display.edges if edge.target_node_id == "course:p"]
    assert incoming_p
    assert all(edge.inferred_only for edge in incoming_p)

    module = next(node for node in display.nodes if node.kind == "module")
    assert module.member_group_ids == ("p",)
    assert module.markable is True
    assert not any(
        edge.source_node_id == module.node_id and edge.target_node_id == "course:p"
        for edge in display.edges
    )
    # The hidden member contributes its source use and official fact, bound to its
    # containing module box and never to a drawn course node of its own.
    emitted_ids = {node.node_id for node in display.nodes}
    member_piece_id = next(
        piece.piece_id
        for piece in compilation.solver.pieces
        if piece.kind == "course" and piece.course_group_id == "p" and piece.module_rule
    )
    hidden_bindings = [
        binding for binding in compilation.solver.bindings if binding.piece_id == member_piece_id
    ]
    assert len(hidden_bindings) == 1
    hidden_binding = hidden_bindings[0]
    assert hidden_binding.node_ids == (module.node_id,)
    assert set(hidden_binding.node_ids) <= emitted_ids
    uses_by_id = {use.use_id: use for use in compilation.solver.uses}
    facts_by_id = {fact.fact_id: fact for fact in compilation.solver.facts}
    assert {
        facts_by_id[uses_by_id[use_id].fact_id].origin for use_id in hidden_binding.use_ids
    } == {PrerequisiteOrigin.OFFICIAL}

    # An independently visible official occurrence suppresses the marker on the shared card and
    # leaves both visible-origin flags true.
    mixed = make_compilation(
        course_summary("root"),
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.COMPOSED,
            composed_role=ComposedAndRole.LOGICAL,
            children=(
                _module("m", member_rule),
                inferred_course("p", inference=metadata),
                official_course("p"),
            ),
        ),
        (course_summary("p"),),
        include_inferred=True,
    )
    assert mixed.display is not None
    mixed_p = next(
        node
        for node in mixed.display.nodes
        if node.kind == "course" and node.course_group_id == "p"
    )
    assert mixed_p.display_as_inferred is False
    assert mixed_p.has_official_provenance is True
    assert mixed_p.has_inferred_provenance is True


def test_childless_diagnostic_leaf_is_drawn() -> None:
    """A childless unresolved node is one explicit drawn leaf."""
    requirements = UnresolvedRequirement(
        type="unresolved",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
        referenced_group_id="missing",
    )
    compilation = make_compilation(course_summary("root"), requirements, ())
    node = next(node for node in compilation.display.nodes if node.kind == "unresolved")
    assert node.reason == "missing_course"
    assert node.referenced_group_id == "missing"


def test_single_child_and_or_wrappers_collapse_without_changing_meaning(
    solver_bundle: None,
) -> None:
    """A singleton module wrapper and a stored inferred wrapper collapse to their child."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    singleton_study = catalogue_module(
        "module-single",
        (
            module_version(
                "module-single-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="leaf"),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    outer_degree = catalogue_module(
        "module-degree",
        (
            module_version(
                "module-degree-v1",
                rule=module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-single"),
                curriculum_periods=year_period,
                module_type=ModuleType.DEGREE_PROGRAMME,
            ),
        ),
    )
    module_root = catalogue_course(
        "module-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-degree"),
            ),
        ),
    )
    module_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                module_root,
                catalogue_course(
                    "leaf",
                    prerequisite_options=(
                        prerequisite_option(
                            0,
                            PrerequisiteRequirementKind.COMPULSORY,
                            prerequisite_course_member(0, "external"),
                        ),
                    ),
                ),
                catalogue_course("external"),
            ),
            (outer_degree, singleton_study),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("module-root")
    module_piece = _root_piece(module_compilation.solver)
    assert module_piece is not None
    assert module_piece.kind == "module_block"
    assert module_piece.module_group_id == "module-degree"
    single_root = child_uses(module_compilation.solver, module_compilation.solver.root_use_id)[0]
    assert piece_of(module_compilation.solver, single_root).kind == "module_block"
    assert piece_of(module_compilation.solver, single_root).module_group_id == "module-single"
    leaf_use = child_uses(module_compilation.solver, single_root)[0]
    assert piece_of(module_compilation.solver, leaf_use).kind == "expanded_course"
    leaf_head, leaf_descendants = child_uses(module_compilation.solver, leaf_use)
    assert piece_of(module_compilation.solver, leaf_head).course_group_id == "leaf"
    assert leaf_group_ids(module_compilation.solver, leaf_descendants) == {"external"}
    # Structural nesting elides: the degree module collects the singleton's leaf card and the leaf's
    # external prerequisite, with no singleton module node and no independently drawn leaf course.
    modules = _nodes(module_compilation.display, "module")
    assert [node.module_group_id for node in modules] == ["module-degree"]
    degree_node = modules[0]
    assert degree_node.member_group_ids == ("leaf",)
    assert {node.course_group_id for node in _nodes(module_compilation.display, "course")} == {
        "module-root",
        "external",
    }
    assert not _nodes(module_compilation.display, "and")
    assert not _nodes(module_compilation.display, "or")
    assert {
        (edge.source_node_id, edge.target_node_id) for edge in module_compilation.display.edges
    } == {
        ("course:module-root", degree_node.node_id),
        (degree_node.node_id, "course:external"),
    }
    route = solve_route(module_compilation.solver, [])
    assert route["state"] == "exact"
    assert Decimal(route["total_new_credits"]) == Decimal("10")
    assert {entry["course"]["group_id"] for entry in route["new_courses"]} == {
        "leaf",
        "external",
    }
    external_edges = [
        edge
        for edge in module_compilation.display.edges
        if edge.target_node_id == "course:external"
    ]
    assert len(external_edges) == 1
    assert set(route["lit_members"]) & set(external_edges[0].member_ids)
    covered = solve_route(module_compilation.solver, ["leaf"])
    assert covered["state"] == "exact"
    assert Decimal(covered["total_new_credits"]) == Decimal("0")
    assert not (set(covered["lit_members"]) & set(external_edges[0].member_ids))

    # A stored inferred one-child AND wrapping a singleton OR collapses to its inferred child.
    metadata = InferenceNodeMetadata(confidence=Decimal("0.9"))
    one_child_inferred = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=metadata,
        children=(
            OrRequirement(
                type="or",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                inference=metadata,
                children=(inferred_course("solo", inference=metadata),),
            ),
        ),
    )
    inferred_wrapper = PrerequisiteGraphCompiler(
        FakeCurriculumRead((catalogue_course("wrapper-root"), catalogue_course("solo"))),
        RecordingInferredSetRead(
            {
                "wrapper-root": current_result("wrapper-root", expression=one_child_inferred),
                "solo": current_result("solo"),
            }
        ),
        RecordingEquivalenceGroupRead(),
    ).compile("wrapper-root", include_inferred=True)
    inferred_piece = _root_piece(inferred_wrapper.solver)
    assert inferred_piece is not None
    assert inferred_piece.kind == "course"
    assert inferred_piece.course_group_id == "solo"
    assert fact_of(inferred_wrapper.solver, inferred_wrapper.solver.root_use_id).origin is (
        PrerequisiteOrigin.INFERRED
    )

    # A free-only module wrapper is disclosed and drawn once with no fabricated member cards.
    free_module = catalogue_module(
        "module-free",
        (
            module_version(
                "module-free-v1",
                rule=module_rule(
                    ModuleRuleType.CREDITS_RULE,
                    credits_min="5",
                    children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    free_root = catalogue_course(
        "free-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-free"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-free"),
            ),
        ),
    )
    free_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((free_root,), (free_module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("free-root")
    free_piece = _root_piece(free_compilation.solver)
    assert free_piece is not None
    assert free_piece.kind == "or"
    assert [
        piece_of(free_compilation.solver, use).kind
        for use in child_uses(free_compilation.solver, free_compilation.solver.root_use_id)
    ] == ["module_block", "module_block"]
    assert [part.kind for part in ignored_parts(free_compilation.solver)] == ["free_choice"]
    free_modules = _nodes(free_compilation.display, "module")
    assert len(free_modules) == 1
    assert free_modules[0].member_group_ids == ()
    assert len(_nodes(free_compilation.display, "ignored")) == 1

    # Normalized same-operator nesting emits exactly one connector with one edge per endpoint pair.
    nested = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_and("a", "b"), official_course("c")),
    )
    folded = make_compilation(
        course_summary("root"),
        nested,
        (course_summary("a"), course_summary("b"), course_summary("c")),
    )
    assert len(_nodes(folded.display, "and")) == 1
    assert set(_endpoint_pairs(folded.display)) == {
        ("course:root", _nodes(folded.display, "and")[0].node_id),
        (_nodes(folded.display, "and")[0].node_id, "course:a"),
        (_nodes(folded.display, "and")[0].node_id, "course:b"),
        (_nodes(folded.display, "and")[0].node_id, "course:c"),
    }
    assert [edge.edge_id for edge in folded.display.edges] == sorted(
        edge.edge_id for edge in folded.display.edges
    )
    assert _reachable_node_ids(folded.display) == {node.node_id for node in folded.display.nodes}


def test_composed_and_role_distinguishes_logical_join_from_expanded_course() -> None:
    """Only the compiler's expanded-course role qualifies. An identical logical join never does."""
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "required-a"),
            ),
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.RECOMMENDED,
                prerequisite_course_member(0, "recommended-b"),
            ),
        ),
    )
    logical_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (root, catalogue_course("required-a"), catalogue_course("recommended-b"))
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root", include_recommended=True)
    logical_piece = _root_piece(logical_compilation.solver)
    assert logical_piece is not None
    assert logical_piece.kind == "and"
    logical_children = child_uses(
        logical_compilation.solver, logical_compilation.solver.root_use_id
    )
    assert [
        (
            piece_of(logical_compilation.solver, use).course_group_id,
            fact_of(logical_compilation.solver, use).official_kind,
        )
        for use in logical_children
    ] == [
        ("required-a", OfficialPrerequisiteKind.COMPULSORY),
        ("recommended-b", OfficialPrerequisiteKind.RECOMMENDED),
    ]

    expanded_root = catalogue_course(
        "expanded-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "course-with-descendant"),
                prerequisite_course_member(1, "required-peer"),
            ),
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.RECOMMENDED,
                prerequisite_course_member(0, "recommended-peer"),
            ),
        ),
    )
    descendant_course = catalogue_course(
        "course-with-descendant",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "descendant-a"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "descendant-b"),
            ),
        ),
    )
    expanded_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                expanded_root,
                descendant_course,
                catalogue_course("required-peer"),
                catalogue_course("recommended-peer"),
                catalogue_course("descendant-a"),
                catalogue_course("descendant-b"),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("expanded-root", include_recommended=True)
    expanded_piece = _root_piece(expanded_compilation.solver)
    assert expanded_piece is not None
    assert expanded_piece.kind == "and"
    root_children = child_uses(expanded_compilation.solver, expanded_compilation.solver.root_use_id)
    compulsory_use = root_children[0]
    assert piece_of(expanded_compilation.solver, compulsory_use).kind == "and"
    expanded_course_use = child_uses(expanded_compilation.solver, compulsory_use)[0]
    assert piece_of(expanded_compilation.solver, expanded_course_use).kind == "expanded_course"
    head_use = child_uses(expanded_compilation.solver, expanded_course_use)[0]
    assert piece_of(expanded_compilation.solver, head_use).course_group_id == (
        "course-with-descendant"
    )

    # A same-operator compulsory AND folds into the root AND: one connector holds the expanded head,
    # the required peer and the recommended peer. The expanded course keeps its own OR alternatives.
    connectors = _nodes(expanded_compilation.display, "and")
    assert len(connectors) == 1
    root_connector = connectors[0]
    or_connectors = _nodes(expanded_compilation.display, "or")
    assert len(or_connectors) == 1
    alternatives = or_connectors[0]
    assert {
        (edge.source_node_id, edge.target_node_id) for edge in expanded_compilation.display.edges
    } == {
        ("course:expanded-root", root_connector.node_id),
        (root_connector.node_id, "course:course-with-descendant"),
        (root_connector.node_id, "course:required-peer"),
        (root_connector.node_id, "course:recommended-peer"),
        ("course:course-with-descendant", alternatives.node_id),
        (alternatives.node_id, "course:descendant-a"),
        (alternatives.node_id, "course:descendant-b"),
    }
    assert _reachable_node_ids(expanded_compilation.display) == {
        node.node_id for node in expanded_compilation.display.nodes
    }


def test_course_nodes_annotate_official_and_inferred_provenance() -> None:
    """Course nodes label official/inferred occurrence provenance without relabeling connectors."""
    root = course_summary("root")
    metadata = InferenceNodeMetadata(confidence=Decimal("0.9"))
    inferred_expanded = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(
            inferred_course("shared", inference=metadata),
            official_course("inferred-desc"),
        ),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            official_course("official-only"),
            inferred_course("inferred-only", inference=metadata),
            official_course("shared"),
            official_course("shared", OfficialPrerequisiteKind.RECOMMENDED),
            inferred_course("shared", InferredPrerequisiteCategory.RECOMMENDED, inference=metadata),
            inferred_expanded,
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("official-only"),
            course_summary("inferred-only"),
            course_summary("shared"),
            course_summary("inferred-desc"),
        ),
        include_inferred=True,
    )
    nodes_by_group = {
        node.course_group_id: node
        for node in _nodes(compilation.display, "course")
        if node.course_group_id is not None
    }

    assert nodes_by_group["root"].has_official_provenance is False
    assert nodes_by_group["root"].has_inferred_provenance is False
    assert nodes_by_group["official-only"].has_official_provenance is True
    assert nodes_by_group["official-only"].has_inferred_provenance is False
    assert nodes_by_group["inferred-only"].has_official_provenance is False
    assert nodes_by_group["inferred-only"].has_inferred_provenance is True
    # One canonical node reached both officially and inferred reports both.
    assert nodes_by_group["shared"].has_official_provenance is True
    assert nodes_by_group["shared"].has_inferred_provenance is True
    # An official descendant of the inferred occurrence inherits the inferred path flag but keeps
    # its own official occurrence provenance.
    assert nodes_by_group["inferred-desc"].via_inferred is True
    assert nodes_by_group["inferred-desc"].has_official_provenance is True
    assert nodes_by_group["inferred-desc"].has_inferred_provenance is False
    # The one drawing-only display marker: inferred only without any official occurrence, and the
    # selected root never displays as its own prerequisite.
    assert nodes_by_group["root"].display_as_inferred is False
    assert nodes_by_group["official-only"].display_as_inferred is False
    assert nodes_by_group["inferred-only"].display_as_inferred is True
    assert nodes_by_group["shared"].display_as_inferred is False
    assert nodes_by_group["inferred-desc"].display_as_inferred is False

    # The node annotation never touches relationship provenance. One endpoint connection holds all
    # four official compulsory/recommended and inferred required/recommended members, each with its
    # own fact.
    shared_connections = [
        edge for edge in compilation.display.edges if edge.target_node_id == "course:shared"
    ]
    assert len(shared_connections) == 1
    shared_facts = [
        next(fact for fact in compilation.solver.facts if fact.fact_id == member.fact_id)
        for member in compilation.solver.members
        if member.member_id in shared_connections[0].member_ids
    ]
    assert len(shared_facts) == 4
    assert {(fact.origin, fact.official_kind, fact.inferred_category) for fact in shared_facts} == {
        (PrerequisiteOrigin.OFFICIAL, OfficialPrerequisiteKind.COMPULSORY, None),
        (PrerequisiteOrigin.OFFICIAL, OfficialPrerequisiteKind.RECOMMENDED, None),
        (PrerequisiteOrigin.INFERRED, None, InferredPrerequisiteCategory.REQUIRED),
        (PrerequisiteOrigin.INFERRED, None, InferredPrerequisiteCategory.RECOMMENDED),
    }
    desc_edges = [
        edge for edge in compilation.display.edges if edge.target_node_id == "course:inferred-desc"
    ]
    desc_facts = [
        next(fact for fact in compilation.solver.facts if fact.fact_id == member.fact_id)
        for edge in desc_edges
        for member in compilation.solver.members
        if member.member_id in edge.member_ids
    ]
    assert {fact.origin for fact in desc_facts} == {PrerequisiteOrigin.OFFICIAL}


def test_active_projection_compacts_source_alternatives_with_shared_course_chains(
    solver_bundle: None,
) -> None:
    """The shared-node drawing comes from real source alternatives."""
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "110"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.RECOMMENDED,
                prerequisite_course_member(0, "db100"),
            ),
            prerequisite_option(
                2,
                PrerequisiteRequirementKind.RECOMMENDED,
                prerequisite_course_member(0, "db100"),
                prerequisite_course_member(1, "115"),
            ),
        ),
    )
    courses = (
        root,
        catalogue_course(
            "110",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "100"),
                ),
            ),
            substitution_options=(substitution_option(0, ("inactive-alt", None)),),
        ),
        catalogue_course(
            "115",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "110"),
                ),
            ),
        ),
        catalogue_course(
            "db100",
            substitution_options=(substitution_option(0, ("inactive-sub", None)),),
        ),
        catalogue_course("100"),
        catalogue_course("inactive-alt", is_active=False),
        catalogue_course("inactive-sub", is_active=False),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root", include_recommended=True, active_only=True)
    structure = compilation.solver
    display = compilation.display
    assert display is not None

    # The unretained inactive substitution alternatives are dropped at compile time.
    assert leaf_group_ids(structure, structure.root_use_id) == {"100", "110", "115", "db100"}

    # Each canonical course is drawn once, and the two logical sources become one AND and one OR.
    assert [node.node_id for node in _nodes(display, "course")] == [
        "course:100",
        "course:110",
        "course:115",
        "course:db100",
        "course:root",
    ]
    assert sorted(node.kind for node in display.nodes if node.kind in ("and", "or")) == [
        "and",
        "and",
        "or",
    ]
    pairs = _endpoint_pairs(display)
    assert len(pairs) == len(set(pairs))
    assert _reachable_node_ids(display) == {node.node_id for node in display.nodes}
    assert len(display.edges) == 9

    # The drawing changes only presentation, so the real route charges the required courses.
    path = solve_route(structure, [])
    assert path["state"] == "exact"
    assert [entry["course"]["group_id"] for entry in path["new_courses"]] == [
        "100",
        "110",
        "db100",
    ]
    assert Decimal(path["total_new_credits"]) == Decimal("15")
    assert project_prerequisite_graph(structure).display == display


def test_mandatory_position_rule_governs_duplicate_cardinality_open_and_cycle_positions(
    solver_bundle: None,
) -> None:
    """A required course expands once, while non-mandatory, bounded and open positions expand
    each slot.
    """
    root = catalogue_course(
        "redundant-root",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "other")
            ),
            prerequisite_option(
                2, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    head = catalogue_course(
        "head",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "head-a"),
                prerequisite_course_member(1, "head-b"),
            ),
        ),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                root,
                head,
                catalogue_course("other"),
                catalogue_course("head-a"),
                catalogue_course("head-b"),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("redundant-root", include_recommended=True)
    structure = compilation.solver
    requirements_use = structure.root_use_id
    assert requirements_use is not None
    assert piece_of(structure, requirements_use).kind == "and"
    compulsory_use, recommended_use = child_uses(structure, requirements_use)
    assert piece_of(structure, compulsory_use).kind == "expanded_course"
    assert piece_of(structure, child_uses(structure, compulsory_use)[0]).course_group_id == "head"
    # The duplicate recommended occurrence stays a bare leaf under its recommended OR.
    assert [
        piece_of(structure, use).course_group_id for use in child_uses(structure, recommended_use)
    ] == ["other", "head"]
    assert _expanded_head_groups(structure, requirements_use) == ["head"]
    # The drawing holds one connector for the head's own requirement.
    head_edges = [
        edge for edge in compilation.display.edges if edge.source_node_id == "course:head"
    ]
    assert len(head_edges) == 1
    assert {
        edge.target_node_id
        for edge in compilation.display.edges
        if edge.source_node_id == head_edges[0].target_node_id
    } == {"course:head-a", "course:head-b"}

    # Two separate mandatory conjunction paths each carry their own expanded shared slot.
    repeat_root = catalogue_course(
        "repeat-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "via-alpha"),
                prerequisite_course_member(1, "via-beta"),
            ),
        ),
    )
    via_alpha = catalogue_course(
        "via-alpha",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "shared")
            ),
        ),
    )
    via_beta = catalogue_course(
        "via-beta",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "shared")
            ),
        ),
    )
    shared = catalogue_course(
        "shared",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "shared-base"),
                prerequisite_course_member(1, "shared-other"),
            ),
        ),
    )
    repeat_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                repeat_root,
                via_alpha,
                via_beta,
                shared,
                catalogue_course("shared-base"),
                catalogue_course("shared-other"),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("repeat-root")
    repeat_groups = _expanded_head_groups(
        repeat_compilation.solver, repeat_compilation.solver.root_use_id
    )
    assert sorted(repeat_groups) == ["shared", "shared", "via-alpha", "via-beta"]
    shared_edges = [
        edge for edge in repeat_compilation.display.edges if edge.source_node_id == "course:shared"
    ]
    assert len(shared_edges) == 1
    assert {
        edge.target_node_id
        for edge in repeat_compilation.display.edges
        if edge.source_node_id == shared_edges[0].target_node_id
    } == {"course:shared-base", "course:shared-other"}
    route = solve_route(repeat_compilation.solver, [])
    assert Decimal(route["total_new_credits"]) == Decimal("25")
    # A saved key on the shared logical box is not a markable box identity, so the drawing has one
    # normalized connector and the minimum route charges 25 new credits.
    marked_structure = repeat_compilation.solver.model_copy(
        update={"excluded_node_keys": (shared_edges[0].target_node_id,)}
    )
    marked = project_prerequisite_graph(marked_structure)
    assert marked.display is not None
    assert {(edge.source_node_id, edge.target_node_id) for edge in marked.display.edges} == {
        (edge.source_node_id, edge.target_node_id) for edge in repeat_compilation.display.edges
    }
    assert Decimal(solve_route(marked_structure, [])["total_new_credits"]) == Decimal("25")

    # A single-child wrapper at a mandatory position passes the mandatory flag to its child. Module
    # bodies are their own context: the member head expands inside the module while the independent
    # recommended occurrence also keeps its closure.
    wrapper_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    wrapper_module = catalogue_module(
        "module-wrapper",
        (
            module_version(
                "module-wrapper-v1",
                rule=module_rule(
                    ModuleRuleType.COURSE_UNIT_COUNT_RULE,
                    count_min=1,
                    count_max=1,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="head"),
                    ),
                ),
                curriculum_periods=wrapper_period,
            ),
        ),
    )
    wrapper_root = catalogue_course(
        "wrapper-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-wrapper"),
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "other")
            ),
            prerequisite_option(
                2, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    wrapper_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                wrapper_root,
                head,
                catalogue_course("other"),
                catalogue_course("head-a"),
                catalogue_course("head-b"),
            ),
            (wrapper_module,),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("wrapper-root", include_recommended=True)
    assert _expanded_head_groups(
        wrapper_compilation.solver, wrapper_compilation.solver.root_use_id
    ) == ["head", "head"]

    # A course reached only through a cardinality child is not a mandatory head: both slots expand.
    cardinality_module = catalogue_module(
        "module-cardinality",
        (
            module_version(
                "module-cardinality-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    require_min=1,
                    require_max=1,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="head"),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=1,
                            referenced_group_id="other",
                        ),
                    ),
                ),
                curriculum_periods=wrapper_period,
            ),
        ),
    )
    cardinality_root = catalogue_course(
        "cardinality-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-cardinality"),
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "other")
            ),
            prerequisite_option(
                2, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    cardinality_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                cardinality_root,
                head,
                catalogue_course("other"),
                catalogue_course("head-a"),
                catalogue_course("head-b"),
            ),
            (cardinality_module,),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("cardinality-root", include_recommended=True)
    assert _expanded_head_groups(
        cardinality_compilation.solver, cardinality_compilation.solver.root_use_id
    ) == ["head", "head"]

    # A course with no mandatory occurrence expands in every non-mandatory position.
    open_root = catalogue_course(
        "open-root",
        prerequisite_options=(
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                2, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    open_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (open_root, head, catalogue_course("head-a"), catalogue_course("head-b"))
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("open-root", include_recommended=True)
    assert _expanded_head_groups(open_compilation.solver, open_compilation.solver.root_use_id) == [
        "head",
        "head",
    ]

    # A cycle leaf is preserved with its closing piece and one located course-cycle issue.
    cycle_root = catalogue_course(
        "cycle-root",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "cycle-a")
            ),
        ),
    )
    cycle_a = catalogue_course(
        "cycle-a",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "cycle-root"),
            ),
        ),
    )
    cycle_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((cycle_root, cycle_a)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("cycle-root")
    cycle_piece = _root_piece(cycle_compilation.solver)
    assert cycle_piece is not None and cycle_piece.kind == "expanded_course"
    closing = [
        piece
        for piece in cycle_compilation.solver.pieces
        if piece.kind == "course" and piece.cycle_closing and piece.course_group_id == "cycle-root"
    ]
    assert len(closing) == 1
    assert [
        issue.kind for issue in cycle_compilation.solver.diagnostics if issue.kind == "course_cycle"
    ] == ["course_cycle"]


def test_a_course_with_a_substitution_expands_at_its_compulsory_and_repeated_recommended_occurrences() -> (
    None
):
    """A course carrying a substitution expands at both its compulsory and recommended slots."""
    root = catalogue_course(
        "alternatives-root",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "other")
            ),
            prerequisite_option(
                2, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    head = catalogue_course(
        "head",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "head-base"),
            ),
        ),
        substitution_options=(substitution_option(0, ("head-alt", None)),),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                root,
                head,
                catalogue_course("other"),
                catalogue_course("head-base"),
                catalogue_course("head-alt"),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("alternatives-root", include_recommended=True)
    structure = compilation.solver
    requirements_use = structure.root_use_id
    assert requirements_use is not None
    assert piece_of(structure, requirements_use).kind == "and"
    compulsory_use, recommended_use = child_uses(structure, requirements_use)

    # The compulsory slot wraps the head's expansion in a course-alternatives OR whose first child
    # is the expanded occurrence and whose alternative is the official substitute.
    assert piece_of(structure, compulsory_use).kind == "course_alternatives"
    represented_use, substitute_use = child_uses(structure, compulsory_use)
    assert piece_of(structure, represented_use).kind == "expanded_course"
    assert piece_of(structure, child_uses(structure, represented_use)[0]).course_group_id == "head"
    substitute_piece = piece_of(structure, substitute_use)
    substitute_fact = fact_of(structure, substitute_use)
    assert substitute_piece.kind == "course" and substitute_piece.course_group_id == "head-alt"
    assert substitute_fact.official_kind is OfficialPrerequisiteKind.SUBSTITUTION

    # The repeated recommended occurrence also expands the head and keeps its own wrapper.
    assert piece_of(structure, recommended_use).kind == "or"
    repeated = [
        use
        for use in child_uses(structure, recommended_use)
        if piece_of(structure, use).kind == "course_alternatives"
    ]
    assert len(repeated) == 1
    repeated_represented = child_uses(structure, repeated[0])[0]
    assert piece_of(structure, repeated_represented).kind == "expanded_course"
    repeated_head_use = child_uses(structure, repeated_represented)[0]
    assert piece_of(structure, repeated_head_use).course_group_id == "head"
    assert (
        fact_of(structure, repeated_head_use).official_kind is OfficialPrerequisiteKind.RECOMMENDED
    )
    assert _expanded_head_groups(structure, requirements_use) == ["head", "head"]


def test_projection_aggregates_course_path_flags_without_rewriting_provenance() -> None:
    """Course nodes aggregate independent visibility flags while local provenance is exact."""
    root = course_summary("root")
    metadata = InferenceNodeMetadata(confidence=Decimal("0.9"))
    recommended_branch = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.RECOMMENDED,
        children=(
            official_course("recommended-only", OfficialPrerequisiteKind.RECOMMENDED),
            official_course("shared", OfficialPrerequisiteKind.RECOMMENDED),
        ),
    )
    substitution_wrapper = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.COURSE_ALTERNATIVES,
        children=(
            official_course("inferred-desc"),
            AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
                children=(official_course("substitute", OfficialPrerequisiteKind.SUBSTITUTION),),
            ),
        ),
    )
    inferred_expanded = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(inferred_course("shared", inference=metadata), substitution_wrapper),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            official_course("required-only"),
            recommended_branch,
            inferred_expanded,
            inferred_course(
                "recommended-inferred",
                InferredPrerequisiteCategory.RECOMMENDED,
                inference=metadata,
            ),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("required-only"),
            course_summary("recommended-only"),
            course_summary("recommended-inferred"),
            course_summary("shared"),
            course_summary("inferred-desc"),
            course_summary("substitute"),
        ),
        include_recommended=True,
        include_inferred=True,
    )
    nodes_by_group = {
        node.course_group_id: node
        for node in _nodes(compilation.display, "course")
        if node.course_group_id is not None
    }

    assert nodes_by_group["root"].via_inferred is False
    assert nodes_by_group["root"].via_recommended is False
    assert nodes_by_group["required-only"].via_inferred is False
    assert nodes_by_group["required-only"].via_recommended is False
    # One canonical course reached through separate recommended and inferred occurrences keeps both.
    assert nodes_by_group["shared"].via_recommended is True
    assert nodes_by_group["shared"].via_inferred is True
    assert nodes_by_group["recommended-only"].via_recommended is True
    assert nodes_by_group["recommended-only"].via_inferred is False
    assert nodes_by_group["inferred-desc"].via_inferred is True
    assert nodes_by_group["inferred-desc"].via_recommended is False
    # An inferred recommended occurrence is on both the inferred and recommended paths.
    assert nodes_by_group["recommended-inferred"].via_inferred is True
    assert nodes_by_group["recommended-inferred"].via_recommended is True
    # Official substitution members beneath a bare inferred parent inherit the inferred path.
    assert nodes_by_group["substitute"].via_inferred is True
    assert nodes_by_group["substitute"].via_recommended is False

    # Local provenance is preserved through the native facts of the merged endpoint relationships.
    def edge_facts(target: str):
        return [
            next(fact for fact in compilation.solver.facts if fact.fact_id == member.fact_id)
            for edge in compilation.display.edges
            if edge.target_node_id == target
            for member in compilation.solver.members
            if member.member_id in edge.member_ids
        ]

    inferred_recommended_facts = edge_facts("course:recommended-inferred")
    assert len(inferred_recommended_facts) == 1
    assert inferred_recommended_facts[0].origin is PrerequisiteOrigin.INFERRED
    assert (
        inferred_recommended_facts[0].inferred_category is InferredPrerequisiteCategory.RECOMMENDED
    )
    assert inferred_recommended_facts[0].official_kind is None
    assert {fact.official_kind for fact in edge_facts("course:shared")} == {
        None,
        OfficialPrerequisiteKind.RECOMMENDED,
    }
    substitution_facts = [
        next(fact for fact in compilation.solver.facts if fact.fact_id == member.fact_id)
        for edge in compilation.display.edges
        for member in compilation.solver.members
        if member.member_id in edge.member_ids
        and next(
            fact for fact in compilation.solver.facts if fact.fact_id == member.fact_id
        ).official_kind
        is OfficialPrerequisiteKind.SUBSTITUTION
    ]
    assert substitution_facts
    assert all(fact.origin is PrerequisiteOrigin.OFFICIAL for fact in substitution_facts)

    # Deterministic: an identical structure projects to the same aggregated flags.
    assert project_prerequisite_graph(compilation.solver).display == compilation.display


def test_module_cards_follow_activity_retention_and_unretained_member_reports_no_solution(
    solver_bundle: None,
) -> None:
    """Module cards follow activity retention and exclusion, and an unretained member blocks the route."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module = catalogue_module(
        "module-a",
        (
            module_version(
                "module-a-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    require_min=2,
                    require_max=2,
                    children=(
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=0,
                            referenced_group_id="inactive-member",
                        ),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=1,
                            referenced_group_id="active-member",
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
                prerequisite_module_member(0, "module-a"),
            ),
        ),
    )
    active_member = catalogue_course(
        "active-member",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "external-prerequisite"),
            ),
        ),
    )
    courses = (
        root,
        catalogue_course("inactive-member", is_active=False),
        active_member,
        catalogue_course("external-prerequisite"),
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    )

    # Both official module members are cards, and the active member's prerequisite draws.
    all_courses = compiler.compile("root")
    assert {node.course_group_id for node in _nodes(all_courses.display, "course")} == {
        "external-prerequisite",
        "root",
    }
    module_node = _nodes(all_courses.display, "module")[0]
    assert module_node.member_group_ids == ("active-member", "inactive-member")
    internal = _nodes(all_courses.display, "internal_requirement")
    assert [node.member_group_ids for node in internal] == [("inactive-member",)]

    # Active-only drops the unretained inactive member, so the rule cannot meet its bound.
    active_only = compiler.compile("root", active_only=True)
    active_module = _nodes(active_only.display, "module")[0]
    assert active_module.member_group_ids == ("active-member",)
    assert _nodes(active_only.display, "internal_requirement") == []
    assert solve_route(active_only.solver, [])["state"] == "no_solution"

    # Retaining the selected identity restores the card, the disclosure and a satisfiable route.
    retained = compiler.compile("root", active_only=True, retained_group_ids=("inactive-member",))
    assert _nodes(retained.display, "module")[0].member_group_ids == (
        "active-member",
        "inactive-member",
    )
    assert [node.member_group_ids for node in _nodes(retained.display, "internal_requirement")] == [
        ("inactive-member",)
    ]
    retained_path = solve_route(retained.solver, ["inactive-member"])
    assert retained_path["state"] == "exact"

    # An excluded member is a visible card but is denied by the calculation.
    excluded = compiler.compile("root", excluded_group_ids=("inactive-member",))
    assert _nodes(excluded.display, "module")[0].member_group_ids == (
        "active-member",
        "inactive-member",
    )
    excluded_path = solve_route(excluded.solver, [])
    assert excluded_path["state"] == "no_solution"
    assert excluded_path["blocked_excluded_group_ids"] == ["inactive-member"]


def test_external_module_dependencies_preserve_conditional_route_evidence(
    solver_bundle: None,
) -> None:
    """A hidden-member diamond holds one framed external obligation and exact route evidence."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module = catalogue_module(
        "module-abc",
        (
            module_version(
                "module-abc-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=tuple(
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=index,
                            referenced_group_id=group_id,
                        )
                        for index, group_id in enumerate(("A", "B", "C", "D"))
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
                prerequisite_module_member(0, "module-abc"),
                prerequisite_course_member(1, "outside"),
            ),
        ),
    )

    def require(*group_ids: str) -> tuple:
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

    outside = catalogue_course(
        "outside",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "B")
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "X")
            ),
        ),
    )
    courses = (
        root,
        catalogue_course("A", prerequisite_options=require("B", "C")),
        catalogue_course("B", prerequisite_options=require("D")),
        catalogue_course("C", prerequisite_options=require("D")),
        catalogue_course("D", prerequisite_options=require("E")),
        catalogue_course("E"),
        outside,
        catalogue_course("X"),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")
    display = compilation.display
    assert display is not None
    assert len(display.edges) == len(
        {(edge.source_node_id, edge.target_node_id) for edge in display.edges}
    )

    module_node = next(
        node for node in _nodes(display, "module") if node.module_group_id == "module-abc"
    )
    assert module_node.member_group_ids == ("A", "B", "C", "D")
    module_edges = [edge for edge in display.edges if edge.source_node_id == module_node.node_id]
    # Unary normalization leaves the module one direct external attachment.
    assert len(module_edges) == 1
    module_to_e = module_edges[0]
    assert module_to_e.target_node_id == "course:E"
    assert module_to_e.member_ids

    # A and C are hidden module cards. The independent B occurrence keeps its own closure, so B
    # and its prerequisite D draw as standalone course nodes, while E is the shared external node.
    course_ids = {node.course_group_id for node in _nodes(display, "course")}
    assert "A" not in course_ids
    assert "C" not in course_ids
    assert {"B", "D", "E", "outside", "X"} <= course_ids
    b_nodes = [node for node in _nodes(display, "course") if node.course_group_id == "B"]
    assert len(b_nodes) == 1
    assert b_nodes[0].has_official_provenance is True
    assert b_nodes[0].display_as_inferred is False
    assert {(edge.source_node_id, edge.target_node_id) for edge in display.edges} >= {
        ("course:B", "course:D"),
        ("course:D", "course:E"),
    }
    assert not any(
        edge.source_node_id == module_node.node_id
        and edge.target_node_id in {"course:B", "course:C", "course:D"}
        for edge in display.edges
    )
    outside_edges = [edge for edge in display.edges if edge.source_node_id == "course:outside"]
    assert len(outside_edges) == 1
    outside_or_id = outside_edges[0].target_node_id
    assert next(node for node in display.nodes if node.node_id == outside_or_id).kind == "or"
    assert {
        edge.target_node_id for edge in display.edges if edge.source_node_id == outside_or_id
    } == {
        "course:B",
        "course:X",
    }

    # Every module member's course-head use binds to an emitted containing location.
    emitted_ids = {node.node_id for node in display.nodes}
    assert all(
        binding.node_ids and set(binding.node_ids) <= emitted_ids
        for binding in compilation.solver.bindings
    )
    for member in ("A", "B", "C", "D"):
        member_piece_ids = {
            piece.piece_id
            for piece in compilation.solver.pieces
            if piece.kind == "course" and piece.course_group_id == member
        }
        assert [
            binding
            for binding in compilation.solver.bindings
            if binding.piece_id in member_piece_ids
        ]

    path = solve_route(compilation.solver, [])
    assert path["state"] == "exact"
    assert tuple(entry["course"]["group_id"] for entry in path["new_courses"]) == (
        "A",
        "B",
        "C",
        "D",
        "E",
        "outside",
    )
    assert Decimal(path["total_new_credits"]) == Decimal("30")
    # The needed external E relationship is lit by the actual route and correlates.
    assert set(path["lit_members"]) & set(module_to_e.member_ids)
    assert set(path["lit_members"]) <= {
        member_id for edge in display.edges for member_id in edge.member_ids
    }

    # Basis-covered heads bypass their own prerequisites, so E is neither needed nor lit.
    covered = solve_route(compilation.solver, ["A", "B", "C", "D", "outside"])
    assert covered["state"] == "exact"
    assert Decimal(covered["total_new_credits"]) == Decimal("0")
    assert covered["new_courses"] == []
    assert not (
        set(covered["lit_members"])
        & {
            member.member_id
            for member in compilation.solver.members
            if member.target_node_id == "course:E"
        }
    )

    # A mixed module choice represents this option as a childless requirement disclosure.
    choice_module = catalogue_module(
        "module-choice",
        (
            module_version(
                "module-choice-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    require_min=1,
                    require_max=1,
                    children=(
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            referenced_group_id="choice-internal",
                        ),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=1,
                            referenced_group_id="choice-external",
                        ),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    choice_root = catalogue_course(
        "choice-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-choice"),
            ),
        ),
    )
    choice_external = catalogue_course(
        "choice-external", prerequisite_options=require("choice-dep")
    )
    choice_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                choice_root,
                catalogue_course("choice-internal"),
                choice_external,
                catalogue_course("choice-dep"),
            ),
            (choice_module,),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("choice-root")
    choice_module_node = next(
        node
        for node in _nodes(choice_compilation.display, "module")
        if node.module_group_id == "module-choice"
    )
    assert choice_module_node.member_group_ids == ("choice-external", "choice-internal")
    assert _nodes(choice_compilation.display, "cardinality")
    assert _nodes(choice_compilation.display, "internal_requirement")
    assert "choice-dep" in {
        node.course_group_id for node in _nodes(choice_compilation.display, "course")
    }


def test_member_whole_module_prerequisite_draws_a_distinct_module_node(solver_bundle: None) -> None:
    """A member's whole-module prerequisite draws its own node while structural nesting elides."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    outer_module = catalogue_module(
        "module-a",
        (
            module_version(
                "module-a-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-s"),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    structural_module = catalogue_module(
        "module-s",
        (
            module_version(
                "module-s-v1",
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
    whole_module = catalogue_module(
        "module-n",
        (
            module_version(
                "module-n-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="Q"),
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
                prerequisite_module_member(0, "module-a"),
            ),
        ),
    )
    member_p = catalogue_course(
        "P",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-n"),
            ),
        ),
    )
    member_q = catalogue_course(
        "Q",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "E"),
            ),
        ),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (root, member_p, member_q, catalogue_course("E")),
            (outer_module, structural_module, whole_module),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")
    display = compilation.display
    assert display is not None
    modules = {node.module_group_id: node for node in _nodes(display, "module")}
    assert set(modules) == {"module-a", "module-n"}
    module_a_node = modules["module-a"]
    module_n_node = modules["module-n"]
    assert module_a_node.member_group_ids == ("P",)
    assert module_n_node.member_group_ids == ("Q",)
    assert {node.course_group_id for node in _nodes(display, "course")} == {"root", "E"}
    assert set(_endpoint_pairs(display)) == {
        ("course:root", module_a_node.node_id),
        (module_a_node.node_id, module_n_node.node_id),
        (module_n_node.node_id, "course:E"),
    }

    # The structurally nested module binds to the emitted containing box.
    structural_piece = next(
        piece
        for piece in compilation.solver.pieces
        if piece.kind == "module_block" and piece.module_group_id == "module-s"
    )
    structural_binding = next(
        binding
        for binding in compilation.solver.bindings
        if binding.piece_id == structural_piece.piece_id
    )
    assert structural_binding.node_ids == (module_a_node.node_id,)

    path = solve_route(compilation.solver, [])
    assert path["state"] == "exact"
    assert [entry["course"]["group_id"] for entry in path["new_courses"]] == ["E", "P", "Q"]
    assert Decimal(path["total_new_credits"]) == Decimal("15")
    module_to_e = next(
        edge
        for edge in display.edges
        if edge.source_node_id == module_n_node.node_id and edge.target_node_id == "course:E"
    )
    emitted_members = {member_id for edge in display.edges for member_id in edge.member_ids}
    assert set(path["lit_members"]) <= emitted_members
    for pair in _endpoint_pairs(display):
        edge = next(
            edge for edge in display.edges if (edge.source_node_id, edge.target_node_id) == pair
        )
        assert set(path["lit_members"]) & set(edge.member_ids)
    assert set(path["lit_members"]) & set(module_to_e.member_ids)

    covered = solve_route(compilation.solver, ["P"])
    assert covered["state"] == "exact"
    assert Decimal(covered["total_new_credits"]) == Decimal("0")
    assert not (set(covered["lit_members"]) & set(module_to_e.member_ids))


def test_module_membership_scopes_shared_external_course_connections(solver_bundle: None) -> None:
    """Each module draws its own external member connection, and another membership redirects
    none.
    """
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
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    module_m3 = catalogue_module(
        "M3",
        (
            module_version(
                "M3-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="Q"),
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
                prerequisite_module_member(1, "M2"),
                prerequisite_module_member(2, "M3"),
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
            (root, member_p, catalogue_course("Q")), (module_m1, module_m2, module_m3)
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")
    display = compilation.display
    assert display is not None
    modules = {node.module_group_id: node for node in _nodes(display, "module")}
    assert set(modules) == {"M1", "M2", "M3"}
    assert {node.course_group_id for node in _nodes(display, "course")} == {"root", "Q"}
    pairs = set(_endpoint_pairs(display))
    external_edges = {}
    for group_id in ("M1", "M2"):
        external_edges[group_id] = next(
            edge
            for edge in display.edges
            if edge.source_node_id == modules[group_id].node_id
            and edge.target_node_id == "course:Q"
        )
        assert (modules[group_id].node_id, "course:Q") in pairs
        assert (modules[group_id].node_id, modules["M3"].node_id) not in pairs
    assert not any(
        edge.source_node_id == modules["M3"].node_id and edge.target_node_id.startswith("course:")
        for edge in display.edges
    )

    path = solve_route(compilation.solver, [])
    assert path["state"] == "exact"
    assert [entry["course"]["group_id"] for entry in path["new_courses"]] == ["P", "Q"]
    assert Decimal(path["total_new_credits"]) == Decimal("10")
    for edge in external_edges.values():
        assert set(path["lit_members"]) & set(edge.member_ids)

    covered = solve_route(compilation.solver, ["P", "Q"])
    assert covered["state"] == "exact"
    assert Decimal(covered["total_new_credits"]) == Decimal("0")
    for edge in external_edges.values():
        assert not (set(covered["lit_members"]) & set(edge.member_ids))


def test_member_prerequisite_choice_draws_its_conditional_or(solver_bundle: None) -> None:
    """A member's official and inferred alternatives keep one conditional OR with its disclosure."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module_a = catalogue_module(
        "A",
        (
            module_version(
                "A-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="P"),
                        module_rule(
                            ModuleRuleType.COMPOSITE_RULE,
                            sibling_position=1,
                            require_min=0,
                            require_max=1,
                            children=(
                                module_rule(
                                    ModuleRuleType.COURSE_UNIT_RULE,
                                    referenced_group_id="Q",
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
                prerequisite_module_member(0, "A"),
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
    member_q = catalogue_course("Q", representative=course_version(code="Q", credits_min="10"))
    metadata = InferenceNodeMetadata(confidence=Decimal("0.9"))
    inferred = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=metadata,
        children=(
            OrRequirement(
                type="or",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                inference=metadata,
                children=(inferred_course("E"),),
            ),
        ),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (root, member_p, member_q, catalogue_course("E")),
            (module_a,),
        ),
        RecordingInferredSetRead(
            {
                "P": current_result("P", expression=inferred),
                "Q": current_result("Q"),
                "E": current_result("E"),
            }
        ),
        RecordingEquivalenceGroupRead(),
    ).compile("root", include_inferred=True)
    display = compilation.display
    assert display is not None
    module_node = next(node for node in _nodes(display, "module") if node.module_group_id == "A")
    assert module_node.member_group_ids == ("P", "Q")
    assert {node.course_group_id for node in _nodes(display, "course")} == {"root", "E"}
    assert not any(edge.target_node_id == "course:Q" for edge in display.edges)
    or_nodes = _nodes(display, "or")
    assert len(or_nodes) == 1
    choice_or = or_nodes[0]
    assert choice_or.owner_group_id == "P"
    disclosure = next(
        node for node in _nodes(display, "internal_requirement") if node.owner_group_id == "P"
    )
    assert disclosure.member_group_ids == ("Q",)
    assert {
        edge.target_node_id for edge in display.edges if edge.source_node_id == choice_or.node_id
    } == {disclosure.node_id, "course:E"}
    reachable = {module_node.node_id}
    pending = [module_node.node_id]
    while pending:
        current = pending.pop()
        for edge in display.edges:
            if edge.source_node_id == current and edge.target_node_id not in reachable:
                reachable.add(edge.target_node_id)
                pending.append(edge.target_node_id)
    assert choice_or.node_id in reachable

    or_to_e = next(
        edge
        for edge in display.edges
        if edge.source_node_id == choice_or.node_id and edge.target_node_id == "course:E"
    )
    assert or_to_e.inferred_only is True
    facts = {fact.fact_id: fact for fact in compilation.solver.facts}
    member_records = {member.member_id: member for member in compilation.solver.members}
    assert {
        facts[member_records[member_id].fact_id].origin for member_id in or_to_e.member_ids
    } == {PrerequisiteOrigin.INFERRED}

    path = solve_route(compilation.solver, [])
    assert path["state"] == "exact"
    assert [entry["course"]["group_id"] for entry in path["new_courses"]] == ["E", "P"]
    assert Decimal(path["total_new_credits"]) == Decimal("10")
    assert set(path["lit_members"]) & set(or_to_e.member_ids)

    covered = solve_route(compilation.solver, ["P"])
    assert covered["state"] == "exact"
    assert Decimal(covered["total_new_credits"]) == Decimal("0")
    assert not (set(covered["lit_members"]) & set(or_to_e.member_ids))
