"""Exception/token vocabulary for target-scoped inference failure isolation.

This module owns only the fixed, content-free vocabulary the job, selection producers, provider and
target writer share to classify a target-scoped failure from an infrastructure/control failure. It
holds no scheduler, store, retry loop or controller: :class:`TargetSelectionError` and
:class:`TargetResultError` carry only their fixed ``reason`` token (never source or model text),
:class:`TargetPassFailure` reports an already-attempted whole-target operation with its actual request
count and exhaustion flag (for generation the sole writer records one safe episode per failed attempt.
This aggregate only summarizes an exhausted bounded pass), :class:`TargetContextError` is the fixed
content-free signal that no configured execution route fits an oversized packet, and
:class:`InferenceTargetsFailed` is the content-free terminal signal the job emits only after useful
publication. Unknown programmer, infrastructure and control errors stay loud and are never relabelled
through these types.
"""

from __future__ import annotations

from typing import Literal

FailureStage = Literal["multiview", "rerank", "inference_preparation", "inference"]
FailureReason = Literal[
    "missing_target_chunks",
    "insufficient_candidates",
    "incomplete_views",
    "request_failed",
    "provider_output",
    "invalid_result",
    "ambiguous_code",
    "multiple_requirement_sets",
    "target_direct_source",
    "context_exceeded",
]


class TargetSelectionError(ValueError):
    """One target-scoped multiview selection failure carrying only its fixed reason token."""

    def __init__(self, reason: FailureReason) -> None:
        super().__init__(reason)
        self.reason: FailureReason = reason


class TargetResultError(ValueError):
    """One target-scoped generated-output rejection carrying only its fixed reason token."""

    def __init__(self, reason: FailureReason) -> None:
        super().__init__(reason)
        self.reason: FailureReason = reason


class TargetPassFailure(RuntimeError):
    """A route-budgeted whole-target operation already performed, reporting its real request count.

    ``attempt_count`` is the number of whole-target actions actually started in that invocation
    (provider preparation actions or generation requests, per the owner that raised it), ``error_type``
    is the producer's safe exception class name, and ``exhausted`` is ``True`` only when the route's
    bound was actually consumed (a bounded route's per-pass budget. The local route never exhausts and
    records one episode per failed attempt instead). It never carries model or source text and never
    grants an outer job retry.
    """

    def __init__(
        self, *, attempt_count: int, reason: FailureReason, error_type: str, exhausted: bool
    ) -> None:
        super().__init__(f"target pass failure: {reason}")
        self.attempt_count = attempt_count
        self.reason: FailureReason = reason
        self.error_type = error_type
        self.exhausted = exhausted


class TargetContextError(ValueError):
    """No configured execution route fits one rendered target packet.

    It carries only one fixed content-free message: the packet's tokenized prompt plus the configured
    output and headroom exceeds every configured local key and no oversize route was supplied, so the
    target fails as a capacity failure.
    No prompt, input, credential or model text is ever a member.
    """

    def __init__(self) -> None:
        super().__init__("no configured inference execution route fits this target packet")


class TargetPreparationFailure(TargetPassFailure):
    """A target-scoped provider preparation failure after one or more started preparation actions.

    It inherits exactly the base constructor and fields and reports already-started preparation
    actions, not generation requests. The job must distinguish this subtype before its base.
    """


class InferenceTargetsFailed(RuntimeError):
    """Content-free terminal signal emitted only after useful targets have been published."""
