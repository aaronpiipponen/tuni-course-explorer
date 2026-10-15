"""Strict label-free candidate-context identity, matching, fusion, and packet contracts.

This module owns the retained inference-side candidate-context boundary: one immutable per-course
teaching identity used as a retrieval key, provenance-complete matched-chunk evidence, the
label-free multiview fusion helper, and the strict target/candidate packet DTOs with their canonical
digests. Packets and their hashes contain only effective teaching text and provenance. Official
prerequisite structure and every label-derived rank/score/unmeasurable value are absent, so they
can never enter a packet, candidate-query input, prompt example, or model input. Canonical digests
all come from the neutral ``course_explorer.hashing`` owner, so no second JSON/SHA-256
dialect exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from course_explorer.curriculum import CatalogueCourse, CatalogueTeachingCourse
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)
from course_explorer.hashing import canonical_json_sha256
from course_explorer.inference.domain import (
    InferenceTargetResultV2,
    validate_target_result_acceptance,
)
from course_explorer.inference.failures import TargetSelectionError
from course_explorer.prerequisite._helpers import _unique_ids
from course_explorer.teaching_text.service import (
    EffectiveCourseTeachingText,
    EffectiveTeachingTextCatalogue,
)
from course_explorer.validation import (
    require_sha256 as _require_sha256,
)
from course_explorer.validation import (
    require_text as _require_text,
)

_CANONICAL_FIELD_ORDER: tuple[TeachingTextField, ...] = tuple(TeachingTextField)
_VALID_FIELDS = frozenset(field.value for field in TeachingTextField)
_VALID_LANGUAGES = frozenset(language.value for language in TeachingTextLanguage)


class _PacketModel(BaseModel):
    """Frozen, closed, strict DTO base for the candidate-context contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class InferenceCourseEmbeddingIdentity(_PacketModel):
    """One exact current course/representative identity used as a candidate retrieval key."""

    group_id: str
    sisu_course_unit_id: str
    representative_source_sha256: str

    @field_validator("group_id", "sisu_course_unit_id")
    @classmethod
    def validate_identity_text(cls, value: str) -> str:
        """Require meaningful canonical and exact source identities."""
        return _require_text(value, "course embedding identity")

    @field_validator("representative_source_sha256")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        """Require the exact representative source digest."""
        return _require_sha256(value, "representative_source_sha256")


class InferenceMatchedChunk(_PacketModel):
    """One exact teaching chunk provenances behind a candidate/target cosine match."""

    field: TeachingTextField
    language: TeachingTextLanguage
    chunk_index: int = Field(ge=0)
    text_origin: TeachingTextOrigin
    chunk_text_sha256: str

    @field_validator("chunk_text_sha256")
    @classmethod
    def validate_chunk_hash(cls, value: str) -> str:
        """Require the exact matched chunk-text digest."""
        return _require_sha256(value, "chunk_text_sha256")


class InferenceCandidateMatch(_PacketModel):
    """One exact target-chunk/candidate-chunk cosine match with complete provenance."""

    course: InferenceCourseEmbeddingIdentity
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    target_chunk: InferenceMatchedChunk
    candidate_chunk: InferenceMatchedChunk


class InferenceRankedCandidate(_PacketModel):
    """One candidate match at its deterministic contiguous score-descending rank."""

    rank: int = Field(gt=0)
    match: InferenceCandidateMatch


class InferenceMultiviewCandidate(_PacketModel):
    """One course-level fused multiview candidate with its per-view reciprocal ranks.

    ``fusion_score`` is the sum of ``1 / (rank_offset + view_rank)`` over the views that actually
    surfaced the candidate. It is a distinct score. ``match`` is copied from
    the all-field ranking, so the canonical cosine score and matched-chunk provenance remain the
    source of truth. No official label or label-derived value can appear here.
    """

    rank: int = Field(gt=0)
    match: InferenceCandidateMatch
    fusion_score: float = Field(ge=0, allow_inf_nan=False)
    view_ranks: tuple[tuple[TeachingTextField | None, int], ...]

    @model_validator(mode="after")
    def validate_view_ranks(self) -> InferenceMultiviewCandidate:
        """Require canonical ordered unique view keys with positive contiguous source ranks."""
        keys = tuple(key for key, _ in self.view_ranks)
        if not keys:
            raise ValueError("a fused multiview candidate requires at least one view rank")
        _unique_ids(keys, "multiview candidate view keys")
        ordered = tuple(
            sorted(
                keys,
                key=lambda field: (
                    0 if field is None else 1,
                    _CANONICAL_FIELD_ORDER.index(field) if field is not None else 0,
                ),
            )
        )
        if keys != ordered:
            raise ValueError(
                "multiview candidate view keys must be all-field first then canonical field order"
            )
        for _, view_rank in self.view_ranks:
            if isinstance(view_rank, bool) or not isinstance(view_rank, int) or view_rank < 1:
                raise ValueError("multiview candidate view ranks must be positive integers")
        return self


def fuse_candidate_views(
    views: tuple[tuple[TeachingTextField | None, tuple[InferenceRankedCandidate, ...]], ...],
    *,
    rank_offset: int,
) -> tuple[InferenceMultiviewCandidate, ...]:
    """Fuse all-field plus configured field views into one deterministic label-blind ranking.

    The caller supplies the all-field ranking first followed by each configured field view. Every
    source ranking must carry contiguous one-based ranks, unique group identities, and the exact
    score-descending/group-id ordering the repository produces. All views must cover the same
    candidate universe so a missing candidate is a real miss rather than a differently bounded
    view. A view with no entries (for example a target without a compatible chunk in one field)
    contributes no synthetic rank even when the all-field ranking is nonempty.

    Fusion is the sum of ``1 / (rank_offset + view_rank)`` over the views that actually surfaced
    each group. Ties are broken by candidate group ID only. Official labels, official structure,
    baseline label ranks, and any measured recall never influence selection or tie-breaking.
    """
    if isinstance(rank_offset, bool) or not isinstance(rank_offset, int) or rank_offset < 1:
        raise ValueError("rank_offset must be a positive integer")
    if not views:
        raise ValueError("multiview fusion requires the all-field ranking")
    keys = tuple(key for key, _ in views)
    _unique_ids(keys, "multiview fusion view keys")
    if keys[0] is not None:
        raise ValueError("multiview fusion requires the all-field ranking first")
    field_keys = keys[1:]
    if tuple(sorted(field_keys, key=_CANONICAL_FIELD_ORDER.index)) != field_keys:
        raise ValueError("multiview fusion field keys must follow canonical field order")

    all_field_matches: dict[str, InferenceCandidateMatch] = {}
    all_field_group_ids: tuple[str, ...] = ()
    for index, (key, ranked) in enumerate(views):
        if key is not None and not isinstance(key, TeachingTextField):
            raise ValueError("multiview fusion field keys must be TeachingTextField or None")
        ranks = tuple(candidate.rank for candidate in ranked)
        if ranks != tuple(range(1, len(ranks) + 1)):
            raise ValueError("multiview source ranks must be contiguous one-based ascending")
        group_ids = tuple(candidate.match.course.group_id for candidate in ranked)
        _unique_ids(group_ids, "multiview source candidate identities")
        ordered = tuple(
            sorted(
                ranked,
                key=lambda candidate: (-candidate.match.score, candidate.match.course.group_id),
            )
        )
        if ranked != ordered:
            raise ValueError(
                "multiview source candidates must be score-descending then group-id ascending"
            )
        if index == 0:
            all_field_group_ids = group_ids
            all_field_matches = {
                candidate.match.course.group_id: candidate.match for candidate in ranked
            }
            continue
        # A field with no completed compatible target chunk contributes no entries. The
        # all-field identity validation above already proved the target itself is measurable.
        if not group_ids:
            continue
        # Field rankings order by their own field score, so only the candidate universe must
        # match. Each candidate must carry the identical course identity from the all-field
        # ranking.
        if set(group_ids) != set(all_field_group_ids):
            raise TargetSelectionError("incomplete_views")
        for candidate in ranked:
            all_field_match = all_field_matches[candidate.match.course.group_id]
            if candidate.match.course != all_field_match.course:
                raise ValueError(
                    "a candidate must carry the identical course identity in every field view"
                )

    fused: dict[str, float] = {}
    view_ranks_by_group: dict[str, list[tuple[TeachingTextField | None, int]]] = {}
    for key, ranked in views:
        for candidate in ranked:
            group_id = candidate.match.course.group_id
            fused[group_id] = fused.get(group_id, 0.0) + 1.0 / (rank_offset + candidate.rank)
            view_ranks_by_group.setdefault(group_id, []).append((key, candidate.rank))

    ordered_group_ids = sorted(fused, key=lambda group_id: (-fused[group_id], group_id))
    return tuple(
        InferenceMultiviewCandidate(
            rank=rank,
            match=all_field_matches[group_id],
            fusion_score=fused[group_id],
            view_ranks=tuple(view_ranks_by_group[group_id]),
        )
        for rank, group_id in enumerate(ordered_group_ids, start=1)
    )


class InferencePacketText(_PacketModel):
    """One effective teaching-text cell copied verbatim with its origin and hashes.

    The effective-text producer already guarantees canonical field/language order and exact
    text/source digests, so this transient packet cell copies them without re-hashing or
    re-ordering them.
    """

    field: TeachingTextField
    language: TeachingTextLanguage
    text: str
    origin: TeachingTextOrigin
    text_sha256: str
    source_text_sha256: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Require meaningful effective teaching text."""
        return _require_text(value, "packet text")

    @field_validator("text_sha256", "source_text_sha256")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        """Require exact effective and source text digests."""
        return _require_sha256(value, "packet text hash")


class InferencePacketCourse(_PacketModel):
    """One label-free packet course: identity, activity, and effective teaching cells."""

    identity: InferenceCourseEmbeddingIdentity
    course_code: str
    is_active: bool
    activity_as_of_academic_year_start: int = Field(gt=0)
    activity_window_years: int = Field(gt=0)
    texts: tuple[InferencePacketText, ...]

    @field_validator("course_code")
    @classmethod
    def validate_course_code(cls, value: str) -> str:
        """Require one meaningful official course code."""
        return _require_text(value, "packet course_code")


class InferenceCandidatePacket(_PacketModel):
    """One label-free candidate packet entry carrying only its packet course.

    The assembler proves each match identity against the current catalogue and then discards the
    retrieval provenance and per-course source digest, so no stored candidate keeps text-derived
    hashes or match metadata.
    """

    course: InferencePacketCourse


class InferenceTargetPacket(_PacketModel):
    """One strict label-free target packet: target plus its complete ranked candidate context.

    This DTO and every nested packet DTO carry no official prerequisite structure:
    no field can hold a target's official options, and none is ever hashed into it.
    """

    packet_version: Literal["v1"]
    target: InferencePacketCourse
    candidates: tuple[InferenceCandidatePacket, ...]
    embedding_configuration_sha256: str

    @field_validator("embedding_configuration_sha256")
    @classmethod
    def validate_hashes(cls, value: str) -> str:
        """Require the exact embedding-configuration digest."""
        return _require_sha256(value, "target packet hash")

    @model_validator(mode="after")
    def validate_packet_shape(self) -> InferenceTargetPacket:
        """Require a nonempty candidate context with unique identities and no self-candidate.

        Candidate rank is this tuple's order, which the assembler copies from the caller's
        deterministic rank: single-view score-descending/group-id query ordering or the
        equivalent-order multiview fused pool, never a stored rank field.
        """
        identities = tuple(candidate.course.identity for candidate in self.candidates)
        _unique_ids(identities, "packet candidate identities")
        if self.target.identity in identities:
            raise ValueError("the target course must not also be a packet candidate")
        return self


class InferenceCourseReference(_PacketModel):
    """One exact current course/representative reference for stored selection and work identity.

    It carries only the canonical group identity, the current representative's source unit and
    source digest, and the text-only teaching digest. Teaching text itself is in the
    effective-text owner and the transient request packet.
    """

    group_id: str
    sisu_course_unit_id: str
    representative_source_sha256: str
    teaching_text_sha256: str

    @field_validator("group_id", "sisu_course_unit_id")
    @classmethod
    def validate_identity_text(cls, value: str) -> str:
        """Require meaningful canonical and exact source identities."""
        return _require_text(value, "course reference identity")

    @field_validator("representative_source_sha256", "teaching_text_sha256")
    @classmethod
    def validate_reference_hashes(cls, value: str) -> str:
        """Require exact representative-source and teaching-text digests."""
        return _require_sha256(value, "course reference hash")


class InferenceSelectionReferences(_PacketModel):
    """One target's compact ordered selection: target plus exact ranked candidate references."""

    target: InferenceCourseReference
    candidates: tuple[InferenceCourseReference, ...]


def selection_references_sha256(value: InferenceSelectionReferences) -> str:
    """Hash the compact ordered selection references exactly as canonical JSON."""
    return canonical_json_sha256(value.model_dump(mode="json"))


class RequestCourseDescriptor(_PacketModel):
    """One resolved label-free request course descriptor: identity, code, and source digest."""

    group_id: str
    course_code: str
    representative_source_sha256: str

    @field_validator("group_id", "course_code")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        """Require a meaningful canonical identity or displayed code."""
        return _require_text(value, "request course descriptor")

    @field_validator("representative_source_sha256")
    @classmethod
    def validate_source_sha256(cls, value: str) -> str:
        """Require the exact representative source digest."""
        return _require_sha256(value, "request descriptor representative_source_sha256")


class RequestCourseDescriptors(_PacketModel):
    """The resolved target and ordered candidate descriptors of one target request."""

    target: RequestCourseDescriptor
    candidates: tuple[RequestCourseDescriptor, ...]

    @model_validator(mode="after")
    def validate_unique_identities(self) -> RequestCourseDescriptors:
        """Require unique canonical group IDs and representative source digests."""
        descriptors = (self.target, *self.candidates)
        group_ids = [descriptor.group_id for descriptor in descriptors]
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("request descriptors must not repeat a canonical group ID")
        source_hashes = [descriptor.representative_source_sha256 for descriptor in descriptors]
        if len(set(source_hashes)) != len(source_hashes):
            raise ValueError("request descriptors must not repeat a representative source digest")
        return self


def request_descriptors_from_packet(packet: InferenceTargetPacket) -> RequestCourseDescriptors:
    """Project one transient target packet's target and ordered candidate descriptors.

    It reads the current code/group/source fields directly and never parses a saved prompt.
    """

    def descriptor(course: InferencePacketCourse) -> RequestCourseDescriptor:
        return RequestCourseDescriptor(
            group_id=course.identity.group_id,
            course_code=course.course_code,
            representative_source_sha256=course.identity.representative_source_sha256,
        )

    return RequestCourseDescriptors(
        target=descriptor(packet.target),
        candidates=tuple(descriptor(candidate.course) for candidate in packet.candidates),
    )


def resolve_result_codes(
    result: InferenceTargetResultV2, descriptors: RequestCourseDescriptors
) -> dict[str, str]:
    """Resolve one untrusted result's codes through its request descriptors and accept it.

    It builds the code/group map once from the descriptors and delegates to the one shared
    acceptance owner, so no second acceptance implementation exists.
    """
    groups_by_code: dict[str, set[str]] = {}
    for descriptor in (descriptors.target, *descriptors.candidates):
        groups_by_code.setdefault(descriptor.course_code, set()).add(descriptor.group_id)
    return validate_target_result_acceptance(
        result,
        target_group_id=descriptors.target.group_id,
        course_groups_by_code={code: frozenset(groups) for code, groups in groups_by_code.items()},
    )


def processing_text_sha256(cells: Sequence[tuple[str, str, str]]) -> str:
    """Hash the exact effective teaching-text cells with no provenance or metadata.

    Every cell is an exact ``(field, language, text)`` triple over a known field/language with
    nonblank text. A field/language pair may appear at most once. The cells are sorted and hashed as
    a JSON object list, so an empty input hashes the real empty cell list rather than a fabricated
    teaching text. Course code, source ID/hash, origin, translation provenance, year/activity,
    generator configuration, and official prerequisites are absent.
    """
    triples = tuple(cells)
    seen: set[tuple[str, str]] = set()
    for cell in triples:
        if not isinstance(cell, tuple) or len(cell) != 3:
            raise ValueError("processing text cells must be (field, language, text) triples")
        field, language, text = cell
        if field not in _VALID_FIELDS:
            raise ValueError("processing text field must be a known teaching-text field")
        if language not in _VALID_LANGUAGES:
            raise ValueError("processing text language must be a known teaching-text language")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("processing text must be a nonblank string")
        key = (field, language)
        if key in seen:
            raise ValueError("processing text cells must be unique per field and language")
        seen.add(key)
    ordered = sorted(triples, key=lambda cell: (cell[0], cell[1], cell[2]))
    return canonical_json_sha256(
        {
            "cells": [
                {"field": field, "language": language, "text": text}
                for field, language, text in ordered
            ]
        }
    )


def catalogue_identity_sha256(
    courses: Sequence[CatalogueCourse | CatalogueTeachingCourse],
    effective: EffectiveTeachingTextCatalogue,
    *,
    embedding_configuration_hash: str,
) -> str:
    """Hash canonical identity/activity/effective-text evidence plus the compatible embedding hash.

    The identity covers canonical group/representative/source, activity context, and each
    effective cell's field/language/origin/text+source hashes, so it changes exactly when
    candidate context could change. It excludes official prerequisite labels/text.
    """
    _require_sha256(embedding_configuration_hash, "embedding_configuration_hash")
    effective_by_group = {course.group_id: course for course in effective.courses}
    payload: list[dict[str, object]] = []
    for course in sorted(courses, key=lambda item: item.group_id):
        cells = effective_by_group.get(course.group_id)
        representative = course.representative
        payload.append(
            {
                "group_id": course.group_id,
                "is_active": course.is_active,
                "activity_as_of_academic_year_start": course.activity_as_of_academic_year_start,
                "activity_window_years": course.activity_window_years,
                "sisu_course_unit_id": (
                    None if representative is None else representative.sisu_course_unit_id
                ),
                "representative_source_hash": (
                    None if representative is None else representative.source_hash
                ),
                "effective_texts": (
                    []
                    if cells is None
                    else [
                        {
                            "field": cell.field.value,
                            "language": cell.language.value,
                            "origin": cell.origin.value,
                            "text_hash": cell.text_hash,
                            "source_text_hash": cell.source_text_hash,
                        }
                        for cell in cells.texts
                    ]
                ),
            }
        )
    return canonical_json_sha256(
        {"embedding_configuration_sha256": embedding_configuration_hash, "courses": payload}
    )


def _packet_course(
    course: CatalogueCourse | CatalogueTeachingCourse,
    effective: EffectiveCourseTeachingText,
) -> InferencePacketCourse:
    """Map one canonical course plus its effective cells into one label-free packet course."""
    representative = course.representative
    if representative is None:
        raise ValueError(f"packet course {course.group_id} has no selected representative")
    return InferencePacketCourse(
        identity=InferenceCourseEmbeddingIdentity(
            group_id=course.group_id,
            sisu_course_unit_id=representative.sisu_course_unit_id,
            representative_source_sha256=representative.source_hash,
        ),
        course_code=representative.code,
        is_active=course.is_active,
        activity_as_of_academic_year_start=course.activity_as_of_academic_year_start,
        activity_window_years=course.activity_window_years,
        texts=tuple(
            InferencePacketText(
                field=cell.field,
                language=cell.language,
                text=cell.text,
                origin=cell.origin,
                text_sha256=cell.text_hash,
                source_text_sha256=cell.source_text_hash,
            )
            for cell in effective.texts
        ),
    )


def _course_reference(
    course: CatalogueCourse | CatalogueTeachingCourse,
    effective: EffectiveCourseTeachingText,
) -> InferenceCourseReference:
    """Map one canonical course plus its effective cells into one compact selection reference."""
    representative = course.representative
    if representative is None:
        raise ValueError(f"course reference {course.group_id} has no selected representative")
    return InferenceCourseReference(
        group_id=course.group_id,
        sisu_course_unit_id=representative.sisu_course_unit_id,
        representative_source_sha256=representative.source_hash,
        teaching_text_sha256=processing_text_sha256(
            tuple((cell.field.value, cell.language.value, cell.text) for cell in effective.texts)
        ),
    )
