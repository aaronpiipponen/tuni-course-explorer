"""Neutral retry/backoff and outer-JSON decode mechanics for product HTTP clients.

This module is the single product owner of the two shared mechanics that the Kori, embedding,
translation, local-inference and external-provider clients use: a bounded
request/status retry loop and the outer HTTP response JSON decode. Each caller keeps its own
request shape, response validation, DTO models, error types, credential protocol and retry
policy. This module never receives or inspects a request body, URL, header, prompt, schema,
model output or setting. It records only a caller-supplied fixed ``method + endpoint`` prefix,
a transport exception class name, or the HTTP status, reads no configuration, and performs no
I/O beyond the caller's own request callable.

A caller may additionally supply a pure admission callback and a request-scope factory. The
admission callback reads a live cooperative control boundary and returns whether one more
request may start. It never blocks and never mutates state. Admission is consulted immediately
before the initial request (unless the caller already owns that boundary with
``check_initial=False``) and before and after every retry backoff. When admission is refused, a
new initial call raises the fixed content-free :class:`RequestNotStarted`. A mid-retry refusal
instead raises the same terminal safe request/contract error the attempt would otherwise have
produced rather than sleeping, retrying, or hiding the failure. A response that arrives in full
is returned and committed even if control changed while it was in flight.

Security: a terminal error must not retain untrusted transport or response text. A credential
boundary therefore calls with ``chain_transport_error=False`` and
``chain_error=False``. In those modes the safe exception is raised after the ``except`` block
has exited so neither ``__cause__`` nor ``__context__`` can reach the raw transport exception
or a body-derived ``JSONDecodeError``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any, TypeVar

import httpx

ResultT = TypeVar("ResultT")


class RequestNotStarted(RuntimeError):
    """Fixed content-free cooperative signal for a declined model request.

    Raised when a caller-supplied admission callback refuses a model request, either at the very
    first request of a call or immediately before a claimed request starts. It may carry the
    caller's fixed method/endpoint prefix but never a request body, untrusted or variable endpoint
    detail, transport text, or credential material, so a worker can end a cycle cleanly without
    fabricating a result.
    """


def request_json_with_retries(  # noqa: UP047 - one module-level ResultT is the shared contract
    *,
    request: Callable[[], httpx.Response],
    validate: Callable[[httpx.Response], ResultT],
    max_attempts: int,
    retry_backoff_seconds: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    error_prefix: str,
    request_error: type[RuntimeError],
    contract_error: type[ValueError],
    retry_contract_errors: bool,
    chain_transport_error: bool = True,
    before_request: Callable[[], bool] | None = None,
    check_initial: bool = True,
    request_scope: Callable[[], AbstractContextManager[None]] | None = None,
    classify_request_error: Callable[[int | type[httpx.TransportError]], type[RuntimeError]]
    | None = None,
) -> ResultT:
    """Run one caller request with the shared bounded retry and status policy.

    ``failed_index`` is zero-based: the delay before call ``N`` is
    ``retry_backoff_seconds * 2 ** (N - 1)`` and the configured attempt count includes the
    initial call. The retry-timing parameters are consulted only when a retry can occur, so a
    one-attempt caller may omit them. Only ``httpx.TransportError`` and the supplied ``contract_error`` retry.
    Transport failures and retryable 429/5xx status failures obey the attempt budget. Contract
    failures retry only when ``retry_contract_errors`` is set. Every other non-200 status is
    terminal immediately, and no status reports a response body or header.

    An optional pure ``classify_request_error`` maps the raw HTTP status or transport exception
    type to the safe exception class to raise. It is a producer-owned data/type classification and
    never inspects an error message or a cause. With no classifier, behaviour is the same and the
    supplied ``request_error`` owns every failure. With one, a returned class that is not the
    supplied ``request_error`` names an infrastructure category that is never retried. Only the
    target class keeps the retryable transport/429/5xx policy. The classifier receives only the
    integer status or the exception type, never an exception value, body or header.
    """
    scope = request_scope if request_scope is not None else nullcontext
    last_failed_index = max_attempts - 1

    def refused() -> bool:
        return before_request is not None and not before_request()

    def select_class(failure: int | type[httpx.TransportError]) -> type[RuntimeError]:
        if classify_request_error is None:
            return request_error
        return classify_request_error(failure)

    for failed_index in range(max_attempts):
        if failed_index == 0 and check_initial and refused():
            raise RequestNotStarted(f"{error_prefix}: request not started")
        terminal_transport_name: str | None = None
        terminal_transport_class: type[RuntimeError] = request_error
        try:
            with scope():
                response = request()
        except httpx.TransportError as exc:
            error_class = select_class(type(exc))
            if error_class is request_error:
                if failed_index < last_failed_index and not refused():
                    sleep(retry_backoff_seconds * 2**failed_index)
                    if not refused():
                        continue
            if chain_transport_error:
                raise error_class(f"{error_prefix}: transport {type(exc).__name__}") from exc
            terminal_transport_name = type(exc).__name__
            terminal_transport_class = error_class
        if terminal_transport_name is not None:
            raise terminal_transport_class(f"{error_prefix}: transport {terminal_transport_name}")

        status = response.status_code
        if status != 200:
            error_class = select_class(status)
            retryable = status == 429 or 500 <= status <= 599
            if (
                error_class is request_error
                and retryable
                and failed_index < last_failed_index
                and not refused()
            ):
                sleep(retry_backoff_seconds * 2**failed_index)
                if not refused():
                    continue
            raise error_class(f"{error_prefix}: HTTP {status}")

        try:
            return validate(response)
        except contract_error:
            if retry_contract_errors and failed_index < last_failed_index and not refused():
                sleep(retry_backoff_seconds * 2**failed_index)
                if not refused():
                    continue
            raise

    # Settings validate max_attempts >= 1, so every loop path returns, retries, or raises.
    raise AssertionError("request_json_with_retries requires max_attempts >= 1")


def decode_json_response(
    response: httpx.Response,
    *,
    error_prefix: str,
    contract_error: type[ValueError],
    chain_error: bool = True,
) -> Any:
    """Decode one successful HTTP response body, mapping any JSON error to ``contract_error``.

    ``chain_error=True`` keeps the ordinary client's ``from exc`` cause. ``chain_error=False``
    (the credential-boundary mode) raises after the ``except`` block so no ``__cause__`` or
    ``__context__`` can reach the body-derived ``JSONDecodeError``.
    """
    try:
        return response.json()
    except ValueError as exc:
        if chain_error:
            raise contract_error(f"{error_prefix}: response is not valid JSON") from exc
    raise contract_error(f"{error_prefix}: response is not valid JSON")
