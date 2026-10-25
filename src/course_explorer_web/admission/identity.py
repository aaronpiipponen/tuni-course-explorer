"""Identify one anonymous browser by its admission cookie and render that cookie's value."""

from __future__ import annotations

import re
import secrets

from starlette.types import Scope

# The name of the anonymous identity cookie. Its value is 32 lowercase hexadecimal characters.
COOKIE_NAME = "tce_anon"

_COOKIE_VALUE = re.compile(r"[0-9a-f]{32}")


def identify(scope: Scope) -> str:
    """Return the request's valid admission cookie value, or a freshly minted identity.

    Only the ``tce_anon`` cookie is matched. An absent, malformed or differently named cookie
    contributes nothing, so the caller limits the minted identity like any other.
    """
    for name, value in scope.get("headers", ()):
        if name != b"cookie":
            continue
        for part in value.decode("latin-1").split(";"):
            key, separator, raw = part.strip().partition("=")
            if key == COOKIE_NAME and separator and _COOKIE_VALUE.fullmatch(raw):
                return raw
    return secrets.token_hex(16)


def set_cookie_value(cookie_id: str, max_age_seconds: int) -> bytes:
    """Return the ``set-cookie`` header value that keeps and slides one identity cookie."""
    return (
        f"{COOKIE_NAME}={cookie_id}; Max-Age={max_age_seconds}; Path=/; HttpOnly; Secure; "
        "SameSite=Lax"
    ).encode("latin-1")
