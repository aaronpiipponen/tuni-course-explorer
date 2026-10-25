"""Deterministic missing-cell selection and resumable translation-only worker.

This module owns the product-neutral contracts that select every missing representative
name/content/outcomes target for all active and inactive canonical courses, translate each
cell from its same-field opposite official source through the one translation provider, and
emit a provenance-complete ``DerivedTranslationInput`` JSON array. A derived cell
is current only when its official source matches and, for MODEL rows, its persisted model
identity equals the configured provenance model. A current-source MANUAL row has no model by
contract and is current.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from course_explorer.administration import atomic_write_private_text
from course_explorer.administration import utc_now as _utc_now
from course_explorer.config import TranslationSettings
from course_explorer.curriculum import CatalogueCourse, CatalogueTeachingCourse, CurriculumRead
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.http_retry import RequestNotStarted
from course_explorer.teaching_text.commands import load_translation_file
from course_explorer.teaching_text.service import (
    DerivedTranslation,
    DerivedTranslationInput,
    DerivedTranslationRead,
    TranslationKey,
    index_derived_translations,
    official_teaching_text,
    teaching_text_sha256,
    translation_key,
)
from course_explorer.translation.provider import (
    TranslationContractError,
    TranslationRequestError,
)

_SAFE_FAILURE_MESSAGE = re.compile(r"^[A-Za-z0-9_ /:().-]+$")
_OPPOSITE_LANGUAGE = {
    TeachingTextLanguage.FI: TeachingTextLanguage.EN,
    TeachingTextLanguage.EN: TeachingTextLanguage.FI,
}


class _TranslationModel(BaseModel):
    """Frozen, closed DTO base for the translation worker contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TranslationWorkItem(_TranslationModel):
    """One official-gap cell that must be translated from its official same-field source."""

    group_id: str
    sisu_course_unit_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    source_language: TeachingTextLanguage
    source_text: str
    source_text_hash: str


class TranslationSelectionCount(_TranslationModel):
    """One field/language cell's four-way partition over selected representatives."""

    field: TeachingTextField
    language: TeachingTextLanguage
    official_target_count: int = Field(ge=0)
    current_derived_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    missing_source_count: int = Field(ge=0)


class TranslationWorkSelection(_TranslationModel):
    """Deterministic translation selection with per-cell counts and ordered pending work."""

    canonical_course_count: int = Field(ge=0)
    representative_course_count: int = Field(ge=0)
    no_representative_course_count: int = Field(ge=0)
    active_representative_count: int = Field(ge=0)
    inactive_representative_count: int = Field(ge=0)
    fields: tuple[TranslationSelectionCount, ...]
    items: tuple[TranslationWorkItem, ...]


class TranslationFailureRecord(_TranslationModel):
    """One deterministic, text-free record of a terminal worker failure.

    The cell tuple is the failure identity and the record type identifies the stage. It carries
    only the safe error class and a short safe reason.
    """

    sisu_course_unit_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    error_type: str
    error_message: str

    @field_validator("sisu_course_unit_id", "error_type", "error_message")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("failure record text values must not be blank")
        return value


class TranslationRunReport(_TranslationModel):
    """One completed worker run's partition counts and output totals, without any text."""

    canonical_course_count: int = Field(ge=0)
    representative_course_count: int = Field(ge=0)
    no_representative_course_count: int = Field(ge=0)
    active_representative_count: int = Field(ge=0)
    inactive_representative_count: int = Field(ge=0)
    fields: tuple[TranslationSelectionCount, ...]
    desired_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    output_count: int = Field(ge=0)


class TranslationTextProvider(Protocol):
    """Provider boundary consumed by the worker for one same-field source-cell translation."""

    def translate(
        self,
        text: str,
        *,
        source_language: TeachingTextLanguage,
        target_language: TeachingTextLanguage,
    ) -> str: ...


def _safe_failure_message(exc: Exception) -> str:
    """Keep only short fixed-shape provider text. Otherwise return the exception class name."""
    if isinstance(exc, (TranslationRequestError, TranslationContractError)):
        message = str(exc)
        if (
            1 <= len(message) <= 200
            and message.isascii()
            and _SAFE_FAILURE_MESSAGE.fullmatch(message) is not None
        ):
            return message
    return type(exc).__name__


def _selection_counts() -> dict[tuple[TeachingTextField, TeachingTextLanguage], dict[str, int]]:
    return {
        (field, language): {
            "official_target": 0,
            "current_derived": 0,
            "pending": 0,
            "missing_source": 0,
        }
        for field in TeachingTextField
        for language in TeachingTextLanguage
    }


def _collect_course_work(
    course: CatalogueCourse | CatalogueTeachingCourse,
    derived_by_key: dict[TranslationKey, DerivedTranslation],
    *,
    provenance_model: str,
    counts: dict[tuple[TeachingTextField, TeachingTextLanguage], dict[str, int]],
) -> tuple[tuple[TranslationWorkItem, ...], tuple[TranslationWorkItem, ...]]:
    """Classify one course's six cells, returning all candidates and the pending subset.

    An unrepresented course returns two empty tuples. Official targets, absent opposite
    same-field sources, current manual/current-model rows, stale sources and changed models
    classify exactly as the selector contract requires. Stored rows are never modified.
    """
    version = course.representative
    if version is None:
        return (), ()
    candidates: list[TranslationWorkItem] = []
    pending: list[TranslationWorkItem] = []
    for field in TeachingTextField:
        for language in TeachingTextLanguage:
            if official_teaching_text(version, field, language) is not None:
                counts[(field, language)]["official_target"] += 1
                continue
            source_language = _OPPOSITE_LANGUAGE[language]
            source_text = official_teaching_text(version, field, source_language)
            if source_text is None:
                counts[(field, language)]["missing_source"] += 1
                continue
            item = TranslationWorkItem(
                group_id=course.group_id,
                sisu_course_unit_id=version.sisu_course_unit_id,
                field=field,
                language=language,
                source_language=source_language,
                source_text=source_text,
                source_text_hash=teaching_text_sha256(source_text),
            )
            candidates.append(item)
            existing = derived_by_key.get(
                translation_key(version.sisu_course_unit_id, field, language)
            )
            if (
                existing is not None
                and existing.source_language is source_language
                and existing.source_text_hash == item.source_text_hash
                and (
                    existing.translation_method is TranslationMethod.MANUAL
                    or existing.translation_model == provenance_model
                )
            ):
                counts[(field, language)]["current_derived"] += 1
            else:
                counts[(field, language)]["pending"] += 1
                pending.append(item)
    return tuple(candidates), tuple(pending)


def _collect_translation_work(
    courses: Sequence[CatalogueCourse | CatalogueTeachingCourse],
    translations: DerivedTranslationRead,
    *,
    provenance_model: str,
    course_limit: int | None,
) -> tuple[TranslationWorkSelection, tuple[TranslationWorkItem, ...]]:
    """Partition every selected representative cell and return candidates in stable order.

    A derived cell is current only when its source language and exact source hash match and it
    is either a current-source MANUAL row (no model by contract) or a MODEL row whose persisted
    ``translation_model`` equals ``provenance_model``. A MODEL row from a different configured
    model is requeued as pending. Selection never overwrites or deletes stored rows.
    """
    if course_limit is not None:
        courses = courses[:course_limit]
    representative_ids = tuple(
        course.representative.sisu_course_unit_id
        for course in courses
        if course.representative is not None
    )
    derived = translations.list_for_course_versions(representative_ids)
    derived_by_key = index_derived_translations(derived)

    counts = _selection_counts()
    candidates: list[TranslationWorkItem] = []
    pending: list[TranslationWorkItem] = []
    active_representative_count = 0
    for course in courses:
        if course.representative is None:
            continue
        if course.is_active:
            active_representative_count += 1
        course_candidates, course_pending = _collect_course_work(
            course, derived_by_key, provenance_model=provenance_model, counts=counts
        )
        candidates.extend(course_candidates)
        pending.extend(course_pending)

    representative_course_count = len(representative_ids)
    selection = TranslationWorkSelection(
        canonical_course_count=len(courses),
        representative_course_count=representative_course_count,
        no_representative_course_count=len(courses) - representative_course_count,
        active_representative_count=active_representative_count,
        inactive_representative_count=representative_course_count - active_representative_count,
        fields=tuple(
            TranslationSelectionCount(
                field=field,
                language=language,
                official_target_count=counts[(field, language)]["official_target"],
                current_derived_count=counts[(field, language)]["current_derived"],
                pending_count=counts[(field, language)]["pending"],
                missing_source_count=counts[(field, language)]["missing_source"],
            )
            for field in TeachingTextField
            for language in TeachingTextLanguage
        ),
        items=tuple(pending),
    )
    return selection, tuple(candidates)


def _collect(
    curriculum: CurriculumRead,
    translations: DerivedTranslationRead,
    settings: TranslationSettings,
    *,
    course_limit: int | None,
) -> tuple[TranslationWorkSelection, tuple[TranslationWorkItem, ...]]:
    """Read all courses once and partition their representative cells in stable order."""
    courses = curriculum.list_teaching_courses(active_only=None)
    return _collect_translation_work(
        courses,
        translations,
        provenance_model=settings.provenance_model,
        course_limit=course_limit,
    )


def select_translation_work(
    curriculum: CurriculumRead,
    translations: DerivedTranslationRead,
    settings: TranslationSettings,
    *,
    course_limit: int | None = None,
) -> TranslationWorkSelection:
    """Partition representative cells and queue missing or invalidated same-field gaps.

    A matching-source derived cell is current only when it is a current-source MANUAL row or a
    MODEL row produced by ``settings.provenance_model``. A MODEL row not produced by ``settings.provenance_model`` is requeued without
    being modified.
    """
    if course_limit is not None and course_limit <= 0:
        raise ValueError("course_limit must be positive or None")
    selection, _ = _collect(curriculum, translations, settings, course_limit=course_limit)
    return selection


def _entries_json(entries: Sequence[DerivedTranslationInput]) -> str:
    return (
        json.dumps(
            [entry.model_dump(mode="json") for entry in entries],
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def _load_retained_output(output_path: Path) -> dict[TranslationKey, DerivedTranslationInput]:
    """Load retained output entries by key, or return empty when the output is absent."""
    if not output_path.exists():
        return {}
    retained: dict[TranslationKey, DerivedTranslationInput] = {}
    for entry in load_translation_file(output_path):
        key = translation_key(entry.sisu_course_unit_id, entry.field, entry.language)
        if key in retained:
            raise ValueError(
                "duplicate retained output entry for "
                f"{entry.sisu_course_unit_id}/{entry.field}/{entry.language}"
            )
        retained[key] = entry
    return retained


class TranslationWorkerService:
    """One idempotent, resumable worker over selected gap cells and the sole provider."""

    def __init__(
        self,
        curriculum: CurriculumRead,
        translations: DerivedTranslationRead,
        provider: TranslationTextProvider,
        settings: TranslationSettings,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._curriculum = curriculum
        self._translations = translations
        self._provider = provider
        self._settings = settings
        self._clock = clock

    def _validate_retained(
        self,
        retained: dict[TranslationKey, DerivedTranslationInput],
        candidates: dict[TranslationKey, TranslationWorkItem],
    ) -> None:
        for key, entry in retained.items():
            candidate = candidates.get(key)
            if candidate is None:
                raise ValueError(
                    "retained output is not an official-gap candidate in the selected scope: "
                    f"{entry.sisu_course_unit_id}/{entry.field}/{entry.language}"
                )
            if (
                entry.source_language is not candidate.source_language
                or entry.source_text != candidate.source_text
            ):
                raise ValueError(
                    "retained output source language or text no longer matches the official source: "
                    f"{entry.sisu_course_unit_id}/{entry.field}/{entry.language}"
                )
            if entry.translation_method is not TranslationMethod.MODEL:
                raise ValueError(
                    "retained output must be a model translation: "
                    f"{entry.sisu_course_unit_id}/{entry.field}/{entry.language}"
                )
            if entry.translation_model != self._settings.provenance_model:
                raise ValueError(
                    "retained output was produced by a different translation model: "
                    f"{entry.sisu_course_unit_id}/{entry.field}/{entry.language}"
                )

    def _write_failure(self, sidecar: Path, item: TranslationWorkItem, exc: Exception) -> None:
        record = TranslationFailureRecord(
            sisu_course_unit_id=item.sisu_course_unit_id,
            field=item.field,
            language=item.language,
            error_type=type(exc).__name__,
            error_message=_safe_failure_message(exc),
        )
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        atomic_write_private_text(sidecar, payload)

    def _translate_item(self, item: TranslationWorkItem, sidecar: Path) -> DerivedTranslationInput:
        """Translate one item, publishing a terminal safe sidecar for a real provider failure.

        ``RequestNotStarted`` is a cooperative refusal and is re-raised without a sidecar. Any
        other provider exception records the sidecar and re-raises.
        """
        try:
            text = self._provider.translate(
                item.source_text,
                source_language=item.source_language,
                target_language=item.language,
            )
        except RequestNotStarted:
            raise
        except Exception as exc:
            self._write_failure(sidecar, item, exc)
            raise
        return DerivedTranslationInput(
            sisu_course_unit_id=item.sisu_course_unit_id,
            field=item.field,
            language=item.language,
            source_language=item.source_language,
            source_text=item.source_text,
            text=text,
            translation_method=TranslationMethod.MODEL,
            translation_model=self._settings.provenance_model,
            generated_at=self._clock(),
        )

    def run(
        self,
        *,
        output_path: Path,
        course_limit: int | None = None,
        before_pending_item: Callable[[], bool] | None = None,
        on_checkpoint: Callable[[int], None] | None = None,
    ) -> TranslationRunReport:
        """Translate pending gaps, checkpoint each success, and return text-free counts.

        ``before_pending_item`` is consulted immediately before provider I/O for each
        item without retained text. Returning ``False`` ends the run normally without calling
        the provider for that item or subsequent items. ``on_checkpoint`` runs only after a
        success has been atomically published and its matching failure sidecar removed,
        with the number of output entries retained. Neither callback fires for
        retained or completed entries, and the default ``None`` preserves the
        caller contract.
        """
        if course_limit is not None and course_limit <= 0:
            raise ValueError("course_limit must be positive or None")
        if output_path.exists() and output_path.is_dir():
            raise ValueError("output_path must name a file, not a directory")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar = output_path.with_name(output_path.name + ".failure.json")

        selection, ordered_candidates = _collect(
            self._curriculum, self._translations, self._settings, course_limit=course_limit
        )
        candidates = {
            translation_key(item.sisu_course_unit_id, item.field, item.language): item
            for item in ordered_candidates
        }
        order = [
            translation_key(item.sisu_course_unit_id, item.field, item.language)
            for item in ordered_candidates
        ]

        retained = _load_retained_output(output_path)
        self._validate_retained(retained, candidates)

        output: dict[TranslationKey, DerivedTranslationInput] = dict(retained)
        generated_count = 0
        for item in selection.items:
            key = translation_key(item.sisu_course_unit_id, item.field, item.language)
            if key in output:
                continue
            if before_pending_item is not None and not before_pending_item():
                break
            try:
                entry = self._translate_item(item, sidecar)
            except RequestNotStarted:
                # A pause/stop refusal ends the run at this durable boundary. The retained
                # output is the partial report and no failure sidecar is fabricated.
                break
            output[key] = entry
            generated_count += 1
            atomic_write_private_text(
                output_path,
                _entries_json(
                    [output[candidate_key] for candidate_key in order if candidate_key in output]
                ),
            )
            sidecar.unlink(missing_ok=True)
            if on_checkpoint is not None:
                on_checkpoint(len(output))

        reused_count = len(retained)
        output_count = len(output)
        return TranslationRunReport(
            canonical_course_count=selection.canonical_course_count,
            representative_course_count=selection.representative_course_count,
            no_representative_course_count=selection.no_representative_course_count,
            active_representative_count=selection.active_representative_count,
            inactive_representative_count=selection.inactive_representative_count,
            fields=selection.fields,
            desired_count=reused_count + generated_count,
            reused_count=reused_count,
            generated_count=generated_count,
            output_count=output_count,
        )
