"""Shared test support: committed public configuration values and common fixtures.

This module owns the committed example TOML settings under ``examples/config/`` plus the committed
``examples/.env.example`` template, the alias-keyed settings factory every package settings helper
uses, the shared official catalogue builders and in-memory read double, and the shared
derived-translation read double and DTO fixture builder. Its values come from the committed example
tree and template.
"""

from __future__ import annotations

import functools
import json
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings

from course_explorer import configuration
from course_explorer.configuration import environment_value
from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueCourseVersion,
    CatalogueModuleLookup,
    CatalogueTeachingCourse,
    CatalogueTeachingText,
    CatalogueTeachingTextInput,
    RepresentedCourseSummary,
    course_summary,
)
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.service import (
    DerivedTranslation,
    teaching_text_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = REPO_ROOT / "examples"
_TEMPLATE_PATH = EXAMPLE_ROOT / ".env.example"

HASH_A = "a" * 64
HASH_B = "b" * 64
DIMENSION = 1024
GENERATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

_JSON_ALIASES = (
    "INFERENCE_LOCAL_VARIANTS",
    "INFERENCE_CHAT_TEMPLATE_KWARGS",
    "SEARCH_TIER_PRIORITY",
    "INFERENCE_MULTIVIEW_EVALUATION_FIELDS",
    "EMBEDDING_HUB_VECTOR",
    "EMBEDDING_OUTCOMES_HUB_VECTOR",
)
_SYNTHETIC_VALUES = {
    "POSTGRES_PASSWORD": "local-password",
    "SELECTED_DATASET_ENABLED": "0",
}


@functools.cache
def _declared_base_aliases() -> frozenset[str]:
    """Return every validation alias the base product settings families declare.

    The base settings live in their own package, so a base fixture map carries only base aliases.
    A field
    with no validation alias and a default is a code-owned default.
    """
    from course_explorer import config as base_config

    aliases: set[str] = set()
    for value in vars(base_config).values():
        if isinstance(value, type) and issubclass(value, BaseSettings):
            aliases.update(_aliases(value))
    return frozenset(aliases)


@functools.cache
def public_environment() -> dict[str, str]:
    """Return the cached settings fixture map from the committed example tree and template.

    The committed example TOML values are serialized through the one shared helper so string-valued
    fixtures preserve their form, and the committed ``examples/.env.example`` supplies the
    machine-local placeholder aliases that a fixture must provide. Only aliases a
    base settings family declares are kept. Only the committed example tree and template supply
    values.
    """
    declared = _declared_base_aliases()
    environment = {
        alias: environment_value(value)
        for alias, value in configuration.read_public_configuration(EXAMPLE_ROOT).items()
        if alias in declared
    }
    template = dotenv_values(_TEMPLATE_PATH, encoding="utf-8", interpolate=False)
    environment.update(
        {
            alias: value
            for alias, value in template.items()
            if value is not None and alias in declared
        }
    )
    return environment


def write_example_config_tree(root: Path, *, include_derived: bool = True) -> Path:
    """Materialize the committed example configuration under one temporary root.

    Every registered subsystem ``examples/config/*.toml`` source is copied to ``<root>/config/`` so a
    test can bind the real owner's canonical layout to the actually committed example assets without
    touching the checkout's own configuration. The two generated ``derived/`` hub artifacts are copied
    too unless a caller exercises the hub-less case with ``include_derived=False``.
    """
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    for relative in configuration.PUBLIC_CONFIG_FILES:
        shutil.copyfile(EXAMPLE_ROOT / relative, config / Path(relative).name)
    derived = EXAMPLE_ROOT / "config" / "derived"
    if include_derived and derived.is_dir():
        shutil.copytree(derived, config / "derived")
    return root


def _aliases(settings_type: type[BaseSettings]) -> tuple[str, ...]:
    """Return each required/aliased field's validation alias, defaulting to the field name.

    A field with no validation alias and a default is a code-owned default rather than a missing
    public input, so it is skipped instead of being required from the composed environment.
    """
    aliases: list[str] = []
    for name, field in settings_type.model_fields.items():
        if field.validation_alias is None and not field.is_required():
            continue
        alias = field.validation_alias
        aliases.append(alias if isinstance(alias, str) else name)
    return tuple(aliases)


def settings_factory[T: BaseSettings](settings_type: type[T], **overrides: object) -> T:
    """Build one settings object from the composed public mapping plus explicit overrides.

    Every field's validation alias is supplied explicitly, so an ambient credential cannot fill a
    missing input. Test-only synthetic secrets replace the template placeholders. Alias-keyed
    overrides win last, and the four JSON-valued aliases are decoded only when they are strings.
    """
    environment = public_environment()
    values: dict[str, object] = {}
    for alias in _aliases(settings_type):
        if alias not in environment:
            raise ValueError(f"no composed public value for settings alias {alias}")
        values[alias] = environment[alias]
    for alias, synthetic in _SYNTHETIC_VALUES.items():
        if alias in values:
            values[alias] = synthetic
    values.update(overrides)
    for alias in _JSON_ALIASES:
        if isinstance(values.get(alias), str):
            values[alias] = json.loads(values[alias])
    return settings_type(**values)


def version(
    source_id: str,
    *,
    name_fi: str | None = None,
    name_en: str | None = None,
    code: str | None = None,
    source_hash: str = HASH_A,
    content_fi: str | None = None,
    content_en: str | None = None,
    outcomes_fi: str | None = None,
    outcomes_en: str | None = None,
) -> CatalogueCourseVersion:
    """Build one detached official representative fixture."""
    return CatalogueCourseVersion(
        sisu_course_unit_id=source_id,
        source_hash=source_hash,
        code=code if code is not None else f"CODE.{source_id}",
        name_fi=name_fi,
        name_en=name_en,
        credits_min=Decimal("5"),
        official_url=f"https://example.test/{source_id}",
        document_state="ACTIVE",
        curriculum_period_ids=(),
        teaching_text=CatalogueTeachingText(
            content_fi=content_fi,
            content_en=content_en,
            outcomes_fi=outcomes_fi,
            outcomes_en=outcomes_en,
        ),
        prerequisite_options=(),
        substitution_options=(),
    )


def course(
    group_id: str,
    representative: CatalogueCourseVersion | None,
    *,
    is_active: bool = True,
) -> CatalogueCourse:
    """Build one detached canonical course fixture."""
    return CatalogueCourse(
        group_id=group_id,
        is_active=is_active,
        activity_as_of_academic_year_start=2026,
        activity_window_years=3,
        representative=representative,
    )


def represented_rows(
    courses: tuple[CatalogueCourse, ...],
) -> tuple[RepresentedCourseSummary, ...]:
    """Wrap supplied represented fixture courses with the public summary projection.

    This is fixture assembly only: it returns the supplied represented fixtures as the shared
    official read seam does.
    """
    return tuple(
        RepresentedCourseSummary(
            summary=course_summary(item),
            sisu_course_unit_id=item.representative.sisu_course_unit_id,
            source_hash=item.representative.source_hash,
        )
        for item in courses
        if item.representative is not None
    )


class FakeCurriculum:
    """In-memory official read seam returning caller-supplied fixture profiles.

    Teaching fixtures are projected once through the real public DTOs. Represented-summary reads
    return only the explicitly supplied activity profiles and never recompute or filter them.
    """

    def __init__(
        self,
        courses: tuple[CatalogueCourse, ...],
        *,
        summaries_by_activity: dict[bool | None, tuple[RepresentedCourseSummary, ...]]
        | None = None,
        module_lookup: tuple[CatalogueModuleLookup, ...] = (),
    ) -> None:
        self._teaching_courses = tuple(
            CatalogueTeachingCourse.model_validate(item, from_attributes=True) for item in courses
        )
        self._teaching_text_inputs = tuple(
            CatalogueTeachingTextInput.model_validate(item, from_attributes=True)
            for item in courses
        )
        self._summaries_by_activity = dict(summaries_by_activity or {})
        self._module_lookup = module_lookup
        self._code_identities = tuple(
            sorted(
                (course.group_id, course.representative.code)
                for course in courses
                if course.representative is not None
            )
        )
        self._active_by_group = {course.group_id: course.is_active for course in courses}
        self.calls: list[bool | None] = []
        self.scoped_summary_calls: list[tuple[tuple[str, ...], bool | None]] = []
        self.code_identity_calls: list[bool | None] = []

    def list_courses(self, *, active_only: bool | None = None) -> tuple[CatalogueCourse, ...]:
        """Fail loudly: tests must not materialize full catalogue courses."""
        raise AssertionError("tests must not materialize full catalogue courses")

    def list_teaching_courses(
        self, *, active_only: bool | None = None
    ) -> tuple[CatalogueTeachingCourse, ...]:
        """Return the prepared teaching fixtures for the unfiltered read only."""
        if active_only is None:
            return self._teaching_courses
        raise ValueError(f"unsupported teaching-course activity profile: {active_only!r}")

    def list_teaching_text_inputs(self) -> tuple[CatalogueTeachingTextInput, ...]:
        """Return the prepared teaching-text input fixtures, in canonical order."""
        return self._teaching_text_inputs

    def list_represented_summaries(
        self, *, active_only: bool | None = None
    ) -> tuple[RepresentedCourseSummary, ...]:
        """Record the requested activity profile and return the supplied profile fixtures."""
        self.calls.append(active_only)
        try:
            return self._summaries_by_activity[active_only]
        except KeyError as error:
            raise KeyError(
                f"no represented summary profile for active_only={active_only!r}"
            ) from error

    def get_represented_summaries(
        self, group_ids, *, active_only: bool | None = None
    ) -> tuple[RepresentedCourseSummary, ...]:
        """Return only the requested supplied records under the requested activity profile.

        This fixture records the requested identity scope separately so a resolver proof can assert
        that only candidates were read.
        """
        requested = tuple(sorted({group_id for group_id in group_ids if group_id}))
        self.scoped_summary_calls.append((requested, active_only))
        profile = self._summaries_by_activity[active_only]
        wanted = set(requested)
        return tuple(record for record in profile if record.summary.group_id in wanted)

    def list_course_code_identities(
        self, *, active_only: bool | None = None
    ) -> tuple[tuple[str, str], ...]:
        """Return the supplied `(group_id, code)` projection filtered by the canonical activity."""
        self.code_identity_calls.append(active_only)
        if active_only is None:
            return self._code_identities
        return tuple(
            pair for pair in self._code_identities if self._active_by_group[pair[0]] is active_only
        )

    def list_module_lookup(self) -> tuple[CatalogueModuleLookup, ...]:
        """Return the prepared module projection directly, never selecting or matching."""
        return self._module_lookup


class FakeTranslations:
    """In-memory derived read seam returning the canned rows for every requested version."""

    def __init__(self, rows: tuple[DerivedTranslation, ...] = ()) -> None:
        self._rows = rows

    def list_for_course_versions(self, sisu_course_unit_ids):
        return self._rows


def derived_translation(
    source_id: str,
    field: TeachingTextField,
    language: TeachingTextLanguage,
    source_language: TeachingTextLanguage,
    source_text: str,
    text: str,
    *,
    method: TranslationMethod = TranslationMethod.MANUAL,
    translation_model: str | None = None,
) -> DerivedTranslation:
    """Build one persisted derived translation fixture with a matching source hash."""
    return DerivedTranslation(
        sisu_course_unit_id=source_id,
        field=field,
        language=language,
        source_language=source_language,
        source_text_hash=teaching_text_sha256(source_text),
        text=text,
        translation_method=method,
        generated_at=GENERATED_AT,
        translation_model=translation_model,
    )
