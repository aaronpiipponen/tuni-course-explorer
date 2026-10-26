"""Product-owned label-free candidate-selection and cross-encoder scoring kernel.

The kernel projects the represented-course identities, fuses one target's all-field ranking with
each configured field view by reciprocal rank, renders bounded label-free teaching text, and scores
the query/document pairs in input order. The caller supplies the already-computed all-field ranking
and the pairs to score. The renderer writes one code line and then one ``field/language: text`` line
per effective cell in canonical field-then-language order, and truncates once to the given character
bound. ``FINAL_CANDIDATE_MAX`` caps the selected packet, and the accepted pool depth comes from the
validated selection settings.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from course_explorer.curriculum import CatalogueCourse, CatalogueTeachingCourse
from course_explorer.enums import TeachingTextField
from course_explorer.http_retry import RequestNotStarted
from course_explorer.inference.context import (
    InferenceCourseEmbeddingIdentity,
    InferenceMultiviewCandidate,
    InferencePacketCourse,
    InferenceRankedCandidate,
    fuse_candidate_views,
)
from course_explorer.inference.context_repository import InferenceCandidateRepository
from course_explorer.inference.provider import RerankProvider
from course_explorer.validation import require_text as _require_nonblank

# The one hard maximum the whole-target packet may carry. The configured accepted pool depth is a
# validated selection setting and is independent of this product ceiling.
FINAL_CANDIDATE_MAX = 50


class _SelectionModel(BaseModel):
    """Frozen, closed, strict DTO base for the label-free rendering/pair contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def render_rerank_course_text(
    course: InferencePacketCourse,
    *,
    max_characters: int,
) -> str:
    """Render one packet course into bounded label-free teaching text.

    Only the course code and the effective teaching cells are read. The renderer writes one code
    line, then one ``field/language: text`` line per effective cell, joins the lines with newlines,
    and truncates once to the first ``max_characters`` Python characters. The cells arrive in the
    effective-text producer's canonical field-then-language order, and both the query and the
    document use this renderer.
    """
    lines = [f"code: {course.course_code}"]
    for cell in course.texts:
        lines.append(f"{cell.field.value}/{cell.language.value}: {cell.text}")
    return "\n".join(lines)[:max_characters]


class InferenceRerankPair(_SelectionModel):
    """One label-free query/document pair for a single cross-encoder request."""

    target_group_id: str
    candidate_group_id: str
    query: str
    document: str

    @field_validator("target_group_id", "candidate_group_id", "query", "document")
    @classmethod
    def validate_pair_text(cls, value: str) -> str:
        """Require meaningful nonblank pair identities and rendered text."""
        return _require_nonblank(value, "rerank pair value")


class InferenceScoredCandidate(_SelectionModel):
    """One scored candidate in its original input order."""

    candidate_group_id: str
    saved_pool_position: int = Field(ge=1)
    score: float = Field(allow_inf_nan=False)

    @field_validator("candidate_group_id")
    @classmethod
    def validate_candidate_id(cls, value: str) -> str:
        """Require the meaningful canonical candidate identity."""
        return _require_nonblank(value, "rerank candidate id")


def represented_identities(
    courses: Sequence[CatalogueCourse | CatalogueTeachingCourse],
) -> tuple[InferenceCourseEmbeddingIdentity, ...]:
    """Build the exact current represented-course identity tuple once per batch.

    The projection is identical for every caller: the canonical group ID, the current
    representative's source unit, and its source hash, skipping unrepresented courses. It reads
    only those three values.
    """
    return tuple(
        InferenceCourseEmbeddingIdentity(
            group_id=course.group_id,
            sisu_course_unit_id=course.representative.sisu_course_unit_id,
            representative_source_sha256=course.representative.source_hash,
        )
        for course in courses
        if course.representative is not None
    )


def rank_multiview_pool(
    repository: InferenceCandidateRepository,
    target_identity: InferenceCourseEmbeddingIdentity,
    *,
    represented_courses: tuple[InferenceCourseEmbeddingIdentity, ...],
    embedding_hash: str,
    evaluation_fields: tuple[TeachingTextField, ...],
    rank_offset: int,
    unfiltered: tuple[InferenceRankedCandidate, ...],
) -> tuple[InferenceMultiviewCandidate, ...]:
    """Fuse one target's all-field ranking with each configured field view.

    The caller supplies the already-computed all-field ``unfiltered`` ranking, which the repository
    was queried for once. This helper queries each configured field view exactly once and fuses that
    ranking with those views by the configured rank offset. A field view that surfaces nothing (for
    example a target without a compatible chunk in one field) contributes no synthetic rank.
    """
    views: list[tuple[TeachingTextField | None, tuple[InferenceRankedCandidate, ...]]] = [
        (None, unfiltered)
    ]
    for field in evaluation_fields:
        views.append(
            (
                field,
                repository.rank_candidates(
                    target_identity,
                    represented_courses=represented_courses,
                    embedding_configuration_hash=embedding_hash,
                    target_field=field,
                ),
            )
        )
    return fuse_candidate_views(tuple(views), rank_offset=rank_offset)


def score_rerank_pairs(
    pairs: tuple[InferenceRerankPair, ...],
    scorer: RerankProvider,
    *,
    before_request: Callable[[], bool] | None = None,
) -> tuple[tuple[InferenceScoredCandidate, ...], tuple[str, ...]]:
    """Score every label-free pair once in input order and return the deterministic ranking.

    Returns the scored candidates in input order and the complete ranking of unique
    candidate group IDs (score descending, then input position, then candidate id). Any transport,
    HTTP, or contract failure propagates immediately so an incomplete score set can never be
    reported as a full result. It is the one scoring/order core used by the operating path.

    ``before_request`` is the pure live-control admission callback checked before each pair. A
    refusal raises the fixed content-free :class:`RequestNotStarted` and never returns a partial
    ranking. The provider checks ``before_request`` again before its single POST.
    """
    scored: list[InferenceScoredCandidate] = []
    for position, pair in enumerate(pairs, start=1):
        if before_request is not None and not before_request():
            raise RequestNotStarted("rerank request not started")
        result = scorer.score(pair.query, pair.document)
        scored.append(
            InferenceScoredCandidate(
                candidate_group_id=pair.candidate_group_id,
                saved_pool_position=position,
                score=result.score,
            )
        )
    ranked = tuple(
        candidate.candidate_group_id
        for candidate in sorted(
            scored,
            key=lambda candidate: (
                -candidate.score,
                candidate.saved_pool_position,
                candidate.candidate_group_id,
            ),
        )
    )
    return tuple(scored), ranked
