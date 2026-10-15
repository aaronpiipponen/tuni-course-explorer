"""Shared in-process HTTP boundary for the base local providers and the reranker.

It patches the two base HTTP-client construction sites to real clients backed by
``httpx.MockTransport``, so provider, routing, target-pass and context tests exercise the real
request/retry/validation code. The inference provider tests reuse this
same boundary. Callers set the knobs they need.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from course_explorer.config import InferenceSettings

DEFAULT_CONTENT = json.dumps(
    {
        "required": [],
        "recommended": [],
        "equivalence": [],
        "routing": {"confidence": 0.5, "flags": [], "suppressed": []},
    }
)


class InferenceHttpBoundary:
    """One canned HTTP boundary emitting the pinned runtime's endpoint responses only.

    Public knobs: ``content`` (a complete-target JSON document string returned as model content),
    ``prompt_tokens`` (the tokenize-array length and completion prompt count), ``failure_path`` and
    ``failure_status`` (a matching path returns that status with a synthetic error JSON body),
    ``content_for`` (an optional per-completion ``(index, request) -> content`` selector over a
    per-request counter, so a caller can script canned bad-then-good responses), and
    ``tokenize_tokens_for`` (an optional per-request ``request -> token count`` selector, so a caller
    can make one target's rendered packet oversized while another fits).
    """

    def __init__(
        self,
        settings: InferenceSettings,
        *,
        content: str | None = None,
        prompt_tokens: int = 1000,
    ) -> None:
        self._settings = settings
        self.content = content if content is not None else DEFAULT_CONTENT
        self.prompt_tokens = prompt_tokens
        self.failure_path: str | None = None
        self.failure_status: int = 500
        self.fail_if: Callable[[httpx.Request], bool] | None = None
        self.content_for: Callable[[int, httpx.Request], str] | None = None
        self.tokenize_tokens_for: Callable[[httpx.Request], int] | None = None
        self.completion_count = 0
        self.rerank_position = 0
        self.requests: list[httpx.Request] = []

    def reset_rerank(self) -> None:
        """Reset the increasing rerank score position for a deterministic second scoring run."""
        self.rerank_position = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Return one canned endpoint response for the request path, or fail loudly."""
        self.requests.append(request)
        path = request.url.path
        if self.failure_path is not None and self.failure_path in path:
            return httpx.Response(
                self.failure_status,
                json={"error": {"message": "synthetic failure", "type": "synthetic_error"}},
            )
        if self.fail_if is not None and self.fail_if(request):
            return httpx.Response(
                self.failure_status,
                json={"error": {"message": "synthetic failure", "type": "synthetic_error"}},
            )
        if path.endswith("/apply-template"):
            messages = json.loads(request.content).get("messages", [])
            return httpx.Response(
                200,
                json={"prompt": "\n".join(str(message.get("content", "")) for message in messages)},
            )
        if path.endswith("/tokenize"):
            count = (
                self.prompt_tokens
                if self.tokenize_tokens_for is None
                else int(self.tokenize_tokens_for(request))
            )
            return httpx.Response(200, json={"tokens": list(range(count))})
        if path.endswith("/rerank"):
            return self._rerank_response()
        if path.endswith("/chat/completions"):
            return self._completion(request)
        raise AssertionError(f"unsupported inference endpoint path {path}")

    def _rerank_response(self) -> httpx.Response:
        score = float(self.rerank_position + 1)
        self.rerank_position += 1
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": score}]})

    def _completion(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model = payload["model"]
        index = self.completion_count
        self.completion_count += 1
        content = self.content if self.content_for is None else self.content_for(index, request)
        body: dict[str, object] = {
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": self.prompt_tokens, "completion_tokens": 10},
        }
        if request.url.host == self._settings.inference_host:
            body["object"] = "chat.completion"
            body["system_fingerprint"] = f"b-{self._settings.inference_runtime_revision[:9]}"
            body["timings"] = {"prompt_per_second": 100.0, "predicted_per_second": 10.0}
        return httpx.Response(200, json=body)


def completion_response(
    content: str = DEFAULT_CONTENT,
    *,
    model: str,
    fingerprint: str,
    prompt_tokens: int = 120,
    completion_tokens: int = 45,
    **overrides: Any,
) -> httpx.Response:
    """Build one local chat-completion response body for the provider contract tests."""
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
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        "timings": {"prompt_per_second": 512.5, "predicted_per_second": 42.75},
    }
    body.update(overrides)
    return httpx.Response(200, json=body)


def local_structured_provider(
    settings: InferenceSettings, boundary: InferenceHttpBoundary, *, variant_index: int = 0
) -> Any:
    """Build one real local provider over the boundary for direct bounded-target proofs."""
    from course_explorer.inference.provider import StructuredJsonProvider

    return StructuredJsonProvider(
        settings,
        settings.inference_local_variants[variant_index],
        transport=httpx.MockTransport(boundary.handle),
    )


def install_inference_http(monkeypatch: Any, boundary: InferenceHttpBoundary) -> None:
    """Patch only the two base HTTP-client construction sites to real clients over the boundary."""
    from course_explorer.inference import job as job_module
    from course_explorer.inference import routing as routing_module
    from course_explorer.inference.provider import RerankProvider, StructuredJsonProvider

    transport = httpx.MockTransport(boundary.handle)

    def local_provider(settings, variant, **kwargs):
        return StructuredJsonProvider(settings, variant, transport=transport, **kwargs)

    def rerank_provider(settings, **kwargs):
        return RerankProvider(settings, transport=transport, **kwargs)

    monkeypatch.setattr(routing_module, "StructuredJsonProvider", local_provider)
    monkeypatch.setattr(job_module, "RerankProvider", rerank_provider)
