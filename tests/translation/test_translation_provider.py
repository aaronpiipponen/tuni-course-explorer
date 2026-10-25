"""HTTP contract tests for the loopback TranslationProvider."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from course_explorer.config import TranslationSettings
from course_explorer.enums import TeachingTextLanguage
from course_explorer.http_retry import RequestNotStarted
from course_explorer.translation.provider import (
    TranslationContractError,
    TranslationProvider,
    TranslationRequestError,
)
from tests.support import settings_factory

FINGERPRINT = "b7823-bb02f74c6"
CONTENT = "This course teaches the fundamentals of linear algebra."


def settings(**overrides: Any) -> TranslationSettings:
    values: dict[str, object] = {
        "TRANSLATION_ARTIFACT_PATH": "models/translategemma-12b-it-Q5_K_M.gguf",
        **overrides,
    }
    return settings_factory(TranslationSettings, **values)


def completion(
    content: str = CONTENT,
    *,
    model: str = "translategemma-12b-it",
    fingerprint: str = FINGERPRINT,
    **overrides: Any,
) -> httpx.Response:
    body: dict[str, Any] = {
        "object": "chat.completion",
        "model": model,
        "system_fingerprint": fingerprint,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    body.update(overrides)
    return httpx.Response(200, content=json.dumps(body).encode())


def test_translation_provider_returns_exact_content() -> None:
    """The provider returns exact whitespace-bearing content as-is."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return completion(content="  " + CONTENT + "  ")

    with TranslationProvider(settings(), transport=httpx.MockTransport(handler)) as provider:
        result = provider.translate(
            "Tämä kurssi opettaa lineaarialgebran perusteet.",
            source_language=TeachingTextLanguage.FI,
            target_language=TeachingTextLanguage.EN,
        )

    assert result == "  " + CONTENT + "  "
    assert len(requests) == 1


def test_translation_provider_retries_transport_status_and_contract_failures() -> None:
    """A contract-invalid 200 response retries once and then returns the valid content."""
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return completion(content="")
        return completion()

    with TranslationProvider(
        settings(TRANSLATION_MAX_ATTEMPTS=2),
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    ) as provider:
        result = provider.translate(
            "lähde",
            source_language=TeachingTextLanguage.FI,
            target_language=TeachingTextLanguage.EN,
        )

    assert result == CONTENT
    assert len(attempts) == 2
    assert sleeps


def test_translation_provider_stops_on_nonretryable_status_without_leaking_body() -> None:
    """A terminal 4xx fails once and its body never appears in the error message."""
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, content=b"secret-response-body")

    with TranslationProvider(
        settings(), transport=httpx.MockTransport(handler), sleep=sleeps.append
    ) as provider:
        with pytest.raises(TranslationRequestError) as error:
            provider.translate(
                "lähde",
                source_language=TeachingTextLanguage.FI,
                target_language=TeachingTextLanguage.EN,
            )

    assert attempts == 1
    assert sleeps == []
    assert "secret-response-body" not in str(error.value)


def test_translation_provider_rejects_wrong_model_runtime_choice_role_finish_or_content() -> None:
    """Runtime identity and response shape are strict. Incomplete output is never returned."""
    cases: list[httpx.Response] = [
        completion(model="other-model"),
        completion(fingerprint="b7823-fffffffff"),
        completion(content=""),
    ]
    wrong_choice = completion()
    body = json.loads(wrong_choice.content)
    body["choices"][0]["finish_reason"] = "length"
    cases.append(httpx.Response(200, content=json.dumps(body).encode()))

    for response in cases:

        def handler(request: httpx.Request, response: httpx.Response = response) -> httpx.Response:
            return response

        with TranslationProvider(
            settings(TRANSLATION_MAX_ATTEMPTS=1), transport=httpx.MockTransport(handler)
        ) as provider:
            with pytest.raises(TranslationContractError):
                provider.translate(
                    "lähde",
                    source_language=TeachingTextLanguage.FI,
                    target_language=TeachingTextLanguage.EN,
                )


def test_translation_provider_control_stops_contract_retry() -> None:
    """A control request during backoff raises the pending contract error with no retry."""
    calls = 0
    admitted = {"value": True}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"not-json")

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        admitted["value"] = False

    with TranslationProvider(
        settings(TRANSLATION_MAX_ATTEMPTS=3),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        before_request=lambda: admitted["value"],
    ) as provider:
        with pytest.raises(TranslationContractError):
            provider.translate(
                "lähde",
                source_language=TeachingTextLanguage.FI,
                target_language=TeachingTextLanguage.EN,
            )

    assert calls == 1
    assert sleeps


def test_translation_provider_control_declines_initial_request_without_io() -> None:
    """A refused admission raises the fixed cooperative signal before any request."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return completion()

    with TranslationProvider(
        settings(),
        transport=httpx.MockTransport(handler),
        before_request=lambda: False,
    ) as provider:
        with pytest.raises(RequestNotStarted):
            provider.translate(
                "lähde",
                source_language=TeachingTextLanguage.FI,
                target_language=TeachingTextLanguage.EN,
            )
    assert calls == 0
