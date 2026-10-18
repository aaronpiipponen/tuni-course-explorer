"""Drawing-graph projection, deduplication, wrapper collapse, and connector pruning."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
)
from course_explorer.enums import (
    ModuleRuleType,
    ModuleType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedAndRole,
    ComposedOrRole,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    InferenceEvidenceKind,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
    expression_course_leaf_group_ids,
)
from course_explorer.prerequisite.graph import (
    DirectPrerequisiteReadContext,
    PrerequisiteCalculationTree,
    PrerequisiteDrawingGraph,
    PrerequisiteGraphCompiler,
    PrerequisiteGraphConnectorKind,
    _iter_expression_occurrences,
    is_expanded_course_branch,
    project_prerequisite_graph,
)
from course_explorer.prerequisite.path import (
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from course_explorer.prerequisite.satisfaction import (
    evaluate_prerequisite_node_states,
)
from tests.prerequisite._graph_support import (
    INFERENCE_METADATA,
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    course_summary,
    current_result,
    inferred_course,
    make_tree,
    module_rule,
    module_version,
    official_course,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
    substitution_option,
)


def test_projection_deduplicates_canonical_courses_and_exact_edges_only() -> None:
    """Projection shares canonical nodes, merges exact edges, and keeps scoped connectors."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            official_course("shared"),
            official_course("shared"),
            CardinalityRequirement(
                type="cardinality",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                require_min=1,
                require_max=2,
                children=(official_course("other"), official_course("shared")),
            ),
        ),
    )
    tree = make_tree(
        root,
        requirements,
        (course_summary("shared"), course_summary("other")),
    )
    graph = project_prerequisite_graph(tree)

    # Repeated occurrences of one canonical course share one node with one root flag.
    shared_nodes = [node for node in graph.course_nodes if node.course.group_id == "shared"]
    assert len(shared_nodes) == 1
    assert shared_nodes[0].is_root is False
    assert sum(1 for node in graph.course_nodes if node.is_root) == 1

    # Exact duplicate relationships merge terminal occurrence IDs inside one visible connection.
    # Distinct connectors stay separate.
    shared_edges = [
        edge
        for edge in graph.edges
        if edge.target_node_id == "course:shared" and edge.source_node_id == "connector:r"
    ]
    assert len(shared_edges) == 1
    assert shared_edges[0].relationships[0].occurrence_ids == ("r.0", "r.1")
    connector_ids = {node.node_id for node in graph.connector_nodes}
    assert {"connector:r", "connector:r.2"} <= connector_ids
    assert not any(node.node_id.startswith("course:module") for node in graph.course_nodes)

    # Deterministic: identical trees project to equal graphs.
    assert project_prerequisite_graph(tree) == graph
    assert [node.node_id for node in graph.connector_nodes] == sorted(
        node.node_id for node in graph.connector_nodes
    )
    assert list(graph.edges) == sorted(
        graph.edges,
        key=lambda edge: (
            edge.source_node_id,
            edge.target_node_id,
            edge.relationships[0].origin.value,
            (
                ""
                if edge.relationships[0].official_kind is None
                else edge.relationships[0].official_kind.value
            ),
        ),
    )

    # Root-only projection when the root has no requirements.
    empty_tree = make_tree(root, None, ())
    empty_graph = project_prerequisite_graph(empty_tree)
    assert len(empty_graph.course_nodes) == 1
    assert empty_graph.connector_nodes == ()
    assert empty_graph.edges == ()

    # Unresolved and numeric connectors preserve their scoped diagnostics.
    unresolved_tree = make_tree(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("5"),
            credits_max=Decimal("10"),
            child=CourseCountRequirement(
                type="course_count",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                count_min=1,
                count_max=2,
                child=UnresolvedRequirement(
                    type="unresolved",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
                ),
            ),
        ),
        (),
    )
    unresolved_graph = project_prerequisite_graph(unresolved_tree)
    credit_connector = next(
        node for node in unresolved_graph.connector_nodes if node.node_id == "connector:r"
    )
    assert credit_connector.kind is PrerequisiteGraphConnectorKind.CREDITS
    assert credit_connector.credits_min == Decimal("5")
    assert credit_connector.credits_max == Decimal("10")
    count_connector = next(
        node for node in unresolved_graph.connector_nodes if node.node_id == "connector:r.0"
    )
    assert count_connector.kind is PrerequisiteGraphConnectorKind.COURSE_COUNT
    assert count_connector.count_min == 1
    assert count_connector.count_max == 2
    assert count_connector.origin is PrerequisiteOrigin.OFFICIAL
    assert count_connector.official_kind is OfficialPrerequisiteKind.MODULE_RULE
    unresolved_connector = next(
        node for node in unresolved_graph.connector_nodes if node.node_id == "connector:r.0.0"
    )
    assert unresolved_connector.kind is PrerequisiteGraphConnectorKind.UNRESOLVED
    assert unresolved_connector.unresolved_reason is UnresolvedPrerequisiteReason.MISSING_MODULE


def test_projection_groups_visible_connections_without_losing_relationship_evidence() -> None:
    """Equal-endpoint, equal-class relationships draw once while keeping every member's evidence."""
    first_metadata = InferenceNodeMetadata(
        confidence=Decimal("0.85"),
        requirement_ids=("requirement-a",),
        evidence=(
            InferenceEvidenceReference(
                kind=InferenceEvidenceKind.EXPRESSION_PROPOSAL, reference_id="evidence-a"
            ),
        ),
    )
    second_metadata = InferenceNodeMetadata(
        confidence=Decimal("0.9"),
        requirement_ids=("requirement-b",),
        evidence=(
            InferenceEvidenceReference(
                kind=InferenceEvidenceKind.EXPRESSION_PROPOSAL, reference_id="evidence-b"
            ),
        ),
    )
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.LOGICAL,
        children=(
            AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.COMPOSED,
                composed_role=ComposedAndRole.LOGICAL,
                children=(inferred_course("grouped", inference=first_metadata),),
            ),
            AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.COMPOSED,
                composed_role=ComposedAndRole.LOGICAL,
                children=(inferred_course("grouped", inference=second_metadata),),
            ),
        ),
    )
    tree = make_tree(
        course_summary("root"),
        requirements,
        (course_summary("grouped"),),
        include_inferred=True,
    )
    graph = project_prerequisite_graph(tree)

    connections = [
        edge
        for edge in graph.edges
        if edge.source_node_id == "connector:r" and edge.target_node_id == "course:grouped"
    ]
    assert len(connections) == 1
    members = connections[0].relationships
    assert [(member.occurrence_ids, member.condition_occurrence_ids) for member in members] == [
        (("r.0.0",), ("r.0",)),
        (("r.1.0",), ("r.1",)),
    ]
    assert [member.inference for member in members] == [first_metadata, second_metadata]
    assert all(member.origin is PrerequisiteOrigin.INFERRED for member in members)
    assert all(
        member.inferred_category is InferredPrerequisiteCategory.REQUIRED for member in members
    )
    assert all(member.official_kind is None for member in members)

    # Deterministic: the same tree projects to the same grouped connection, and each member's full
    # provenance payload carries through JSON serialization.
    assert project_prerequisite_graph(tree) == graph
    assert PrerequisiteDrawingGraph.model_validate_json(graph.model_dump_json()) == graph


def test_single_child_and_or_wrappers_collapse_without_changing_meaning() -> None:
    """A one-child module-rule AND and a stored inferred AND/OR wrapper collapse to their child."""
    # A one-child StudyModule all-mandatory AND collapses to its single course child. The outer
    # DegreeProgramme's singleton ModuleRule reference collapses onto that same surviving object.
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
            (module_root, catalogue_course("leaf")), (outer_degree, singleton_study)
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("module-root")
    tree = module_compilation.tree
    degree_boundary = tree.requirements
    assert isinstance(degree_boundary, ModuleBlockRequirement)
    assert degree_boundary.module_group_id == "module-degree"
    single_boundary = degree_boundary.child
    assert isinstance(single_boundary, ModuleBlockRequirement)
    assert single_boundary.module_group_id == "module-single"
    assert single_boundary.child == official_course("leaf", OfficialPrerequisiteKind.MODULE_RULE)
    # Both selected module boundaries survive on their own wrapper occurrences, outer first.
    assert [(occ.occurrence_id, occ.module.group_id) for occ in tree.module_occurrences] == [
        ("r", "module-degree"),
        ("r.0", "module-single"),
    ]
    assert [occ.member_group_ids for occ in tree.module_occurrences] == [("leaf",), ("leaf",)]
    # Exactly one outer module node with one leaf card is drawn, and no internal subtree appears.
    graph = module_compilation.graph
    assert [node.node_id for node in graph.module_nodes] == ["module:r"]
    assert graph.module_nodes[0].module.group_id == "module-degree"
    assert [card.group_id for card in graph.module_nodes[0].member_courses] == ["leaf"]
    assert [node.course.group_id for node in graph.course_nodes] == ["module-root"]
    assert graph.connector_nodes == ()
    # Positional module metadata carries through calculation-tree serialization, so projection never
    # depends on live compiler-local object identities.
    round_tripped = PrerequisiteCalculationTree.model_validate_json(tree.model_dump_json())
    assert round_tripped == tree
    assert project_prerequisite_graph(round_tripped) == graph

    # A stored inferred one-child AND wrapping a singleton OR projects to its expanded child and
    # keeps the inferred origin/inference metadata of the surviving child.
    one_child_inferred = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=INFERENCE_METADATA,
        children=(
            OrRequirement(
                type="or",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                inference=INFERENCE_METADATA,
                children=(inferred_course("solo"),),
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
    assert inferred_wrapper.tree.requirements == inferred_course("solo")

    # A free-only module wrapper and its containing numeric bound are ignored: the neutral leaf
    # holds, both disclosures draw around the module with no fabricated member card, and the
    # ignored metadata round-trips through tree serialization and reprojection.
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
        ),
    )
    free_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((free_root,), (free_module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("free-root")
    free_tree = free_compilation.tree
    assert isinstance(free_tree.requirements, ModuleBlockRequirement)
    assert isinstance(free_tree.requirements.child, OpaqueCreditRequirement)
    assert free_tree.requirements.child.credits_min == Decimal("5")
    assert [part.kind.value for part in free_tree.ignored_parts] == ["free_choice"]
    assert [node.node_id for node in free_compilation.graph.module_nodes] == ["module:r"]
    assert free_compilation.graph.module_nodes[0].member_courses == ()
    assert [node.node_id for node in free_compilation.graph.ignored_nodes] == [
        part.part_id for part in free_tree.ignored_parts
    ]
    assert all(
        edge.source_node_id == "module:r"
        for edge in free_compilation.graph.edges
        if edge.target_node_id.startswith("ignored:")
    )
    free_round_trip = PrerequisiteCalculationTree.model_validate_json(free_tree.model_dump_json())
    assert free_round_trip == free_tree
    assert project_prerequisite_graph(free_round_trip) == free_compilation.graph


def test_composed_and_role_distinguishes_logical_join_from_expanded_course() -> None:
    """Only the compiler's expanded-course role qualifies. An identical logical join never does."""
    # One singleton compulsory option plus one singleton recommended option join as LOGICAL even
    # though the collapsed result is exactly `AND(course, course)`.
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
    logical = logical_compilation.tree.requirements
    assert isinstance(logical, AndRequirement)
    assert logical.origin is PrerequisiteOrigin.COMPOSED
    assert logical.composed_role is ComposedAndRole.LOGICAL
    assert logical.children == (
        official_course("required-a"),
        official_course("recommended-b", OfficialPrerequisiteKind.RECOMMENDED),
    )

    # An active required course with ordinary descendants compiles to the EXPANDED_COURSE wrapper.
    # A compulsory option holds two members, so its official AND folds into the outer LOGICAL AND
    # while the course's own alternatives stay a nested OR below the expanded head.
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
    expanded = expanded_compilation.tree.requirements
    assert isinstance(expanded, AndRequirement)
    assert expanded.origin is PrerequisiteOrigin.COMPOSED
    assert expanded.composed_role is ComposedAndRole.LOGICAL
    compulsory = expanded.children[0]
    assert isinstance(compulsory, AndRequirement)
    expanded_course = compulsory.children[0]
    assert isinstance(expanded_course, AndRequirement)
    assert expanded_course.composed_role is ComposedAndRole.EXPANDED_COURSE
    assert expanded_course.children[0] == official_course("course-with-descendant")
    # The same two-child course-headed shape is discriminated only by the compiler's role.
    assert logical.children[0] == official_course("required-a")
    assert logical.composed_role is ComposedAndRole.LOGICAL

    # Folding the compulsory AND into the root AND reparents only its direct attachments:
    # the expanded course keeps its own OR and both alternatives as its children.
    graph = expanded_compilation.graph
    assert [node.node_id for node in graph.connector_nodes] == [
        "connector:r",
        "connector:r.0.0.1",
    ]
    edges = {(edge.source_node_id, edge.target_node_id): edge for edge in graph.edges}
    assert set(edges) == {
        ("course:expanded-root", "connector:r"),
        ("connector:r", "course:course-with-descendant"),
        ("connector:r", "course:required-peer"),
        ("connector:r", "course:recommended-peer"),
        ("course:course-with-descendant", "connector:r.0.0.1"),
        ("connector:r.0.0.1", "course:descendant-a"),
        ("connector:r.0.0.1", "course:descendant-b"),
    }
    # Folded inbound head/required-peer edges keep the elided compulsory gate. The head->OR and
    # OR->leaf edges keep empty conditions and their terminal occurrence IDs. Each of these
    # connections is a singleton, so its first relationship member carries the exact evidence.
    head_edge = edges[("connector:r", "course:course-with-descendant")].relationships[0]
    assert head_edge.occurrence_ids == ("r.0.0.0",)
    assert head_edge.condition_occurrence_ids == ("r.0",)
    peer_edge = edges[("connector:r", "course:required-peer")].relationships[0]
    assert peer_edge.occurrence_ids == ("r.0.1",)
    assert peer_edge.condition_occurrence_ids == ("r.0",)
    alternatives_edge = edges[("course:course-with-descendant", "connector:r.0.0.1")].relationships[
        0
    ]
    assert alternatives_edge.occurrence_ids == ("r.0.0.1",)
    assert alternatives_edge.condition_occurrence_ids == ()
    assert edges[("connector:r.0.0.1", "course:descendant-a")].relationships[0].occurrence_ids == (
        "r.0.0.1.0",
    )
    assert edges[("connector:r.0.0.1", "course:descendant-b")].relationships[0].occurrence_ids == (
        "r.0.0.1.1",
    )
    assert (
        edges[("connector:r.0.0.1", "course:descendant-a")]
        .relationships[0]
        .condition_occurrence_ids
        == ()
    )
    assert (
        edges[("connector:r.0.0.1", "course:descendant-b")]
        .relationships[0]
        .condition_occurrence_ids
        == ()
    )
    assert edges[("course:expanded-root", "connector:r")].relationships[0].occurrence_ids == ("r",)


def test_course_nodes_annotate_official_and_inferred_provenance() -> None:
    """Course nodes label official/inferred occurrence provenance without relabeling connectors."""
    root = course_summary("root")
    # A bare inferred course occurrence expands to `And(composed EXPANDED_COURSE, (head leaf,
    # descendants))`, forwarding the inferred path flag to its official descendant occurrence.
    inferred_expanded = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(inferred_course("shared"), official_course("inferred-desc")),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            official_course("official-only"),
            inferred_course("inferred-only"),
            official_course("shared"),
            official_course("shared", OfficialPrerequisiteKind.RECOMMENDED),
            inferred_course("shared", InferredPrerequisiteCategory.RECOMMENDED),
            inferred_expanded,
        ),
    )
    tree = make_tree(
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
    graph = project_prerequisite_graph(tree)
    nodes_by_group = {node.course.group_id: node for node in graph.course_nodes}

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

    # The node annotation never touches relationship provenance. The same endpoints keep one
    # homogeneous connection per official compulsory/recommended and inferred required/recommended
    # class, and no class ever merges with another.
    shared_connections = [
        edge
        for edge in graph.edges
        if edge.source_node_id == "connector:r" and edge.target_node_id == "course:shared"
    ]
    assert len(shared_connections) == 4
    assert {
        (
            edge.relationships[0].origin,
            edge.relationships[0].official_kind,
            edge.relationships[0].inferred_category,
        )
        for edge in shared_connections
    } == {
        (PrerequisiteOrigin.OFFICIAL, OfficialPrerequisiteKind.COMPULSORY, None),
        (PrerequisiteOrigin.OFFICIAL, OfficialPrerequisiteKind.RECOMMENDED, None),
        (PrerequisiteOrigin.INFERRED, None, InferredPrerequisiteCategory.REQUIRED),
        (PrerequisiteOrigin.INFERRED, None, InferredPrerequisiteCategory.RECOMMENDED),
    }
    assert all(
        {
            (member.origin, member.official_kind, member.inferred_category)
            for member in edge.relationships
        }
        == {
            (
                edge.relationships[0].origin,
                edge.relationships[0].official_kind,
                edge.relationships[0].inferred_category,
            )
        }
        for edge in shared_connections
    )
    desc_edges = [edge for edge in graph.edges if edge.target_node_id == "course:inferred-desc"]
    assert {member.origin for edge in desc_edges for member in edge.relationships} == {
        PrerequisiteOrigin.OFFICIAL
    }


def test_projection_draws_every_represented_node_including_a_childless_diagnostic_connector() -> (
    None
):
    """The projector draws every represented course node and a childless diagnostic connector."""
    root = course_summary("root")

    # Two represented inactive leaves draw their canonical nodes: the tree is the only input.
    inactive_leaves = make_tree(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.COMPOSED,
            composed_role=ComposedAndRole.LOGICAL,
            children=(
                official_course("inactive-a"),
                official_course("inactive-b"),
            ),
        ),
        (
            course_summary("inactive-a", is_active=False),
            course_summary("inactive-b", is_active=False),
        ),
        active_only=True,
    )
    inactive_graph = project_prerequisite_graph(inactive_leaves)
    assert {node.course.group_id for node in inactive_graph.course_nodes} == {
        "root",
        "inactive-a",
        "inactive-b",
    }
    assert [node.node_id for node in inactive_graph.connector_nodes] == ["connector:r"]
    # The calculation denies the inactive leaves outside the basis and reports their locations.
    inactive_path = calculate_minimum_new_credits(inactive_leaves, [])
    assert inactive_path.state is PrerequisitePathState.NO_SOLUTION
    assert {problem.occurrence_id for problem in inactive_path.problems} >= {"r.0", "r.1"}

    # A mixed conjunction draws one connector with both the inactive and the active child.
    mixed = make_tree(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.COMPOSED,
            composed_role=ComposedAndRole.LOGICAL,
            children=(official_course("inactive-a"), official_course("active-b")),
        ),
        (
            course_summary("inactive-a", is_active=False),
            course_summary("active-b"),
        ),
        active_only=True,
    )
    mixed_graph = project_prerequisite_graph(mixed)
    assert {node.course.group_id for node in mixed_graph.course_nodes} == {
        "root",
        "inactive-a",
        "active-b",
    }
    assert [(edge.source_node_id, edge.target_node_id) for edge in mixed_graph.edges] == [
        ("connector:r", "course:active-b"),
        ("connector:r", "course:inactive-a"),
        ("course:root", "connector:r"),
    ]

    # An unresolved diagnostic connector has no children and is visible.
    diagnostic = make_tree(
        root,
        UnresolvedRequirement(
            type="unresolved",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
        ),
        (),
        active_only=True,
    )
    diagnostic_graph = project_prerequisite_graph(diagnostic)
    assert any(
        node.kind is PrerequisiteGraphConnectorKind.UNRESOLVED
        for node in diagnostic_graph.connector_nodes
    )


def test_active_projection_compacts_source_alternatives_with_shared_course_chains() -> None:
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
    tree = compilation.tree
    graph = compilation.graph

    # The unretained inactive substitution alternatives are dropped at compile time, so neither the
    # tree nor the drawing carries them, and the real route charges the required courses.
    assert expression_course_leaf_group_ids(tree.requirements) == {
        "100",
        "110",
        "115",
        "db100",
    }

    # Each canonical course is drawn once. The recommended pool draws its two real alternatives and
    # the required pool's unary wrappers fold into their surviving edges.
    assert [node.node_id for node in graph.course_nodes] == [
        "course:100",
        "course:110",
        "course:115",
        "course:db100",
        "course:root",
    ]
    assert [(node.node_id, node.kind.value) for node in graph.connector_nodes] == [
        ("connector:r", "and"),
        ("connector:r.1", "or"),
        ("connector:r.1.1", "and"),
    ]
    assert [(edge.source_node_id, edge.target_node_id) for edge in graph.edges] == [
        ("connector:r", "connector:r.1"),
        ("connector:r", "course:110"),
        ("connector:r.1", "connector:r.1.1"),
        ("connector:r.1", "course:db100"),
        ("connector:r.1.1", "course:115"),
        ("connector:r.1.1", "course:db100"),
        ("course:110", "course:100"),
        ("course:115", "course:110"),
        ("course:root", "connector:r"),
    ]
    # Every course edge carries the terminal occurrence IDs of its real source alternative. The
    # required pool expands 110 and its own prerequisite 100. The 110 occurrence inside the
    # recommended choice branch through 115 is a bare leaf, because the required pool expands 110, so
    # 100 has one terminal occurrence.
    root_pool_edge = next(
        edge
        for edge in graph.edges
        if edge.source_node_id == "connector:r" and edge.target_node_id == "course:110"
    )
    assert root_pool_edge.relationships[0].occurrence_ids == ("r.0.0",)
    choice_edge = next(edge for edge in graph.edges if edge.target_node_id == "course:115")
    assert choice_edge.relationships[0].occurrence_ids == ("r.1.1.1.0",)
    assert next(
        edge
        for edge in graph.edges
        if edge.target_node_id == "course:db100" and edge.source_node_id == "connector:r.1"
    ).relationships[0].occurrence_ids == ("r.1.0",)
    assert next(
        edge
        for edge in graph.edges
        if edge.target_node_id == "course:100" and edge.source_node_id == "course:110"
    ).relationships[0].occurrence_ids == ("r.0.1",)

    # Terminal and gate evidence is inside the tree's own occurrence index, and every emitted node is
    # an edge endpoint reachable from the root: no orphan, placeholder or fabricated course exists.
    occurrence_by_id = {
        occurrence.occurrence_id: occurrence for occurrence in tree.node_occurrences
    }
    endpoints = {
        endpoint for edge in graph.edges for endpoint in (edge.source_node_id, edge.target_node_id)
    }
    for node in (
        *graph.course_nodes,
        *graph.connector_nodes,
        *graph.module_nodes,
        *graph.ignored_nodes,
    ):
        assert node.node_id in endpoints
    action_keys = {
        node.node_id: node.action_key
        for node in (
            *graph.course_nodes,
            *graph.connector_nodes,
            *graph.module_nodes,
            *graph.ignored_nodes,
        )
    }
    for edge in graph.edges:
        for member in edge.relationships:
            for occurrence_id in (
                *member.occurrence_ids,
                *member.condition_occurrence_ids,
            ):
                assert occurrence_id in occurrence_by_id
            terminal_key = occurrence_by_id[member.occurrence_ids[0]].action_key
            assert terminal_key in (
                action_keys[edge.source_node_id],
                action_keys[edge.target_node_id],
            )

    # The drawing changes only presentation, so the real route charges the required courses.
    path = calculate_minimum_new_credits(tree, [])
    assert path.state is PrerequisitePathState.EXACT
    assert [entry.course.group_id for entry in path.new_courses] == ["100", "110", "db100"]
    assert path.total_new_credits == Decimal("15")
    assert project_prerequisite_graph(tree) == graph


def test_mandatory_position_rule_governs_duplicate_cardinality_open_and_cycle_positions() -> None:
    """A required course's duplicate occurrence collapses to a bare leaf in a non-mandatory position.

    A course that an enclosing conjunction requires expands once and is a bare leaf in a
    non-mandatory branch, and two separate mandatory conjunction paths each expand the shared
    course. A single-child wrapper passes its mandatory flag to its child. A `CardinalityRequirement`
    child and a course with no mandatory occurrence expand at every position, and a closing cycle
    occurrence is preserved with its cycle issue.
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
    requirements = compilation.tree.requirements
    assert isinstance(requirements, AndRequirement)
    assert requirements.composed_role is ComposedAndRole.LOGICAL
    compulsory_branch, recommended_branch = requirements.children
    # The compulsory occurrence carries the one expanded subtree for the head course.
    assert is_expanded_course_branch(compulsory_branch)
    assert compulsory_branch.children[0] == official_course("head")
    expanded_heads = [
        expression.children[0].course_group_id
        for _, expression in _iter_expression_occurrences(requirements)
        if is_expanded_course_branch(expression)
    ]
    assert expanded_heads == ["head"]
    # The duplicate recommended occurrence is a bare leaf.
    assert isinstance(recommended_branch, OrRequirement)
    assert recommended_branch.children == (
        official_course("other", OfficialPrerequisiteKind.RECOMMENDED),
        official_course("head", OfficialPrerequisiteKind.RECOMMENDED),
    )
    # The drawing graph holds one connector for the head's own requirement.
    head_requirement_edges = [
        edge
        for edge in compilation.graph.edges
        if edge.source_node_id == "course:head" and edge.target_node_id.startswith("connector:")
    ]
    assert len(head_requirement_edges) == 1
    assert {
        edge.target_node_id
        for edge in compilation.graph.edges
        if edge.source_node_id == head_requirement_edges[0].target_node_id
    } == {"course:head-a", "course:head-b"}

    # Two separate mandatory conjunction paths each expand the shared course.
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
    repeat_requirements = repeat_compilation.tree.requirements
    assert repeat_requirements is not None
    repeat_expanded_heads = [
        expression.children[0].course_group_id
        for _, expression in _iter_expression_occurrences(repeat_requirements)
        if is_expanded_course_branch(expression)
    ]
    assert repeat_expanded_heads == ["via-alpha", "shared", "via-beta", "shared"]
    shared_edges = [
        edge for edge in repeat_compilation.graph.edges if edge.source_node_id == "course:shared"
    ]
    assert len(shared_edges) == 1
    assert sum(len(member.occurrence_ids) for member in shared_edges[0].relationships) == 2
    shared_gate = shared_edges[0].target_node_id
    children = [
        edge for edge in repeat_compilation.graph.edges if edge.source_node_id == shared_gate
    ]
    assert {edge.target_node_id for edge in children} == {
        "course:shared-base",
        "course:shared-other",
    }
    assert all(
        sum(len(member.occurrence_ids) for member in edge.relationships) == 2 for edge in children
    )
    before = repeat_compilation.tree.model_dump()
    route = calculate_minimum_new_credits(repeat_compilation.tree, [])
    assert route.total_new_credits == Decimal("25")
    assert project_prerequisite_graph(repeat_compilation.tree) == repeat_compilation.graph
    assert repeat_compilation.tree.model_dump() == before
    first_gate = next(
        occurrence
        for occurrence in repeat_compilation.tree.node_occurrences
        if occurrence.occurrence_id in shared_edges[0].relationships[0].occurrence_ids
    )
    marked_tree = repeat_compilation.tree.model_copy(
        update={"excluded_node_keys": (first_gate.action_key,)}
    )
    marked_graph = project_prerequisite_graph(marked_tree)
    assert len([edge for edge in marked_graph.edges if edge.source_node_id == "course:shared"]) == 2
    assert calculate_minimum_new_credits(marked_tree, []).state is PrerequisitePathState.NO_SOLUTION

    # A single-child wrapper at a mandatory position passes the mandatory flag to its child, so a
    # course expanded inside the wrapper is a mandatory head and its repeated non-mandatory
    # occurrence collapses. The wrapper is one CourseCountRequirement inside its module boundary.
    wrapper_year = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
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
                curriculum_periods=wrapper_year,
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
    wrapper_requirements = wrapper_compilation.tree.requirements
    assert wrapper_requirements is not None
    assert [
        expression.children[0].course_group_id
        for _, expression in _iter_expression_occurrences(wrapper_requirements)
        if is_expanded_course_branch(expression)
    ] == ["head"]

    # A course reached only through a CardinalityRequirement child is not a mandatory head, so each
    # of its occurrences expands. The bounded composite compiles to one cardinality node.
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
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="other"),
                    ),
                ),
                curriculum_periods=wrapper_year,
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
    cardinality_requirements = cardinality_compilation.tree.requirements
    assert cardinality_requirements is not None
    assert [
        expression.children[0].course_group_id
        for _, expression in _iter_expression_occurrences(cardinality_requirements)
        if is_expanded_course_branch(expression)
    ] == ["head", "head"]

    # A course with no mandatory occurrence at all expands in every non-mandatory position. Both
    # recommended alternatives expand the head course.
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
    open_requirements = open_compilation.tree.requirements
    assert open_requirements is not None
    assert [
        expression.children[0].course_group_id
        for _, expression in _iter_expression_occurrences(open_requirements)
        if is_expanded_course_branch(expression)
    ] == ["head", "head"]

    # A cycle leaf is a bare course occurrence that the prune preserves, and its cycle issue is
    # located at that occurrence.
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
    cycle_requirements = cycle_compilation.tree.requirements
    assert is_expanded_course_branch(cycle_requirements)
    cycle_leaf = cycle_requirements.children[1]
    assert isinstance(cycle_leaf, CourseRequirement)
    assert cycle_leaf.course_group_id == "cycle-root"
    assert [
        issue.occurrence_id
        for issue in cycle_compilation.tree.issues
        if issue.reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
    ] == ["r.1"]


def test_a_course_with_a_substitution_expands_at_its_compulsory_and_repeated_recommended_occurrences() -> (
    None
):
    """A course that carries a substitution expands at its compulsory and repeated recommended occurrence."""
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
    requirements = compilation.tree.requirements
    assert isinstance(requirements, AndRequirement)
    assert requirements.composed_role is ComposedAndRole.LOGICAL
    compulsory_branch, recommended_branch = requirements.children

    # The compulsory occurrence wraps the head's expansion in one COURSE_ALTERNATIVES OR, whose first
    # child is the represented expanded occurrence.
    assert isinstance(compulsory_branch, OrRequirement)
    assert compulsory_branch.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    represented = compulsory_branch.children[0]
    assert is_expanded_course_branch(represented)
    assert represented.children[0] == official_course("head")

    # Every occurrence expands: a course with a substitution is not a mandatory head, because its
    # represented branch sits inside a COURSE_ALTERNATIVES OR. The compulsory occurrence and the
    # repeated recommended occurrence each expand the head.
    expanded_heads = [
        expression.children[0].course_group_id
        for _, expression in _iter_expression_occurrences(requirements)
        if is_expanded_course_branch(expression)
    ]
    assert expanded_heads == ["head", "head"]
    assert isinstance(recommended_branch, OrRequirement)
    repeated = recommended_branch.children[1]
    assert isinstance(repeated, OrRequirement)
    assert repeated.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    repeated_represented = repeated.children[0]
    assert is_expanded_course_branch(repeated_represented)
    assert repeated_represented.children[0] == official_course(
        "head", OfficialPrerequisiteKind.RECOMMENDED
    )


def test_returned_category_pools_are_the_trees_own_objects() -> None:
    """A direct compile returns the pooled expressions the calculation tree itself holds."""
    pair_root = catalogue_course(
        "pair-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "required-peer"),
            ),
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.RECOMMENDED,
                prerequisite_course_member(0, "recommended-peer"),
            ),
        ),
    )
    solo_root = catalogue_course(
        "solo-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "solo-peer"),
            ),
        ),
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                pair_root,
                solo_root,
                catalogue_course("required-peer"),
                catalogue_course("recommended-peer"),
                catalogue_course("solo-peer"),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    )
    (paired,) = compiler.compile_direct_many(
        ("pair-root",), read_context=DirectPrerequisiteReadContext()
    )
    paired_requirements = paired.tree.requirements
    assert isinstance(paired_requirements, AndRequirement)
    assert paired_requirements.children[0] is paired.required
    assert paired_requirements.children[1] is paired.recommended

    (solo,) = compiler.compile_direct_many(
        ("solo-root",), read_context=DirectPrerequisiteReadContext()
    )
    assert solo.recommended is None
    assert solo.tree.requirements is solo.required


def test_projection_aggregates_course_path_flags_without_rewriting_provenance() -> None:
    """Course nodes aggregate independent visibility flags while local provenance is exact."""
    root = course_summary("root")
    recommended_branch = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.RECOMMENDED,
        children=(
            official_course("recommended-only", OfficialPrerequisiteKind.RECOMMENDED),
            official_course("shared", OfficialPrerequisiteKind.RECOMMENDED),
        ),
    )
    # A bare inferred course occurrence expands to `And(composed, (head leaf, its children))`, and
    # its compiled substitution wrapper forwards the inferred path category to official descendants.
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
        children=(inferred_course("shared"), substitution_wrapper),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(
            official_course("required-only"),
            recommended_branch,
            inferred_expanded,
            # An inferred recommended occurrence carries the recommended path exactly like an
            # official recommended one, while keeping inferred origin and its own category.
            inferred_course("recommended-inferred", InferredPrerequisiteCategory.RECOMMENDED),
        ),
    )
    tree = make_tree(
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
    graph = project_prerequisite_graph(tree)
    nodes_by_group = {node.course.group_id: node for node in graph.course_nodes}

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

    # Local provenance is preserved: the recommended connector/edge is recommended, the
    # inferred recommended occurrence keeps its own category, and required/recommended inferred
    # members stay separate.
    recommended_connector = next(
        node
        for node in graph.connector_nodes
        if node.official_kind is OfficialPrerequisiteKind.RECOMMENDED
    )
    assert recommended_connector.kind is PrerequisiteGraphConnectorKind.OR
    assert recommended_connector.inferred_category is None
    inferred_recommended_members = [
        member
        for edge in graph.edges
        if edge.target_node_id == "course:recommended-inferred"
        for member in edge.relationships
    ]
    assert len(inferred_recommended_members) == 1
    assert inferred_recommended_members[0].origin is PrerequisiteOrigin.INFERRED
    assert (
        inferred_recommended_members[0].inferred_category
        is InferredPrerequisiteCategory.RECOMMENDED
    )
    assert inferred_recommended_members[0].official_kind is None
    shared_members = [
        member
        for edge in graph.edges
        if edge.target_node_id == "course:shared"
        for member in edge.relationships
    ]
    assert {member.official_kind for member in shared_members} == {
        None,
        OfficialPrerequisiteKind.RECOMMENDED,
    }
    substitution_members = [
        member
        for edge in graph.edges
        for member in edge.relationships
        if member.official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    ]
    assert substitution_members
    assert all(member.origin is PrerequisiteOrigin.OFFICIAL for member in substitution_members)

    # Deterministic: an identical tree projects to the same aggregated flags.
    assert project_prerequisite_graph(tree) == graph


def test_module_cards_hide_member_closure_without_relabeling_independent_occurrences() -> None:
    """A module card lists only its official member. An independently reached member draws fully."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module = catalogue_module(
        "module-x",
        (
            module_version(
                "module-x-v1",
                rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
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
                prerequisite_module_member(0, "module-x"),
            ),
        ),
    )
    # The member has an ordinary prerequisite and an official substitute. Neither is a module card.
    member = catalogue_course(
        "member",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "member-prereq"),
            ),
        ),
        substitution_options=(substitution_option(0, ("substitute", None)),),
    )
    courses = (root, member, catalogue_course("member-prereq"), catalogue_course("substitute"))
    inferred = RecordingInferredSetRead(
        {
            "root": current_result("root", expression=inferred_course("member")),
            "member": current_result("member"),
            "member-prereq": current_result("member-prereq"),
            "substitute": current_result("substitute"),
        }
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, (module,)), inferred, RecordingEquivalenceGroupRead()
    ).compile("root", include_inferred=True)

    # The module card list is exactly the explicit official member: no ancestor or substitute.
    module_node = next(
        node for node in compilation.graph.module_nodes if node.module.group_id == "module-x"
    )
    assert module_node.occurrence_id == "r.0"
    assert [card.group_id for card in module_node.member_courses] == ["member"]
    # The module boundary hides its internal member closure but exposes the member's real external
    # obligations: its prerequisite and official substitute draw as conditional routes from the
    # module, never as internal member cards.
    assert any(edge.source_node_id == "module:r.0" for edge in compilation.graph.edges)
    assert {
        edge.target_node_id
        for edge in compilation.graph.edges
        if edge.source_node_id == "module:r.0"
    } == {"connector:r.0.0"}
    assert "member-prereq" in {node.course.group_id for node in compilation.graph.course_nodes}
    assert "substitute" in {node.course.group_id for node in compilation.graph.course_nodes}

    # The member independently reached through the inferred alternative draws once as a canonical
    # standalone node. Its official module occurrence and inferred alternative aggregate, and the
    # official occurrence wins the display marker.
    member_node = next(
        node for node in compilation.graph.course_nodes if node.course.group_id == "member"
    )
    assert member_node.has_official_provenance is True
    assert member_node.has_inferred_provenance is True
    assert member_node.via_inferred is True
    assert member_node.display_as_inferred is False
    assert "member-prereq" in {node.course.group_id for node in compilation.graph.course_nodes}

    # Module identity is display metadata only: dropping it changes neither the calculation-tree
    # expression nor the solver result.
    stripped = compilation.model_copy(
        update={
            "tree": compilation.tree.model_copy(update={"module_occurrences": ()}),
            "graph": compilation.graph.model_copy(update={"module_nodes": ()}),
        }
    )
    assert stripped.tree.requirements == compilation.tree.requirements
    assert calculate_minimum_new_credits(stripped.tree, []) == calculate_minimum_new_credits(
        compilation.tree, []
    )


def test_module_cards_follow_activity_retention_and_unretained_member_reports_no_solution() -> None:
    """Module cards follow activity retention and exclusion, and an unretained member makes the route impossible."""
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

    def without_metadata(compilation):
        return compilation.model_copy(
            update={
                "tree": compilation.tree.model_copy(update={"module_occurrences": ()}),
                "graph": compilation.graph.model_copy(update={"module_nodes": ()}),
            }
        )

    # All courses: both official module members are cards. The active member's external prerequisite is drawn.
    all_courses = compiler.compile("root")
    assert [node.course.group_id for node in all_courses.graph.course_nodes] == [
        "external-prerequisite",
        "root",
    ]
    assert [node.node_id for node in all_courses.graph.module_nodes] == ["module:r"]
    assert [card.group_id for card in all_courses.graph.module_nodes[0].member_courses] == [
        "active-member",
        "inactive-member",
    ]
    all_internal = next(
        node
        for node in all_courses.graph.connector_nodes
        if node.kind is PrerequisiteGraphConnectorKind.INTERNAL_REQUIREMENT
    )
    assert all_internal.member_group_ids == ("inactive-member",)

    # Active-only drops the unretained inactive member, so the module node draws only the active
    # member card and the module rule cannot meet its bound with the surviving members.
    active_only = compiler.compile("root", active_only=True)
    assert [node.node_id for node in active_only.graph.module_nodes] == ["module:r"]
    assert [card.group_id for card in active_only.graph.module_nodes[0].member_courses] == [
        "active-member"
    ]
    assert not any(
        node.kind is PrerequisiteGraphConnectorKind.INTERNAL_REQUIREMENT
        for node in active_only.graph.connector_nodes
    )
    assert active_only.graph.course_nodes == all_courses.graph.course_nodes
    active_edges = {(edge.source_node_id, edge.target_node_id) for edge in active_only.graph.edges}
    assert active_edges == {
        (edge.source_node_id, edge.target_node_id) for edge in all_courses.graph.edges
    } - {("connector:r.0", "connector:r.0.0")}
    assert not any("inactive-member" in endpoint for edge in active_edges for endpoint in edge)

    # Retaining the selected/completed identity restores the card and node, and that identity then
    # fully satisfies the obligation as the calculation basis.
    retained = compiler.compile("root", active_only=True, retained_group_ids=("inactive-member",))
    assert [node.node_id for node in retained.graph.module_nodes] == ["module:r"]
    assert [card.group_id for card in retained.graph.module_nodes[0].member_courses] == [
        "active-member",
        "inactive-member",
    ]
    retained_internal = next(
        node
        for node in retained.graph.connector_nodes
        if node.kind is PrerequisiteGraphConnectorKind.INTERNAL_REQUIREMENT
    )
    assert retained_internal.member_group_ids == ("inactive-member",)
    retained_path = calculate_minimum_new_credits(retained.tree, ["inactive-member"])
    assert retained_path.state is PrerequisitePathState.EXACT

    # An excluded member is a visible card but is denied by the calculation.
    excluded = compiler.compile("root", excluded_group_ids=("inactive-member",))
    assert [card.group_id for card in excluded.graph.module_nodes[0].member_courses] == [
        "active-member",
        "inactive-member",
    ]
    excluded_path = calculate_minimum_new_credits(excluded.tree, [])
    assert excluded_path.state is PrerequisitePathState.NO_SOLUTION
    assert excluded_path.blocked_excluded_group_ids == ("inactive-member",)

    # Path/satisfaction values are identical with the display-only module metadata absent. Active-only
    # drops the unretained inactive member, so the module rule cannot meet its bound and the route is
    # impossible.
    assert (
        calculate_minimum_new_credits(active_only.tree, []).state
        is PrerequisitePathState.NO_SOLUTION
    )
    for compilation in (all_courses, active_only, retained, excluded):
        assert calculate_minimum_new_credits(compilation.tree, []) == calculate_minimum_new_credits(
            without_metadata(compilation).tree, []
        )


def test_graph_node_marks_are_stable_scoped_and_history_distinct() -> None:
    """Node action keys are positional-shift stable. Module marks stay graph-only and history-distinct."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module = catalogue_module(
        "module-mark",
        (
            module_version(
                "module-mark-v1",
                rule=module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
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
                prerequisite_module_member(0, "module-mark"),
            ),
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.RECOMMENDED,
                prerequisite_course_member(0, "recommended"),
            ),
            prerequisite_option(1, PrerequisiteRequirementKind.COMPULSORY),
        ),
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (root, catalogue_course("member"), catalogue_course("recommended")), (module,)
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    )

    # A toggle that shifts the module's drawing position never changes its stable action key.
    plain = compiler.compile("root")
    shifted = compiler.compile("root", include_recommended=True)
    plain_module = next(
        occ for occ in plain.tree.node_occurrences if occ.action_key == "module:module-mark"
    )
    shifted_module = next(
        occ for occ in shifted.tree.node_occurrences if occ.action_key == "module:module-mark"
    )
    assert plain_module.occurrence_id == "r"
    assert shifted_module.occurrence_id == "r.0"
    assert plain_module.action_key == shifted_module.action_key

    # Excluding the module blocks its route with no-solution and never globally excludes its members.
    excluded = compiler.compile("root", excluded_node_keys=("module:module-mark",))
    assert excluded.tree.excluded_group_ids == ()
    excluded_states = {
        state.action_key: state
        for state in evaluate_prerequisite_node_states(excluded.tree, [], completed_group_ids=[])
    }
    assert excluded_states["module:module-mark"].is_excluded is True
    assert excluded_states["course:member"].is_excluded is False
    excluded_path = calculate_minimum_new_credits(excluded.tree, [])
    assert excluded_path.state is PrerequisitePathState.NO_SOLUTION
    assert excluded_path.blocked_excluded_node_keys == ("module:module-mark",)
    assert any(
        problem.state == "no_solution"
        and problem.reason == "excluded_node"
        and problem.action_key == "module:module-mark"
        for problem in excluded_path.problems
    )

    # Manually completing the module fulfils it at zero new cost without completing its members.
    manual = compiler.compile("root", completed_node_keys=("module:module-mark",))
    manual_path = calculate_minimum_new_credits(manual.tree, [])
    assert manual_path.state is PrerequisitePathState.EXACT
    assert manual_path.total_new_credits == Decimal("0")
    assert manual_path.new_courses == ()
    manual_states = {
        state.action_key: state
        for state in evaluate_prerequisite_node_states(manual.tree, [], completed_group_ids=[])
    }
    assert manual_states["module:module-mark"].manually_completed is True
    assert manual_states["course:member"].manually_completed is False
    assert manual_states["course:member"].completed_by_courses is False

    disclosure = manual.tree.ignored_parts[0]
    marked_disclosure = compiler.compile(
        "root",
        completed_node_keys=("module:module-mark", disclosure.action_key),
    )
    display_state = next(
        state
        for state in evaluate_prerequisite_node_states(
            marked_disclosure.tree, [], completed_group_ids=[]
        )
        if state.action_key == disclosure.action_key
    )
    assert display_state.occurrence_ids == (disclosure.part_id,)
    assert display_state.manually_completed is True
    assert display_state.completed_by_courses is False
    assert display_state.satisfied_by_basis is False
    assert calculate_minimum_new_credits(marked_disclosure.tree, []).total_new_credits == Decimal(
        "0"
    )

    # An ignored disclosure cannot satisfy or block its unpaid containing module, even when both
    # display marks are present without a manual mark on that module.
    ignored_only = compiler.compile(
        "root",
        completed_node_keys=(disclosure.action_key,),
        excluded_node_keys=(disclosure.action_key,),
    )
    ignored_only_state = next(
        state
        for state in evaluate_prerequisite_node_states(
            ignored_only.tree, [], completed_group_ids=[]
        )
        if state.action_key == disclosure.action_key
    )
    assert ignored_only_state.manually_completed is True
    assert ignored_only_state.is_excluded is True
    assert ignored_only_state.satisfied_by_basis is False
    assert ignored_only_state.completed_by_courses is False
    ignored_only_path = calculate_minimum_new_credits(ignored_only.tree, [])
    assert ignored_only_path.state is PrerequisitePathState.EXACT
    assert ignored_only_path.total_new_credits == Decimal("5")

    free_root = catalogue_course(
        "free-mark-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-mark"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "member"),
            ),
            prerequisite_option(
                2,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-free-mark"),
            ),
        ),
    )
    free_compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (free_root, catalogue_course("member")),
            (
                module,
                catalogue_module(
                    "module-free-mark",
                    (
                        module_version(
                            "module-free-mark-v1",
                            rule=module_rule(
                                ModuleRuleType.COMPOSITE_RULE,
                                all_mandatory=True,
                                children=(
                                    module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),
                                    module_rule(ModuleRuleType.ANY_MODULE_RULE, sibling_position=1),
                                ),
                            ),
                            curriculum_periods=year_period,
                        ),
                    ),
                ),
            ),
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    )
    free_compilation = free_compiler.compile("free-mark-root")
    free_disclosure = next(
        part for part in free_compilation.tree.ignored_parts if part.kind.value == "free_choice"
    )
    free_marked = free_compiler.compile(
        "free-mark-root",
        completed_node_keys=(free_disclosure.action_key,),
        excluded_node_keys=(free_disclosure.action_key,),
    )
    assert calculate_minimum_new_credits(free_marked.tree, []).total_new_credits == Decimal("5")

    # Two disclosure records sharing one stable action key aggregate their distinct IDs once, with
    # calculation occurrences left untouched.
    disclosures = free_compilation.tree.ignored_parts
    assert len(disclosures) == 2
    duplicate_disclosures = (
        disclosures[0],
        disclosures[1].model_copy(update={"action_key": disclosures[0].action_key}),
    )
    aggregated_tree = free_compilation.tree.model_copy(
        update={"ignored_parts": duplicate_disclosures}
    )
    aggregate_state = next(
        state
        for state in evaluate_prerequisite_node_states(aggregated_tree, [], completed_group_ids=[])
        if state.action_key == disclosures[0].action_key
    )
    assert aggregate_state.occurrence_ids == tuple(
        sorted(part.part_id for part in duplicate_disclosures)
    )
    assert aggregated_tree.requirements == free_compilation.tree.requirements

    # Actual completed courses fulfil the module automatically. A selected-only basis satisfies the
    # calculation without being reported as historical completion.
    completed_states = {
        state.action_key: state
        for state in evaluate_prerequisite_node_states(
            plain.tree, ["member"], completed_group_ids=["member"]
        )
    }
    selected_states = {
        state.action_key: state
        for state in evaluate_prerequisite_node_states(
            plain.tree, ["member"], completed_group_ids=[]
        )
    }
    assert completed_states["module:module-mark"].completed_by_courses is True
    assert completed_states["module:module-mark"].satisfied_by_basis is True
    assert selected_states["module:module-mark"].completed_by_courses is False
    assert selected_states["module:module-mark"].satisfied_by_basis is True

    # Two same-child numeric source occurrences keep distinct stable action keys, and a category toggle
    # that shifts their drawing positions never changes those source-lineage keys.
    numeric_module = catalogue_module(
        "module-numeric",
        (
            module_version(
                "module-numeric-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(
                            ModuleRuleType.CREDITS_RULE,
                            credits_min="5",
                            children=(
                                module_rule(
                                    ModuleRuleType.COURSE_UNIT_RULE,
                                    referenced_group_id="member",
                                ),
                            ),
                        ),
                        module_rule(
                            ModuleRuleType.CREDITS_RULE,
                            sibling_position=1,
                            credits_min="5",
                            children=(
                                module_rule(
                                    ModuleRuleType.COURSE_UNIT_RULE,
                                    referenced_group_id="member",
                                ),
                            ),
                        ),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    numeric_root = catalogue_course(
        "numeric-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-numeric"),
            ),
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.RECOMMENDED,
                prerequisite_course_member(0, "member"),
            ),
        ),
    )
    numeric_compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead((numeric_root, catalogue_course("member")), (numeric_module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    )

    def numeric_credit_keys(compilation):
        expression_by_occurrence = dict(_iter_expression_occurrences(compilation.tree.requirements))
        key_by_occurrence = {
            occ.occurrence_id: occ.action_key for occ in compilation.tree.node_occurrences
        }
        return sorted(
            key_by_occurrence[occurrence_id]
            for occurrence_id, expression in expression_by_occurrence.items()
            if isinstance(expression, CreditRequirement)
        )

    numeric_plain = numeric_compiler.compile("numeric-root")
    numeric_shifted = numeric_compiler.compile("numeric-root", include_recommended=True)
    plain_credit_keys = numeric_credit_keys(numeric_plain)
    assert len(plain_credit_keys) == 2
    assert plain_credit_keys[0] != plain_credit_keys[1]
    assert numeric_credit_keys(numeric_shifted) == plain_credit_keys


def test_external_module_dependencies_preserve_conditional_route_evidence() -> None:
    """A compact module exposes its external obligations and shares canonical courses with outside routes."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module = catalogue_module(
        "module-abc",
        (
            module_version(
                "module-abc-v1",
                rule=module_rule(
                    ModuleRuleType.COMPOSITE_RULE,
                    all_mandatory=True,
                    children=(
                        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="A"),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=1,
                            referenced_group_id="B",
                        ),
                        module_rule(
                            ModuleRuleType.COURSE_UNIT_RULE,
                            sibling_position=2,
                            referenced_group_id="C",
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
                prerequisite_module_member(0, "module-abc"),
                prerequisite_course_member(1, "outside"),
            ),
        ),
    )

    def require(first: str, second: str):
        return catalogue_course(
            first,
            prerequisite_options=(
                prerequisite_option(
                    0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, second)
                ),
            ),
        )

    # Module members A->B->C->D (D outside), plus an independently reached outside E requiring B or X.
    a = require("A", "B")
    b = require("B", "C")
    c = require("C", "D")
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
        a,
        b,
        c,
        catalogue_course("D"),
        catalogue_course("X"),
        outside,
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root")
    graph = compilation.graph

    module_node = next(node for node in graph.module_nodes if node.module.group_id == "module-abc")
    assert [card.group_id for card in module_node.member_courses] == ["A", "B", "C"]
    module_edges = [edge for edge in graph.edges if edge.source_node_id == module_node.node_id]
    # A pure mandatory internal chain collapses to its one real external obligation. That obligation
    # is one real conjunction whose condition-distinct source chains travel as members of one
    # visible connection, so route lighting never turns unrelated elided gates into a false all-of
    # condition.
    assert [edge.target_node_id for edge in module_edges] == ["connector:r.0.0"]
    obligation_node = next(
        node for node in graph.connector_nodes if node.node_id == "connector:r.0.0"
    )
    assert obligation_node.kind is PrerequisiteGraphConnectorKind.AND
    external_edges = [
        edge for edge in graph.edges if edge.source_node_id == obligation_node.node_id
    ]
    assert {edge.target_node_id for edge in external_edges} == {"course:D"}
    assert len(external_edges) == 1
    external_members = external_edges[0].relationships
    assert len(external_members) > 1
    assert all(member.condition_occurrence_ids for member in external_members)
    assert len({member.condition_occurrence_ids for member in external_members}) == len(
        external_members
    )
    # No standalone member card is drawn solely for the module. The independently reached B, D and
    # outside draw normally and share the one canonical course node. C appears only as a module card,
    # because the module's mandatory conjunction expands it.
    standalone = {node.course.group_id for node in graph.course_nodes}
    assert "A" not in standalone
    assert {"B", "D", "outside", "X"} <= standalone
    assert "C" not in standalone

    path = calculate_minimum_new_credits(compilation.tree, [])
    assert path.state is PrerequisitePathState.EXACT
    selected = tuple(entry.course.group_id for entry in path.new_courses)
    assert selected == ("A", "B", "C", "D", "outside")
    # The module's exact external evidence is selected, while the unchosen X alternative is not.
    x_occurrences = {
        occurrence_id
        for edge in graph.edges
        if edge.target_node_id == "course:X"
        for member in edge.relationships
        for occurrence_id in member.occurrence_ids
    }
    assert set(module_edges[0].relationships[0].occurrence_ids) <= set(path.selected_occurrence_ids)
    assert all(
        set(member.occurrence_ids) <= set(path.selected_occurrence_ids)
        for edge in external_edges
        for member in edge.relationships
    )
    assert not (x_occurrences & set(path.selected_occurrence_ids))

    # An ordinary expanded course head connects to its descendant condition tree, never as an AND
    # connector with head and descendants as siblings.
    assert any(
        edge.source_node_id == "course:outside" and edge.target_node_id.startswith("connector:")
        for edge in graph.edges
    )

    # A mixed module choice keeps its internal-only option as a childless internal requirement and
    # never collapses the external option into one mandatory edge.
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
                            ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="choice-internal"
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
    choice_external = require("choice-external", "choice-dep")
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
    choice_graph = choice_compilation.graph
    choice_module_node = next(
        node for node in choice_graph.module_nodes if node.module.group_id == "module-choice"
    )
    assert [card.group_id for card in choice_module_node.member_courses] == [
        "choice-external",
        "choice-internal",
    ]
    cardinality_connector = next(
        node
        for node in choice_graph.connector_nodes
        if node.kind is PrerequisiteGraphConnectorKind.CARDINALITY
    )
    choice_targets = {
        edge.target_node_id
        for edge in choice_graph.edges
        if edge.source_node_id == cardinality_connector.node_id
    }
    assert len(choice_targets) == 2
    assert any(
        node.kind is PrerequisiteGraphConnectorKind.INTERNAL_REQUIREMENT
        for node in choice_graph.connector_nodes
    )
    assert "choice-dep" in {node.course.group_id for node in choice_graph.course_nodes}
