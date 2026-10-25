"""HTTP contract tests for the loopback StructuredJsonProvider and RerankProvider."""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest

from course_explorer.config import (
    InferenceRerankSettings,
    InferenceSettings,
)
from course_explorer.http_retry import RequestNotStarted
from course_explorer.inference.evidence import InferenceRequestEvidence
from course_explorer.inference.failures import TargetPreparationFailure
from course_explorer.inference.provider import (
    InferenceContractError,
    InferenceRequestError,
    InferenceTargetRequestError,
    RerankProvider,
    StructuredJsonProvider,
)
from tests.inference._http_support import completion_response
from tests.support import settings_factory

RUNTIME_REVISION = "4ff829ec2e2f526aa6afba529eebbfb3ef1f95ec"
FINGERPRINT = "b8142-" + RUNTIME_REVISION[:9]
MODEL_ALIAS = "qwen3.8-27b-iq3-mix-128k-mtp"
CONTENT = json.dumps(
    {
        "required": [],
        "recommended": [],
        "equivalence": [],
        "routing": {"confidence": 1.0, "flags": [], "suppressed": []},
    }
)
JSON_SCHEMA: dict[str, object] = {"type": "object", "additionalProperties": False}


def settings(**overrides: Any) -> InferenceSettings:
    return settings_factory(InferenceSettings, **overrides)


def open_provider(s: InferenceSettings, **kwargs: Any) -> StructuredJsonProvider:
    """Open the first ordered (MTP) local variant provider for one provider-contract test."""
    return StructuredJsonProvider(s, s.inference_local_variants[0], **kwargs)


def completion(content: str = CONTENT, **overrides: Any) -> httpx.Response:
    return completion_response(content, model=MODEL_ALIAS, fingerprint=FINGERPRINT, **overrides)


def call(provider: StructuredJsonProvider, **overrides: Any) -> Any:
    arguments: dict[str, Any] = {
        "system_prompt": "system contract",
        "user_prompt": "synthetic target request",
        "schema_name": "inference_target_result_v2",
        "json_schema": JSON_SCHEMA,
        "attempt_ordinal": 1,
        "first_attempt": True,
    }
    arguments.update(overrides)
    return provider.generate_json(**arguments)


def test_structured_json_provider_returns_content_attribution_and_metrics() -> None:
    """The provider returns the raw and parsed content with attribution and Decimal token rates."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return completion()

    with open_provider(settings(), transport=httpx.MockTransport(handler)) as provider:
        generation = call(provider)

    assert len(requests) == 1
    assert generation.raw_json == CONTENT
    assert generation.parsed_json == json.loads(CONTENT)
    assert generation.model == MODEL_ALIAS
    assert generation.system_fingerprint == FINGERPRINT
    assert generation.prompt_tokens == 120
    assert generation.completion_tokens == 45
    assert generation.prompt_tokens_per_second == Decimal("512.5")
    assert generation.completion_tokens_per_second == Decimal("42.75")


def _malformed_inner_json() -> httpx.Response:
    return completion(content='{"private":"synthetic-private-output-marker"')


@pytest.mark.parametrize(
    ("response_factory", "expected_error"),
    [
        (lambda: httpx.Response(429, content=b"slow down"), InferenceTargetRequestError),
        (lambda: httpx.Response(503, content=b"unavailable"), InferenceTargetRequestError),
        (lambda: httpx.Response(404, content=b"secret-response-body"), InferenceRequestError),
        (_malformed_inner_json, InferenceContractError),
    ],
)
def test_structured_json_provider_performs_one_request_without_leaking_bodies(
    response_factory: Callable[[], httpx.Response], expected_error: type[Exception]
) -> None:
    """One call makes exactly one HTTP attempt and surfaces a safe classified error.

    A retryable status, a terminal status, and a malformed successful envelope are each a single
    attempt with no provider-local sleep. The whole-target writer owns the retry loop. No response
    body, prompt text, or model output is reachable from the raised error or its chain.
    """
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return response_factory()

    with open_provider(
        settings(), transport=httpx.MockTransport(handler), sleep=sleeps.append
    ) as provider:
        with pytest.raises(expected_error) as error:
            call(provider)

    assert len(attempts) == 1
    assert sleeps == []
    rendered = "".join(traceback.format_exception(error.value))
    assert "secret-response-body" not in rendered
    assert "synthetic target request" not in rendered
    assert "synthetic-private-output-marker" not in rendered
    assert "additionalProperties" not in rendered


def test_structured_json_provider_counts_prompt_tokens_through_template_and_tokenize() -> None:
    """The tokenizer authority renders the same template and tokenizes the returned prompt."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "rendered prompt", "extra": "ignored"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1, 2, 3], "extra": "ignored"})
        raise AssertionError(request.url.path)

    request_evidence = InferenceRequestEvidence(
        system_prompt="system contract",
        user_prompt="synthetic target request",
        schema_name="inference_target_result_v2",
        json_schema=JSON_SCHEMA,
    )
    with open_provider(settings(), transport=httpx.MockTransport(handler)) as provider:
        assert provider.count_prompt_tokens(request_evidence) == 3

    tokenize = next(request for request in requests if request.url.path == "/tokenize")
    assert json.loads(tokenize.content)["content"] == "rendered prompt"

    # A bounded preparation loop retries a transient target error and returns the exact count.
    transient_calls = {"template": 0, "tokenize": 0}

    def transient_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/apply-template":
            transient_calls["template"] += 1
            return httpx.Response(200, json={"prompt": "rendered prompt"})
        transient_calls["tokenize"] += 1
        if transient_calls["tokenize"] == 1:
            return httpx.Response(503, content=b"busy")
        return httpx.Response(200, json={"tokens": [1, 2, 3]})

    with open_provider(
        settings(), transport=httpx.MockTransport(transient_handler), sleep=lambda _s: None
    ) as provider:
        assert provider.count_prompt_tokens(request_evidence) == 3
    assert transient_calls == {"template": 2, "tokenize": 2}

    # A malformed response exhausts the bounded actions with one content-free summary and no
    # endpoint-times-action retry multiplication.
    preparation_calls = {"template": 0, "tokenize": 0}

    def malformed_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/apply-template":
            preparation_calls["template"] += 1
            return httpx.Response(200, json={"prompt": "rendered"})
        preparation_calls["tokenize"] += 1
        return httpx.Response(200, json={"tokens": "not-a-list"})

    with pytest.raises(TargetPreparationFailure) as preparation_error:
        with open_provider(
            settings(),
            transport=httpx.MockTransport(malformed_handler),
            sleep=lambda _s: None,
        ) as provider:
            provider.count_prompt_tokens(request_evidence)
    assert preparation_error.value.exhausted is True
    assert preparation_error.value.attempt_count == 3
    assert preparation_error.value.reason == "provider_output"
    assert preparation_calls == {"template": 3, "tokenize": 3}

    # A transport failure propagates as a request error so a caller never silently falls back.
    transport_calls = 0

    def transport_handler(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        raise httpx.ConnectError("boom")

    with pytest.raises(InferenceRequestError):
        with open_provider(
            settings(INFERENCE_MAX_ATTEMPTS=1),
            transport=httpx.MockTransport(transport_handler),
        ) as provider:
            provider.count_prompt_tokens(request_evidence)
    assert transport_calls == 1


def rerank_settings(**overrides: Any) -> InferenceRerankSettings:
    """Build one valid qualified rerank settings object for the cross-encoder client tests."""
    return settings_factory(InferenceRerankSettings, **overrides)


def rerank_response(
    *,
    results: object | None = None,
) -> httpx.Response:
    """Build one valid single-document rerank response body."""
    if results is None:
        results = [{"index": 0, "relevance_score": 0.75}]
    return httpx.Response(200, content=json.dumps({"results": results}).encode())


def test_rerank_provider_validates_one_finite_indexed_score_and_redacted_failures() -> None:
    """One query/document request, one finite indexed score, and redacted terminal failures."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return rerank_response()

    with RerankProvider(rerank_settings(), transport=httpx.MockTransport(handler)) as provider:
        score = provider.score("target text", "candidate text")

    assert score.index == 0
    assert score.score == 0.75
    assert len(requests) == 1

    # HTTP failures are terminal, bounded, and never leak bodies or pair text.
    def http_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"secret-response-body")

    with RerankProvider(rerank_settings(), transport=httpx.MockTransport(http_handler)) as provider:
        with pytest.raises(InferenceTargetRequestError) as http_error:
            provider.score("secret-query", "secret-document")
    assert type(http_error.value) is InferenceTargetRequestError
    message = str(http_error.value)
    assert "secret-response-body" not in message
    assert "secret-query" not in message
    assert "secret-document" not in message

    # Wrong-index, multi-item, and non-finite responses are contract failures.
    cases: list[httpx.Response] = [
        rerank_response(results=[{"index": 1, "relevance_score": 0.5}]),
        rerank_response(
            results=[{"index": 0, "relevance_score": 0.5}, {"index": 1, "relevance_score": 0.4}]
        ),
        httpx.Response(200, content=b'{"results": [{"index": 0, "relevance_score": NaN}]}'),
    ]
    for response in cases:

        def case_handler(request: httpx.Request, body: httpx.Response = response) -> httpx.Response:
            return body

        with RerankProvider(
            rerank_settings(), transport=httpx.MockTransport(case_handler)
        ) as provider:
            with pytest.raises(InferenceContractError):
                provider.score("query", "document")


def test_rerank_control_declines_initial_request_without_io() -> None:
    """A refused admission prevents the single rerank post entirely."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return rerank_response()

    with RerankProvider(
        rerank_settings(),
        transport=httpx.MockTransport(handler),
        before_request=lambda: False,
    ) as provider:
        with pytest.raises(RequestNotStarted):
            provider.score("query", "document")
    assert calls == 0
