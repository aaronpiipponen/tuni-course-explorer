"""Shared synthetic inference settings, run/evidence builders, and digest fixtures.

This support module owns the one embedding configuration used to derive compatible
hashes, the inference settings plus execution/run-spec builders the evidence tests
share, the final inferred-store row-count helper, and the labelled fixture digest every inference
fixture module reuses. It builds its values from the composed mapping.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import func, select

from course_explorer.config import EmbeddingSettings, InferenceSettings
from course_explorer.db.models import (
    InferredEquivalenceGroup,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.inference.evidence import (
    InferenceExecutionProfile,
    InferencePipelineRunSpec,
)
from course_explorer.inference.routing import local_execution
from tests.support import settings_factory

POLICY_SHA256 = "1" * 64
CATALOGUE_SHA256 = "2" * 64


def fixture_sha256(seed: str) -> str:
    """Return one deterministic lowercase 64-character digest for a labelled fixture value."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def embedding_settings() -> EmbeddingSettings:
    """Build the full required embedding configuration used to derive the compatible hash."""
    return settings_factory(
        EmbeddingSettings,
        EMBEDDING_CONTEXT_SIZE=1024,
        EMBEDDING_REQUEST_TIMEOUT_SECONDS=30,
        EMBEDDING_GENERATION_BATCH_SIZE=16,
        EMBEDDING_ARTIFACT_URL="https://example.test/model.gguf",
        EMBEDDING_ARTIFACT_PATH="models/model.gguf",
        EMBEDDING_ARTIFACT_SHA256="a" * 64,
        EMBEDDING_SERVER_IMAGE="ghcr.io/ggml-org/llama.cpp:server@sha256:" + "b" * 64,
        EMBEDDING_RUNTIME_REVISION="c" * 40,
    )


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


def final_store_counts(factory: object) -> tuple[int, int]:
    """Return current inferred-set and equivalence-group row counts."""
    with session_scope(factory) as session:
        return (
            session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)),
            session.scalar(select(func.count()).select_from(InferredEquivalenceGroup)),
        )
