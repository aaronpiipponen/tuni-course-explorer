"""Proof that one admitted promotion streams its owner's steps and records a failed response send.

Each case sends one authenticated request through the real application, the real admission
middleware and the real fixed-command runner, and stands in for only the promotion owner: it reports
steps, holds completion until the test releases it, and then returns its ordinary result or raises.
The request's answer is the one newline-delimited stream, so the cases prove that a step reaches the
response send before the command finishes, that the terminal result follows exactly once, and that
one safe command-log entry records the outcome. A response send that raises after a step lets the
mutation finish and be recorded. No real promotion, dataset or unit runs here.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from course_explorer_admin import commands as administrative_commands
from course_explorer_admin_web.command_log import CommandLog
from tests.admin_web import _support

DATASET_ID = "a" * 32
PROMOTED_ID = "c" * 32
PROMOTED_DATABASE = "course_admin_copy"


class _Receipt(BaseModel):
    """One tiny terminal report a scripted promotion returns."""

    dataset_id: str
    database_name: str


def _wait_until(predicate: Callable[[], bool], *, timeout: float = 10.0) -> None:
    """Wait for one test observation, failing loudly when it never arrives."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("the promotion boundary did not reach the expected observation")


def _promotion_stream(client, csrf: str):
    """Open the admitted promotion stream of one listed source."""
    return client.stream(
        "POST",
        "/api/datasets/copy-to-selected",
        json={"source_dataset_id": DATASET_ID, "confirm_restart": True},
        headers={"Origin": _support.ORIGIN, "X-CSRF-Token": csrf},
    )


def _promotion_entries(root: Path) -> list:
    """Return the retained entries of the one promotion command, ignoring the login entry."""
    path = root / _support.COMMAND_LOG_PATH
    if not path.exists():
        return []
    return [
        entry
        for entry in CommandLog(root, limit=20).read()
        if entry.command == "datasets copy-to-selected"
    ]


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_promotion_stream_delivers_steps_before_its_terminal_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str
) -> None:
    """One step reaches the client while the owner is held, then one terminal result is recorded."""
    root, settings, clock, _application = _support.site(monkeypatch, tmp_path)
    boundary = _support.ScriptedProcessBoundary()
    application = _support.admin_web_app(root, settings, clock=clock, process_runner=boundary)
    client = _support.authenticated_client(application)
    csrf = client.get("/auth/session").json()["csrf_token"]
    entered = threading.Event()
    released = threading.Event()
    delegated: list[dict[str, object]] = []

    def promotion(
        source_dataset_id: str,
        *,
        confirm_restart: bool = False,
        on_progress: Callable[[str], None] | None = None,
        runner: object = None,
    ) -> _Receipt:
        delegated.append(
            {
                "source_dataset_id": source_dataset_id,
                "confirm_restart": confirm_restart,
                "on_progress": on_progress,
                "runner": runner,
            }
        )
        assert on_progress is not None
        entered.set()
        on_progress("copy")
        if not released.wait(timeout=10):
            raise AssertionError("the test never released the promotion")
        if outcome == "failure":
            raise RuntimeError(_support.OUTPUT_SENTINEL)
        return _Receipt(dataset_id=PROMOTED_ID, database_name=PROMOTED_DATABASE)

    monkeypatch.setattr(administrative_commands, "run_administrative_dataset_promotion", promotion)
    log_path = root / _support.COMMAND_LOG_PATH

    with _promotion_stream(client, csrf) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"
        assert response.headers["cache-control"] == "no-store"
        lines = response.iter_lines()

        # The owner's first step arrives while that owner still holds the command's completion.
        assert json.loads(next(lines)) == {"step": "copy"}
        assert entered.is_set()
        assert not released.is_set()
        # Nothing about the promotion is logged and no terminal result exists until it ends.
        assert _promotion_entries(root) == []

        released.set()
        records = [json.loads(line) for line in lines]

    # The terminal record is the stream's only remaining record and it is the ordinary result.
    assert len(records) == 1
    assert set(records[0]) == {"result"}
    result = records[0]["result"]
    if outcome == "success":
        assert result == {
            "exit_code": 0,
            "report": {"dataset_id": PROMOTED_ID, "database_name": PROMOTED_DATABASE},
            "failure_line": None,
            "guidance_line": None,
        }
    else:
        assert result["exit_code"] == 1
        assert result["report"] is None
        assert json.loads(result["failure_line"]) == {"error": "RuntimeError"}
        assert result["guidance_line"] == administrative_commands.operator_guidance(
            "dataset-promotion"
        )
        assert _support.OUTPUT_SENTINEL not in json.dumps(result)

    # The owner received the validated input, the supplied process runner and one step observer,
    # and the runner launched no subprocess for it.
    assert len(delegated) == 1
    assert delegated[0]["source_dataset_id"] == DATASET_ID
    assert delegated[0]["confirm_restart"] is True
    assert delegated[0]["runner"] is boundary
    assert delegated[0]["on_progress"] is not None
    assert boundary.calls == []

    entries = _promotion_entries(root)
    assert len(entries) == 1
    assert entries[0].command == "datasets copy-to-selected"
    assert entries[0].result == ("success" if outcome == "success" else "failure")
    assert entries[0].exit_code == (0 if outcome == "success" else 1)
    payload = log_path.read_text(encoding="utf-8")
    assert DATASET_ID not in payload
    assert _support.OUTPUT_SENTINEL not in payload


def test_failed_response_send_finishes_and_records_its_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed response send neither cancels the promotion nor its one log entry."""
    root, settings, clock, application = _support.site(monkeypatch, tmp_path)
    boundary = _support.ScriptedProcessBoundary()
    application = _support.admin_web_app(root, settings, clock=clock, process_runner=boundary)
    client = _support.authenticated_client(application)
    csrf = client.get("/auth/session").json()["csrf_token"]
    cookie = _support.session_cookie(client)
    released = threading.Event()
    step_sent = threading.Event()
    finished = threading.Event()
    invocations: list[str] = []
    bodies: list[bytes] = []

    def promotion(
        source_dataset_id: str,
        *,
        confirm_restart: bool = False,
        on_progress: Callable[[str], None] | None = None,
        runner: object = None,
    ) -> _Receipt:
        invocations.append(source_dataset_id)
        assert on_progress is not None
        on_progress("copy")
        if not released.wait(timeout=10):
            raise AssertionError("the test never released the promotion")
        on_progress("build")
        finished.set()
        return _Receipt(dataset_id=PROMOTED_ID, database_name=PROMOTED_DATABASE)

    monkeypatch.setattr(administrative_commands, "run_administrative_dataset_promotion", promotion)

    async def send(message: dict) -> None:
        if message["type"] != "http.response.body":
            return
        bodies.append(message.get("body", b""))
        if b'"step":"copy"' in message.get("body", b""):
            step_sent.set()
            # The response send fails after that step, which leaves the client without a result.
            raise OSError("synthetic send failure")

    request_body = json.dumps({"source_dataset_id": DATASET_ID, "confirm_restart": True}).encode()

    sent_body = False

    async def receive() -> dict:
        nonlocal sent_body
        # Yield to the loop so the streamed body can make progress while the client stays connected.
        await asyncio.sleep(0.01)
        if sent_body:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent_body = True
        return {"type": "http.request", "body": request_body, "more_body": False}

    scope: dict = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/datasets/copy-to-selected",
        "raw_path": b"/api/datasets/copy-to-selected",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", settings.admin_web_origin.removeprefix("https://").encode()),
            (b"origin", _support.ORIGIN.encode()),
            (b"content-type", b"application/json"),
            (b"x-csrf-token", csrf.encode()),
            (b"cookie", f"{_support.SESSION_COOKIE_NAME}={cookie}".encode()),
        ],
        "client": ("127.0.0.1", settings.admin_web_port),
        "server": ("localhost", settings.admin_web_port),
    }
    failures: list[BaseException] = []

    def drive() -> None:
        try:
            asyncio.run(application(scope, receive, send))
        except BaseException as exc:  # noqa: BLE001, the test records the response failure
            failures.append(exc)

    worker = threading.Thread(target=drive, name="promotion-request")
    worker.start()
    try:
        assert step_sent.wait(timeout=10), "the step never reached the response send"
        # The step reached the failed send while the owner still held the command's completion.
        assert not released.is_set()
        assert not finished.is_set()
        released.set()
    finally:
        worker.join(timeout=10)
    assert not worker.is_alive(), "the request never observed the finished producer"

    # A failed send reaches the middleware's content-free failure instead of a payload.
    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeError)
    assert "synthetic send failure" not in str(failures[0])

    _wait_until(finished.is_set)
    _wait_until(lambda: _promotion_entries(root) != [])
    assert bodies != []

    # The one invocation ran to its own end and recorded its ordinary safe outcome.
    assert invocations == [DATASET_ID]
    assert boundary.calls == []
    entries = _promotion_entries(root)
    assert len(entries) == 1
    assert entries[0].command == "datasets copy-to-selected"
    assert entries[0].result == "success"
    assert entries[0].exit_code == 0
    assert DATASET_ID not in (root / _support.COMMAND_LOG_PATH).read_text(encoding="utf-8")
