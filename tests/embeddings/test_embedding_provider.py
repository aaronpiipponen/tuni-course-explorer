"""HTTP contract tests for the loopback EmbeddingProvider."""

import json
from typing import Any

import httpx
import pytest

from course_explorer.config import EmbeddingSettings
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.embeddings.provider import (
    EmbeddingContractError,
    EmbeddingProvider,
    EmbeddingRequestError,
)
from course_explorer.http_retry import RequestNotStarted
from tests.support import settings_factory


def settings(**overrides: Any) -> EmbeddingSettings:
    values: dict[str, object] = {
        "EMBEDDING_CONTEXT_SIZE": 1024,
        "EMBEDDING_REQUEST_TIMEOUT_SECONDS": 30,
        "EMBEDDING_ARTIFACT_URL": "https://example.test/model.gguf",
        "EMBEDDING_ARTIFACT_PATH": "models/model.gguf",
        **overrides,
    }
    return settings_factory(EmbeddingSettings, **values)


def vector(*components: float) -> list[float]:
    """Build one full-length vector keeping its distinctive leading components."""
    return [*components, *([0.0] * (COURSE_EMBEDDING_DIMENSION - len(components)))]


def embedding_response(entries: list[dict[str, Any]], **extra: Any) -> httpx.Response:
    body = {"data": entries, **extra}
    return httpx.Response(200, content=json.dumps(body).encode())


def nonfinite_response() -> httpx.Response:
    """Build one full-length response vector carrying a single NaN component."""
    body = {
        "data": [
            {"index": 0, "embedding": [float("nan"), *([0.0] * (COURSE_EMBEDDING_DIMENSION - 1))]},
            {"index": 1, "embedding": vector(0.0, 1.0)},
        ]
    }
    return httpx.Response(200, content=json.dumps(body).encode())


def test_embedding_provider_returns_vectors_in_input_order() -> None:
    """Successful responses are reordered by response index, not response position."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return embedding_response(
            [
                {"index": 1, "embedding": vector(0.0, 1.0)},
                {"index": 0, "embedding": vector(1.0, 0.0), "extra": "ignored"},
            ],
            model="BAAI/bge-m3",
            usage={"prompt_tokens": 4},
        )

    with EmbeddingProvider(settings(), transport=httpx.MockTransport(handler)) as provider:
        vectors = provider.embed(["first", "second"])

    assert vectors == (tuple(vector(1.0, 0.0)), tuple(vector(0.0, 1.0)))
    assert len(requests) == 1


def test_embedding_provider_does_not_retry_non_retryable_status() -> None:
    """A terminal 4xx fails once, is never retried, and never echoes the response body."""
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, content=b"secret-response-body")

    with EmbeddingProvider(
        settings(), transport=httpx.MockTransport(handler), sleep=sleeps.append
    ) as provider:
        with pytest.raises(EmbeddingRequestError) as error:
            provider.embed(["query"])

    assert attempts == 1
    assert sleeps == []
    assert "secret-response-body" not in str(error.value)


def test_embedding_provider_rejects_malformed_cardinality_indices_dimensions_and_values() -> None:
    """Every malformed or incomplete response fails loudly with no partial vectors."""
    cases: list[httpx.Response] = [
        embedding_response([{"index": 0, "embedding": vector(1.0, 0.0)}]),  # missing one
        embedding_response(
            [
                {"index": 0, "embedding": [*vector(1.0, 0.0), 9.0]},  # one extra component
                {"index": 1, "embedding": vector(0.0, 1.0)},
            ]
        ),
        nonfinite_response(),
        embedding_response(
            [
                {"index": 0, "embedding": vector(1.0, 0.0)},
                {"index": 1, "embedding": vector(0.0, 1.0)},
            ],
            model="other/model",
        ),
    ]
    for response in cases:

        def handler(request: httpx.Request, response: httpx.Response = response) -> httpx.Response:
            return response

        with EmbeddingProvider(settings(), transport=httpx.MockTransport(handler)) as provider:
            with pytest.raises(EmbeddingContractError):
                provider.embed(["first", "second"])


def test_embedding_provider_control_declines_initial_request_without_io() -> None:
    """A refused admission raises the fixed cooperative signal before any request."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return embedding_response([{"index": 0, "embedding": vector(1.0, 0.0)}])

    with EmbeddingProvider(
        settings(EMBEDDING_MAX_ATTEMPTS=3),
        transport=httpx.MockTransport(handler),
        before_request=lambda: False,
    ) as provider:
        with pytest.raises(RequestNotStarted):
            provider.embed(["query"])
    assert calls == 0


def test_embedding_provider_control_arriving_in_backoff_stops_transport_retry() -> None:
    """Control arriving during backoff raises the safe error with no extra call."""
    calls = 0
    admitted = {"value": True}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("timeout")

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        admitted["value"] = False

    with EmbeddingProvider(
        settings(EMBEDDING_MAX_ATTEMPTS=3),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        before_request=lambda: admitted["value"],
    ) as provider:
        with pytest.raises(EmbeddingRequestError):
            provider.embed(["query"])

    assert calls == 1
    assert sleeps
