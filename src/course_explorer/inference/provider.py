"""Single synchronous HTTP client for the pinned loopback llama.cpp runtime endpoints.

This is the only application path that calls a local inference model. For the primary
structured-generation endpoint it posts exactly one schema-constrained chat-completions request per
call and validates untrusted model output (envelope identity, usage counts, timing rates, and JSON
object shape) before returning it. The whole-target writer owns the retry/control loop. For the
separately pinned cross-encoder rerank endpoint it posts one query/document request per call, opens
one shared session per scoring run, and returns exactly one validated finite indexed score without
any retry or fabricated fallback. It never loads a model in-process, never uses a fallback endpoint or
schema, and never includes prompts, schemas, response bodies, generated text, course text, URL
queries, pair text, or credentials in errors. Target-result semantics remain the caller's boundary.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from decimal import Decimal
from types import TracebackType
from typing import Literal, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from course_explorer.config import (
    InferenceLocalVariantSettings,
    InferenceRerankSettings,
    InferenceSettings,
)
from course_explorer.hashing import parse_strict_json, require_json_compatible
from course_explorer.http_retry import (
    RequestNotStarted,
    decode_json_response,
    request_json_with_retries,
)
from course_explorer.inference.evidence import InferenceRequestEvidence
from course_explorer.inference.failures import FailureReason, TargetPreparationFailure
from course_explorer.validation import require_text as _require_text

_SCHEMA_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_CHAT_PATH = "v1/chat/completions"
_RERANK_PATH = "v1/rerank"
_APPLY_TEMPLATE_PATH = "apply-template"
_TOKENIZE_PATH = "tokenize"


class InferenceRequestError(RuntimeError):
    """Terminal transport or HTTP failure against the inference runtime."""


class InferenceTargetRequestError(InferenceRequestError):
    """A target-scoped request failure (rejected target request, 429/5xx, transient transport)."""


class InferenceContractError(ValueError):
    """Malformed or non-conforming structured-generation response contract."""


class InferenceOutputError(InferenceContractError):
    """Malformed target-scoped model output (outer JSON, envelope, content, usage or timing)."""


_TRANSIENT_TRANSPORT_ERRORS: tuple[type[httpx.TransportError], ...] = (
    httpx.TimeoutException,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)
_TARGET_REQUEST_STATUSES = frozenset({400, 413, 422})


def classify_inference_request_error(
    failure: int | type[httpx.TransportError],
    *,
    target_error: type[InferenceRequestError] = InferenceTargetRequestError,
) -> type[RuntimeError]:
    """Classify one raw request failure as target-scoped or infrastructure by data/type only.

    A target request rejected by the endpoint (HTTP 400/413/422), a retryable 429/5xx, or a
    transient transport failure (timeout, read/write, remote protocol) is target-scoped and returns
    ``target_error``. Every other status (including redirect, authentication/permission and missing
    endpoint) and every other transport type (including ``ConnectError``) is infrastructure and
    returns the base :class:`InferenceRequestError`. This never inspects an error message or walks a
    cause, and it returns only a safe exception class.
    """
    if isinstance(failure, int):
        if failure in _TARGET_REQUEST_STATUSES or failure == 429 or 500 <= failure <= 599:
            return target_error
        return InferenceRequestError
    if issubclass(failure, _TRANSIENT_TRANSPORT_ERRORS):
        return target_error
    return InferenceRequestError


class _StructuredModel(BaseModel):
    """Frozen, closed, strict DTO base for the untrusted provider response boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class StructuredGeneration(_StructuredModel):
    """One validated structured generation: exact content plus runtime identity and metrics."""

    raw_json: str
    parsed_json: dict[str, object]
    model: str
    system_fingerprint: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    prompt_tokens_per_second: Decimal = Field(gt=0)
    completion_tokens_per_second: Decimal = Field(gt=0)


class _ChatMessage(_StructuredModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    role: Literal["assistant"]
    content: str


class _ChatChoice(_StructuredModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    index: Literal[0]
    message: _ChatMessage
    finish_reason: Literal["stop"]


class _Usage(_StructuredModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class _Timings(_StructuredModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    prompt_per_second: float
    predicted_per_second: float


class _ChatCompletionCore(_StructuredModel):
    """The common model/choices/usage envelope shared by every chat-completion client.

    It encodes the one-choice, assistant-role, stop-finish and nonnegative-usage contract in the
    strict DTO itself so both providers parse it once and never recheck those guarantees.
    """

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    model: str
    choices: list[_ChatChoice] = Field(min_length=1, max_length=1)
    usage: _Usage


class _ChatCompletionResponse(_ChatCompletionCore):
    """One local pinned-runtime chat completion: protocol object plus fingerprint and timings."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    object: Literal["chat.completion"]
    system_fingerprint: str
    timings: _Timings


class _ApplyTemplateResponse(_StructuredModel):
    """One validated pinned-runtime ``apply-template`` response carrying the rendered prompt."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    prompt: str


class _TokenizeResponse(_StructuredModel):
    """One validated pinned-runtime ``tokenize`` response carrying integer token ids."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    tokens: list[int]


def _validate_generation_inputs(
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    json_schema: Mapping[str, object],
) -> None:
    """Reject blank/NUL prompts, malformed schema names, and non-object schemas.

    This is the one shared generation-input owner for every structured generation client. It uses the
    neutral text and JSON-graph validators instead of a second copy.
    """
    _require_text(system_prompt, "inference system prompt")
    _require_text(user_prompt, "inference user prompt")
    if not isinstance(schema_name, str) or _SCHEMA_NAME_PATTERN.fullmatch(schema_name) is None:
        raise ValueError("inference schema name must match ^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    if not isinstance(json_schema, Mapping) or json_schema.get("type") != "object":
        raise ValueError("inference JSON schema must be a top-level object schema")
    require_json_compatible(json_schema, "inference JSON schema")


def _validate_chat_content(
    parsed: _ChatCompletionCore,
    *,
    expected_model: str,
    error_prefix: str,
    contract_error: type[InferenceContractError],
) -> tuple[str, dict[str, object]]:
    """Check the configured model alias, meaningful NUL-free content, and one strict JSON object.

    Every concrete client parses its own envelope and then calls this owner, so
    the shared content contract exists once. The raised error carries only the endpoint prefix, never
    prompt text, a response body, a header, or a credential.
    """
    if parsed.model != expected_model:
        raise InferenceContractError(
            f"{error_prefix}: response does not match the configured provider contract"
        )
    content = parsed.choices[0].message.content
    if not content.strip() or "\x00" in content:
        raise contract_error(f"{error_prefix}: response content is blank or malformed")
    content_parse_failed = False
    content_object: object = None
    try:
        content_object = parse_strict_json(content, decimal_numbers=True)
    except ValueError:
        content_parse_failed = True
    if content_parse_failed:
        # Raised after the except block so the raw parse error, whose ``doc`` holds the model
        # content, is never reachable through ``__cause__`` or ``__context__``.
        raise contract_error(f"{error_prefix}: model content is not one valid JSON object")
    if not isinstance(content_object, dict):
        raise contract_error(f"{error_prefix}: model content must be one JSON object")
    return content, content_object


class StructuredJsonProvider:
    """The one live HTTP client for one selected local variant's structured JSON generation.

    It owns the exact schema-constrained request payload, the single-attempt request, the runtime
    identity check, usage/timing extraction, and untrusted duplicate-key/non-finite JSON rejection. The
    token-counting path through the same variant's pinned ``apply-template``/``tokenize`` endpoints
    is the same client, so the local request/validation body exists once.
    """

    def __init__(
        self,
        settings: InferenceSettings,
        variant: InferenceLocalVariantSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        before_request: Callable[[], bool] | None = None,
        request_scope: Callable[[float], AbstractContextManager[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._variant = variant
        self._sleep = sleep
        self._before_request = before_request
        self._request_scope = (
            None
            if request_scope is None
            else (lambda: request_scope(settings.inference_request_timeout_seconds))
        )
        self._client = httpx.Client(
            base_url=str(settings.local_base_url(variant)),
            timeout=settings.inference_request_timeout_seconds,
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

    def _payload(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: Mapping[str, object],
        *,
        attempt_ordinal: int,
        first_attempt: bool,
    ) -> dict[str, object]:
        temperature, seed = self._settings.local_generation_parameters(
            attempt_ordinal, first_attempt=first_attempt
        )
        return {
            "model": self._variant.alias,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                },
            },
            "chat_template_kwargs": self._settings.inference_chat_template_kwargs,
            "temperature": temperature,
            "seed": seed,
            "max_tokens": self._settings.inference_max_tokens,
            "stream": False,
        }

    def _validate_response(self, response: httpx.Response) -> StructuredGeneration:
        value = decode_json_response(
            response,
            error_prefix=f"POST /{_CHAT_PATH}",
            contract_error=InferenceOutputError,
            chain_error=False,
        )
        try:
            parsed = _ChatCompletionResponse.model_validate(value)
        except ValidationError:
            parsed = None
        if parsed is None:
            raise InferenceOutputError(
                f"POST /{_CHAT_PATH}: response violates the inference response schema"
            )

        expected_suffix = f"-{self._settings.inference_runtime_revision[:9]}"
        if not parsed.system_fingerprint.strip() or not parsed.system_fingerprint.endswith(
            expected_suffix
        ):
            raise InferenceContractError(
                f"POST /{_CHAT_PATH}: response does not match the configured runtime contract"
            )
        prompt_rate = Decimal(str(parsed.timings.prompt_per_second))
        completion_rate = Decimal(str(parsed.timings.predicted_per_second))
        if not prompt_rate.is_finite() or not completion_rate.is_finite():
            raise InferenceOutputError(f"POST /{_CHAT_PATH}: response timing values must be finite")
        if prompt_rate <= 0 or completion_rate <= 0:
            raise InferenceOutputError(
                f"POST /{_CHAT_PATH}: response timing values must be positive"
            )

        content, content_object = _validate_chat_content(
            parsed,
            expected_model=self._variant.alias,
            error_prefix=f"POST /{_CHAT_PATH}",
            contract_error=InferenceOutputError,
        )
        return StructuredGeneration(
            raw_json=content,
            parsed_json=content_object,
            model=parsed.model,
            system_fingerprint=parsed.system_fingerprint,
            prompt_tokens=parsed.usage.prompt_tokens,
            completion_tokens=parsed.usage.completion_tokens,
            prompt_tokens_per_second=prompt_rate,
            completion_tokens_per_second=completion_rate,
        )

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: Mapping[str, object],
        attempt_ordinal: int,
        first_attempt: bool,
    ) -> StructuredGeneration:
        """POST exactly one schema-constrained request and return the validated structured generation.

        One call makes exactly one HTTP request. The whole-target writer owns the retry/control loop
        and supplies the reserved durable attempt ordinal and the calculation-first flag, from which
        this client derives the greedy-first/deterministic-seed sampling pair. No provider-local retry
        multiplies the writer's attempts.
        """
        if self._client.is_closed:
            raise InferenceRequestError(f"POST /{_CHAT_PATH}: client is closed")
        _validate_generation_inputs(system_prompt, user_prompt, schema_name, json_schema)
        payload = self._payload(
            system_prompt,
            user_prompt,
            schema_name,
            json_schema,
            attempt_ordinal=attempt_ordinal,
            first_attempt=first_attempt,
        )
        return request_json_with_retries(
            request=lambda: self._client.post(_CHAT_PATH, json=payload),
            validate=self._validate_response,
            max_attempts=1,
            error_prefix=f"POST /{_CHAT_PATH}",
            request_error=InferenceTargetRequestError,
            contract_error=InferenceOutputError,
            retry_contract_errors=False,
            before_request=self._before_request,
            request_scope=self._request_scope,
            classify_request_error=classify_inference_request_error,
        )

    @property
    def max_attempts(self) -> int:
        """Return the configured provider-local whole-preparation action bound."""
        return self._settings.inference_max_attempts

    @property
    def retry_backoff_seconds(self) -> float:
        """Return the configured provider-local backoff between preparation actions."""
        return self._settings.inference_retry_backoff_seconds

    def _validate_apply_template_response(self, response: httpx.Response) -> str:
        """Return the rendered prompt or raise a content-free contract error."""
        value = decode_json_response(
            response,
            error_prefix=f"POST /{_APPLY_TEMPLATE_PATH}",
            contract_error=InferenceOutputError,
            chain_error=False,
        )
        try:
            parsed = _ApplyTemplateResponse.model_validate(value)
        except ValidationError:
            raise InferenceOutputError(
                f"POST /{_APPLY_TEMPLATE_PATH}: response violates the apply-template schema"
            ) from None
        if not parsed.prompt.strip() or "\x00" in parsed.prompt:
            raise InferenceOutputError(
                f"POST /{_APPLY_TEMPLATE_PATH}: rendered prompt is blank or malformed"
            )
        return parsed.prompt

    def _validate_tokenize_response(self, response: httpx.Response) -> int:
        """Return the integer token count or raise a content-free contract error."""
        value = decode_json_response(
            response,
            error_prefix=f"POST /{_TOKENIZE_PATH}",
            contract_error=InferenceOutputError,
            chain_error=False,
        )
        try:
            parsed = _TokenizeResponse.model_validate(value)
        except ValidationError:
            raise InferenceOutputError(
                f"POST /{_TOKENIZE_PATH}: response violates the tokenize schema"
            ) from None
        if not parsed.tokens or any(token < 0 for token in parsed.tokens):
            raise InferenceOutputError(
                f"POST /{_TOKENIZE_PATH}: response must be one non-negative integer token array"
            )
        return len(parsed.tokens)

    def count_prompt_tokens(self, request: InferenceRequestEvidence) -> int:
        """Return the exact rendered prompt token count through a bounded preparation loop.

        One preparation action applies the same chat template and chat-template kwargs used for
        generation and then tokenizes the returned prompt with special-token parsing on and no added
        special tokens. At most ``self.max_attempts`` whole two-endpoint actions run, sharing one
        rendered request and one open client. Each endpoint POST is a single attempt, so the loop
        makes at most ``2 * max_attempts`` preparation HTTP calls and never nests endpoint retries
        inside action retries. Only a target request/output failure retries the action. A control
        refusal after a real error raises the content-free :class:`TargetPreparationFailure` with the
        actual started-action count, and an infrastructure failure propagates immediately.
        """
        if self._client.is_closed:
            raise InferenceRequestError(f"POST /{_APPLY_TEMPLATE_PATH}: client is closed")
        _validate_generation_inputs(
            request.system_prompt, request.user_prompt, request.schema_name, request.json_schema
        )
        template_payload = {
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "chat_template_kwargs": self._settings.inference_chat_template_kwargs,
        }
        max_actions = self.max_attempts
        action_count = 0
        last_reason: FailureReason | None = None
        last_error_type: str | None = None

        def admission_denied() -> bool:
            return self._before_request is not None and not self._before_request()

        def apply_template() -> str:
            def do_post() -> httpx.Response:
                nonlocal action_count
                action_count += 1
                return self._client.post(_APPLY_TEMPLATE_PATH, json=template_payload)

            return request_json_with_retries(
                request=do_post,
                validate=self._validate_apply_template_response,
                max_attempts=1,
                error_prefix=f"POST /{_APPLY_TEMPLATE_PATH}",
                request_error=InferenceTargetRequestError,
                contract_error=InferenceOutputError,
                retry_contract_errors=False,
                chain_transport_error=False,
                before_request=self._before_request,
                request_scope=self._request_scope,
                classify_request_error=classify_inference_request_error,
            )

        def tokenize(rendered_prompt: str) -> int:
            return request_json_with_retries(
                request=lambda: self._client.post(
                    _TOKENIZE_PATH,
                    json={
                        "content": rendered_prompt,
                        "add_special": False,
                        "parse_special": True,
                    },
                ),
                validate=self._validate_tokenize_response,
                max_attempts=1,
                error_prefix=f"POST /{_TOKENIZE_PATH}",
                request_error=InferenceTargetRequestError,
                contract_error=InferenceOutputError,
                retry_contract_errors=False,
                chain_transport_error=False,
                before_request=self._before_request,
                request_scope=self._request_scope,
                classify_request_error=classify_inference_request_error,
            )

        def record(exc: InferenceTargetRequestError | InferenceOutputError) -> None:
            nonlocal last_reason, last_error_type
            last_error_type = type(exc).__name__
            last_reason = (
                "request_failed"
                if isinstance(exc, InferenceTargetRequestError)
                else "provider_output"
            )

        def summary(*, exhausted: bool) -> TargetPreparationFailure:
            assert last_reason is not None and last_error_type is not None
            return TargetPreparationFailure(
                attempt_count=action_count,
                reason=last_reason,
                error_type=last_error_type,
                exhausted=exhausted,
            )

        def after_error(*, action_index: int, final_action: bool) -> None:
            """Prepare one more action, or raise the safe summary when it may not start."""
            if final_action:
                raise summary(exhausted=True)
            if admission_denied():
                raise summary(exhausted=False)
            self._sleep(self.retry_backoff_seconds * 2**action_index)
            if admission_denied():
                raise summary(exhausted=False)

        for action_index in range(max_actions):
            if admission_denied():
                if last_reason is None:
                    raise RequestNotStarted(f"POST /{_APPLY_TEMPLATE_PATH}: request not started")
                raise summary(exhausted=False)
            final_action = action_index == max_actions - 1
            try:
                rendered_prompt = apply_template()
            except (InferenceTargetRequestError, InferenceOutputError) as exc:
                record(exc)
                after_error(action_index=action_index, final_action=final_action)
                continue
            except RequestNotStarted:
                if last_reason is None:
                    raise
                raise summary(exhausted=False)
            try:
                return tokenize(rendered_prompt)
            except (InferenceTargetRequestError, InferenceOutputError) as exc:
                record(exc)
                after_error(action_index=action_index, final_action=final_action)
                continue
            except RequestNotStarted:
                if last_reason is None:
                    raise
                raise summary(exhausted=False)
        raise AssertionError("count_prompt_tokens requires max_attempts >= 1")


class RerankScore(_StructuredModel):
    """One validated cross-encoder score for the single document of one rerank request."""

    index: int
    score: float

    @field_validator("index")
    @classmethod
    def validate_index(cls, value: int) -> int:
        """Require the only possible single-document index, zero."""
        if value != 0:
            raise ValueError("rerank score index must be exactly 0")
        return value

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        """Require one finite real relevance score, never a boolean or non-finite value."""
        if not math.isfinite(value):
            raise ValueError("rerank relevance score must be finite")
        return value


class _RerankResult(_StructuredModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    index: int
    relevance_score: float


class _RerankResponse(_StructuredModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    results: list[_RerankResult]


class RerankProvider:
    """One HTTP client that returns one validated cross-encoder score per call.

    It posts a single query/document request to the configured ``POST /v1/rerank`` endpoint over
    one shared session per worker scoring invocation, uses the configured bounded request timeout,
    and never retries, never fabricates a score, and never leaks pair text, response bodies, or
    credentials in errors. It is distinct from the structured-generation provider: the
    cross-encoder has no chat template, schema, sampling, or generation semantics.
    """

    def __init__(
        self,
        settings: InferenceRerankSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        before_request: Callable[[], bool] | None = None,
        request_scope: Callable[[float], AbstractContextManager[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._before_request = before_request
        self._request_scope = (
            None
            if request_scope is None
            else (lambda: request_scope(settings.inference_rerank_request_timeout_seconds))
        )
        self._client = httpx.Client(
            base_url=str(settings.base_url),
            timeout=settings.inference_rerank_request_timeout_seconds,
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
    def _validate_inputs(query: str, document: str) -> None:
        for label, value in (("query", query), ("document", document)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"rerank {label} must be a nonblank string")
            if "\x00" in value:
                raise ValueError(f"rerank {label} must not contain NUL characters")

    def _validate_rerank_response(self, response: httpx.Response) -> RerankScore:
        """Return one validated finite single-document score or raise a content-free error."""
        value = decode_json_response(
            response,
            error_prefix=f"POST /{_RERANK_PATH}",
            contract_error=InferenceOutputError,
            chain_error=False,
        )
        try:
            parsed = _RerankResponse.model_validate(value)
        except ValidationError:
            raise InferenceOutputError(
                f"POST /{_RERANK_PATH}: response violates the rerank response schema"
            ) from None
        if len(parsed.results) != 1 or parsed.results[0].index != 0:
            raise InferenceOutputError(f"POST /{_RERANK_PATH}: response must score exactly index 0")
        try:
            return RerankScore(
                index=parsed.results[0].index,
                score=parsed.results[0].relevance_score,
            )
        except ValidationError:
            raise InferenceOutputError(
                f"POST /{_RERANK_PATH}: response relevance score must be a finite real number"
            ) from None

    def score(self, query: str, document: str) -> RerankScore:
        """POST one query/document pair and return its single validated finite score.

        The request is never retried: one bounded call with a single attempt is terminal on any
        transport, HTTP, or contract failure and surfaces without response bodies, pair text, or
        credentials, so an incomplete or fabricated score can never be mistaken for a real one. A
        transient transport failure is target-scoped and a ``ConnectError`` is infrastructure, both
        content-safe.
        """
        if self._client.is_closed:
            raise InferenceRequestError(f"POST /{_RERANK_PATH}: client is closed")
        self._validate_inputs(query, document)
        payload = {
            "model": self._settings.inference_rerank_model_alias,
            "query": query,
            "documents": [document],
        }
        return request_json_with_retries(
            request=lambda: self._client.post(_RERANK_PATH, json=payload),
            validate=self._validate_rerank_response,
            max_attempts=1,
            error_prefix=f"POST /{_RERANK_PATH}",
            request_error=InferenceTargetRequestError,
            contract_error=InferenceOutputError,
            retry_contract_errors=False,
            chain_transport_error=False,
            before_request=self._before_request,
            request_scope=self._request_scope,
            classify_request_error=classify_inference_request_error,
        )
