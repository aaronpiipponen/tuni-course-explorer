"""HTTP security proofs of the feedback intake boundary over the real front router.

Each test drives the real front router towards real worker applications, so the exact-site check,
the bounded body reader and the transient submission allowance are proved where they run. The
feedback route's settings come from the shared ``feedback_http`` fixture. A test that needs stored
rows supplies the migrated database. A refusal test supplies none.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from course_explorer_web.feedback_intake import FEEDBACK_SUBMISSION_PATH
from tests.feedback._support import _image_bytes, _row_counts, _stored_entries
from tests.feedback.conftest import (
    FEEDBACK_HTTP_ORIGIN,
    FeedbackDatabase,
)

pytestmark = [pytest.mark.integration]

_USAGE_PATH = Path("data") / "usage" / "requests"
_SITE_HEADERS = {
    "missing-origin": None,
    "foreign-origin": {"Origin": "https://evil.example.org"},
    "null-origin": {"Origin": "null"},
    "duplicate-origin": [("Origin", FEEDBACK_HTTP_ORIGIN), ("Origin", FEEDBACK_HTTP_ORIGIN)],
    "wrong-host": {"Host": "evil.example.org"},
    "duplicate-host": [("Host", "evil.example.org"), ("Host", "evil.example.org")],
    "forwarded-host": {
        "Host": "evil.example.org",
        "X-Forwarded-Host": "feedback.example.org",
        "X-Forwarded-Proto": "https",
    },
}


def _image_base64() -> str:
    """Return one genuine small PNG encoded as standard base64."""
    return base64.b64encode(_image_bytes("PNG")).decode("ascii")


def _submission_body(*, title: str = "HTTP submission") -> dict[str, object]:
    """Return one otherwise accepted submission body with one genuine image."""
    return {
        "answers": {"type": "bug", "title": title, "message": "Message text"},
        "attachments": [
            {
                "field_id": "screenshots",
                "filename": "screenshot.png",
                "content_base64": _image_base64(),
            }
        ],
        "public_issue": False,
    }


def _usage_lines(repository_root: Path) -> list[str]:
    """Return the recorded usage lines of one test site's temporary repository root."""
    return (repository_root / _USAGE_PATH).read_text(encoding="utf-8").splitlines()


def _response_body(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Decode one collected ASGI response body."""
    body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return json.loads(body)


def _response_status(messages: list[dict[str, Any]]) -> int:
    """Return one collected ASGI response status."""
    return next(
        message["status"] for message in messages if message["type"] == "http.response.start"
    )


@pytest.mark.parametrize("variant", list(_SITE_HEADERS))
def test_feedback_intake_refuses_cross_site_writes(
    feedback_http: Any,
    variant: str,
) -> None:
    """Each inexact Host or Origin is refused before any read or forward."""
    with feedback_http(admission_enabled=False) as site:
        site.client.headers.pop("Origin", None)
        headers = _SITE_HEADERS[variant]
        response = site.client.post(
            FEEDBACK_SUBMISSION_PATH,
            json=_submission_body(title=f"site sentinel {variant}"),
            headers=headers,
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "Feedback request refused"}
        assert response.headers["cache-control"] == "no-store"
        assert site.harness.calls == []

    lines = _usage_lines(site.repository_root)
    assert len(lines) == 1
    assert json.loads(lines[0])["route"] == FEEDBACK_SUBMISSION_PATH
    assert "site sentinel" not in lines[0]


def test_feedback_intake_bounds_the_body_before_forwarding(
    feedback_http: Any,
) -> None:
    """A declared oversize and an absent-length chunked oversize both stop before forwarding."""
    with feedback_http(admission_enabled=False, max_request_bytes=8) as site:

        async def exercise(declared: bool) -> tuple[int, dict[str, Any], int]:
            messages: list[dict[str, Any]] = []
            reads = 0

            class _Receive:
                def __init__(self, chunks: list[bytes | BaseException]) -> None:
                    self._chunks = list(chunks)

                async def __call__(self) -> dict[str, Any]:
                    nonlocal reads
                    reads += 1
                    chunk = self._chunks.pop(0)
                    if isinstance(chunk, BaseException):
                        raise chunk
                    return {
                        "type": "http.request",
                        "body": chunk,
                        "more_body": bool(self._chunks),
                    }

            headers = [
                (b"host", FEEDBACK_HTTP_ORIGIN.removeprefix("https://").encode("ascii")),
                (b"origin", FEEDBACK_HTTP_ORIGIN.encode("ascii")),
                (b"content-type", b"application/json"),
            ]
            if declared:
                headers.append((b"content-length", b"9"))
                receive = _Receive([AssertionError("a declared oversize must read no chunk")])
            else:
                receive = _Receive(
                    [
                        b"123456",
                        b"789",
                        AssertionError("the read must stop at the crossing chunk"),
                    ]
                )

            async def send(message: dict[str, Any]) -> None:
                messages.append(message)

            await site.router(
                {
                    "type": "http",
                    "method": "POST",
                    "path": FEEDBACK_SUBMISSION_PATH,
                    "raw_path": FEEDBACK_SUBMISSION_PATH.encode("ascii"),
                    "query_string": b"",
                    "root_path": "",
                    "scheme": "https",
                    "http_version": "1.1",
                    "server": ("feedback.example.org", 443),
                    "client": ("127.0.0.1", 12345),
                    "headers": headers,
                },
                receive,
                send,
            )
            return _response_status(messages), _response_body(messages), reads

        declared_status, declared_body, declared_reads = site.client.portal.call(exercise, True)
        streamed_status, streamed_body, streamed_reads = site.client.portal.call(exercise, False)

        assert (declared_status, streamed_status) == (413, 413)
        assert declared_body == streamed_body == {"detail": "Feedback request refused"}
        assert declared_reads == 0
        assert streamed_reads == 2
        assert site.harness.calls == []


@pytest.mark.parametrize("admission_enabled", [False, True], ids=["admission-off", "admission-on"])
def test_feedback_limits_apply_per_browser_and_site(
    feedback_database: FeedbackDatabase,
    feedback_http: Any,
    admission_enabled: bool,
) -> None:
    """Five attempts per browser and 30 per site hold, and the rolling hour reopens the allowance."""
    body = {
        "answers": {"type": "bug", "title": "Quota", "message": "Message text"},
        "attachments": [],
        "public_issue": False,
    }
    with feedback_http(database=feedback_database, admission_enabled=admission_enabled) as site:
        accepted = 0
        for _ in range(5):
            response = site.client.post(FEEDBACK_SUBMISSION_PATH, json=body)
            assert response.status_code == 201
            accepted += 1
        browser = site.client.cookies.get("tce_anon")

        refused = site.client.post(FEEDBACK_SUBMISSION_PATH, json=body)
        assert refused.status_code == 429
        assert refused.json() == {"detail": "Feedback request refused"}
        assert refused.headers["cache-control"] == "no-store"
        assert int(refused.headers["retry-after"]) > 0
        assert browser is not None
        assert f"tce_anon={browser}" in refused.headers["set-cookie"]
        assert _row_counts(feedback_database)[0] == accepted

        for index in range(25):
            site.client.cookies.clear()
            response = site.client.post(
                FEEDBACK_SUBMISSION_PATH,
                json=body,
                headers={"cookie": f"tce_anon={index:032x}"},
            )
            assert response.status_code == 201
            accepted += 1
        assert accepted == 30

        site.client.cookies.clear()
        refused = site.client.post(
            FEEDBACK_SUBMISSION_PATH,
            json=body,
            headers={"cookie": f"tce_anon={'a' * 32}"},
        )
        assert refused.status_code == 429
        assert int(refused.headers["retry-after"]) > 0
        assert _row_counts(feedback_database)[0] == 30

        site.clock[0] += 3600
        site.client.cookies.clear()
        reopened = site.client.post(
            FEEDBACK_SUBMISSION_PATH,
            json=body,
            headers={"cookie": f"tce_anon={'b' * 32}"},
        )
        assert reopened.status_code == 201

    assert _row_counts(feedback_database)[0] == 31
    assert _stored_entries(feedback_database.store_root) == []
