"""Operational label-free CE-only selection and the reusable route-neutral complete-target call.

This module is the operating path's owner of the decision-independent target pipeline: it reads the
current curriculum and effective teaching text once per batch into one frozen catalogue carrier,
selects one target's K1000 multiview pool, scores the exact K1000 label-free packet with the
cross-encoder, and reduces it to the accepted CE-only top-50 packet. It binds the complete selection
(packet digest, score/order digest, rerank model/runtime/input settings, and selection policy) into
one canonical identity so a snapshot rebuild, changed candidate text/embedding, changed selection
mechanics, or changed rerank runtime invalidates stale work rather than reusing it. It reads no
official prerequisite structure, hidden label, saved development pool, or hardcoded development
target ID, and it never rereads the full catalogue inside the per-target function.

:func:`run_operational_target` reuses the one route-budgeted claim/validate/write path in
``target_pass`` rather than forking a second evidence route for any execution route. No production
model, prompt, or routing policy is selected here. The caller supplies the validated execution
profile.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from course_explorer.config import (
    EmbeddingSettings,
    InferenceContextSettings,
    InferenceRerankInputSettings,
    InferenceRerankSettings,
    InferenceSelectionSettings,
    InferenceSettings,
)
from course_explorer.curriculum import CatalogueCourse, CatalogueTeachingCourse, CurriculumRead
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.enums import TeachingTextField
from course_explorer.inference.context import (
    InferenceCandidatePacket,
    InferenceCourseEmbeddingIdentity,
    InferenceCourseReference,
    InferencePacketCourse,
    InferenceSelectionReferences,
    InferenceTargetPacket,
    _course_reference,
    _packet_course,
    catalogue_identity_sha256,
    selection_references_sha256,
)
from course_explorer.inference.context_repository import InferenceCandidateRepository
from course_explorer.inference.evidence import (
    InferenceExecutionProfile,
    InferenceTargetWorkRecord,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.failures import TargetSelectionError
from course_explorer.inference.operational_selection import (
    FINAL_CANDIDATE_MAX,
    InferenceRerankPair,
    rank_multiview_pool,
    render_rerank_course_text,
    represented_identities,
    score_rerank_pairs,
)
from course_explorer.inference.prompts import PromptPack
from course_explorer.inference.provider import RerankProvider
from course_explorer.inference.target_pass import TargetGenerationProvider, run_target
from course_explorer.teaching_text.service import (
    EffectiveCourseTeachingText,
    EffectiveTeachingTextCatalogue,
    TeachingTextService,
)
from course_explorer.validation import (
    require_sha256 as _require_sha256,
)

if TYPE_CHECKING:
    from course_explorer.inference.scheduling import ProcessingTargetRecord, TargetFailureRecord
    from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository


class _OperationalModel(BaseModel):
    """Frozen, closed, strict DTO base for the operational selection contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class OperationalCatalogue(_OperationalModel):
    """One once-per-batch catalogue carrier for the operational target pipeline.

    It holds the current canonical courses, their effective teaching text, the exact represented
    identity universe, and the two bound snapshot identities. A caller builds it once per batch
    boundary and reuses it across every target. No per-target function rereads the catalogue. It
    contains official prerequisite structure only inside the canonical course models, and no
    selector reads that structure while building model inputs.
    """

    courses_by_group: Mapping[str, CatalogueCourse | CatalogueTeachingCourse]
    effective_by_group: Mapping[str, EffectiveCourseTeachingText]
    teaching_text_catalogue: EffectiveTeachingTextCatalogue
    represented_courses: tuple[InferenceCourseEmbeddingIdentity, ...]
    catalogue_identity_sha256: str
    embedding_configuration_sha256: str

    @model_validator(mode="after")
    def validate_catalogue_shape(self) -> OperationalCatalogue:
        """Require digest-bound identities, unique represented courses, and covered courses."""
        _require_sha256(self.catalogue_identity_sha256, "catalogue_identity_sha256")
        _require_sha256(self.embedding_configuration_sha256, "embedding_configuration_sha256")
        identities = tuple(self.represented_courses)
        if len(set(identities)) != len(identities):
            raise ValueError("operational catalogue represented identities must be unique")
        if set(self.teaching_text_catalogue.canonical_group_ids) != set(self.courses_by_group):
            raise ValueError(
                "operational catalogue teaching text catalogue must cover the canonical courses"
            )
        catalogue_groups = {course.group_id for course in self.teaching_text_catalogue.courses}
        if catalogue_groups != set(self.effective_by_group):
            raise ValueError(
                "operational catalogue effective text must match the resolved teaching catalogue"
            )
        represented_keys = {
            group_id
            for group_id, course in self.courses_by_group.items()
            if course.representative is not None
        }
        if set(self.effective_by_group) != represented_keys:
            raise ValueError(
                "operational catalogue effective text must cover exactly represented courses"
            )
        if {identity.group_id for identity in identities} != represented_keys:
            raise ValueError(
                "operational catalogue represented identities must cover represented courses"
            )
        for identity in identities:
            course = self.courses_by_group[identity.group_id]
            representative = course.representative
            if representative is None or (
                representative.sisu_course_unit_id != identity.sisu_course_unit_id
                or representative.source_hash != identity.representative_source_sha256
            ):
                raise ValueError(
                    f"operational catalogue identity for {identity.group_id} is inconsistent"
                )
        return self


def prepare_operational_catalogue(
    curriculum: CurriculumRead,
    teaching_text: TeachingTextService,
    embedding_settings: EmbeddingSettings,
) -> OperationalCatalogue:
    """Read the current catalogue and effective text once and derive both bound identities.

    This is the only operational catalogue read. It lists every course (active or not) because
    inactive courses remain valid candidate prerequisite sources, builds the effective-text
    catalogue once, derives the compatible embedding configuration hash, and hashes the canonical
    identity/activity/effective-text evidence. Official prerequisite fields are never read here.
    Only the canonical course and its representative identity are carried.
    """
    courses = curriculum.list_teaching_courses(active_only=None)
    teaching_text_catalogue = teaching_text.build_catalogue(courses=courses)
    embedding_hash = embedding_configuration_sha256(embedding_settings)
    catalogue_identity = catalogue_identity_sha256(
        courses, teaching_text_catalogue, embedding_configuration_hash=embedding_hash
    )
    return OperationalCatalogue(
        courses_by_group={course.group_id: course for course in courses},
        effective_by_group={course.group_id: course for course in teaching_text_catalogue.courses},
        teaching_text_catalogue=teaching_text_catalogue,
        represented_courses=represented_identities(courses),
        catalogue_identity_sha256=catalogue_identity,
        embedding_configuration_sha256=embedding_hash,
    )


class OperationalPoolInput(_OperationalModel):
    """One complete label-free multiview pool bound to its exact compact ordered references.

    ``references`` is the full configured multiview pool (the accepted K1000 depth) as ordered course
    references. ``pool_sha256`` is its canonical reference digest. The configured pool depth is a
    validated selection setting enforced by the selector, never a constant here.
    """

    references: InferenceSelectionReferences
    pool_sha256: str

    @property
    def target_group_id(self) -> str:
        """Expose the target group id as a nonserialized property of the target reference."""
        return self.references.target.group_id

    @field_validator("pool_sha256")
    @classmethod
    def validate_pool_sha256(cls, value: str) -> str:
        return _require_sha256(value, "operational pool_sha256")


class OperationalTargetInput(_OperationalModel):
    """One complete CE-only target selection bound to its exact compact ordered references.

    ``references`` is the accepted CE-only top-50 selection as ordered course references and
    ``packet_sha256`` is its canonical reference digest. The selection producer enforces the final
    candidate count, so a partially built or stale selection can never reach the evidence path.
    """

    references: InferenceSelectionReferences
    packet_sha256: str

    @property
    def target_group_id(self) -> str:
        """Expose the target group id as a nonserialized property of the target reference."""
        return self.references.target.group_id

    @field_validator("packet_sha256")
    @classmethod
    def validate_packet_sha256(cls, value: str) -> str:
        return _require_sha256(value, "operational packet_sha256")


def materialize_selection_packet(
    references: InferenceSelectionReferences, catalogue: OperationalCatalogue
) -> InferenceTargetPacket:
    """Resolve compact ordered references back into one transient label-free target packet.

    It resolves ids through the already-prepared mappings and ``_packet_course``, preserving order
    and teaching origins with no SQL/model/retrieval call. Missing current ids fail naturally. The
    job's coarse entry-time check owns compatibility, so no per-reference revalidation is repeated.
    """

    def course(reference: InferenceCourseReference) -> InferencePacketCourse:
        candidate_course = catalogue.courses_by_group.get(reference.group_id)
        if candidate_course is None:
            raise ValueError(f"reference {reference.group_id} is not in the current catalogue")
        effective = catalogue.effective_by_group.get(reference.group_id)
        if effective is None:
            raise ValueError(f"reference {reference.group_id} has no effective teaching text")
        return _packet_course(candidate_course, effective)

    return InferenceTargetPacket(
        packet_version="v1",
        target=course(references.target),
        candidates=tuple(
            InferenceCandidatePacket(course=course(reference))
            for reference in references.candidates
        ),
        embedding_configuration_sha256=catalogue.embedding_configuration_sha256,
    )


def select_operational_multiview_pool(
    catalogue: OperationalCatalogue,
    target_group_id: str,
    candidate_repository: InferenceCandidateRepository,
    *,
    selection: InferenceSelectionSettings,
    context_settings: InferenceContextSettings,
) -> OperationalPoolInput:
    """Select one target's accepted full multiview pool from the current live identities.

    The target must be a current active represented course with a compatible embedding. Field views
    are ranked once through the shared multiview helper, the exact configured pool depth is assembled
    into compact ordered references, and the configured depth must be reachable. No saved development
    pool is replayed, no official label or hidden rank is read, and no full catalogue is reread. No
    model call happens here. The cross-encoder rerank is a separate live stage.
    """
    pool_k = selection.inference_selection_pool_k
    target = catalogue.courses_by_group.get(target_group_id)
    if target is None:
        raise ValueError(f"operational target {target_group_id} is not in the current catalogue")
    if not target.is_active or target.representative is None:
        raise ValueError(f"operational target {target_group_id} is not a current active course")
    represented_by_group = {
        identity.group_id: identity for identity in catalogue.represented_courses
    }
    target_identity = represented_by_group.get(target_group_id)
    if target_identity is None:
        raise ValueError(f"operational target {target_group_id} has no represented identity")

    evaluation_fields = tuple(
        TeachingTextField(field) for field in context_settings.inference_multiview_evaluation_fields
    )
    unfiltered = candidate_repository.rank_candidates(
        target_identity,
        represented_courses=catalogue.represented_courses,
        embedding_configuration_hash=catalogue.embedding_configuration_sha256,
    )
    fused = rank_multiview_pool(
        candidate_repository,
        target_identity,
        represented_courses=catalogue.represented_courses,
        embedding_hash=catalogue.embedding_configuration_sha256,
        evaluation_fields=evaluation_fields,
        rank_offset=context_settings.inference_multiview_fusion_rank_offset,
        unfiltered=unfiltered,
    )
    if len(fused) < pool_k:
        raise TargetSelectionError("insufficient_candidates")
    references = InferenceSelectionReferences(
        target=_course_reference(target, catalogue.effective_by_group[target_group_id]),
        candidates=tuple(
            _course_reference(
                catalogue.courses_by_group[entry.match.course.group_id],
                catalogue.effective_by_group[entry.match.course.group_id],
            )
            for entry in fused[:pool_k]
        ),
    )
    return OperationalPoolInput(
        references=references,
        pool_sha256=selection_references_sha256(references),
    )


def rerank_operational_pool(
    value: OperationalPoolInput,
    reranker: RerankProvider,
    *,
    catalogue: OperationalCatalogue,
    selection: InferenceSelectionSettings,
    context_settings: InferenceContextSettings,
    rerank_input: InferenceRerankInputSettings,
    rerank_settings: InferenceRerankSettings,
    before_request: Callable[[], bool] | None = None,
) -> OperationalTargetInput:
    """Score one full multiview pool once and reduce it to the accepted CE-only top-50 selection.

    The configured final count must equal the accepted :data:`FINAL_CANDIDATE_MAX`. A mismatch fails
    loudly instead of selecting a different policy. The pool references are materialized once for
    scoring, every pair is scored once through the shared scoring core, and the complete score-derived
    ranking reduces the pool to its compact ordered references. A declined admission raises the fixed
    :class:`RequestNotStarted` and never yields a partial result.
    """
    final_k = selection.inference_selection_final_k
    if final_k != FINAL_CANDIDATE_MAX:
        raise ValueError(f"the operational CE-only path requires final_k == {FINAL_CANDIDATE_MAX}")
    packet = materialize_selection_packet(value.references, catalogue)
    query = render_rerank_course_text(
        packet.target,
        max_characters=rerank_input.inference_rerank_query_max_characters,
    )
    pairs = tuple(
        InferenceRerankPair(
            target_group_id=value.target_group_id,
            candidate_group_id=candidate.course.identity.group_id,
            query=query,
            document=render_rerank_course_text(
                candidate.course,
                max_characters=rerank_input.inference_rerank_document_max_characters,
            ),
        )
        for candidate in packet.candidates
    )
    _scored, ranked_candidate_group_ids = score_rerank_pairs(
        pairs, reranker, before_request=before_request
    )
    references_by_group = {
        reference.group_id: reference for reference in value.references.candidates
    }
    selected_references = InferenceSelectionReferences(
        target=value.references.target,
        candidates=tuple(
            references_by_group[group_id] for group_id in ranked_candidate_group_ids[:final_k]
        ),
    )
    return OperationalTargetInput(
        references=selected_references,
        packet_sha256=selection_references_sha256(selected_references),
    )


def run_operational_target(
    value: OperationalTargetInput,
    pack: PromptPack,
    settings: InferenceSettings,
    repository: InferenceEvidenceRepository,
    provider: TargetGenerationProvider,
    execution: InferenceExecutionProfile,
    *,
    packet: InferenceTargetPacket,
    scheduling_repository: InferenceSchedulingRepository,
    cycle_id: UUID,
    retry_failed: bool = False,
    before_request: Callable[[], bool] | None = None,
    on_failure: Callable[[ProcessingTargetRecord, TargetFailureRecord], None] | None = None,
) -> InferenceTargetWorkRecord:
    """Run or reuse exactly one complete-target call through the sole evidence path.

    It delegates only to :func:`run_target` for request rendering, claim/retry, schema validation,
    code-boundary check, and immutable completion writer. The transient ``packet`` is the router's
    one materialization. ``target_work_identity`` validates that the pack matches the configured
    prompt version before any request. The supplied execution profile selects the local fit key or
    a caller-injected alternative route, and no catalogue loop or second controller is involved.
    """
    return run_target(
        value,
        pack,
        settings,
        repository,
        provider,
        execution,
        packet=packet,
        scheduling_repository=scheduling_repository,
        cycle_id=cycle_id,
        retry_failed=retry_failed,
        before_request=before_request,
        on_failure=on_failure,
    )
