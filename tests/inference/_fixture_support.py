"""Shared synthetic inference settings, run/evidence builders, and digest fixtures.

This support module owns the inference settings plus execution/run-spec builders the evidence tests
share, the empty completion result with its descriptor and fact builders, the final inferred-store
row-count helper, and the labelled fixture digest every inference fixture module reuses. It builds
its values from the composed mapping.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import func, select

from course_explorer.config import InferenceSettings
from course_explorer.db.models import (
    InferredEquivalenceGroup,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.inference.context import (
    RequestCourseDescriptor,
    RequestCourseDescriptors,
)
from course_explorer.inference.domain import (
    InferenceRoutingMetadata,
    InferenceTargetResultV2,
)
from course_explorer.inference.evidence import (
    InferenceCompletionFacts,
    InferenceExecutionProfile,
    InferencePipelineRunSpec,
)
from course_explorer.inference.routing import local_execution
from tests.support import settings_factory


def fixture_sha256(seed: str) -> str:
    """Return one deterministic lowercase 64-character digest for a labelled fixture value."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def inference_settings(**overrides: Any) -> InferenceSettings:
    """Build one otherwise valid inference settings object for identity tests."""
    return settings_factory(InferenceSettings, **overrides)


def execution_profile(settings: InferenceSettings | None = None) -> InferenceExecutionProfile:
    """Build one local execution profile from the selected first fit key."""
    resolved = settings if settings is not None else inference_settings()
    return local_execution(resolved, resolved.inference_local_variants[0])


def run_spec(
    settings: InferenceSettings | None = None,
    *,
    execution: InferenceExecutionProfile | None = None,
) -> InferencePipelineRunSpec:
    """Derive one shared execution spec from the validated settings and execution profile."""
    resolved = settings if settings is not None else inference_settings()
    return InferencePipelineRunSpec.from_contracts(
        resolved,
        execution=execution if execution is not None else execution_profile(resolved),
    )


def _empty_result() -> InferenceTargetResultV2:
    """Build one complete target result with no finding."""
    return InferenceTargetResultV2(
        required=(),
        recommended=(),
        equivalence=(),
        routing=InferenceRoutingMetadata(confidence=0.5, flags=(), suppressed=()),
    )


def _descriptors(target_group_id: str) -> RequestCourseDescriptors:
    """Build one completion's target descriptors with no candidate."""
    return RequestCourseDescriptors(
        target=RequestCourseDescriptor(
            group_id=target_group_id,
            course_code="TARGET.1",
            representative_source_sha256="a" * 64,
        ),
        candidates=(),
    )


def _facts() -> InferenceCompletionFacts:
    """Build one completion's teaching-text identity over no candidate."""
    return InferenceCompletionFacts(target_teaching_text_sha256="b" * 64, candidate_count=0)


def final_store_counts(factory: object) -> tuple[int, int]:
    """Return current inferred-set and equivalence-group row counts."""
    with session_scope(factory) as session:
        return (
            session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)),
            session.scalar(select(func.count()).select_from(InferredEquivalenceGroup)),
        )
