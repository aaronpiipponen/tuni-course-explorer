"""Single synchronous HTTP client for the pinned loopback TranslateGemma runtime.

This is the only application path that calls the offline translation model. It posts the one
official-template chat-completions request shape, retries within configured
limits, and validates untrusted model output through strict typed models before returning any
text. An error carries none of the source text, generated text, prompts, response bodies or
credentials.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from course_explorer.config import TranslationSettings
from course_explorer.enums import TeachingTextLanguage
from course_explorer.http_retry import decode_json_response, request_json_with_retries


class TranslationRequestError(RuntimeError):
    """Terminal transport or HTTP failure against the translation runtime."""


class TranslationContractError(ValueError):
    """Malformed or non-conforming translation response contract."""


class _ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    role: str
    content: str


class _ChatChoice(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    index: int
    message: _ChatMessage
    finish_reason: str


class _ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    object: str
    model: str
    system_fingerprint: str
    choices: list[_ChatChoice]


class TranslationProvider:
    """One HTTP client that returns exact validated translation text for one request."""

    def __init__(
        self,
        settings: TranslationSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        before_request: Callable[[], bool] | None = None,
        request_scope: Callable[[float], AbstractContextManager[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._before_request = before_request
        self._request_scope = (
            None
            if request_scope is None
            else (lambda: request_scope(settings.translation_request_timeout_seconds))
        )
        self._client = httpx.Client(
            base_url=str(settings.base_url),
            timeout=settings.translation_request_timeout_seconds,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )

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

    @staticmethod
    def _validate_inputs(
        text: str,
        source_language: TeachingTextLanguage,
        target_language: TeachingTextLanguage,
    ) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("translation text must be a non-blank string")
        if source_language is target_language:
            raise ValueError("translation source and target languages must differ")

    def _payload(
        self,
        text: str,
        source_language: TeachingTextLanguage,
        target_language: TeachingTextLanguage,
    ) -> dict:
        return {
            "model": self._settings.translation_model_alias,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "source_lang_code": source_language.value,
                            "target_lang_code": target_language.value,
                            "text": text,
                        }
                    ],
                }
            ],
            "chat_template_kwargs": {
                "source_lang_code": source_language.value,
                "target_lang_code": target_language.value,
            },
            "temperature": self._settings.translation_temperature,
            "max_tokens": self._settings.translation_max_tokens,
            "stream": False,
        }

    def _validate_response(self, response: httpx.Response) -> str:
        value = decode_json_response(
            response,
            error_prefix="POST /v1/chat/completions",
            contract_error=TranslationContractError,
        )
        try:
            parsed = _ChatCompletionResponse.model_validate(value)
        except ValidationError as exc:
            raise TranslationContractError(
                "POST /v1/chat/completions: response violates translation response schema"
            ) from exc

        expected_suffix = f"-{self._settings.translation_runtime_revision[:9]}"
        if (
            parsed.object != "chat.completion"
            or parsed.model != self._settings.translation_model_alias
            or not parsed.system_fingerprint.strip()
            or not parsed.system_fingerprint.endswith(expected_suffix)
            or len(parsed.choices) != 1
            or parsed.choices[0].index != 0
            or parsed.choices[0].message.role != "assistant"
            or parsed.choices[0].finish_reason != "stop"
        ):
            raise TranslationContractError(
                "POST /v1/chat/completions: response does not match the configured runtime contract"
            )
        content = parsed.choices[0].message.content
        if not content.strip() or "\x00" in content:
            raise TranslationContractError(
                "POST /v1/chat/completions: response content is blank or malformed"
            )
        return content

    def translate(
        self,
        text: str,
        *,
        source_language: TeachingTextLanguage,
        target_language: TeachingTextLanguage,
    ) -> str:
        """POST one typed chat-completion request and return exact validated content."""
        if self._client.is_closed:
            raise TranslationRequestError("POST /v1/chat/completions: client is closed")
        self._validate_inputs(text, source_language, target_language)
        payload = self._payload(text, source_language, target_language)
        return request_json_with_retries(
            request=lambda: self._client.post("v1/chat/completions", json=payload),
            validate=self._validate_response,
            max_attempts=self._settings.translation_max_attempts,
            retry_backoff_seconds=self._settings.translation_retry_backoff_seconds,
            sleep=self._sleep,
            error_prefix="POST /v1/chat/completions",
            request_error=TranslationRequestError,
            contract_error=TranslationContractError,
            retry_contract_errors=True,
            before_request=self._before_request,
            request_scope=self._request_scope,
        )
