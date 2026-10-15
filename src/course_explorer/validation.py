"""Neutral product owner for the shared text, hash, timestamp, and numeric validators.

Several packages enforce the same five shapes: meaningful nonblank NUL-free text, a full lowercase
SHA-256 digest, a timezone-aware datetime, a safe ASCII exception-class name, and a finite
nonnegative float. This module owns those predicates once, so the same regex, blank refusal, and range check live in
one place. It uses the standard library and returns accepted values as given.
"""

from __future__ import annotations

import re
from datetime import datetime

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_NUL = "\x00"


def require_error_type(value: str, *, max_length: int) -> str:
    """Require one safe ASCII exception-class identifier within the caller's length bound.

    It returns the exact value without normalization. The single exception-class pattern is owned
    here so every caller imports one shape.
    """
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= max_length
        or _ERROR_TYPE_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            f"error_type must be an ASCII identifier of at most {max_length} characters"
        )
    return value


def require_nonblank_text(value: str, *, message: str) -> str:
    """Reject a blank text value without normalizing it."""
    if not value.strip():
        raise ValueError(message)
    return value


def require_text(value: str | None, label: str) -> str:
    """Require one nonblank, NUL-free identity, version, prompt, or error value."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a nonblank string")
    checked = require_nonblank_text(value, message=f"{label} must be a nonblank string")
    if _NUL in checked:
        raise ValueError(f"{label} must not contain NUL characters")
    return checked


def require_sha256(value: str, label: str) -> str:
    """Require one full lowercase SHA-256 digest without coercion."""
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def require_aware(value: datetime, label: str) -> datetime:
    """Require one timezone-aware timestamp so persisted ordering is meaningful."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def require_finite_nonnegative(value: float, label: str) -> float:
    """Require one finite nonnegative float so a persisted duration or clock is meaningful."""
    if value != value or value in (float("inf"), float("-inf")) or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return value
