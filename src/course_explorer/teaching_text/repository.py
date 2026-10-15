"""Persistence seam for provenance-aware derived teaching-text translations.

This is the sole writer and reader for `derived_course_texts`. It validates every input against
the selected representative's current official same-field source text before any database write,
computes the persisted source hash itself, and reconciles rows transactionally. It never
touches official `course_versions` names or `course_texts`.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.curriculum import CatalogueRepresentativeTeachingText
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import (
    CourseVersion,
    DerivedCourseText,
)
from course_explorer.db.session import session_scope
from course_explorer.teaching_text.service import (
    DerivedTranslation,
    DerivedTranslationInput,
    DerivedTranslationRead,
    TranslationImportReport,
    TranslationKey,
    official_teaching_text,
    teaching_text_sha256,
    translation_key,
)


def _prepare_inputs(
    inputs: tuple[DerivedTranslationInput, ...],
    representatives: dict[str, CatalogueRepresentativeTeachingText],
) -> tuple[tuple[DerivedTranslationInput, str], ...]:
    """Validate every input against official text and return it with its source hash.

    The whole batch is prepared before any database write, so one invalid entry leaves no rows.
    """
    prepared: list[tuple[DerivedTranslationInput, str]] = []
    seen: set[TranslationKey] = set()
    for item in inputs:
        key = translation_key(item.sisu_course_unit_id, item.field, item.language)
        if key in seen:
            raise ValueError(
                "duplicate translation input for "
                f"{item.sisu_course_unit_id}/{item.field}/{item.language}"
            )
        seen.add(key)
        representative = representatives.get(item.sisu_course_unit_id)
        if representative is None:
            raise ValueError(
                f"{item.sisu_course_unit_id} is not a selected representative course version"
            )
        if official_teaching_text(representative, item.field, item.language) is not None:
            raise ValueError(
                f"{item.sisu_course_unit_id}/{item.field}/{item.language} already has official text"
            )
        source = official_teaching_text(representative, item.field, item.source_language)
        if source is None:
            raise ValueError(
                f"{item.sisu_course_unit_id}/{item.field}/{item.source_language} "
                "has no official source text"
            )
        if source != item.source_text:
            raise ValueError(
                f"{item.sisu_course_unit_id}/{item.field} source text does not match official text"
            )
        prepared.append((item, teaching_text_sha256(item.source_text)))
    return tuple(prepared)


def _translation_values(item: DerivedTranslationInput, source_hash: str) -> dict[str, Any]:
    """Return the exact mutable derived-row column mapping for one prepared input."""
    return {
        "text": item.text,
        "source_language": item.source_language,
        "source_text_hash": source_hash,
        "translation_method": item.translation_method,
        "translation_model": item.translation_model,
        "generated_at": item.generated_at,
    }


class DerivedTranslationRepository(DerivedTranslationRead):
    """Validate, upsert, and read derived translations through one transaction seam."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list_for_course_versions(
        self, sisu_course_unit_ids: Collection[str]
    ) -> tuple[DerivedTranslation, ...]:
        """Return detached derived rows for the requested source IDs in stable order."""
        source_ids = tuple(sisu_course_unit_ids)
        if not source_ids:
            return ()
        with self._factory() as session:
            rows = session.execute(
                select(DerivedCourseText, CourseVersion.sisu_course_unit_id)
                .join(CourseVersion, CourseVersion.id == DerivedCourseText.course_version_id)
                .where(CourseVersion.sisu_course_unit_id.in_(source_ids))
                .order_by(
                    CourseVersion.sisu_course_unit_id,
                    DerivedCourseText.field,
                    DerivedCourseText.language,
                )
            )
            return tuple(
                DerivedTranslation(
                    sisu_course_unit_id=sisu_course_unit_id,
                    field=row.field,
                    language=row.language,
                    source_language=row.source_language,
                    source_text_hash=row.source_text_hash,
                    text=row.text,
                    translation_method=row.translation_method,
                    generated_at=row.generated_at,
                    translation_model=row.translation_model,
                )
                for row, sisu_course_unit_id in rows
            )

    def upsert(self, translations: Sequence[DerivedTranslationInput]) -> TranslationImportReport:
        """Validate inputs against official text and reconcile rows in one transaction."""
        inputs = tuple(translations)
        if not inputs:
            return TranslationImportReport(
                requested_count=0,
                inserted_count=0,
                updated_count=0,
                unchanged_count=0,
            )
        representatives: dict[str, CatalogueRepresentativeTeachingText] = {
            representative.sisu_course_unit_id: representative
            for representative in CurriculumRepository(
                self._factory
            ).get_representative_teaching_texts(tuple(item.sisu_course_unit_id for item in inputs))
        }
        prepared = _prepare_inputs(inputs, representatives)

        inserted = 0
        updated = 0
        unchanged = 0
        with session_scope(self._factory) as session:
            versions = {
                sisu_course_unit_id: version_id
                for sisu_course_unit_id, version_id in session.execute(
                    select(CourseVersion.sisu_course_unit_id, CourseVersion.id).where(
                        CourseVersion.sisu_course_unit_id.in_(
                            tuple(item.sisu_course_unit_id for item, _ in prepared)
                        )
                    )
                )
            }
            for item, _ in prepared:
                if item.sisu_course_unit_id not in versions:
                    raise ValueError(
                        f"selected representative course version {item.sisu_course_unit_id} is missing"
                    )
            version_ids = tuple(versions.values())
            existing = {
                (row.course_version_id, row.field, row.language): row
                for row in session.scalars(
                    select(DerivedCourseText).where(
                        DerivedCourseText.course_version_id.in_(version_ids)
                    )
                )
            }
            for item, source_hash in prepared:
                version_id = versions[item.sisu_course_unit_id]
                row = existing.get((version_id, item.field, item.language))
                values = _translation_values(item, source_hash)
                if row is None:
                    session.add(
                        DerivedCourseText(
                            course_version_id=version_id,
                            field=item.field,
                            language=item.language,
                            **values,
                        )
                    )
                    inserted += 1
                    continue
                if all(getattr(row, name) == value for name, value in values.items()):
                    unchanged += 1
                    continue
                for name, value in values.items():
                    setattr(row, name, value)
                updated += 1
            session.flush()
        return TranslationImportReport(
            requested_count=len(prepared),
            inserted_count=inserted,
            updated_count=updated,
            unchanged_count=unchanged,
        )
