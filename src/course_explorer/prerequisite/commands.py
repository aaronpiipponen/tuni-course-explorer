"""Database-backed composition for the two machine-readable prerequisite operations.

This module owns the process-level orchestration behind `scripts/prerequisites.py`, the fixed web
`/api/prerequisites` graph read and the fixed web `/api/minimum-route` read. One
preparation resolves caller-supplied target/selected/completed/excluded canonical group IDs or
exact official codes through the official lookup owner and compiles the authoritative
calculation tree exactly once with the caller's independent recommended/inferred visibility inputs,
the activity scope, the compile-time retention and display set, the canonical exclusions, and the
caller's graph-node marks. Both public operations consume that one immutable preparation:
`run_prerequisite_command` returns the normalized drawing graph and its node presentation states,
while `run_minimum_route_command` returns the exact-or-approximate minimum-new-credit result. The
command is read-only toward official, inferred, and accepted equivalence-group storage. Every
fail-loud service error propagates.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from course_explorer.config import load_database_settings, load_search_settings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.prerequisite._helpers import _PrerequisiteModel
from course_explorer.prerequisite.equivalence_repository import InferredEquivalenceRepository
from course_explorer.prerequisite.graph import (
    PrerequisiteCalculationTree,
    PrerequisiteDrawingGraph,
    PrerequisiteGraphCompilation,
    PrerequisiteGraphCompiler,
    project_prerequisite_graph,
)
from course_explorer.prerequisite.path import (
    MinimumCreditPathEvaluation,
    calculate_minimum_new_credits,
)
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from course_explorer.prerequisite.satisfaction import evaluate_prerequisite_node_states
from course_explorer.search.lookup import CourseLookupService

_SUPPORTED_NODE_PREFIXES = ("course:", "module:", "requirement:", "opaque:")


class PrerequisiteCalculationBasis(StrEnum):
    """Which caller-owned course set satisfies prerequisites in one calculation."""

    COMPLETED = "completed"
    SELECTED = "selected"


class PrerequisiteDrawingAllowance(_PrerequisiteModel):
    """Request-local counts for the drawing surface, separate from calculation."""

    allowed: bool
    limit: int | None
    course_count: int
    node_count: int
    edge_count: int
    element_count: int


def prerequisite_drawing_allowance(
    graph: PrerequisiteDrawingGraph, *, max_elements: int | None
) -> PrerequisiteDrawingAllowance:
    """Count every node and edge the browser presents.

    A caller without a drawing surface passes no limit, so drawing is always allowed.
    """
    node_count = (
        len(graph.course_nodes)
        + len(graph.module_nodes)
        + len(graph.ignored_nodes)
        + len(graph.connector_nodes)
    )
    edge_count = len(graph.edges)
    element_count = node_count + edge_count
    return PrerequisiteDrawingAllowance(
        allowed=max_elements is None or element_count <= max_elements,
        limit=max_elements,
        course_count=len(graph.course_nodes),
        node_count=node_count,
        edge_count=edge_count,
        element_count=element_count,
    )


class PrerequisiteGraphReport(_PrerequisiteModel):
    """One prerequisite graph report embedding the authoritative compilation and drawing.

    `selected_group_ids`/`completed_group_ids`/`excluded_group_ids` preserve the caller's full
    canonical input sets. `completed_node_keys`/`excluded_node_keys` preserve the caller's graph
    marks. These are request context, and no route result is embedded: a minimum route is a
    separate explicit operation with its own result.
    """

    compilation: PrerequisiteGraphCompilation
    selected_group_ids: tuple[str, ...]
    completed_group_ids: tuple[str, ...]
    basis: PrerequisiteCalculationBasis
    excluded_group_ids: tuple[str, ...] = ()
    completed_node_keys: tuple[str, ...] = ()
    excluded_node_keys: tuple[str, ...] = ()
    drawing: PrerequisiteDrawingAllowance


@dataclass(frozen=True)
class _PrerequisiteCommandContext:
    """One ephemeral prepared command input shared by both public prerequisite operations.

    It carries the compiled immutable calculation tree and the canonical caller inputs both
    operations need. It is never persisted, cached, or returned as a second report or store.
    """

    tree: PrerequisiteCalculationTree
    basis: PrerequisiteCalculationBasis
    selected_group_ids: tuple[str, ...]
    completed_group_ids: tuple[str, ...]
    excluded_group_ids: tuple[str, ...]
    basis_group_ids: tuple[str, ...]
    completed_node_keys: tuple[str, ...]
    excluded_node_keys: tuple[str, ...]


def _validate_node_keys(keys: Collection[str], *, label: str) -> tuple[str, ...]:
    """Require nonblank supported-prefix action keys, rejecting course keys in a completion set."""
    normalized: list[str] = []
    for key in keys:
        if not key.strip():
            raise ValueError(f"{label} node key must not be blank")
        if not key.startswith(_SUPPORTED_NODE_PREFIXES):
            raise ValueError(f"{label} node key {key!r} has an unsupported prefix")
        normalized.append(key)
    return tuple(sorted(set(normalized)))


def _prepare_prerequisite_command(
    target_code: str,
    *,
    completed_codes: Collection[str] = (),
    selected_codes: Collection[str] = (),
    excluded_codes: Collection[str] = (),
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    basis: str = "completed",
    completed_node_keys: Collection[str] = (),
    excluded_node_keys: Collection[str] = (),
) -> _PrerequisiteCommandContext:
    """Resolve one request's canonical inputs and compile its authoritative calculation tree.

    Selected, completed and excluded canonical IDs or exact official codes are resolved in the one
    bulk id-or-code lookup. The canonical selected set is the compile-time retention and display set.
    The chosen basis (completed subset or selected set) is the sole calculation basis. When no selected
    codes are supplied the canonical completed set is also the selected set, so the selected basis
    never fails for omitted selected input. Excluded IDs or codes resolve in the same bulk call and
    reach the compiler as canonical exclusions. They are never subtracted from selected/completed or
    their subset checks. Graph-node marks are opaque report-issued action keys: a course key in
    `excluded_node_keys` is canonical exclusion, and a course key in `completed_node_keys` is
    rejected with guidance to use the shared completed course input. The database context is disposed
    before the immutable tree is returned.
    """
    normalized_basis = PrerequisiteCalculationBasis(basis)
    normalized_completed_node_keys = _validate_node_keys(completed_node_keys, label="completed")
    if any(key.startswith("course:") for key in normalized_completed_node_keys):
        raise ValueError(
            "completed course nodes use the shared completed course input, not --completed-node"
        )
    normalized_excluded_node_keys = _validate_node_keys(excluded_node_keys, label="excluded")
    completed_inputs = tuple(completed_codes)
    selected_inputs = tuple(selected_codes)
    excluded_inputs = tuple(excluded_codes)
    search_settings = load_search_settings()
    with _database_context(load_database_settings()) as factory:
        curriculum = CurriculumRepository(factory)
        lookup = CourseLookupService(curriculum, search_settings)
        resolved = lookup.resolve_courses(
            (target_code, *selected_inputs, *completed_inputs, *excluded_inputs)
        )
        target_group_id = resolved[0].summary.group_id
        selected_group_id_slice = resolved[1 : 1 + len(selected_inputs)]
        completed_slice = resolved[
            1 + len(selected_inputs) : 1 + len(selected_inputs) + len(completed_inputs)
        ]
        excluded_slice = resolved[1 + len(selected_inputs) + len(completed_inputs) :]
        canonical_selected = tuple(
            sorted({record.summary.group_id for record in selected_group_id_slice})
        )
        canonical_completed = tuple(sorted({record.summary.group_id for record in completed_slice}))
        canonical_excluded = tuple(sorted({record.summary.group_id for record in excluded_slice}))
        if selected_inputs:
            offenders = sorted(set(canonical_completed) - set(canonical_selected))
            if offenders:
                raise ValueError(f"completed courses must be selected: {', '.join(offenders)}")
            effective_selected = canonical_selected
        else:
            effective_selected = canonical_completed
        calculation_basis = (
            effective_selected
            if normalized_basis is PrerequisiteCalculationBasis.SELECTED
            else canonical_completed
        )
        inferred_sets = InferredPrerequisiteRepository(factory)
        equivalence_groups = InferredEquivalenceRepository(factory)
        compiler = PrerequisiteGraphCompiler(curriculum, inferred_sets, equivalence_groups)
        tree = compiler.compile_tree(
            target_group_id,
            include_recommended=include_recommended,
            include_inferred=include_inferred,
            active_only=active_only,
            retained_group_ids=effective_selected,
            excluded_group_ids=canonical_excluded,
            completed_node_keys=normalized_completed_node_keys,
            excluded_node_keys=normalized_excluded_node_keys,
        )
    return _PrerequisiteCommandContext(
        tree=tree,
        basis=normalized_basis,
        selected_group_ids=effective_selected,
        completed_group_ids=canonical_completed,
        excluded_group_ids=canonical_excluded,
        basis_group_ids=calculation_basis,
        completed_node_keys=normalized_completed_node_keys,
        excluded_node_keys=normalized_excluded_node_keys,
    )


def run_prerequisite_command(
    target_code: str,
    *,
    completed_codes: Collection[str] = (),
    selected_codes: Collection[str] = (),
    excluded_codes: Collection[str] = (),
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    basis: str = "completed",
    completed_node_keys: Collection[str] = (),
    excluded_node_keys: Collection[str] = (),
    max_drawing_elements: int | None = None,
) -> PrerequisiteGraphReport:
    """Compose one lookup, one compile, one node-state evaluation and one projection into a report.

    `max_drawing_elements` is the caller's browser-drawing limit. Omitted, drawing is never refused.
    The operation returns the normalized backend-owned drawing with its node states and never
    calculates, schedules or fabricates a minimum-route result.
    """
    context = _prepare_prerequisite_command(
        target_code,
        completed_codes=completed_codes,
        selected_codes=selected_codes,
        excluded_codes=excluded_codes,
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        active_only=active_only,
        basis=basis,
        completed_node_keys=completed_node_keys,
        excluded_node_keys=excluded_node_keys,
    )
    node_states = evaluate_prerequisite_node_states(
        context.tree, context.basis_group_ids, completed_group_ids=context.completed_group_ids
    )
    graph = project_prerequisite_graph(context.tree, node_states=node_states)
    return PrerequisiteGraphReport(
        compilation=PrerequisiteGraphCompilation(tree=context.tree, graph=graph),
        selected_group_ids=context.selected_group_ids,
        completed_group_ids=context.completed_group_ids,
        basis=context.basis,
        excluded_group_ids=context.excluded_group_ids,
        completed_node_keys=context.completed_node_keys,
        excluded_node_keys=context.excluded_node_keys,
        drawing=prerequisite_drawing_allowance(graph, max_elements=max_drawing_elements),
    )


def run_minimum_route_command(
    target_code: str,
    *,
    completed_codes: Collection[str] = (),
    selected_codes: Collection[str] = (),
    excluded_codes: Collection[str] = (),
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    basis: str = "completed",
    completed_node_keys: Collection[str] = (),
    excluded_node_keys: Collection[str] = (),
) -> MinimumCreditPathEvaluation:
    """Compose one lookup, one compile and one bounded minimum-new-credit calculation.

    The result is exact by default. It uses the configured compact-allocation limit to mark
    approximate routes and size-triggered `search_too_large` failures, and may report a guarded
    module shortfall under active-only scope. The operation never projects or returns a drawing
    graph and never evaluates graph-node presentation states.
    """
    context = _prepare_prerequisite_command(
        target_code,
        completed_codes=completed_codes,
        selected_codes=selected_codes,
        excluded_codes=excluded_codes,
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        active_only=active_only,
        basis=basis,
        completed_node_keys=completed_node_keys,
        excluded_node_keys=excluded_node_keys,
    )
    return calculate_minimum_new_credits(
        context.tree,
        context.basis_group_ids,
        max_compact_nodes=load_search_settings().prerequisite_path_max_compact_nodes,
    )
