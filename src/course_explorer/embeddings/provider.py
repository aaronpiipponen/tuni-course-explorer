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
from course_explorer.embeddings.query_cache import SharedQueryEmbeddingCache
from course_explorer.http_retry import decode_json_response, request_json_with_retries


class EmbeddingRequestError(RuntimeError):
    """Terminal transport or HTTP failure against the embedding service."""


class EmbeddingContractError(ValueError):
    """Malformed or non-conforming embedding response contract."""


def embedding_client(
    settings: EmbeddingRuntimeSettings,
    *,
    timeout: float,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """Return one client for the pinned loopback embedding service endpoint.

    The provider and the web supervisor share this constructor, so both name the same base URL and
    never follow a redirect away from the loopback service.
    """
    return httpx.Client(
        base_url=str(settings.base_url),
        timeout=timeout,
        transport=transport,
        follow_redirects=False,
    )


class _EmbeddingData(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    index: int
    embedding: list[float]


class _EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    data: list[_EmbeddingData]
    model: str | None = None


class EmbeddingProvider:
    """One HTTP client that returns validated vectors in exact input order.

    A client supplied in ``client`` belongs to its owner for the process lifetime, so ``close``
    leaves it open. A provider that builds its own client closes that client in ``close``.
    """

    def __init__(
        self,
        settings: EmbeddingRuntimeSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        before_request: Callable[[], bool] | None = None,
        request_scope: Callable[[float], AbstractContextManager[None]] | None = None,
        query_cache: SharedQueryEmbeddingCache | None = None,
        cache_configuration: str | None = None,
    ) -> None:
        if (query_cache is None) != (cache_configuration is None):
            raise ValueError(
                "a query embedding cache requires its embedding configuration identity"
            )
        if client is not None and transport is not None:
            raise ValueError("a supplied embedding client owns its transport")
        self._settings = settings
        self._sleep = sleep
        self._before_request = before_request
        self._query_cache = query_cache
        self._cache_configuration = cache_configuration
        self._request_scope = (
            None
            if request_scope is None
            else (lambda: request_scope(settings.embedding_request_timeout_seconds))
        )
        self._owned_client = client is None
        self._client = client or embedding_client(
            settings,
            timeout=settings.embedding_request_timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        """Close a client this provider created, leaving a supplied process-lifetime client open."""
        if self._owned_client:
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
        cached = self._cached(validated)
        if cached is not None:
            return cached
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
        if self._query_cache is not None and len(vectors) == 1:
            assert self._cache_configuration is not None
            self._query_cache.put(validated[0], vectors[0], configuration=self._cache_configuration)
        return tuple(vectors)

    def _cached(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...] | None:
        """Return the cached single-query vector, or ``None`` when the request must be embedded."""
        if self._query_cache is None or len(texts) != 1:
            return None
        assert self._cache_configuration is not None
        vector = self._query_cache.get(texts[0], configuration=self._cache_configuration)
        return None if vector is None else (vector,)
