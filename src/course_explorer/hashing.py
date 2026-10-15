"""Neutral canonical JSON validation and hashing for the whole product.

This module is the single product-wide owner of strict JSON validation: one
``parse_strict_json`` hook rejects duplicate object keys and non-finite constants for every
untrusted JSON boundary, and one canonical hasher rejects non-string mapping keys, non-finite
numbers, and values without a standard JSON encoding instead of coercing them, then hashes sorted
compact UTF-8. ``canonical_json_bytes`` and ``json_sha256`` expose the same canonical serializer
with an explicit ``ensure_ascii`` flag so the non-strict dialects (manifest object hashing,
embedding configuration, translation work keys, prerequisite payloads) share one implementation
while preserving their bytes. It reads no configuration, performs no I/O, and depends only
on the standard library.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build one JSON object while rejecting a repeated key."""
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError("JSON object contains a duplicate key")
        mapping[key] = value
    return mapping


def _reject_constant(token: str) -> Any:
    """Reject ``NaN``/``Infinity`` JSON constants before any numeric validation."""
    raise ValueError(f"JSON constant {token} is not a finite number")


def parse_strict_json(raw: str | bytes, *, decimal_numbers: bool = False) -> object:
    """Parse one strict JSON document, rejecting duplicate keys and non-finite constants.

    This is the product-wide single strict-JSON parse hook: the untrusted target-result,
    prompt-artifact, local-provider, and external-provider response boundaries all call it instead of
    each
    repeating ``object_pairs_hook``/``parse_constant``. ``raw`` may be text or bytes. The caller
    keeps its own context error message by wrapping the raised ``ValueError``. ``decimal_numbers``
    selects exact ``Decimal`` parsing for the domain and provider callers that never want a binary
    float. The default keeps ordinary Python numbers for the prompt-artifact caller. It reads no
    configuration and performs no I/O.
    """
    if not isinstance(raw, str | bytes):
        raise ValueError("JSON input must be a string or bytes")
    keywords: dict[str, object] = {
        "object_pairs_hook": _reject_duplicate_keys,
        "parse_constant": _reject_constant,
    }
    if decimal_numbers:
        keywords["parse_float"] = Decimal
        keywords["parse_int"] = Decimal
    return json.loads(raw, **keywords)


def require_json_compatible(value: object, label: str) -> None:
    """Reject any value that is not recursively string-keyed, finite JSON data."""
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{label} must not contain a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} mapping keys must be strings")
            require_json_compatible(item, label)
        return
    if isinstance(value, list | tuple):
        for item in value:
            require_json_compatible(item, label)
        return
    raise ValueError(f"{label} must contain only JSON-compatible values")


def canonical_json_bytes(value: object, *, ensure_ascii: bool, allow_nan: bool = True) -> bytes:
    """Serialize one value as sorted compact JSON under the supplied escaping and NaN flags.

    This is the one shared canonical serializer. Callers that must preserve their digest
    bytes pass the matching flag, while the strict hasher passes ``ensure_ascii=False``
    and ``allow_nan=False`` after its own compatibility check.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
        allow_nan=allow_nan,
    ).encode("utf-8")


def json_sha256(value: object, *, ensure_ascii: bool) -> str:
    """Hash one canonical-JSON value as UTF-8 with the supplied escaping convention."""
    return hashlib.sha256(canonical_json_bytes(value, ensure_ascii=ensure_ascii)).hexdigest()


def canonical_json_sha256(value: object) -> str:
    """Hash one strictly JSON-serializable value as sorted compact UTF-8 without coercing it."""
    require_json_compatible(value, "value")
    try:
        encoded = canonical_json_bytes(value, ensure_ascii=False, allow_nan=False)
    except TypeError as exc:
        raise ValueError("value must be JSON-serializable without custom encoders") from exc
    return hashlib.sha256(encoded).hexdigest()
