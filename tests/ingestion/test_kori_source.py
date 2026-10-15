"""HTTP contract tests using source-shaped Kori fixtures."""

import json
from copy import deepcopy
from pathlib import Path
from threading import Event, Lock
from typing import Any

import httpx
import pytest

from course_explorer.config import KoriSettings
from course_explorer.ingestion.kori import TuniKoriSource
from course_explorer.ingestion.source import KoriContractError, KoriRequestError
from tests.support import settings_factory

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "kori"


def load_fixture(name: str) -> bytes:
    """Load exact committed fixture bytes as a response body."""
    return (FIXTURE_ROOT / name).read_bytes()


def settings(**overrides: Any) -> KoriSettings:
    """Build Kori settings from the composed public files plus explicit test overrides."""
    defaults: dict[str, Any] = {
        "KORI_FIRST_ACADEMIC_YEAR": "2026-2027",
        "CURRENT_ACADEMIC_YEAR": "2026-2027",
    }
    defaults.update(overrides)
    return settings_factory(KoriSettings, **defaults)


def response(name: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, content=load_fixture(name))


def request_parts(request: httpx.Request) -> tuple[str, tuple[tuple[str, str], ...]]:
    return request.url.path.removeprefix("/kori"), tuple(request.url.params.multi_items())


def test_curriculum_periods_use_source_ids_with_contiguous_configured_bounds() -> None:
    """Period IDs come from source objects and request parameters remain exact."""

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/curriculum-periods"
        assert params == (("universityOrgId", "tuni-university-root-id"),)
        return response("curriculum_periods.json")

    with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
        result = source.get_curriculum_periods()

    assert result.value[0].id == "uta-lvv-2026"
    assert result.value[0].academic_year_start == 2026
    assert result.captured.body == load_fixture("curriculum_periods.json")


def test_enumeration_rejects_partition_union_below_truncated_broad_total() -> None:
    """A complete partition union below the broad floor remains invalid evidence."""
    broad = deepcopy(json.loads(load_fixture("course_search_broad_truncated.json")))
    broad["total"] = 3

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/course-unit-search"
        expected_prefix = (
            ("curriculumPeriodId", "uta-lvv-2026"),
            ("universityOrgId", "tuni-university-root-id"),
        )
        query = dict(params)
        if "codeQuery" not in query:
            assert params == expected_prefix + (("start", "0"), ("limit", "1000"))
            return httpx.Response(200, json=broad)
        assert params == expected_prefix + (
            ("codeQuery", query["codeQuery"]),
            ("start", "0"),
            ("limit", "1000"),
        )
        if query["codeQuery"] in {"A", "B"}:
            return response(f"course_search_{query['codeQuery'].lower()}.json")
        return response("search_empty.json")

    with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
        with pytest.raises(KoriContractError):
            tuple(source.iter_course_version_refs(["uta-lvv-2026"]))


def test_truncated_enumeration_visits_every_declared_partition() -> None:
    """Exhaustive root visitation cannot be skipped when the union already clears its floor."""
    broad = deepcopy(json.loads(load_fixture("course_search_broad_truncated.json")))
    broad["total"] = 1
    z_item = deepcopy(json.loads(load_fixture("course_search_a.json"))["searchResults"][0])
    z_item.update({"id": "course-z-v1", "groupId": "course-group-z", "code": "Z.001"})
    expected_roots = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    requested_roots: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/course-unit-search"
        expected_prefix = (
            ("curriculumPeriodId", "uta-lvv-2026"),
            ("universityOrgId", "tuni-university-root-id"),
        )
        query = dict(params)
        if "codeQuery" not in query:
            assert params == expected_prefix + (("start", "0"), ("limit", "1000"))
            return httpx.Response(200, json=broad)
        prefix = query["codeQuery"]
        assert len(prefix) == 1
        requested_roots.add(prefix)
        assert params == expected_prefix + (
            ("codeQuery", prefix),
            ("start", "0"),
            ("limit", "1000"),
        )
        if prefix == "A":
            return response("course_search_a.json")
        if prefix == "B":
            return response("course_search_b.json")
        if prefix == "Z":
            payload = deepcopy(json.loads(load_fixture("course_search_a.json")))
            payload["searchResults"] = [z_item]
            return httpx.Response(200, json=payload)
        return response("search_empty.json")

    with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
        responses = tuple(source.iter_course_version_refs(["uta-lvv-2026"]))

    assert requested_roots == expected_roots
    assert {ref.id for item in responses for ref in item.value} == {
        "course-a-v1",
        "course-b-v1",
        "course-z-v1",
    }


def test_enumeration_paginates_non_truncated_queries_with_source_progress() -> None:
    """Non-truncated pages advance by returned item count and preserve source order."""

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/course-unit-search"
        expected_prefix = (
            ("curriculumPeriodId", "uta-lvv-2026"),
            ("universityOrgId", "tuni-university-root-id"),
        )
        start = dict(params)["start"]
        assert params == expected_prefix + (("start", start), ("limit", "1"))
        payload = json.loads(
            load_fixture("course_search_a.json" if start == "0" else "course_search_b.json")
        )
        payload["limit"] = 1
        payload["start"] = int(start)
        payload["total"] = 2
        return httpx.Response(200, json=payload)

    with TuniKoriSource(
        settings(KORI_SEARCH_PAGE_SIZE=1), transport=httpx.MockTransport(handler)
    ) as source:
        responses = tuple(source.iter_course_version_refs(["uta-lvv-2026"]))

    assert [ref.id for item in responses for ref in item.value] == ["course-a-v1", "course-b-v1"]


def test_enumeration_rejects_partition_depth_exhaustion() -> None:
    """A truncated leaf at configured maximum depth fails loudly."""

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/course-unit-search"
        query = dict(params)
        expected_prefix = (
            ("curriculumPeriodId", "uta-lvv-2026"),
            ("universityOrgId", "tuni-university-root-id"),
        )
        if "codeQuery" in query:
            assert params == expected_prefix + (
                ("codeQuery", query["codeQuery"]),
                ("start", "0"),
                ("limit", "1000"),
            )
        else:
            assert params == expected_prefix + (("start", "0"), ("limit", "1000"))
        if "codeQuery" not in query:
            return response("course_search_broad_truncated.json")
        return response("course_search_broad_truncated.json")

    with TuniKoriSource(
        settings(KORI_MAX_PARTITION_DEPTH=1), transport=httpx.MockTransport(handler)
    ) as source:
        with pytest.raises(KoriContractError):
            tuple(source.iter_course_version_refs(["uta-lvv-2026"]))


def test_module_enumeration_recurses_deduplicates_and_proves_broad_total() -> None:
    """Module full-text partitions may overlap while broad union remains complete."""
    broad = deepcopy(json.loads(load_fixture("module_search_broad_truncated.json")))
    broad["total"] = 1

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/module-search"
        expected_prefix = (
            ("curriculumPeriodId", "uta-lvv-2026"),
            ("universityOrgId", "tuni-university-root-id"),
            ("moduleType", "StudyModule"),
        )
        query = dict(params)
        prefix = query.get("fullTextQuery")
        if prefix is None:
            assert params == expected_prefix + (("start", "0"), ("limit", "1000"))
            root_queries.append(prefix)
            return httpx.Response(200, json=broad)
        assert params == expected_prefix + (
            ("fullTextQuery", prefix),
            ("start", "0"),
            ("limit", "1000"),
        )
        if len(prefix) == 1:
            root_queries.append(prefix)
        if prefix.startswith("A") and len(prefix) == 2:
            a_child_queries.append(prefix)
        if prefix == "A":
            return response("module_search_a_truncated.json")
        if prefix in {"AA", "AB", "B"}:
            return response(f"module_search_{prefix.lower()}.json")
        return response("search_empty.json")

    root_queries: list[str | None] = []
    a_child_queries: list[str] = []
    with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
        responses = tuple(source.iter_module_version_refs(["uta-lvv-2026"], "StudyModule"))

    ids = [ref.id for item in responses for ref in item.value]
    assert ids.count("module-aa-v1") == 1
    assert ids.count("module-ab-v1") == 2
    assert set(root_queries) == set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") | {None}
    assert set(a_child_queries) == {
        f"A{character}" for character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    }


def test_enumeration_rejects_truncation_total_drift_and_malformed_items() -> None:
    """Incomplete or error-bearing search evidence never becomes a partial iterator result."""
    base = json.loads(load_fixture("course_search_a.json"))
    cases: list[dict[str, Any]] = []
    malformed = deepcopy(base)
    malformed["total"] = 2
    cases.append(malformed)
    malformed = deepcopy(base)
    malformed["notifications"] = [{"type": "ERROR"}]
    cases.append(malformed)

    for bad_payload in cases:

        def handler(
            request: httpx.Request, bad_payload: dict[str, Any] = bad_payload
        ) -> httpx.Response:
            path, params = request_parts(request)
            assert path == "/api/course-unit-search"
            query = dict(params)
            expected = (
                ("curriculumPeriodId", "uta-lvv-2026"),
                ("universityOrgId", "tuni-university-root-id"),
            )
            if "codeQuery" in query:
                expected += (("codeQuery", query["codeQuery"]),)
            expected += (("start", query["start"]), ("limit", "1000"))
            assert params == expected
            if "codeQuery" not in query:
                return response("course_search_broad_truncated.json")
            if query["codeQuery"] == "A":
                payload = deepcopy(bad_payload)
                payload["start"] = int(query["start"])
                return httpx.Response(200, json=payload)
            assert len(query["codeQuery"]) == 1
            return response("search_empty.json")

        with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
            with pytest.raises(KoriContractError):
                tuple(source.iter_course_version_refs(["uta-lvv-2026"]))


def test_batch_fetch_uses_repeated_id_and_rejects_missing_objects() -> None:
    """Exact batches preserve requested order and reject incomplete source responses."""
    calls: list[tuple[tuple[str, str], ...]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/course-units"
        calls.append(params)
        assert params == (("id", "course-a-v1"), ("id", "course-b-v1"))
        return response("course_units.json")

    with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
        result = tuple(source.iter_course_versions(["course-a-v1", "course-b-v1"]))
    assert calls == [(("id", "course-a-v1"), ("id", "course-b-v1"))]
    assert [item["id"] for item in result[0].value] == ["course-a-v1", "course-b-v1"]

    def missing_handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        assert path == "/api/course-units"
        assert params == (("id", "course-a-v1"), ("id", "course-b-v1"))
        return httpx.Response(200, json=[json.loads(load_fixture("course_units.json"))[0]])

    with TuniKoriSource(settings(), transport=httpx.MockTransport(missing_handler)) as source:
        with pytest.raises(KoriContractError):
            tuple(source.iter_course_versions(["course-a-v1", "course-b-v1"]))


def test_group_fetch_uses_public_parameters_and_allows_empty_result() -> None:
    """Public group endpoints validate group identity and retain explicit empty results."""

    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request_parts(request)
        if path == "/api/course-units":
            assert params == (
                ("groupId", "course-group-a"),
                ("rootOrg", "tuni-university-root-id"),
                ("includeExpired", "true"),
            )
            course = json.loads(load_fixture("course_units.json"))[0]
            return httpx.Response(200, json=[course])
        assert path == "/api/modules/by-group-id"
        assert params == (
            ("groupId", "missing-module"),
            ("universityId", "tuni-university-root-id"),
        )
        return httpx.Response(200, content=b"[]")

    with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
        course_result = source.get_course_group_versions("course-group-a")
        module_result = source.get_module_group_versions("missing-module")
    assert len(course_result.value) == 1
    assert module_result.value == ()


@pytest.mark.parametrize("family", ["course", "module"])
def test_group_iterators_use_configured_concurrency_and_yield_input_order(family: str) -> None:
    """Group transport is concurrent. Bounded windows stop before the next window starts."""
    active = 0
    maximum_active = 0
    state_lock = Lock()
    release_first = Event()
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active
        path, params = request_parts(request)
        group_id = params[0][1]
        requested.append(group_id)
        if family == "course":
            assert path == "/api/course-units"
            assert params[0][0] == "groupId"
            assert params[1:] == (
                ("rootOrg", "tuni-university-root-id"),
                ("includeExpired", "true"),
            )
        else:
            assert path == "/api/modules/by-group-id"
            assert params == (
                ("groupId", group_id),
                ("universityId", "tuni-university-root-id"),
            )
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            if group_id == "group-a":
                assert release_first.wait(timeout=2)
            elif group_id == "group-b":
                release_first.set()
            return httpx.Response(
                200,
                json=[{"id": f"{group_id}-v1", "groupId": group_id}],
            )
        finally:
            with state_lock:
                active -= 1

    ids = ["group-a", "group-b", "group-c"]

    def open_iterator(source: TuniKoriSource):
        if family == "course":
            return source.iter_course_group_versions(ids)
        return source.iter_module_group_versions(ids)

    with TuniKoriSource(
        settings(KORI_CONCURRENCY=2), transport=httpx.MockTransport(handler)
    ) as source:
        iterator = open_iterator(source)
        first = next(iterator)
        iterator.close()

    assert maximum_active == 2
    assert first.value[0]["groupId"] == "group-a"
    assert "group-c" not in requested

    # A separate iterator proves the complete ordered output across every bounded window.
    requested.clear()
    with TuniKoriSource(
        settings(KORI_CONCURRENCY=2), transport=httpx.MockTransport(handler)
    ) as source:
        values = tuple(open_iterator(source))
    assert [item.value[0]["groupId"] for item in values] == ids


def test_transient_requests_stop_retrying_after_control_denies() -> None:
    """A pause/stop request stops Kori transport retries after the in-flight attempt fails.

    An admitted initial source pull belongs to the capture boundary and runs. Only
    the next retry is refused, and the safe request error is raised without extra calls.
    """
    attempts = 0
    admitted = {"value": True}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, content=b"not logged")

    def sleep(seconds: float) -> None:
        admitted["value"] = False

    with TuniKoriSource(
        settings(),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        before_request=lambda: admitted["value"],
    ) as source:
        with pytest.raises(KoriRequestError):
            source.get_curriculum_periods()
    assert attempts == 1


def test_request_errors_do_not_expose_response_body() -> None:
    """Terminal request failures contain method/path/status but never response content."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"secret-response-body")

    with TuniKoriSource(settings(), transport=httpx.MockTransport(handler)) as source:
        with pytest.raises(KoriRequestError) as error:
            source.get_curriculum_periods()
    assert "GET /api/curriculum-periods" in str(error.value)
    assert "secret-response-body" not in str(error.value)
