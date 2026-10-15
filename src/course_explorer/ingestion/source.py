"""Immutable public curriculum-source contracts and captured response evidence."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

KoriModuleType = Literal["DegreeProgramme", "StudyModule"]


@dataclass(frozen=True)
class CapturedResponse:
    """Exact successful response bytes and ordered request parameters for capture."""

    request_path: str
    request_params: tuple[tuple[str, str], ...]
    body: bytes


T = TypeVar("T")


@dataclass(frozen=True)
class SourceResponse(Generic[T]):  # noqa: UP046 - contract uses explicit Generic[T] form
    """A validated source value paired with its exact HTTP response evidence."""

    captured: CapturedResponse
    value: T


@dataclass(frozen=True)
class CurriculumPeriodRef:
    """A source curriculum-period ID and its parsed academic-year start."""

    id: str
    academic_year_start: int


@dataclass(frozen=True)
class SourceVersionRef:
    """An exact source version ID, canonical group ID, and period memberships."""

    id: str
    group_id: str
    curriculum_period_ids: tuple[str, ...]


SourceObject = dict[str, Any]


class KoriRequestError(RuntimeError):
    """A public Kori request failed after its configured retry budget."""


class KoriContractError(ValueError):
    """A public Kori response violates the source contract."""


class CurriculumSource(Protocol):
    """Stable source seam consumed by the capture and normalization services."""

    def get_curriculum_periods(self) -> SourceResponse[tuple[CurriculumPeriodRef, ...]]: ...

    def iter_course_version_refs(
        self, period_ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]: ...

    def iter_module_version_refs(
        self, period_ids: Sequence[str], module_type: KoriModuleType
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]: ...

    def iter_course_versions(
        self, ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]: ...

    def iter_module_versions(
        self, ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]: ...

    def get_course_group_versions(
        self, group_id: str
    ) -> SourceResponse[tuple[SourceObject, ...]]: ...

    def get_module_group_versions(
        self, group_id: str
    ) -> SourceResponse[tuple[SourceObject, ...]]: ...

    def iter_course_group_versions(
        self, group_ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]: ...

    def iter_module_group_versions(
        self, group_ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]: ...
