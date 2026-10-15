"""Effective teaching-text resolution over official and separately derived translations.

This module owns the product-neutral contract for derived teaching text and the deterministic
resolution of per-field, per-language effective text. Official source text always wins. A derived
translation is usable only while its recorded source hash matches the current same-field
official source text. Stale derived rows are reported, never silently used or deleted. Prerequisite
and additional-information text never participate here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueCourseVersion,
    CatalogueRepresentativeTeachingText,
    CatalogueTeachingCourse,
    CatalogueTeachingTextInput,
    CurriculumRead,
)
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)
from course_explorer.validation import require_aware, require_sha256


def _method_model_consistent(
    translation_method: TranslationMethod, translation_model: str | None
) -> None:
    if translation_method is TranslationMethod.MANUAL:
        if translation_model is not None:
            raise ValueError("manual translations must not record a translation model")
        return
    if translation_model is None or not translation_model.strip():
        raise ValueError("model translations require a nonblank translation model")


class _TeachingTextModel(BaseModel):
    """Frozen, closed DTO base for the effective-teaching-text contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class _DerivedTranslationModel(_TeachingTextModel):
    """Shared validation for both derived-translation wire DTOs.

    Fieldless so each concrete DTO keeps its own field declaration order and defaults. The
    field validators apply to whichever concrete subclass declares the named field.
    """

    @field_validator("sisu_course_unit_id", check_fields=False)
    @classmethod
    def reject_blank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sisu_course_unit_id must not be blank")
        return value

    @field_validator("text", check_fields=False)
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("generated_at", check_fields=False)
    @classmethod
    def reject_naive_timestamp(cls, value: datetime) -> datetime:
        return require_aware(value, "generated_at")

    @model_validator(mode="after")
    def validate_provenance_relations(self) -> Self:
        if self.source_language is self.language:
            raise ValueError("source and target languages must differ")
        _method_model_consistent(self.translation_method, self.translation_model)
        return self


class DerivedTranslationInput(_DerivedTranslationModel):
    """Operator- or worker-supplied derived translation awaiting persistence."""

    sisu_course_unit_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    source_language: TeachingTextLanguage
    source_text: str
    text: str
    translation_method: TranslationMethod
    generated_at: datetime
    translation_model: str | None = None

    @field_validator("source_text")
    @classmethod
    def reject_blank_source_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_text must not be blank")
        return value


class DerivedTranslation(_DerivedTranslationModel):
    """Persisted derived translation for one course unit, field and language."""

    sisu_course_unit_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    source_language: TeachingTextLanguage
    source_text_hash: str
    text: str
    translation_method: TranslationMethod
    generated_at: datetime
    translation_model: str | None = None

    @field_validator("source_text_hash")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        return require_sha256(value, "hash values")


TranslationKey = tuple[str, TeachingTextField, TeachingTextLanguage]


def translation_key(
    sisu_course_unit_id: str,
    field: TeachingTextField,
    language: TeachingTextLanguage,
) -> TranslationKey:
    """Return one derived translation identity key without normalizing its parts."""
    return (sisu_course_unit_id, field, language)


def index_derived_translations(
    translations: Sequence[DerivedTranslation],
) -> dict[TranslationKey, DerivedTranslation]:
    """Index derived rows by exact identity, refusing ambiguous duplicate keys."""
    by_key: dict[TranslationKey, DerivedTranslation] = {}
    for translation in translations:
        key = translation_key(
            translation.sisu_course_unit_id, translation.field, translation.language
        )
        if key in by_key:
            raise ValueError(
                "duplicate derived translation rows for "
                f"{translation.sisu_course_unit_id}/{translation.field}/{translation.language}"
            )
        by_key[key] = translation
    return by_key


class TranslationImportReport(_TeachingTextModel):
    """Insert, update, or identical outcomes of one validated translation import batch."""

    requested_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)


class EffectiveTeachingText(_TeachingTextModel):
    """One resolved effective field/language cell with its origin and provenance."""

    field: TeachingTextField
    language: TeachingTextLanguage
    text: str
    origin: TeachingTextOrigin
    text_hash: str
    source_text_hash: str
    translation_method: TranslationMethod | None = None
    translation_model: str | None = None
    translation_generated_at: datetime | None = None


class EffectiveCourseTeachingText(_TeachingTextModel):
    """All effective cells for one canonical course's selected representative."""

    group_id: str
    sisu_course_unit_id: str
    representative_source_hash: str
    is_active: bool
    texts: tuple[EffectiveTeachingText, ...]


class StaleDerivedText(_TeachingTextModel):
    """One retained derived row whose recorded source hash differs from official text."""

    group_id: str
    sisu_course_unit_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    source_language: TeachingTextLanguage
    stored_source_text_hash: str
    current_source_text_hash: str | None


class TeachingTextCoverageCount(_TeachingTextModel):
    """Origin classification counts for one field/language cell over representatives."""

    field: TeachingTextField
    language: TeachingTextLanguage
    official_count: int = Field(ge=0)
    derived_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)


class TeachingTextCoverageReport(_TeachingTextModel):
    """Representative-catalogue teaching-text coverage and stale-row inventory."""

    canonical_course_count: int = Field(ge=0)
    representative_course_count: int = Field(ge=0)
    no_representative_course_count: int = Field(ge=0)
    name_only_course_count: int = Field(ge=0)
    unembeddable_course_count: int = Field(ge=0)
    fields: tuple[TeachingTextCoverageCount, ...]
    stale_texts: tuple[StaleDerivedText, ...]
    unrepresented_group_ids: tuple[str, ...] = ()


class EffectiveTeachingTextCatalogue(_TeachingTextModel):
    """Resolved effective teaching text for every representative plus coverage."""

    canonical_group_ids: tuple[str, ...]
    courses: tuple[EffectiveCourseTeachingText, ...]
    coverage: TeachingTextCoverageReport


class DerivedTranslationRead(Protocol):
    """Read boundary for persisted derived translations consumed by the effective service."""

    def list_for_course_versions(
        self, sisu_course_unit_ids: Collection[str]
    ) -> tuple[DerivedTranslation, ...]: ...


def teaching_text_sha256(text: str) -> str:
    """Return the SHA-256 of exact text bytes without normalizing the text."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("cannot hash blank teaching text")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def official_teaching_text(
    version: CatalogueCourseVersion | CatalogueRepresentativeTeachingText,
    field: TeachingTextField,
    language: TeachingTextLanguage,
) -> str | None:
    """Return one nonblank official name/content/outcomes value, ignoring other fields."""
    if field is TeachingTextField.NAME:
        value = version.name_fi if language is TeachingTextLanguage.FI else version.name_en
    elif field is TeachingTextField.CONTENT:
        value = (
            version.teaching_text.content_fi
            if language is TeachingTextLanguage.FI
            else version.teaching_text.content_en
        )
    else:
        value = (
            version.teaching_text.outcomes_fi
            if language is TeachingTextLanguage.FI
            else version.teaching_text.outcomes_en
        )
    if value is None or not value.strip():
        return None
    return value


def _resolve_cell(
    version: CatalogueCourseVersion | CatalogueRepresentativeTeachingText,
    translation: DerivedTranslation | None,
    *,
    field: TeachingTextField,
    language: TeachingTextLanguage,
) -> tuple[
    EffectiveTeachingText | None, Literal["official", "derived", "stale", "missing"], str | None
]:
    """Resolve one field/language cell and classify its origin.

    The third element is the current same-field official source text hash for a stale derived row
    (``None`` when that source is absent). Every non-stale classification returns ``None`` there.
    Official text wins. A derived row is usable only while its recorded source hash matches
    the current same-field official source text.
    """
    official = official_teaching_text(version, field, language)
    if official is not None:
        cell_hash = teaching_text_sha256(official)
        return (
            EffectiveTeachingText(
                field=field,
                language=language,
                text=official,
                origin=TeachingTextOrigin.OFFICIAL,
                text_hash=cell_hash,
                source_text_hash=cell_hash,
            ),
            "official",
            None,
        )
    if translation is None:
        return None, "missing", None
    source = official_teaching_text(version, field, translation.source_language)
    current_hash = None if source is None else teaching_text_sha256(source)
    if current_hash == translation.source_text_hash:
        return (
            EffectiveTeachingText(
                field=field,
                language=language,
                text=translation.text,
                origin=TeachingTextOrigin.DERIVED,
                text_hash=teaching_text_sha256(translation.text),
                source_text_hash=translation.source_text_hash,
                translation_method=translation.translation_method,
                translation_model=translation.translation_model,
                translation_generated_at=translation.generated_at,
            ),
            "derived",
            None,
        )
    return None, "stale", current_hash


def _resolve_representative_cells(
    group_id: str,
    representative: CatalogueRepresentativeTeachingText,
    derived_by_key: dict[TranslationKey, DerivedTranslation],
    counts: dict[tuple[TeachingTextField, TeachingTextLanguage], dict[str, int]],
    stale_texts: list[StaleDerivedText],
) -> tuple[EffectiveTeachingText, ...]:
    """Resolve one represented input's six cells and accumulate its cell/stale counts.

    Called only for represented entries. The caller derives name-only/unembeddable bookkeeping
    from the returned effective cells. ``_resolve_cell`` is the sole per-cell classifier.
    """
    cells: list[EffectiveTeachingText] = []
    for field in TeachingTextField:
        for language in TeachingTextLanguage:
            translation = derived_by_key.get(
                translation_key(representative.sisu_course_unit_id, field, language)
            )
            cell, classification, current_hash = _resolve_cell(
                representative, translation, field=field, language=language
            )
            counts[(field, language)][classification] += 1
            if cell is not None:
                cells.append(cell)
            elif classification == "stale":
                stale_texts.append(
                    StaleDerivedText(
                        group_id=group_id,
                        sisu_course_unit_id=representative.sisu_course_unit_id,
                        field=field,
                        language=language,
                        source_language=translation.source_language,
                        stored_source_text_hash=translation.source_text_hash,
                        current_source_text_hash=current_hash,
                    )
                )
    return tuple(cells)


def _resolve_teaching_inputs(
    inputs: Sequence[CatalogueTeachingTextInput],
    derived: Sequence[DerivedTranslation],
) -> tuple[dict[str, tuple[EffectiveTeachingText, ...]], TeachingTextCoverageReport]:
    """Resolve every input's six cells once and accumulate the shared coverage report.

    This one accumulator owns the unique derived-key check, the six-cell origin counts, the stale
    inventory, and the name-only/unembeddable/unrepresented bookkeeping for both the effective
    catalogue and the projected coverage read. It never materializes a full ``CatalogueCourse``.
    """
    by_key = index_derived_translations(derived)

    counts: dict[tuple[TeachingTextField, TeachingTextLanguage], dict[str, int]] = {
        (field, language): {"official": 0, "derived": 0, "stale": 0, "missing": 0}
        for field in TeachingTextField
        for language in TeachingTextLanguage
    }
    cells_by_group: dict[str, tuple[EffectiveTeachingText, ...]] = {}
    stale_texts: list[StaleDerivedText] = []
    unrepresented_group_ids: list[str] = []
    representative_count = 0
    name_only_count = 0
    unembeddable_count = 0
    for entry in inputs:
        representative = entry.representative
        if representative is None:
            unrepresented_group_ids.append(entry.group_id)
            continue
        representative_count += 1
        cells = _resolve_representative_cells(
            entry.group_id, representative, by_key, counts, stale_texts
        )
        cells_by_group[entry.group_id] = cells
        has_name = any(cell.field is TeachingTextField.NAME for cell in cells)
        has_body = any(cell.field is not TeachingTextField.NAME for cell in cells)
        if has_name and not has_body:
            name_only_count += 1
        if not has_name and not has_body:
            unembeddable_count += 1
    stale_texts.sort(
        key=lambda stale: (
            stale.group_id,
            stale.sisu_course_unit_id,
            stale.field.value,
            stale.language.value,
        )
    )
    coverage = TeachingTextCoverageReport(
        canonical_course_count=len(inputs),
        representative_course_count=representative_count,
        no_representative_course_count=len(unrepresented_group_ids),
        name_only_course_count=name_only_count,
        unembeddable_course_count=unembeddable_count,
        fields=tuple(
            TeachingTextCoverageCount(
                field=field,
                language=language,
                official_count=counts[(field, language)]["official"],
                derived_count=counts[(field, language)]["derived"],
                stale_count=counts[(field, language)]["stale"],
                missing_count=counts[(field, language)]["missing"],
            )
            for field in TeachingTextField
            for language in TeachingTextLanguage
        ),
        stale_texts=tuple(stale_texts),
        unrepresented_group_ids=tuple(unrepresented_group_ids),
    )
    return cells_by_group, coverage


class TeachingTextService:
    """Resolve deterministic effective teaching text over the official read seam."""

    def __init__(self, curriculum: CurriculumRead, translations: DerivedTranslationRead) -> None:
        self._curriculum = curriculum
        self._translations = translations

    def build_catalogue(
        self, *, courses: Sequence[CatalogueCourse | CatalogueTeachingCourse] | None = None
    ) -> EffectiveTeachingTextCatalogue:
        """Resolve every representative cell and report origin/coverage evidence.

        ``courses`` lets one caller that already read the current catalogue reuse that exact
        tuple. The supplied courses go through the identical
        resolver/coverage logic. With the default ``None`` this reads the projected teaching
        catalogue, which carries only the identity, source hash, code, names and teaching text.
        """
        courses = (
            self._curriculum.list_teaching_courses(active_only=None)
            if courses is None
            else tuple(courses)
        )
        representative_ids = tuple(
            course.representative.sisu_course_unit_id
            for course in courses
            if course.representative is not None
        )
        derived = self._translations.list_for_course_versions(representative_ids)
        inputs = tuple(
            CatalogueTeachingTextInput(
                group_id=course.group_id,
                representative=(
                    None
                    if course.representative is None
                    else CatalogueRepresentativeTeachingText(
                        sisu_course_unit_id=course.representative.sisu_course_unit_id,
                        name_fi=course.representative.name_fi,
                        name_en=course.representative.name_en,
                        teaching_text=course.representative.teaching_text,
                    )
                ),
            )
            for course in courses
        )
        cells_by_group, coverage = _resolve_teaching_inputs(inputs, derived)
        effective_courses = tuple(
            EffectiveCourseTeachingText(
                group_id=course.group_id,
                sisu_course_unit_id=course.representative.sisu_course_unit_id,
                representative_source_hash=course.representative.source_hash,
                is_active=course.is_active,
                texts=cells_by_group[course.group_id],
            )
            for course in courses
            if course.representative is not None
        )
        return EffectiveTeachingTextCatalogue(
            canonical_group_ids=tuple(course.group_id for course in courses),
            courses=effective_courses,
            coverage=coverage,
        )

    def coverage(self) -> TeachingTextCoverageReport:
        """Return representative-catalogue teaching-text coverage without full-course reads.

        It reads the narrow projected teaching-text inputs and the derived rows once and shares the
        exact resolution/coverage accumulator with ``build_catalogue``, so its report is identical
        for the same state while no full ``CatalogueCourse`` or ``EffectiveCourseTeachingText`` is
        materialized.
        """
        inputs = self._curriculum.list_teaching_text_inputs()
        representative_ids = tuple(
            entry.representative.sisu_course_unit_id
            for entry in inputs
            if entry.representative is not None
        )
        derived = self._translations.list_for_course_versions(representative_ids)
        _cells, coverage = _resolve_teaching_inputs(inputs, derived)
        return coverage
