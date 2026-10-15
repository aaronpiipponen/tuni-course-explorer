"""Single synchronous HTTP client for the pinned loopback BGE-M3 embedding service."""

import math
import time
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from course_explorer.config import EmbeddingRuntimeSettings
from course_explorer.http_retry import decode_json_response, request_json_with_retries


class EmbeddingRequestError(RuntimeError):
    """Terminal transport or HTTP failure against the embedding service."""


class EmbeddingContractError(ValueError):
    """Malformed or non-conforming embedding response contract."""


class _EmbeddingData(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    index: int
    embedding: list[float]


class _EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    data: list[_EmbeddingData]
    model: str | None = None


class EmbeddingProvider:
    """One HTTP client that returns validated vectors in exact input order."""

    def __init__(
        self,
        settings: EmbeddingRuntimeSettings,
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
            else (lambda: request_scope(settings.embedding_request_timeout_seconds))
        )
        self._client = httpx.Client(
            base_url=str(settings.base_url),
            timeout=settings.embedding_request_timeout_seconds,
            transport=transport,
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
    def _validate_inputs(texts: Sequence[str]) -> tuple[str, ...]:
        if len(texts) == 0:
            raise ValueError("embedding inputs must not be empty")
        validated: list[str] = []
        for text in texts:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("embedding inputs must be non-blank strings")
            validated.append(text)
        return tuple(validated)

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """POST one batch and return one validated vector per input, in input order."""
        if self._client.is_closed:
            raise EmbeddingRequestError("POST /v1/embeddings: client is closed")
        validated = self._validate_inputs(texts)
        payload = {
            "input": list(validated),
            "model": self._settings.embedding_model,
            "encoding_format": "float",
        }

        value = request_json_with_retries(
            request=lambda: self._client.post("v1/embeddings", json=payload),
            validate=lambda response: decode_json_response(
                response,
                error_prefix="POST /v1/embeddings",
                contract_error=EmbeddingContractError,
            ),
            max_attempts=self._settings.embedding_max_attempts,
            retry_backoff_seconds=self._settings.embedding_retry_backoff_seconds,
            sleep=self._sleep,
            error_prefix="POST /v1/embeddings",
            request_error=EmbeddingRequestError,
            contract_error=EmbeddingContractError,
            retry_contract_errors=False,
            before_request=self._before_request,
            request_scope=self._request_scope,
        )
        try:
            parsed = _EmbeddingResponse.model_validate(value)
        except ValidationError as exc:
            raise EmbeddingContractError(
                "POST /v1/embeddings: response violates embedding schema"
            ) from exc

        if "model" in parsed.model_fields_set and parsed.model != self._settings.embedding_model:
            raise EmbeddingContractError("POST /v1/embeddings: response model mismatch")

        expected_indices = set(range(len(validated)))
        by_index: dict[int, list[float]] = {}
        for item in parsed.data:
            if item.index in by_index:
                raise EmbeddingContractError("POST /v1/embeddings: duplicate embedding index")
            by_index[item.index] = item.embedding
        if set(by_index) != expected_indices:
            raise EmbeddingContractError(
                "POST /v1/embeddings: response cardinality or indices do not match input"
            )

        vectors: list[tuple[float, ...]] = []
        for index in range(len(validated)):
            embedding = by_index[index]
            if len(embedding) != self._settings.embedding_dimension:
                raise EmbeddingContractError(
                    "POST /v1/embeddings: response vector dimension mismatch"
                )
            components = tuple(float(component) for component in embedding)
            if any(not math.isfinite(component) for component in components):
                raise EmbeddingContractError(
                    "POST /v1/embeddings: response vector contains non-finite values"
                )
            vectors.append(components)
        return tuple(vectors)
