"""Shared fixtures for the target-pass and routing contract tests.

These helpers build strict label-free packets and the real identity/execution inputs so the real
renderer, identity, route-budgeted writer and router run without a model or worker. Database-backed
writer proofs seed their packet target through ``_scheduling_support`` and use the shared HTTP boundary.
"""

from __future__ import annotations

import json

from course_explorer.config import InferenceSettings
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)
from course_explorer.inference.context import (
    InferenceCandidatePacket,
    InferenceCourseEmbeddingIdentity,
    InferenceCourseReference,
    InferencePacketCourse,
    InferencePacketText,
    InferenceSelectionReferences,
    InferenceTargetPacket,
    processing_text_sha256,
    selection_references_sha256,
)
from course_explorer.inference.evidence import InferenceExecutionProfile
from course_explorer.inference.operational import OperationalTargetInput
from course_explorer.inference.routing import local_execution
from tests.inference._fixture_support import fixture_sha256 as _text_sha
from tests.support import settings_factory

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
POOL_DEPTH = 1000
TARGET_GROUP_ID = "tut-cu-g-99999"
TARGET_CODE = "TARGET.1"


def target_settings() -> InferenceSettings:
    """Build one v9/v2 settings object from the composed public mapping."""
    return settings_factory(InferenceSettings)


def execution_profile(
    settings: InferenceSettings | None = None, *, variant_index: int = 0
) -> InferenceExecutionProfile:
    """Build one local execution profile from the selected configured key."""
    resolved = settings if settings is not None else target_settings()
    return local_execution(resolved, resolved.inference_local_variants[variant_index])


def _cell(field: TeachingTextField, text: str) -> InferencePacketText:
    digest = _text_sha(text)
    return InferencePacketText(
        field=field,
        language=TeachingTextLanguage.FI,
        text=text,
        origin=TeachingTextOrigin.OFFICIAL,
        text_sha256=digest,
        source_text_sha256=digest,
    )


def packet_course(group_id: str, code: str, body: str) -> InferencePacketCourse:
    return InferencePacketCourse(
        identity=InferenceCourseEmbeddingIdentity(
            group_id=group_id,
            sisu_course_unit_id=f"source-{group_id}",
            representative_source_sha256=_text_sha(f"source-{group_id}"),
        ),
        course_code=code,
        is_active=True,
        activity_as_of_academic_year_start=2026,
        activity_window_years=3,
        texts=(
            _cell(TeachingTextField.NAME, f"name {group_id}"),
            _cell(TeachingTextField.CONTENT, body),
        ),
    )


def target_packet(count: int = POOL_DEPTH) -> InferenceTargetPacket:
    target = packet_course(TARGET_GROUP_ID, TARGET_CODE, "target body")
    candidates = tuple(
        InferenceCandidatePacket(
            course=packet_course(f"cand-{index:04d}", f"COMP.C.{index:04d}", f"body {index}")
        )
        for index in range(1, count + 1)
    )
    return InferenceTargetPacket(
        packet_version="v1",
        target=target,
        candidates=candidates,
        embedding_configuration_sha256=HASH_E,
    )


def _reference(course: InferencePacketCourse) -> InferenceCourseReference:
    return InferenceCourseReference(
        group_id=course.identity.group_id,
        sisu_course_unit_id=course.identity.sisu_course_unit_id,
        representative_source_sha256=course.identity.representative_source_sha256,
        teaching_text_sha256=processing_text_sha256(
            tuple((cell.field.value, cell.language.value, cell.text) for cell in course.texts)
        ),
    )


def _references(packet: InferenceTargetPacket) -> InferenceSelectionReferences:
    return InferenceSelectionReferences(
        target=_reference(packet.target),
        candidates=tuple(_reference(candidate.course) for candidate in packet.candidates),
    )


def operational_input(packet: InferenceTargetPacket | None = None) -> OperationalTargetInput:
    """Build one CE-only operational carrier bound to the exact 50-candidate selection digest."""
    resolved = packet if packet is not None else target_packet(50)
    references = _references(resolved)
    return OperationalTargetInput(
        references=references,
        packet_sha256=selection_references_sha256(references),
    )


def empty_result_json() -> str:
    return json.dumps(
        {
            "required": [],
            "recommended": [],
            "equivalence": [],
            "routing": {"confidence": 0.5, "flags": [], "suppressed": []},
        }
    )
