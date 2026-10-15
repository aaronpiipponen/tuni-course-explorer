"""Synchronous, fail-loud adapter for anonymous public Tampere Kori JSON."""

import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from itertools import batched
from types import TracebackType
from typing import Any, Literal, Self, TypeVar, get_args

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from course_explorer.config import KoriSettings
from course_explorer.http_retry import decode_json_response, request_json_with_retries
from course_explorer.ingestion.source import (
    CapturedResponse,
    CurriculumPeriodRef,
    KoriContractError,
    KoriModuleType,
    KoriRequestError,
    SourceObject,
    SourceResponse,
    SourceVersionRef,
)

_PARTITION_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_ItemT = TypeVar("_ItemT")
_ResultT = TypeVar("_ResultT")


class _ActivePeriod(BaseModel):
    model_config = ConfigDict(extra="allow")

    start_date: date = Field(validation_alias="startDate")


class _CurriculumPeriod(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    active_period: _ActivePeriod = Field(validation_alias="activePeriod")

    @field_validator("id")
    @classmethod
    def reject_blank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("curriculum period id must not be blank")
        return value


class _Notification(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["INFO", "WARNING", "ERROR"]


class _SearchItemBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    group_id: str = Field(validation_alias="groupId")
    curriculum_period_ids: list[str] = Field(validation_alias="curriculumPeriodIds")

    @field_validator("id", "group_id", "code", check_fields=False)
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("search item text fields must not be blank")
        return value

    @field_validator("curriculum_period_ids")
    @classmethod
    def validate_period_ids(cls, value: list[str]) -> list[str]:
        if any(not isinstance(period_id, str) or not period_id.strip() for period_id in value):
            raise ValueError("curriculum period IDs must be non-blank strings")
        if len(value) != len(set(value)):
            raise ValueError("curriculum period IDs must not contain duplicates")
        return value


class _CourseSearchItem(_SearchItemBase):
    code: str


class _ModuleSearchItem(_SearchItemBase):
    pass


class _SearchEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    start: int = Field(ge=0)
    limit: int = Field(ge=0)
    total: int = Field(ge=0)
    search_results: list[dict[str, Any]] = Field(validation_alias="searchResults")
    truncated: bool
    notifications: list[_Notification] | None


class TuniKoriSource:
    """One synchronous public Kori client with bounded retries and parallel batches."""

    def __init__(
        self,
        settings: KoriSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        before_request: Callable[[], bool] | None = None,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._before_request = before_request
        client = httpx.Client(
            base_url=str(settings.kori_base_url).rstrip("/") + "/",
            timeout=settings.kori_request_timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )
        self._client = client

    def close(self) -> None:
        """Close the shared HTTP client and release its connections."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _request_json(
        self, path: str, params: Sequence[tuple[str, str]]
    ) -> tuple[CapturedResponse, Any]:
        if not path.startswith("/api/"):
            raise KoriContractError("Kori request path must begin with /api/")
        frozen_params = tuple(params)

        def validate(response: httpx.Response) -> tuple[httpx.Response, Any]:
            return response, decode_json_response(
                response, error_prefix=f"GET {path}", contract_error=KoriContractError
            )

        response, value = request_json_with_retries(
            request=lambda: self._client.get(path.removeprefix("/"), params=list(frozen_params)),
            validate=validate,
            max_attempts=self._settings.kori_max_attempts,
            retry_backoff_seconds=self._settings.kori_retry_backoff_seconds,
            sleep=self._sleep,
            error_prefix=f"GET {path}",
            request_error=KoriRequestError,
            contract_error=KoriContractError,
            retry_contract_errors=False,
            before_request=self._before_request,
            check_initial=False,
        )
        captured = CapturedResponse(
            request_path=path,
            request_params=frozen_params,
            body=response.content,
        )
        return captured, value

    @staticmethod
    def _contract_model(model_type: type[BaseModel], value: Any, context: str) -> BaseModel:
        try:
            return model_type.model_validate(value)
        except ValidationError as exc:
            raise KoriContractError(f"{context} violates Kori schema") from exc

    def get_curriculum_periods(self) -> SourceResponse[tuple[CurriculumPeriodRef, ...]]:
        """Discover source period IDs and prove configured academic-year continuity."""
        captured, value = self._request_json(
            "/api/curriculum-periods",
            (("universityOrgId", self._settings.tuni_university_id),),
        )
        if not isinstance(value, list):
            raise KoriContractError("curriculum periods response must be a list")

        selected: dict[int, CurriculumPeriodRef] = {}
        for raw_period in value:
            period = self._contract_model(_CurriculumPeriod, raw_period, "curriculum period")
            year = period.active_period.start_date.year
            if (
                self._settings.first_academic_year_start
                <= year
                <= self._settings.current_academic_year_start
            ):
                if year in selected:
                    raise KoriContractError("multiple curriculum periods share an academic year")
                selected[year] = CurriculumPeriodRef(id=period.id, academic_year_start=year)

        expected_years = range(
            self._settings.first_academic_year_start,
            self._settings.current_academic_year_start + 1,
        )
        if set(selected) != set(expected_years):
            raise KoriContractError("configured curriculum-period range has gaps")
        return SourceResponse(
            captured=captured, value=tuple(selected[year] for year in expected_years)
        )

    def _search_page(
        self,
        path: str,
        params: tuple[tuple[str, str], ...],
        item_model: type[_SearchItemBase],
    ) -> tuple[CapturedResponse, _SearchEnvelope, list[_SearchItemBase]]:
        captured, value = self._request_json(path, params)
        if not isinstance(value, dict):
            raise KoriContractError("search response must be an object")
        envelope = self._contract_model(_SearchEnvelope, value, "search envelope")
        if envelope.notifications is not None and any(
            notification.type == "ERROR" for notification in envelope.notifications
        ):
            raise KoriContractError("search response contains an ERROR notification")
        items: list[_SearchItemBase] = []
        for raw_item in envelope.search_results:
            items.append(self._contract_model(item_model, raw_item, "search item"))
        return captured, envelope, items

    def _iter_search_query(
        self,
        *,
        path: str,
        fixed_params: tuple[tuple[str, str], ...],
        item_model: type[_SearchItemBase],
        period_id: str,
        prefix: str | None,
        first: tuple[CapturedResponse, _SearchEnvelope, list[_SearchItemBase]] | None = None,
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]:
        first_page = first or self._search_page(
            path,
            fixed_params + (("start", "0"), ("limit", str(self._settings.kori_search_page_size))),
            item_model,
        )
        captured, envelope, items = first_page
        self._validate_search_items(items, period_id, prefix, item_model is _CourseSearchItem)
        if envelope.start != 0:
            raise KoriContractError("search response start does not match requested start")
        if envelope.truncated:
            if items or envelope.total <= 0:
                raise KoriContractError(
                    "truncated search response must be empty with positive total"
                )
            yield SourceResponse(captured=captured, value=tuple())
            if prefix is not None and len(prefix) >= self._settings.kori_max_partition_depth:
                raise KoriContractError("search partition depth exhausted")
            for character in _PARTITION_ALPHABET:
                child_prefix = character if prefix is None else prefix + character
                prefix_param = "codeQuery" if item_model is _CourseSearchItem else "fullTextQuery"
                parent_params = fixed_params if prefix is None else fixed_params[:-1]
                child_params = parent_params + (
                    (
                        prefix_param,
                        child_prefix,
                    ),
                )
                yield from self._iter_search_query(
                    path=path,
                    fixed_params=child_params,
                    item_model=item_model,
                    period_id=period_id,
                    prefix=child_prefix,
                )
            return

        yield from self._iter_paginated_pages(
            path=path,
            fixed_params=fixed_params,
            item_model=item_model,
            period_id=period_id,
            prefix=prefix,
            first_page=first_page,
        )

    def _iter_paginated_pages(
        self,
        *,
        path: str,
        fixed_params: tuple[tuple[str, str], ...],
        item_model: type[_SearchItemBase],
        period_id: str,
        prefix: str | None,
        first_page: tuple[CapturedResponse, _SearchEnvelope, list[_SearchItemBase]],
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]:
        """Walk one non-truncated search query's exact pagination to its reported total."""
        captured, envelope, items = first_page
        seen_ids: set[str] = set()
        accumulated = 0
        previous_start = envelope.start
        while True:
            if envelope.start != previous_start:
                raise KoriContractError("search response start does not match requested start")
            if envelope.total != first_page[1].total:
                raise KoriContractError("search total changed during pagination")
            if len(items) == 0 and accumulated < envelope.total:
                raise KoriContractError("search pagination made no progress")
            page_refs = self._search_refs(items)
            page_ids = {ref.id for ref in page_refs}
            if len(page_ids) != len(page_refs) or seen_ids.intersection(page_ids):
                raise KoriContractError("search query contains duplicate IDs")
            seen_ids.update(page_ids)
            accumulated += len(page_refs)
            if accumulated > envelope.total:
                raise KoriContractError("search results exceed reported total")
            yield SourceResponse(captured=captured, value=tuple(page_refs))
            if accumulated == envelope.total:
                return

            previous_start = envelope.start + len(items)
            params = fixed_params + (
                ("start", str(previous_start)),
                ("limit", str(self._settings.kori_search_page_size)),
            )
            captured, envelope, items = self._search_page(path, params, item_model)
            if envelope.truncated:
                raise KoriContractError("later search page must not be truncated")
            self._validate_search_items(items, period_id, prefix, item_model is _CourseSearchItem)

    @staticmethod
    def _validate_search_items(
        items: list[_SearchItemBase],
        period_id: str,
        prefix: str | None,
        course_items: bool,
    ) -> None:
        for item in items:
            if period_id not in item.curriculum_period_ids:
                raise KoriContractError("search item is missing requested curriculum period")
            if (
                course_items
                and prefix is not None
                and not item.code.casefold().startswith(prefix.casefold())
            ):
                raise KoriContractError("course search item does not match code prefix")

    @staticmethod
    def _search_refs(items: list[_SearchItemBase]) -> list[SourceVersionRef]:
        return [
            SourceVersionRef(
                id=item.id,
                group_id=item.group_id,
                curriculum_period_ids=tuple(item.curriculum_period_ids),
            )
            for item in items
        ]

    @staticmethod
    def _validate_period_ids(period_ids: Sequence[str]) -> tuple[str, ...]:
        result = tuple(period_ids)
        if any(not isinstance(period_id, str) or not period_id.strip() for period_id in result):
            raise KoriContractError("period IDs must be non-blank strings")
        if len(result) != len(set(result)):
            raise KoriContractError("period IDs must not contain duplicates")
        return result

    def _iter_version_refs(
        self,
        *,
        path: str,
        item_model: type[_SearchItemBase],
        period_ids: Sequence[str],
        extra_params: tuple[tuple[str, str], ...],
        disjoint: bool,
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]:
        """Enumerate one search endpoint's complete results per requested period.

        ``disjoint`` selects the course rule (duplicate IDs across partitions are refused) versus
        the module rule (overlap is deduplicated). Both preserve exact pagination and a broad-total
        floor whenever the root query was truncated.
        """
        for period_id in self._validate_period_ids(period_ids):
            fixed_params = (
                ("curriculumPeriodId", period_id),
                ("universityOrgId", self._settings.tuni_university_id),
            ) + extra_params
            first = self._search_page(
                path,
                fixed_params
                + (("start", "0"), ("limit", str(self._settings.kori_search_page_size))),
                item_model,
            )
            all_ids: set[str] = set()
            broad_total = first[1].total
            for response in self._iter_search_query(
                path=path,
                fixed_params=fixed_params,
                item_model=item_model,
                period_id=period_id,
                prefix=None,
                first=first,
            ):
                if disjoint:
                    for ref in response.value:
                        if ref.id in all_ids:
                            raise KoriContractError(
                                "course ID occurs in disjoint search partitions"
                            )
                        all_ids.add(ref.id)
                else:
                    all_ids.update(ref.id for ref in response.value)
                yield response
            if first[1].truncated and len(all_ids) < broad_total:
                family = "course" if disjoint else "module"
                raise KoriContractError(f"{family} partition union is below broad total floor")

    def iter_course_version_refs(
        self, period_ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]:
        """Enumerate every complete course search response in caller period order."""
        yield from self._iter_version_refs(
            path="/api/course-unit-search",
            item_model=_CourseSearchItem,
            period_ids=period_ids,
            extra_params=(),
            disjoint=True,
        )

    def iter_module_version_refs(
        self, period_ids: Sequence[str], module_type: KoriModuleType
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]:
        """Enumerate each public module family independently and prove its union total."""
        if module_type not in get_args(KoriModuleType):
            raise KoriContractError("unsupported public module type")
        yield from self._iter_version_refs(
            path="/api/module-search",
            item_model=_ModuleSearchItem,
            period_ids=period_ids,
            extra_params=(("moduleType", module_type),),
            disjoint=False,
        )

    @staticmethod
    def _validate_input_ids(ids: Sequence[str]) -> tuple[str, ...]:
        result = tuple(ids)
        if any(not isinstance(identifier, str) or not identifier.strip() for identifier in result):
            raise KoriContractError("object IDs must be non-blank strings")
        if len(result) != len(set(result)):
            raise KoriContractError("object IDs must not contain duplicates")
        return result

    def _fetch_exact_batch(
        self, ids: tuple[str, ...], path: str
    ) -> SourceResponse[tuple[SourceObject, ...]]:
        captured, value = self._request_json(path, tuple(("id", identifier) for identifier in ids))
        if not isinstance(value, list):
            raise KoriContractError("exact-object response must be a list")
        by_id: dict[str, SourceObject] = {}
        for item in value:
            if not isinstance(item, dict):
                raise KoriContractError("exact-object response item must be an object")
            identifier = item.get("id")
            group_id = item.get("groupId")
            if not isinstance(identifier, str) or not identifier.strip():
                raise KoriContractError("exact-object item ID must be non-blank")
            if not isinstance(group_id, str) or not group_id.strip():
                raise KoriContractError("exact-object groupId must be non-blank")
            if identifier in by_id:
                raise KoriContractError("exact-object response contains duplicate IDs")
            by_id[identifier] = item
        if set(by_id) != set(ids):
            raise KoriContractError("exact-object response IDs do not match request")
        return SourceResponse(captured, tuple(by_id[identifier] for identifier in ids))

    def _iter_concurrently(
        self, items: Sequence[_ItemT], fetch: Callable[[_ItemT], _ResultT]
    ) -> Iterator[_ResultT]:
        """Run bounded source requests concurrently while yielding input order.

        Only one window of ``kori_concurrency`` items is submitted at a time. The next window is
        submitted only when the consumer advances past the current one, so pause/stop between
        windows cannot leave the whole remaining frontier queued.
        """
        if not items:
            return
        window_size = self._settings.kori_concurrency
        with ThreadPoolExecutor(max_workers=window_size) as executor:
            futures: list[Future[_ResultT]] = []
            try:
                for window in batched(items, window_size):
                    futures = [executor.submit(fetch, item) for item in window]
                    for future in futures:
                        yield future.result()
            except BaseException:
                for future in futures:
                    if not future.done():
                        future.cancel()
                raise

    def _iter_exact_versions(
        self, ids: Sequence[str], path: str
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        ordered_ids = self._validate_input_ids(ids)
        batches = tuple(
            ordered_ids[index : index + self._settings.kori_batch_size]
            for index in range(0, len(ordered_ids), self._settings.kori_batch_size)
        )
        yield from self._iter_concurrently(
            batches, lambda batch: self._fetch_exact_batch(batch, path)
        )

    def iter_course_versions(
        self, ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        """Fetch exact course versions in ordered, bounded concurrent batches."""
        yield from self._iter_exact_versions(ids, "/api/course-units")

    def iter_module_versions(
        self, ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        """Fetch exact module versions in ordered, bounded concurrent batches."""
        yield from self._iter_exact_versions(ids, "/api/modules")

    def get_course_group_versions(self, group_id: str) -> SourceResponse[tuple[SourceObject, ...]]:
        """Fetch all public course versions for one canonical group."""
        if not isinstance(group_id, str) or not group_id.strip():
            raise KoriContractError("course group ID must be non-blank")
        captured, value = self._request_json(
            "/api/course-units",
            (
                ("groupId", group_id),
                ("rootOrg", self._settings.tuni_university_id),
                ("includeExpired", "true"),
            ),
        )
        return SourceResponse(captured, self._validate_group_objects(value, group_id))

    def get_module_group_versions(self, group_id: str) -> SourceResponse[tuple[SourceObject, ...]]:
        """Fetch all public module versions for one canonical group."""
        if not isinstance(group_id, str) or not group_id.strip():
            raise KoriContractError("module group ID must be non-blank")
        captured, value = self._request_json(
            "/api/modules/by-group-id",
            (("groupId", group_id), ("universityId", self._settings.tuni_university_id)),
        )
        return SourceResponse(captured, self._validate_group_objects(value, group_id))

    def iter_course_group_versions(
        self, group_ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        """Fetch course groups concurrently while preserving caller order."""
        ordered_ids = self._validate_input_ids(group_ids)
        yield from self._iter_concurrently(ordered_ids, self.get_course_group_versions)

    def iter_module_group_versions(
        self, group_ids: Sequence[str]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        """Fetch module groups concurrently while preserving caller order."""
        ordered_ids = self._validate_input_ids(group_ids)
        yield from self._iter_concurrently(ordered_ids, self.get_module_group_versions)

    @staticmethod
    def _validate_group_objects(value: Any, requested_group_id: str) -> tuple[SourceObject, ...]:
        if not isinstance(value, list):
            raise KoriContractError("group response must be a list")
        objects: list[SourceObject] = []
        seen_ids: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                raise KoriContractError("group response item must be an object")
            identifier = item.get("id")
            group_id = item.get("groupId")
            if not isinstance(identifier, str) or not identifier.strip():
                raise KoriContractError("group response item ID must be non-blank")
            if not isinstance(group_id, str) or not group_id.strip():
                raise KoriContractError("group response groupId must be non-blank")
            if group_id != requested_group_id:
                raise KoriContractError("group response contains a different group ID")
            if identifier in seen_ids:
                raise KoriContractError("group response contains duplicate IDs")
            seen_ids.add(identifier)
            objects.append(item)
        return tuple(objects)
