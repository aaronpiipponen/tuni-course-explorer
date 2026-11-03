"""Native prerequisite compiler facade over the per-worker database fact loader.

The compiler, its fact loader, its identity authority, its projector and its structure emitter are
native. This module keeps the facade the command layer calls. `native_compiler` materializes
the returned records into the frozen DTOs without deriving an identity.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure

if TYPE_CHECKING:
    from course_explorer.prerequisite.native_compiler import NativeBundle
    from course_explorer.prerequisite.projection import PrerequisiteGraphCompilation


@dataclass(frozen=True)
class PrerequisiteSolverSummary:
    """One direct compilation's root identity, academic year and course summaries.

    ``compile_direct_many`` fills ``courses`` with the candidate's own course summary, which is the
    only course discovery reads.
    """

    root_group_id: str
    academic_year_start: int
    courses: tuple[CourseSummary, ...]


@dataclass(frozen=True)
class DirectPrerequisiteCompilation:
    """One target's request-local full native structure that the graph projection reads."""

    solver: PrerequisiteSolverStructure
    native_bundle: NativeBundle | None = None


@dataclass(frozen=True)
class DirectPrerequisiteSummaryCompilation:
    """One candidate's narrow native identity and request-local outcome bundle."""

    summary: PrerequisiteSolverSummary
    native_bundle: NativeBundle | None = None


class PrerequisiteGraphCompiler:
    """Compile one selected canonical course through the native loader and structure emitter."""

    def __init__(self, *, native_handle: int | None = None) -> None:
        """Keep the native database fact handle this compiler evaluates through."""
        self._native_handle = native_handle

    def compile(
        self,
        target_group_id: str,
        *,
        include_recommended: bool = False,
        include_inferred: bool = False,
        active_only: bool = False,
        retained_group_ids: Collection[str] = (),
        excluded_group_ids: Collection[str] = (),
        completed_node_keys: Collection[str] = (),
        excluded_node_keys: Collection[str] = (),
        max_drawing_elements: int | None = None,
        include_display: bool = True,
    ) -> PrerequisiteGraphCompilation:
        """Build the native structure and its drawing projection for one root."""
        if self._native_handle is None:
            raise ValueError("the native prerequisite fact handle is not open")
        from course_explorer.prerequisite import native_compiler

        return native_compiler.compile_graph(
            self._native_handle,
            target_group_id,
            include_recommended=include_recommended,
            include_inferred=include_inferred,
            active_only=active_only,
            retained=tuple(retained_group_ids),
            excluded=tuple(excluded_group_ids),
            completed=tuple(completed_node_keys),
            excluded_keys=tuple(excluded_node_keys),
            max_drawing_elements=max_drawing_elements,
            include_display=include_display,
        )

    def compile_direct_many(
        self,
        target_group_ids: Collection[str],
        *,
        include_inferred: bool = False,
        active_only: bool = False,
        retained_group_ids: Collection[str] = (),
    ) -> tuple[DirectPrerequisiteSummaryCompilation, ...]:
        """Compile only the candidates' own direct options, without course ancestors.

        Each structure is materialized as its root identity, academic year and course summaries and
        paired with the request's native bundle. ``NativeBundle.evaluate`` computes the native
        outcome of each structure for a chosen basis.
        """
        targets = tuple(sorted(set(target_group_ids)))
        if not targets:
            return ()
        if self._native_handle is None:
            raise ValueError("the native prerequisite fact handle is not open")
        from course_explorer.prerequisite import native_compiler

        bundle = native_compiler.compile_direct_many(
            self._native_handle,
            targets,
            tuple(retained_group_ids),
            active_only=active_only,
            include_inferred=include_inferred,
        )
        return tuple(
            DirectPrerequisiteSummaryCompilation(
                summary=structure.summary,
                native_bundle=bundle,
            )
            for structure in bundle.structures
        )
