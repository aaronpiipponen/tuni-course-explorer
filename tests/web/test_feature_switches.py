"""Server enforcement proofs for the two per-site feature switches."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from course_explorer.comparison import commands as comparison_commands
from course_explorer.next_courses import commands as next_courses_commands
from course_explorer.prerequisite import commands as prerequisite_commands
from course_explorer.recommendations import commands as recommendation_commands
from course_explorer.search import commands as search_commands
from course_explorer_web.app import app
from course_explorer_web.routes.next_courses import NextCoursesRequest
from course_explorer_web.routes.prerequisite_inputs import PrerequisitesRequest
from course_explorer_web.routes.recommendations import RecommendationsRequest
from course_explorer_web.routes.search import SearchRequest

_DRAWING_LIMIT = 137


class _SentinelReport(BaseModel):
    """The one small serializable report a spied command boundary returns."""

    payload: str


class _FeatureReadCase:
    """One embeddings-off read, its minimal closed request and its owning command boundary."""

    __slots__ = ("body", "command", "endpoint", "owner")

    def __init__(self, endpoint: str, body: dict[str, object], owner: object, command: str) -> None:
        self.endpoint = endpoint
        self.body = body
        self.owner = owner
        self.command = command


class _PolicyCase:
    """One read, its closed request model, its owning command and the site policy it applies."""

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
        drawing_limit: bool,
        *,
        site_switch: str,
        policy_field: str,
        requested_field: str | None,
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
        PrerequisitesRequest,
        prerequisite_commands,
        "run_prerequisite_command",
        True,
        site_switch="WEB_INFERENCE_ENABLED",
        policy_field="include_inferred",
        requested_field="include_inferred",
    ),
    _PolicyCase(
        "/api/minimum-route",
        {"target_code": "COMP.CS.100"},
        PrerequisitesRequest,
        prerequisite_commands,
        "run_minimum_route_command",
        False,
        site_switch="WEB_INFERENCE_ENABLED",
        policy_field="include_inferred",
        requested_field="include_inferred",
    ),
    _PolicyCase(
        "/api/next-courses",
        {"display_language": "fi"},
        NextCoursesRequest,
        next_courses_commands,
        "run_next_courses_command",
        False,
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
        False,
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
    False,
    site_switch="WEB_EMBEDDINGS_ENABLED",
    policy_field="include_semantic",
    requested_field=None,
)

_CASE_IDS = (
    "graph",
    "minimum route",
    "next courses",
    "recommendations",
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
    body = {**case.body}
    if case.requested_field is not None:
        body[case.requested_field] = requested
    received: list[dict[str, object]] = []

    def sentinel(**kwargs: object) -> _SentinelReport:
        received.append(kwargs)
        return _SentinelReport(payload="sentinel")

    monkeypatch.setattr(case.owner, case.command, sentinel)

    response = TestClient(app).post(case.endpoint, json=body)

    assert response.status_code == 200
    assert response.json() == {"payload": "sentinel"}
    expected = case.model.model_validate(body).model_dump()
    expected[case.policy_field] = (
        site_enabled and bool(requested) if case.requested_field is not None else site_enabled
    )
    if case.drawing_limit:
        expected["max_drawing_elements"] = _DRAWING_LIMIT
    assert received == [expected]
