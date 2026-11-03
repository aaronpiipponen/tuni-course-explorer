"""Native prerequisite library ABI, loader and record materializer.

The module declares the `ctypes` call and record layouts, loads the shared library once and
materializes the returned record view into frozen DTOs. The native library owns every calculation
and display identity, the reachable id tables and the drawing projection. The materializer reads the
returned record view through `ctypes`, converts enum codes and decimal text, and constructs the
frozen product models. A missing or version-mismatched library raises one `ValueError` naming the
build command. The materialized structures are request-local.
"""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

from course_explorer import administration, native_library
from course_explorer.curriculum import CourseSummary, ModuleSummary
from course_explorer.enums import InferredCoverageState, ModuleType
from course_explorer.prerequisite.domain import (
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    InferredSetCoverage,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.structure import (
    InferredCoverageRecord,
    PrerequisiteDiagnostic,
    PrerequisitePiece,
    PrerequisiteProjectionChild,
    PrerequisiteProjectionContext,
    PrerequisiteRelationshipMember,
    PrerequisiteSolverStructure,
    PrerequisiteSourceFact,
    PrerequisiteSourceUse,
    PrerequisiteSupportBinding,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from course_explorer.prerequisite.graph import (
        DirectPrerequisiteCompilation,
        DirectPrerequisiteSummaryCompilation,
    )
    from course_explorer.prerequisite.projection import PrerequisiteGraphCompilation

# Format version the loaded compiler library must report.
FORMAT_VERSION = 5
_NATIVE_LOCK = threading.RLock()

_PIECE_KINDS = {
    0: "course",
    1: "and",
    2: "or",
    3: "course_alternatives",
    4: "cardinality",
    5: "credits",
    6: "course_count",
    7: "module_block",
    8: "opaque_credits",
    9: "unresolved",
    10: "expanded_course",
}
_DISPLAY_KINDS = {
    0: "course",
    1: "module",
    2: "and",
    3: "or",
    4: "cardinality",
    5: "credits",
    6: "course_count",
    7: "opaque_credits",
    8: "internal_requirement",
    9: "unresolved",
    10: "ignored",
}
_ORIGINS = {
    0: PrerequisiteOrigin.OFFICIAL,
    1: PrerequisiteOrigin.INFERRED,
    2: PrerequisiteOrigin.COMPOSED,
}
_OFFICIAL_KINDS = {
    0: OfficialPrerequisiteKind.COMPULSORY,
    1: OfficialPrerequisiteKind.RECOMMENDED,
    2: OfficialPrerequisiteKind.MODULE_RULE,
    3: OfficialPrerequisiteKind.SUBSTITUTION,
}
_INFERRED_CATEGORIES = {
    0: InferredPrerequisiteCategory.REQUIRED,
    1: InferredPrerequisiteCategory.RECOMMENDED,
}


class _StringList(ctypes.Structure):
    _fields_ = [
        ("items", ctypes.POINTER(ctypes.c_char_p)),
        ("count", ctypes.c_int32),
    ]


class _Piece(ctypes.Structure):
    _fields_ = [
        ("piece_id", ctypes.c_char_p),
        ("kind", ctypes.c_int32),
        ("children", _StringList),
        ("course_group_id", ctypes.c_char_p),
        ("module_group_id", ctypes.c_char_p),
        ("work_key", ctypes.c_char_p),
        ("require_min", ctypes.c_int32),
        ("require_max", ctypes.c_int32),
        ("credits_min", ctypes.c_char_p),
        ("credits_max", ctypes.c_char_p),
        ("count_min", ctypes.c_int32),
        ("count_max", ctypes.c_int32),
        ("reason", ctypes.c_char_p),
        ("referenced_group_id", ctypes.c_char_p),
        ("detail", ctypes.c_char_p),
        ("manual_credits_min", ctypes.c_char_p),
        ("module_rule", ctypes.c_uint8),
        ("cycle_closing", ctypes.c_uint8),
    ]


class _Use(ctypes.Structure):
    _fields_ = [
        ("use_id", ctypes.c_char_p),
        ("piece_id", ctypes.c_char_p),
        ("fact_id", ctypes.c_char_p),
        ("children", _StringList),
        ("diagnostic_ids", _StringList),
        ("member_group_ids", _StringList),
    ]


class _Fact(ctypes.Structure):
    _fields_ = [
        ("fact_id", ctypes.c_char_p),
        ("origin", ctypes.c_int32),
        ("official_kind", ctypes.c_int32),
        ("inferred_category", ctypes.c_int32),
        ("inference", ctypes.c_char_p),
    ]


class _Diagnostic(ctypes.Structure):
    _fields_ = [
        ("diagnostic_id", ctypes.c_char_p),
        ("kind", ctypes.c_char_p),
        ("fact_id", ctypes.c_char_p),
        ("referenced_group_ids", _StringList),
        ("detail", ctypes.c_char_p),
        ("module_group_id", ctypes.c_char_p),
    ]


class _Course(ctypes.Structure):
    _fields_ = [
        ("group_id", ctypes.c_char_p),
        ("name_fi", ctypes.c_char_p),
        ("name_en", ctypes.c_char_p),
        ("code", ctypes.c_char_p),
        ("credits_min", ctypes.c_char_p),
        ("credits_max", ctypes.c_char_p),
        ("official_url", ctypes.c_char_p),
        ("has_name_fi", ctypes.c_uint8),
        ("has_name_en", ctypes.c_uint8),
        ("has_credits_max", ctypes.c_uint8),
        ("is_active", ctypes.c_uint8),
    ]


class _Module(ctypes.Structure):
    _fields_ = [
        ("group_id", ctypes.c_char_p),
        ("sisu_module_id", ctypes.c_char_p),
        ("module_type", ctypes.c_char_p),
        ("code", ctypes.c_char_p),
        ("name_fi", ctypes.c_char_p),
        ("name_en", ctypes.c_char_p),
        ("has_code", ctypes.c_uint8),
        ("has_name_fi", ctypes.c_uint8),
        ("has_name_en", ctypes.c_uint8),
    ]


class _Coverage(ctypes.Structure):
    _fields_ = [
        ("target_group_id", ctypes.c_char_p),
        ("coverage_state", ctypes.c_char_p),
        ("eligible_source_count", ctypes.c_int64),
        ("processed_source_count", ctypes.c_int64),
        ("accepted_source_count", ctypes.c_int64),
    ]


class _Binding(ctypes.Structure):
    _fields_ = [
        ("support_id", ctypes.c_char_p),
        ("owner_group_id", ctypes.c_char_p),
        ("piece_id", ctypes.c_char_p),
        ("use_ids", _StringList),
        ("node_ids", _StringList),
        ("mark_node_ids", _StringList),
    ]


class _ContextChild(ctypes.Structure):
    _fields_ = [
        ("slot", ctypes.c_int32),
        ("context_id", ctypes.c_char_p),
    ]


class _Context(ctypes.Structure):
    _fields_ = [
        ("context_id", ctypes.c_char_p),
        ("owner_group_id", ctypes.c_char_p),
        ("piece_id", ctypes.c_char_p),
        ("children", ctypes.POINTER(_ContextChild)),
        ("child_count", ctypes.c_int32),
        ("member_ids", _StringList),
    ]


class _Member(ctypes.Structure):
    _fields_ = [
        ("member_id", ctypes.c_char_p),
        ("source_node_id", ctypes.c_char_p),
        ("target_node_id", ctypes.c_char_p),
        ("fact_id", ctypes.c_char_p),
    ]


class _DisplayNode(ctypes.Structure):
    _fields_ = [
        ("node_id", ctypes.c_char_p),
        ("kind", ctypes.c_int32),
        ("owner_group_id", ctypes.c_char_p),
        ("course_group_id", ctypes.c_char_p),
        ("module_group_id", ctypes.c_char_p),
        ("require_min", ctypes.c_int32),
        ("require_max", ctypes.c_int32),
        ("credits_min", ctypes.c_char_p),
        ("credits_max", ctypes.c_char_p),
        ("count_min", ctypes.c_int32),
        ("count_max", ctypes.c_int32),
        ("referenced_group_id", ctypes.c_char_p),
        ("reason", ctypes.c_char_p),
        ("detail", ctypes.c_char_p),
        ("member_group_ids", _StringList),
        ("diagnostic_ids", _StringList),
        ("is_root", ctypes.c_uint8),
        ("via_inferred", ctypes.c_uint8),
        ("via_recommended", ctypes.c_uint8),
        ("has_official_provenance", ctypes.c_uint8),
        ("has_inferred_provenance", ctypes.c_uint8),
        ("display_as_inferred", ctypes.c_uint8),
        ("markable", ctypes.c_uint8),
    ]


class _DisplayEdge(ctypes.Structure):
    _fields_ = [
        ("edge_id", ctypes.c_char_p),
        ("source_node_id", ctypes.c_char_p),
        ("target_node_id", ctypes.c_char_p),
        ("member_ids", _StringList),
        ("inferred_only", ctypes.c_uint8),
    ]


class _Structure(ctypes.Structure):
    _fields_ = [
        ("root_group_id", ctypes.c_char_p),
        ("academic_year_start", ctypes.c_int32),
        ("active_only", ctypes.c_uint8),
        ("include_recommended", ctypes.c_uint8),
        ("include_inferred", ctypes.c_uint8),
        ("requirements_use_id", ctypes.c_char_p),
        ("required_use_id", ctypes.c_char_p),
        ("recommended_use_id", ctypes.c_char_p),
        ("pieces", ctypes.POINTER(_Piece)),
        ("piece_count", ctypes.c_int32),
        ("uses", ctypes.POINTER(_Use)),
        ("use_count", ctypes.c_int32),
        ("facts", ctypes.POINTER(_Fact)),
        ("fact_count", ctypes.c_int32),
        ("diagnostics", ctypes.POINTER(_Diagnostic)),
        ("diagnostic_count", ctypes.c_int32),
        ("courses", ctypes.POINTER(_Course)),
        ("course_count", ctypes.c_int32),
        ("modules", ctypes.POINTER(_Module)),
        ("module_count", ctypes.c_int32),
        ("coverage", ctypes.POINTER(_Coverage)),
        ("coverage_count", ctypes.c_int32),
        ("excluded_group_ids", _StringList),
        ("completed_node_keys", _StringList),
        ("excluded_node_keys", _StringList),
        ("root_diagnostic_ids", _StringList),
        ("projection_root_context_id", ctypes.c_char_p),
        ("bindings", ctypes.POINTER(_Binding)),
        ("binding_count", ctypes.c_int32),
        ("contexts", ctypes.POINTER(_Context)),
        ("context_count", ctypes.c_int32),
        ("members", ctypes.POINTER(_Member)),
        ("member_count", ctypes.c_int32),
        ("drawing_course_count", ctypes.c_int32),
        ("drawing_node_count", ctypes.c_int32),
        ("drawing_edge_count", ctypes.c_int32),
        ("nodes", ctypes.POINTER(_DisplayNode)),
        ("node_count", ctypes.c_int32),
        ("edges", ctypes.POINTER(_DisplayEdge)),
        ("edge_count", ctypes.c_int32),
    ]


class _NativeOutcome(ctypes.Structure):
    """The C outcome record for one compiled structure, in bundle order."""

    _fields_ = [
        ("root", ctypes.c_char_p),
        ("has_outcome", ctypes.c_int),
        ("required_coverage", ctypes.c_double),
        ("recommended_coverage", ctypes.c_double),
        ("has_required", ctypes.c_int),
        ("has_recommended", ctypes.c_int),
    ]


@dataclass(frozen=True)
class NativeOutcome:
    """One structure's native eligibility and coverage outcome."""

    compilation: DirectPrerequisiteCompilation | DirectPrerequisiteSummaryCompilation
    has_outcome: bool
    required_coverage: float | None
    recommended_coverage: float | None


def _text(value: bytes | None) -> str:
    return "" if not value else value.decode()


def _optional(value: bytes | None) -> str | None:
    return value.decode() if value else None


def _strings(values: _StringList) -> tuple[str, ...]:
    return tuple(values.items[index].decode() for index in range(values.count))


def _decimal(value: bytes | None) -> Decimal | None:
    return Decimal(value.decode()) if value else None


def _optional_int(value: int) -> int | None:
    return value if value >= 0 else None


def _courses(structure: _Structure) -> tuple[CourseSummary, ...]:
    courses = []
    for index in range(structure.course_count):
        record = structure.courses[index]
        courses.append(
            CourseSummary.model_construct(
                group_id=_text(record.group_id),
                name_fi=_text(record.name_fi) if record.has_name_fi else None,
                name_en=_text(record.name_en) if record.has_name_en else None,
                code=_text(record.code),
                credits_min=Decimal(_text(record.credits_min)),
                credits_max=Decimal(_text(record.credits_max)) if record.has_credits_max else None,
                is_active=bool(record.is_active),
                official_url=_text(record.official_url),
            )
        )
    return tuple(courses)


def _pieces(structure: _Structure) -> tuple[PrerequisitePiece, ...]:
    pieces = []
    for index in range(structure.piece_count):
        record = structure.pieces[index]
        pieces.append(
            PrerequisitePiece.model_construct(
                piece_id=_text(record.piece_id),
                kind=_PIECE_KINDS[record.kind],
                children=_strings(record.children),
                course_group_id=_optional(record.course_group_id),
                module_group_id=_optional(record.module_group_id),
                work_key=_optional(record.work_key),
                require_min=_optional_int(record.require_min),
                require_max=_optional_int(record.require_max),
                credits_min=_decimal(record.credits_min),
                credits_max=_decimal(record.credits_max),
                count_min=_optional_int(record.count_min),
                count_max=_optional_int(record.count_max),
                reason=_optional(record.reason),
                referenced_group_id=_optional(record.referenced_group_id),
                detail=_optional(record.detail),
                manual_credits_min=_decimal(record.manual_credits_min),
                module_rule=bool(record.module_rule),
                cycle_closing=bool(record.cycle_closing),
            )
        )
    return tuple(pieces)


def _facts(structure: _Structure) -> tuple[PrerequisiteSourceFact, ...]:
    facts = []
    for index in range(structure.fact_count):
        record = structure.facts[index]
        raw = record.inference
        facts.append(
            PrerequisiteSourceFact.model_construct(
                fact_id=_text(record.fact_id),
                origin=_ORIGINS[record.origin],
                official_kind=(
                    None if record.official_kind < 0 else _OFFICIAL_KINDS[record.official_kind]
                ),
                inferred_category=(
                    None
                    if record.inferred_category < 0
                    else _INFERRED_CATEGORIES[record.inferred_category]
                ),
                inference=(
                    InferenceNodeMetadata.model_validate_json(raw.decode()) if raw else None
                ),
            )
        )
    return tuple(facts)


def _diagnostics(structure: _Structure) -> tuple[PrerequisiteDiagnostic, ...]:
    diagnostics = []
    for index in range(structure.diagnostic_count):
        record = structure.diagnostics[index]
        diagnostics.append(
            PrerequisiteDiagnostic.model_construct(
                diagnostic_id=_text(record.diagnostic_id),
                kind=_text(record.kind),
                fact_id=_text(record.fact_id),
                referenced_group_ids=_strings(record.referenced_group_ids),
                detail=_optional(record.detail),
                module_group_id=_optional(record.module_group_id),
            )
        )
    return tuple(diagnostics)


def _uses(structure: _Structure) -> tuple[PrerequisiteSourceUse, ...]:
    uses = []
    for index in range(structure.use_count):
        record = structure.uses[index]
        uses.append(
            PrerequisiteSourceUse.model_construct(
                use_id=_text(record.use_id),
                piece_id=_text(record.piece_id),
                fact_id=_text(record.fact_id),
                children=_strings(record.children),
                diagnostic_ids=_strings(record.diagnostic_ids),
                member_group_ids=_strings(record.member_group_ids),
            )
        )
    return tuple(uses)


def _modules(structure: _Structure) -> tuple[ModuleSummary, ...]:
    modules = []
    for index in range(structure.module_count):
        record = structure.modules[index]
        modules.append(
            ModuleSummary.model_construct(
                group_id=_text(record.group_id),
                sisu_module_id=_text(record.sisu_module_id),
                module_type=ModuleType(_text(record.module_type)),
                code=_text(record.code) if record.has_code else None,
                name_fi=_text(record.name_fi) if record.has_name_fi else None,
                name_en=_text(record.name_en) if record.has_name_en else None,
            )
        )
    return tuple(modules)


def _bindings(structure: _Structure) -> tuple[PrerequisiteSupportBinding, ...]:
    bindings = []
    for index in range(structure.binding_count):
        record = structure.bindings[index]
        bindings.append(
            PrerequisiteSupportBinding.model_construct(
                support_id=_text(record.support_id),
                owner_group_id=_text(record.owner_group_id),
                piece_id=_text(record.piece_id),
                use_ids=_strings(record.use_ids),
                node_ids=_strings(record.node_ids),
                mark_node_ids=_strings(record.mark_node_ids),
            )
        )
    return tuple(bindings)


def _members(structure: _Structure) -> tuple[PrerequisiteRelationshipMember, ...]:
    members = []
    for index in range(structure.member_count):
        record = structure.members[index]
        members.append(
            PrerequisiteRelationshipMember.model_construct(
                member_id=_text(record.member_id),
                source_node_id=_text(record.source_node_id),
                target_node_id=_text(record.target_node_id),
                fact_id=_text(record.fact_id),
            )
        )
    return tuple(members)


def _contexts(structure: _Structure) -> tuple[PrerequisiteProjectionContext, ...]:
    contexts = []
    for index in range(structure.context_count):
        record = structure.contexts[index]
        children = []
        for child in range(record.child_count):
            item = record.children[child]
            children.append(
                PrerequisiteProjectionChild.model_construct(
                    slot=item.slot,
                    context_id=_text(item.context_id),
                )
            )
        contexts.append(
            PrerequisiteProjectionContext.model_construct(
                context_id=_text(record.context_id),
                owner_group_id=_text(record.owner_group_id),
                piece_id=_text(record.piece_id),
                children=tuple(children),
                member_ids=_strings(record.member_ids),
            )
        )
    return tuple(contexts)


def _structure(record: _Structure) -> PrerequisiteSolverStructure:
    """Construct one frozen solver structure from the native record view."""
    coverage_records = []
    for index in range(record.coverage_count):
        item = record.coverage[index]
        coverage_records.append(
            InferredCoverageRecord.model_construct(
                target_group_id=_text(item.target_group_id),
                coverage_state=InferredCoverageState(_text(item.coverage_state)),
                coverage=InferredSetCoverage(
                    eligible_source_count=item.eligible_source_count,
                    processed_source_count=item.processed_source_count,
                    accepted_source_count=item.accepted_source_count,
                ),
            )
        )
    coverage = tuple(coverage_records)
    return PrerequisiteSolverStructure.model_construct(
        root_group_id=_text(record.root_group_id),
        academic_year_start=record.academic_year_start,
        root_use_id=_optional(record.requirements_use_id),
        pieces=_pieces(record),
        uses=_uses(record),
        facts=_facts(record),
        diagnostics=_diagnostics(record),
        root_diagnostic_ids=_strings(record.root_diagnostic_ids),
        courses=_courses(record),
        modules=_modules(record),
        include_recommended=bool(record.include_recommended),
        include_inferred=bool(record.include_inferred),
        active_only=bool(record.active_only),
        inferred_coverage=coverage,
        excluded_group_ids=_strings(record.excluded_group_ids),
        completed_node_keys=_strings(record.completed_node_keys),
        excluded_node_keys=_strings(record.excluded_node_keys),
        bindings=_bindings(record),
        projection_root_context_id=_optional(record.projection_root_context_id),
        projection_contexts=_contexts(record),
        members=_members(record),
    )


def _display(record: _Structure):
    """Construct one frozen drawing graph from the native record view."""
    from course_explorer.prerequisite.projection import (
        PrerequisiteDisplayEdge,
        PrerequisiteDisplayNode,
        PrerequisiteDrawingGraph,
    )

    nodes = []
    for index in range(record.node_count):
        item = record.nodes[index]
        nodes.append(
            PrerequisiteDisplayNode.model_construct(
                node_id=_text(item.node_id),
                kind=_DISPLAY_KINDS[item.kind],
                owner_group_id=_optional(item.owner_group_id),
                course_group_id=_optional(item.course_group_id),
                module_group_id=_optional(item.module_group_id),
                require_min=_optional_int(item.require_min),
                require_max=_optional_int(item.require_max),
                credits_min=_decimal(item.credits_min),
                credits_max=_decimal(item.credits_max),
                count_min=_optional_int(item.count_min),
                count_max=_optional_int(item.count_max),
                referenced_group_id=_optional(item.referenced_group_id),
                reason=_optional(item.reason),
                detail=_optional(item.detail),
                member_group_ids=_strings(item.member_group_ids),
                diagnostic_ids=_strings(item.diagnostic_ids),
                is_root=bool(item.is_root),
                via_inferred=bool(item.via_inferred),
                via_recommended=bool(item.via_recommended),
                has_official_provenance=bool(item.has_official_provenance),
                has_inferred_provenance=bool(item.has_inferred_provenance),
                display_as_inferred=bool(item.display_as_inferred),
                markable=bool(item.markable),
            )
        )
    edges = []
    for index in range(record.edge_count):
        item = record.edges[index]
        edges.append(
            PrerequisiteDisplayEdge.model_construct(
                edge_id=_text(item.edge_id),
                source_node_id=_text(item.source_node_id),
                target_node_id=_text(item.target_node_id),
                member_ids=_strings(item.member_ids),
                inferred_only=bool(item.inferred_only),
            )
        )
    return PrerequisiteDrawingGraph(nodes=tuple(nodes), edges=tuple(edges))


def _materialize_structure(record: _Structure) -> DirectPrerequisiteCompilation:
    """Materialize one full structure for the graph projection."""
    from course_explorer.prerequisite.graph import DirectPrerequisiteCompilation

    return DirectPrerequisiteCompilation(solver=_structure(record))


def _materialize_summary(record: _Structure) -> DirectPrerequisiteSummaryCompilation:
    """Materialize one narrow discovery summary from the native record view."""
    from course_explorer.prerequisite.graph import (
        DirectPrerequisiteSummaryCompilation,
        PrerequisiteSolverSummary,
    )

    return DirectPrerequisiteSummaryCompilation(
        summary=PrerequisiteSolverSummary(
            root_group_id=_text(record.root_group_id),
            academic_year_start=record.academic_year_start,
            courses=_courses(record),
        )
    )


def _projection(
    record: _Structure,
    solver: PrerequisiteSolverStructure,
    *,
    max_drawing_elements: int | None,
    include_display: bool,
) -> PrerequisiteGraphCompilation:
    """Pair a materialized solver with its permitted drawing graph."""
    from course_explorer.prerequisite.projection import (
        PrerequisiteGraphCompilation,
        prerequisite_drawing_allowance,
    )

    allowance = prerequisite_drawing_allowance(
        course_count=record.drawing_course_count,
        node_count=record.drawing_node_count,
        edge_count=record.drawing_edge_count,
        max_elements=max_drawing_elements,
    )
    display = _display(record) if include_display and allowance.allowed else None
    return PrerequisiteGraphCompilation(solver=solver, display=display, drawing=allowance)


class NativeBundle:
    """One request-local native bundle pointer and its materialized structures."""

    def __init__(
        self,
        pointer: int,
        records: tuple[_Structure, ...],
        structures: tuple[
            DirectPrerequisiteCompilation | DirectPrerequisiteSummaryCompilation, ...
        ],
        library: ctypes.CDLL,
    ) -> None:
        self._pointer = pointer
        self._records = records
        self.structures = structures
        self._library = library

    def evaluate(self, basis: tuple[str, ...], *, mode: int) -> tuple[NativeOutcome, ...]:
        """Return every structure's native outcome in bundle order."""
        library = self._library
        basis_buffer, basis_offsets = _blob(basis)
        outcomes = (_NativeOutcome * len(self.structures))()
        written = library.course_prerequisite_evaluate(
            self._pointer,
            basis_buffer,
            basis_offsets,
            len(basis),
            mode,
            outcomes,
            len(self.structures),
        )
        if written < 0:
            message = library.course_prerequisite_last_error()
            raise ValueError(
                message.decode() if message else "native prerequisite evaluation failed"
            )
        if written != len(self.structures):
            raise ValueError("native prerequisite evaluation returned a different structure count")
        return tuple(
            NativeOutcome(
                compilation=self.structures[index],
                has_outcome=bool(outcomes[index].has_outcome),
                required_coverage=(
                    None
                    if outcomes[index].required_coverage < 0
                    else outcomes[index].required_coverage
                ),
                recommended_coverage=(
                    None
                    if outcomes[index].recommended_coverage < 0
                    else outcomes[index].recommended_coverage
                ),
            )
            for index in range(written)
        )

    def close(self) -> None:
        """Free the native bundle after the request finishes evaluating it."""
        if self._pointer:
            self._library.course_prerequisite_free_bundle(self._pointer)
            self._pointer = 0


def _library_path() -> Path:
    return administration.repository_root() / "native" / "libcourse_prerequisite.so"


def _configure(library: ctypes.CDLL) -> Callable[[], int]:
    library.course_prerequisite_version.restype = ctypes.c_int32
    library.course_prerequisite_open.restype = ctypes.c_int
    library.course_prerequisite_open.argtypes = [ctypes.c_char_p]
    library.course_prerequisite_close.argtypes = [ctypes.c_int]
    library.course_prerequisite_compile_bundle.restype = ctypes.c_void_p
    library.course_prerequisite_compile_bundle.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int,
        ctypes.c_int32,
        ctypes.c_int,
    ]
    library.course_prerequisite_structures.restype = ctypes.POINTER(_Structure)
    library.course_prerequisite_structures.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int32),
    ]
    library.course_prerequisite_free_bundle.argtypes = [ctypes.c_void_p]
    library.course_prerequisite_last_error.restype = ctypes.c_char_p
    library.course_prerequisite_evaluate.restype = ctypes.c_int
    library.course_prerequisite_evaluate.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(_NativeOutcome),
        ctypes.c_int,
    ]
    return library.course_prerequisite_version


def _load() -> ctypes.CDLL:
    return native_library.load(_library_path(), FORMAT_VERSION, _configure)


def _blob(values: tuple[str, ...]) -> tuple[ctypes.Array, ctypes.Array]:
    data = b""
    offsets = [0]
    for value in values:
        data += value.encode()
        offsets.append(len(data))
    return ctypes.create_string_buffer(data), (ctypes.c_int64 * len(offsets))(*offsets)


def _materialize(
    pointer: int, *, lightweight: bool, library: ctypes.CDLL | None = None
) -> NativeBundle:
    native = library or _load()
    if not pointer:
        message = native.course_prerequisite_last_error()
        raise ValueError(message.decode() if message else "native prerequisite compile failed")
    try:
        count = ctypes.c_int32(0)
        records = native.course_prerequisite_structures(pointer, ctypes.byref(count))
        if not records and count.value:
            raise ValueError("native prerequisite bundle returned no structure records")
        retained = tuple(records[index] for index in range(count.value))
        materializer = _materialize_summary if lightweight else _materialize_structure
        structures = tuple(materializer(record) for record in retained)
        return NativeBundle(pointer, retained, structures, native)
    except BaseException:
        native.course_prerequisite_free_bundle(pointer)
        raise


def compile_direct_many(
    handle: int,
    candidates: tuple[str, ...],
    retained: tuple[str, ...],
    *,
    active_only: bool,
    include_inferred: bool = False,
) -> NativeBundle:
    """Compile only the candidates' own direct options, without course ancestors."""
    return _compile(
        handle,
        candidates,
        retained,
        active_only=active_only,
        include_recommended=True,
        include_inferred=include_inferred,
        direct_only=True,
        excluded=(),
        completed=(),
        excluded_keys=(),
        lightweight=True,
        project=False,
    )


def _compile(
    handle: int,
    targets: tuple[str, ...],
    retained: tuple[str, ...],
    *,
    active_only: bool,
    include_recommended: bool,
    include_inferred: bool,
    direct_only: bool,
    excluded: tuple[str, ...],
    completed: tuple[str, ...],
    excluded_keys: tuple[str, ...],
    lightweight: bool = False,
    project: bool = True,
) -> NativeBundle:
    """Compile one request while holding the worker's native lock."""
    with _NATIVE_LOCK:
        library = _load()
        target_buffer, target_offsets = _blob(targets)
        retained_buffer, retained_offsets = _blob(retained)
        excluded_buffer, excluded_offsets = _blob(excluded)
        completed_buffer, completed_offsets = _blob(completed)
        keys_buffer, keys_offsets = _blob(excluded_keys)
        pointer = library.course_prerequisite_compile_bundle(
            handle,
            target_buffer,
            target_offsets,
            len(targets),
            retained_buffer,
            retained_offsets,
            len(retained),
            1 if active_only else 0,
            1 if include_recommended else 0,
            1 if include_inferred else 0,
            1 if direct_only else 0,
            excluded_buffer,
            excluded_offsets,
            len(excluded),
            completed_buffer,
            completed_offsets,
            len(completed),
            keys_buffer,
            keys_offsets,
            len(excluded_keys),
            1 if lightweight else 0,
            1 if project else 0,
        )
        return _materialize(pointer, lightweight=lightweight)


def compile_graph(
    handle: int,
    target: str,
    *,
    include_recommended: bool,
    include_inferred: bool,
    active_only: bool,
    retained: tuple[str, ...],
    excluded: tuple[str, ...] = (),
    completed: tuple[str, ...] = (),
    excluded_keys: tuple[str, ...] = (),
    max_drawing_elements: int | None = None,
    include_display: bool = True,
):
    """Compile one target and materialize its permitted drawing graph."""
    bundle = _compile(
        handle,
        (target,),
        retained,
        active_only=active_only,
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        direct_only=False,
        excluded=excluded,
        completed=completed,
        excluded_keys=excluded_keys,
    )
    try:
        compilation = cast("DirectPrerequisiteCompilation", bundle.structures[0])
        return _projection(
            bundle._records[0],
            compilation.solver,
            max_drawing_elements=max_drawing_elements,
            include_display=include_display,
        )
    finally:
        bundle.close()


def close_compilations(
    compilations: Sequence[DirectPrerequisiteCompilation | DirectPrerequisiteSummaryCompilation],
) -> None:
    """Free the request-local native bundle shared by one direct candidate array."""
    if not compilations:
        return
    bundle = compilations[0].native_bundle
    if bundle is not None:
        bundle.close()
