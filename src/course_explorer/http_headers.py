"""Shared request-header access for the two HTTP surfaces.

The feature router and the administration console both read a header as the exact list of values
the request carried, preserving duplicates and their order.
"""

from __future__ import annotations

from collections.abc import Iterable


def header_values(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> list[bytes]:
    """Return every value of one request header, preserving duplicates and their order."""
    return [value for key, value in headers if key.lower() == name]
