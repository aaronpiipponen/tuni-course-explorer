"""Server enforcement proofs for the two per-site feature switches and the serving identity."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

import course_explorer.administration as administration
from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.comparison import commands as comparison_commands
from course_explorer.config import load_web_settings
from course_explorer.datasets import DatasetReceipt, SelectedDatasetPointer
from course_explorer.hashing import json_sha256
from course_explorer.next_courses import commands as next_courses_commands
from course_explorer.prerequisite import commands as prerequisite_commands
from course_explorer.recommendations import commands as recommendation_commands
from course_explorer.search import commands as search_commands
from course_explorer.search import lookup_commands
from course_explorer.study_structure import commands as study_structure_commands
from course_explorer_web.app import app
from course_explorer_web.dataset import SERVING_GENERATION_ENV, resolve_serving_dataset
from course_explorer_web.routes.comparison import ComparisonRequest
from course_explorer_web.routes.next_courses import NextCoursesRequest
from course_explorer_web.routes.prerequisite_inputs import PrerequisiteGraphRequest
from course_explorer_web.routes.recommendations import RecommendationsRequest
from course_explorer_web.routes.search import SearchRequest
from course_explorer_web.serving import MEASURE_GRAPH_HEADER
from course_explorer_web.serving_cache import serving_caches
from tests.datasets._support import sample_receipt

_DRAWING_LIMIT = 137
_COMPACT_NODE_LIMIT = 4242
_PROJECTION_ROUTES = ("/api/search", "/api/catalogue")
_SOURCE_CACHE_ROUTES = ("/api/prerequisites", "/api/next-courses", "/api/recommendations")


def _retained_cache_arguments(endpoint: str, serving) -> dict[str, object]:
    """Return the cache keywords one route passes to its command boundary."""
    cache = serving_caches(serving, load_web_settings())
    if endpoint in _PROJECTION_ROUTES:
        return {"projection_cache": cache.lookup_projection}
    if endpoint == "/api/recommendations":
        return {
            "source_cache": cache.prerequisite_sources,
            "chunk_cache": cache.descriptive_chunks,
        }
    if endpoint in _SOURCE_CACHE_ROUTES:
        return {"source_cache": cache.prerequisite_sources}
    return {}


class _SentinelReport(BaseModel):
    """The one small serializable report a spied command boundary returns."""

    payload: str

    @property
    def solver(self) -> SimpleNamespace:
        """Return the solver root the graph route compares its target against."""
        return SimpleNamespace(root_group_id="sentinel-target", courses=())


class _RootedReport(BaseModel):
    """One serializable graph report whose solver names one root course and its official code."""

    payload: str

    @property
    def solver(self) -> SimpleNamespace:
        """Return a solver whose root `group-root` carries the official code `COMP.CS.100`."""
        return SimpleNamespace(
            root_group_id="group-root",
            courses=(SimpleNamespace(group_id="group-root", code="COMP.CS.100"),),
        )


class _FeatureReadCase:
    """One embeddings-off read, its minimal closed request and its owning command boundary."""

    __slots__ = ("body", "command", "endpoint", "owner")

    def __init__(self, endpoint: str, body: dict[str, object], owner: object, command: str) -> None:
        self.endpoint = endpoint
        self.body = body
        self.owner = owner
        self.command = command


class _PolicyCase:
    """One cached read, its closed request model, its command boundary and the policy it applies."""

    __slots__ = (
        "body",
        "command",
        "drawing_limit",
        "endpoint",
        "model",
        "owner",
        "policy_field",
        "requested_field",
        "site_switch",
    )

    def __init__(
        self,
        endpoint: str,
        body: dict[str, object],
        model: type[BaseModel],
        owner: object,
        command: str,
        *,
        site_switch: str,
        policy_field: str,
        requested_field: str | None,
        drawing_limit: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.body = body
        self.model = model
        self.owner = owner
        self.command = command
        self.drawing_limit = drawing_limit
        self.site_switch = site_switch
        self.policy_field = policy_field
        self.requested_field = requested_field


class _CachedRead:
    """One cached HTTP read, its command spy call shape and its published metadata."""

    __slots__ = (
        "body",
        "command",
        "endpoint",
        "model",
        "owner",
        "positional",
        "with_compact_nodes",
    )

    def __init__(
        self,
        endpoint: str,
        body: dict[str, object],
        model: type[BaseModel],
        owner: object,
        command: str,
        *,
        positional: tuple[object, ...] = (),
        with_compact_nodes: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.body = body
        self.model = model
        self.owner = owner
        self.command = command
        self.positional = positional
        self.with_compact_nodes = with_compact_nodes


_FEATURE_READ_CASES = (
    _FeatureReadCase(
        "/api/comparison",
        {"course_a": "COMP.CS.100", "course_b": "COMP.CS.200"},
        comparison_commands,
        "run_course_comparison_command",
    ),
    _FeatureReadCase(
        "/api/recommendations",
        {"display_language": "fi"},
        recommendation_commands,
        "run_recommendations_command",
    ),
)

_INFERENCE_CASES = (
    _PolicyCase(
        "/api/prerequisites",
        {"target_code": "COMP.CS.100"},
        PrerequisiteGraphRequest,
        prerequisite_commands,
        "run_prerequisite_command",
        site_switch="WEB_INFERENCE_ENABLED",
        policy_field="include_inferred",
        requested_field="include_inferred",
        drawing_limit=True,
    ),
    _PolicyCase(
        "/api/next-courses",
        {"display_language": "fi"},
        NextCoursesRequest,
        next_courses_commands,
        "run_next_courses_command",
        site_switch="WEB_INFERENCE_ENABLED",
        policy_field="include_inferred",
        requested_field="include_inferred",
    ),
    _PolicyCase(
        "/api/recommendations",
        {"display_language": "fi"},
        RecommendationsRequest,
        recommendation_commands,
        "run_recommendations_command",
        site_switch="WEB_INFERENCE_ENABLED",
        policy_field="include_inferred",
        requested_field="include_inferred",
    ),
)

_SEARCH_CASE = _PolicyCase(
    "/api/search",
    {"query": "synthetic query", "display_language": "fi"},
    SearchRequest,
    search_commands,
    "run_search_command",
    site_switch="WEB_EMBEDDINGS_ENABLED",
    policy_field="include_semantic",
    requested_field=None,
)

_CASE_IDS = (
    "graph",
    "next courses",
    "recommendations",
)

_CACHED_READS = (
    _CachedRead(
        "/api/search",
        {"query": "synthetic query", "display_language": "fi"},
        SearchRequest,
        search_commands,
        "run_search_command",
    ),
    _CachedRead(
        "/api/comparison",
        {"course_a": "COMP.CS.100", "course_b": "COMP.CS.200"},
        ComparisonRequest,
        comparison_commands,
        "run_course_comparison_command",
    ),
    _CachedRead(
        "/api/prerequisites",
        {"target_code": "COMP.CS.100"},
        PrerequisiteGraphRequest,
        prerequisite_commands,
        "run_prerequisite_command",
        with_compact_nodes=True,
    ),
    _CachedRead(
        "/api/next-courses",
        {"display_language": "fi"},
        NextCoursesRequest,
        next_courses_commands,
        "run_next_courses_command",
    ),
    _CachedRead(
        "/api/recommendations",
        {"display_language": "fi"},
        RecommendationsRequest,
        recommendation_commands,
        "run_recommendations_command",
    ),
    _CachedRead(
        "/api/course-summaries",
        {"identifiers": ["group-a", "group-a"]},
        BaseModel,
        lookup_commands,
        "run_course_summaries_command",
        positional=(("group-a", "group-a"),),
    ),
    _CachedRead("/api/catalogue", {}, BaseModel, lookup_commands, "run_catalogue_command"),
    _CachedRead(
        "/api/study-structure",
        {
            "root_group_ids": ["module-a", "module-b"],
            "module_versions": {"module-a": "module-a-v1"},
        },
        BaseModel,
        study_structure_commands,
        "run_study_structures_command",
        positional=(("module-a", "module-b"),),
    ),
)
_CACHED_IDS = (
    "search",
    "comparison",
    "graph",
    "next-courses",
    "recommendations",
    "summaries",
    "catalogue",
    "structures",
)


def _policy_parameters() -> list[pytest.param]:
    """Return one parameter per site policy and requested value on one route."""
    parameters: list[pytest.param] = []
    for case_id, case in zip(_CASE_IDS, _INFERENCE_CASES, strict=True):
        for site in (False, True):
            for requested in (False, True):
                parameters.append(
                    pytest.param(
                        case,
                        site,
                        requested,
                        id=(
                            f"{case_id.replace(' ', '-')}"
                            f"-site-{'on' if site else 'off'}"
                            f"-requested-{'on' if requested else 'off'}"
                        ),
                    )
                )
    for site in (False, True):
        parameters.append(
            pytest.param(
                _SEARCH_CASE,
                site,
                None,
                id=f"search-site-{'on' if site else 'off'}",
            )
        )
    return parameters


def _policy_expected(
    case: _PolicyCase,
    body: dict[str, object],
    site_enabled: bool,
    requested: bool | None,
    serving,
) -> dict[str, object]:
    """Return the exact keyword arguments a policy route passes to its command boundary."""
    expected = case.model.model_validate(body).model_dump()
    expected[case.policy_field] = (
        site_enabled and bool(requested) if case.requested_field is not None else site_enabled
    )
    if case.drawing_limit:
        expected["max_drawing_elements"] = _DRAWING_LIMIT
    expected["database_settings"] = serving.settings
    expected.update(_retained_cache_arguments(case.endpoint, serving))
    return expected


@pytest.mark.parametrize(
    "case",
    _FEATURE_READ_CASES,
    ids=("comparison", "recommendations"),
)
def test_disabled_embedding_features_refuse_reads(
    monkeypatch: pytest.MonkeyPatch, case: _FeatureReadCase
) -> None:
    """An embeddings-off site refuses both embedding reads before its command runs."""
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "0")
    monkeypatch.setenv("WEB_INFERENCE_ENABLED", "1")

    def refuse_reached_command(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(f"{case.command} ran while embeddings are off")

    monkeypatch.setattr(case.owner, case.command, refuse_reached_command)

    response = TestClient(app).post(case.endpoint, json=case.body)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("case", "site_enabled", "requested"),
    _policy_parameters(),
)
def test_site_feature_switch_bounds_delegated_policy(
    monkeypatch: pytest.MonkeyPatch,
    case: _PolicyCase,
    site_enabled: bool,
    requested: bool | None,
) -> None:
    """Each read delegates once with its site's feature policy applied to the requested value."""
    site_value = "1" if site_enabled else "0"
    monkeypatch.setenv(
        "WEB_EMBEDDINGS_ENABLED",
        site_value if case.site_switch == "WEB_EMBEDDINGS_ENABLED" else "1",
    )
    monkeypatch.setenv(
        "WEB_INFERENCE_ENABLED",
        site_value if case.site_switch == "WEB_INFERENCE_ENABLED" else "1",
    )
    monkeypatch.setenv("PREREQUISITE_GRAPH_MAX_ELEMENTS", str(_DRAWING_LIMIT))
    monkeypatch.setenv("PREREQUISITE_PATH_MAX_COMPACT_NODES", str(_COMPACT_NODE_LIMIT))
    monkeypatch.setenv(SERVING_GENERATION_ENV, "a" * 32)
    body = {**case.body}
    if case.requested_field is not None:
        body[case.requested_field] = requested
    received: list[dict[str, object]] = []
    serving = resolve_serving_dataset()

    def sentinel(**kwargs: object) -> _SentinelReport:
        received.append(kwargs)
        return _SentinelReport(payload="sentinel")

    monkeypatch.setattr(case.owner, case.command, sentinel)

    response = TestClient(app).post(case.endpoint, json=body)

    assert response.status_code == 200
    expected_response: dict[str, object] = {
        "payload": "sentinel",
        "dataset_identity": serving.identity,
    }
    if case.drawing_limit:
        expected_response["max_compact_nodes"] = _COMPACT_NODE_LIMIT
    assert response.json() == expected_response
    assert received == [_policy_expected(case, body, site_enabled, requested, serving)]


def _write_dataset(state: Path, receipt: DatasetReceipt) -> None:
    """Publish one dataset receipt in its own confined directory."""
    directory = state / "datasets" / receipt.dataset_id
    directory.mkdir(mode=0o700, parents=True)
    atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))


def _select_dataset(state: Path, dataset_id: str) -> None:
    """Point the real selected-dataset pointer at one written receipt."""
    atomic_write_private_text(
        state / "selected-dataset.json",
        administrative_json(SelectedDatasetPointer(schema_version=1, dataset_id=dataset_id)),
    )


class _Recorded:
    """One command spy invocation with its positional and keyword arguments."""

    def __init__(self, args: tuple[object, ...], kwargs: dict[str, object]) -> None:
        self.args = args
        self.kwargs = kwargs


def _cached_read_expected(
    case: _CachedRead, serving
) -> tuple[tuple[object, ...], dict[str, object]]:
    """Return the exact call a cached route makes on its command boundary."""
    if case.endpoint == "/api/study-structure":
        kwargs: dict[str, object] = {
            "allow_unavailable": False,
            "module_versions": case.body["module_versions"],
        }
    elif case.endpoint in (
        "/api/search",
        "/api/comparison",
        "/api/prerequisites",
        "/api/next-courses",
        "/api/recommendations",
    ):
        kwargs = case.model.model_validate(case.body).model_dump()
    else:
        kwargs = {}
    if case.endpoint == "/api/search":
        kwargs["include_semantic"] = True
    if case.endpoint == "/api/prerequisites":
        kwargs["max_drawing_elements"] = _DRAWING_LIMIT
    kwargs["database_settings"] = serving.settings
    kwargs.update(_retained_cache_arguments(case.endpoint, serving))
    return case.positional, kwargs


@pytest.mark.parametrize("selected", (False, True), ids=("raw", "selected"))
@pytest.mark.parametrize("case", _CACHED_READS, ids=_CACHED_IDS)
def test_cached_reads_report_one_serving_dataset_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, selected: bool, case: _CachedRead
) -> None:
    """Every cached read reports the identity of the database it resolved, and only that."""
    state = tmp_path / "state"
    initial = sample_receipt(database_name="selected_one")
    returned = DatasetReceipt(
        dataset_id="1" * 32,
        database_name="selected_two",
        predecessor_id="0" * 32,
        kind="returned",
        dump_sha256="d" * 64,
        verification=initial.verification,
    )
    for receipt in (initial, returned):
        _write_dataset(state, receipt)
    _select_dataset(state, initial.dataset_id)
    monkeypatch.setattr(administration, "repository_root", lambda: tmp_path)
    monkeypatch.setenv("ADMIN_STATE_ROOT", "state")
    monkeypatch.setenv("PREREQUISITE_PATH_MAX_COMPACT_NODES", str(_COMPACT_NODE_LIMIT))
    monkeypatch.setenv("PREREQUISITE_GRAPH_MAX_ELEMENTS", str(_DRAWING_LIMIT))
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "1")
    monkeypatch.setenv("WEB_INFERENCE_ENABLED", "1")
    monkeypatch.setenv("POSTGRES_DB", "raw_test")
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "1" if selected else "0")
    generation = "a" * 32
    monkeypatch.setenv(SERVING_GENERATION_ENV, generation)
    calls: list[_Recorded] = []

    def sentinel(*args: object, **kwargs: object) -> _SentinelReport:
        calls.append(_Recorded(args, kwargs))
        return _SentinelReport(payload="sentinel")

    monkeypatch.setattr(case.owner, case.command, sentinel)
    client = TestClient(app)
    initial_id = initial.dataset_id if selected else None
    initial_identity = json_sha256([generation, initial_id], ensure_ascii=False)

    feature = client.post("/api/features", json={})
    assert feature.status_code == 200
    assert feature.json()["dataset_identity"] == initial_identity
    response = client.post(case.endpoint, json=case.body)
    assert response.status_code == 200
    expected_response: dict[str, object] = {
        "payload": "sentinel",
        "dataset_identity": initial_identity,
    }
    if case.with_compact_nodes:
        expected_response["max_compact_nodes"] = _COMPACT_NODE_LIMIT
    assert response.json() == expected_response
    assert len(calls) == 1
    served = calls[0].kwargs["database_settings"]
    assert served.postgres_db == ("selected_one" if selected else "raw_test")
    args, kwargs = _cached_read_expected(case, resolve_serving_dataset())
    assert (calls[0].args, calls[0].kwargs) == (args, kwargs)
    # The identity is an opaque digest, and no connection detail reaches either response.
    assert len(initial_identity) == 64
    for name in ("raw_test", "selected_one", "postgres", "password"):
        assert name not in feature.text
        assert name not in response.text

    # A fresh serving generation changes the identity in both database modes.
    generation = "b" * 32
    monkeypatch.setenv(SERVING_GENERATION_ENV, generation)
    next_identity = json_sha256([generation, initial_id], ensure_ascii=False)
    assert client.post("/api/features", json={}).json()["dataset_identity"] == next_identity
    response = client.post(case.endpoint, json=case.body)
    assert response.json()["dataset_identity"] == next_identity
    assert calls[-1].kwargs["database_settings"].postgres_db == (
        "selected_one" if selected else "raw_test"
    )

    # A selected receipt switch changes the identity without changing the generation.
    if selected:
        _select_dataset(state, returned.dataset_id)
        switched = json_sha256([generation, returned.dataset_id], ensure_ascii=False)
        assert switched != next_identity
        assert client.post("/api/features", json={}).json()["dataset_identity"] == switched
        response = client.post(case.endpoint, json=case.body)
        assert response.json()["dataset_identity"] == switched
        assert calls[-1].kwargs["database_settings"].postgres_db == "selected_two"

    # The ordinary paired resolver and the feature read agree on the resolved identity.
    features = json.loads(client.post("/api/features", json={}).text)
    assert set(features) == {"embeddings_enabled", "inference_enabled", "dataset_identity"}
    assert resolve_serving_dataset().identity == features["dataset_identity"]


@pytest.mark.parametrize(
    ("target", "measured"),
    (("group-root", True), ("COMP.CS.100", True), ("comp.cs.100", False)),
    ids=("canonical-id", "official-code", "other-spelling"),
)
def test_graph_read_marks_the_root_id_and_its_official_code_for_measurement(
    monkeypatch: pytest.MonkeyPatch, target: str, measured: bool
) -> None:
    """A graph read is marked for measurement under the root's canonical id or exact official code."""
    monkeypatch.setenv(SERVING_GENERATION_ENV, "a" * 32)
    monkeypatch.setattr(
        prerequisite_commands,
        "run_prerequisite_command",
        lambda **_kwargs: _RootedReport(payload="graph"),
    )

    response = TestClient(app).post("/api/prerequisites", json={"target_code": target})

    assert response.status_code == 200
    assert (response.headers.get(MEASURE_GRAPH_HEADER) == "1") is measured
