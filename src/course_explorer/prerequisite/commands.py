"""Database-backed composition for the machine-readable prerequisite graph and route operations.

This module owns the process-level orchestration behind `scripts/prerequisites.py` and the fixed
web `/api/prerequisites` graph read. One preparation resolves caller inputs through the official
lookup owner, compiles the native calculation structure exactly once, projects the one drawing
through its configured allowance, and shares that preparation between the graph presentation and
the machine route calculation. The route operation runs the shared TypeScript solver through Node
outside the serving path. The command is read-only toward official, inferred and accepted
equivalence-group storage. Every service error propagates.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from course_explorer.administration import repository_root
from course_explorer.config import DatabaseSettings, load_database_settings, load_search_settings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.prerequisite._helpers import _PrerequisiteModel
from course_explorer.prerequisite.equivalence_repository import InferredEquivalenceRepository
from course_explorer.prerequisite.graph import PrerequisiteGraphCompiler
from course_explorer.prerequisite.projection import (
    PrerequisiteDrawingAllowance,
    PrerequisiteDrawingGraph,
    project_prerequisite_graph,
)
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from course_explorer.prerequisite.source_cache import (
    PrerequisiteSourceFactCache,
    ReusingCurriculumGraphRead,
)
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure
from course_explorer.search.lookup import CourseLookupService

_BOX_KEY = re.compile(r"^s:.+:d:[0-9a-f]{24}$")

_NODE_SOLVER_BUILD_COMMAND = "npm --prefix web run solver:build"


class PrerequisiteCalculationBasis(StrEnum):
    """Which caller-owned course set satisfies prerequisites in one calculation."""

    COMPLETED = "completed"
    SELECTED = "selected"


class PrerequisiteGraphReport(_PrerequisiteModel):
    """One prerequisite graph report carrying the native structure and its permitted display."""

    solver: PrerequisiteSolverStructure
    display: PrerequisiteDrawingGraph | None = None
    drawing: PrerequisiteDrawingAllowance


@dataclass(frozen=True)
class _PrerequisiteCommandContext:
    """One ephemeral prepared command input shared by both public prerequisite operations."""

    solver: PrerequisiteSolverStructure
    display: PrerequisiteDrawingGraph | None
    drawing: PrerequisiteDrawingAllowance
    basis: PrerequisiteCalculationBasis
    selected_group_ids: tuple[str, ...]
    completed_group_ids: tuple[str, ...]
    excluded_group_ids: tuple[str, ...]
    basis_group_ids: tuple[str, ...]
    completed_node_keys: tuple[str, ...]
    excluded_node_keys: tuple[str, ...]


def _validate_node_keys(keys: Collection[str], *, label: str) -> tuple[str, ...]:
    """Require complete current graph-box keys, rejecting every incompatible shape."""
    normalized: list[str] = []
    for key in keys:
        if not _BOX_KEY.fullmatch(key):
            raise ValueError(
                f"{label} node key {key!r} is not a current graph-box key (s:<owner>:d:<24 hex>)"
            )
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
    max_drawing_elements: int | None = None,
    include_display: bool = True,
    database_settings: DatabaseSettings | None = None,
    source_cache: PrerequisiteSourceFactCache | None = None,
) -> _PrerequisiteCommandContext:
    """Resolve one request's canonical inputs and compile and project its native structure once.

    A supplied source cache answers the compiler's raw course and module reads with the facts it
    retains for this dataset.
    """
    normalized_basis = PrerequisiteCalculationBasis(basis)
    normalized_completed_node_keys = _validate_node_keys(completed_node_keys, label="completed")
    normalized_excluded_node_keys = _validate_node_keys(excluded_node_keys, label="excluded")
    completed_inputs = tuple(completed_codes)
    selected_inputs = tuple(selected_codes)
    excluded_inputs = tuple(excluded_codes)
    search_settings = load_search_settings()
    connection_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    with _database_context(connection_settings) as factory:
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
        graph_read = (
            ReusingCurriculumGraphRead(curriculum, source_cache)
            if source_cache is not None
            else curriculum
        )
        compiler = PrerequisiteGraphCompiler(graph_read, inferred_sets, equivalence_groups)
        structure = compiler.compile_structure(
            target_group_id,
            include_recommended=include_recommended,
            include_inferred=include_inferred,
            active_only=active_only,
            retained_group_ids=effective_selected,
            excluded_group_ids=canonical_excluded,
            completed_node_keys=normalized_completed_node_keys,
            excluded_node_keys=normalized_excluded_node_keys,
        )
    compilation = project_prerequisite_graph(
        structure,
        max_drawing_elements=max_drawing_elements,
        include_display=include_display,
    )
    return _PrerequisiteCommandContext(
        solver=compilation.solver,
        display=compilation.display,
        drawing=compilation.drawing,
        basis=normalized_basis,
        selected_group_ids=effective_selected,
        completed_group_ids=canonical_completed,
        excluded_group_ids=canonical_excluded,
        basis_group_ids=calculation_basis,
        completed_node_keys=normalized_completed_node_keys,
        excluded_node_keys=normalized_excluded_node_keys,
    )


def _run_node_solver(request: dict[str, Any]) -> Any:
    """Run the bundled TypeScript solver once and return its one JSON result.

    The bundle is a build artifact and is never built here. A missing bundle raises
    `FileNotFoundError`, and a nonzero exit or unparsable output raises `RuntimeError` carrying the
    process's standard error.
    """
    bundle = repository_root() / "web" / ".solver-cli" / "cli.js"
    if not bundle.is_file():
        raise FileNotFoundError(
            f"the TypeScript solver bundle {bundle} is missing; run `{_NODE_SOLVER_BUILD_COMMAND}`"
        )
    completed = subprocess.run(
        ["node", str(bundle)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"the TypeScript solver exited with status {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"the TypeScript solver returned malformed output: {error}; "
            f"standard error: {completed.stderr.strip()}"
        ) from error


def _node_route(context: _PrerequisiteCommandContext) -> dict[str, Any]:
    """Run the TypeScript route solver over one prepared context."""
    return _run_node_solver(
        {
            "operation": "route",
            "structure": context.solver.model_dump(mode="json"),
            "basis_group_ids": list(context.basis_group_ids),
            "max_compact_nodes": load_search_settings().prerequisite_path_max_compact_nodes,
        }
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
    database_settings: DatabaseSettings | None = None,
    source_cache: PrerequisiteSourceFactCache | None = None,
) -> PrerequisiteGraphReport:
    """Compose one lookup, one compile and one projection of the permitted drawing."""
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
        max_drawing_elements=max_drawing_elements,
        database_settings=database_settings,
        source_cache=source_cache,
    )
    return PrerequisiteGraphReport(
        solver=context.solver,
        display=context.display,
        drawing=context.drawing,
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
) -> dict[str, Any]:
    """Compose one lookup and one compile, then solve through the bundled TypeScript solver.

    The result is the JSON object the Node process wrote, without a drawing. The size limit is the
    configured `prerequisite_path_max_compact_nodes`, read here and passed to the solver.
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
        include_display=False,
    )
    return _node_route(context)
