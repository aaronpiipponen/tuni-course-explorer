"""Shared process double and synthetic site constants for the rebuild and promotion proofs.

The double answers every fixed systemd, npm, Compose, socket and Git read, and records each
command in order. Synthetic site and administration units, the web bind and candidate listener
ownership are shared by the rebuild contracts and the SQL promotion proofs. A promotion proof opts
into forwarding the real Compose commands, and it can inject a bounded number of restart failures
so the caller's rollback restart runs against the same boundary.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from course_explorer_admin import datasets as datasets_module
from course_explorer_admin import mechanics

_UNIT = "synthetic-site-web.service"
_ADMIN_UNIT = "synthetic-site-admin.service"
_WEB_HOST = "127.0.0.1"
_WEB_PORT = 18026
_WEB_WORKERS = 2
_MAIN_PID = 4242
_RESTARTED_PID = 5252
_SENTINEL = "synthetic-failure-output"
_OWNED_PROCESS = 'users:(("python",pid={owner},fd=4))'

_COMPOSE_PREFIXES = (
    mechanics.compose_prefix(interpreter=True),
    mechanics.compose_prefix(non_interactive=True, interpreter=True),
)


class _RebuildProcessBoundary:
    """Answer the fixed rebuild process reads and record every command in order.

    The web unit is answered with this checkout's web launcher and the administration unit with this
    checkout's administration launcher, so an owner that selects the wrong unit or the wrong launcher
    is refused before it mutates anything. The administration build and restart outcomes are decided
    by their own flags, so one double serves the site rebuild, the administration build and the
    administration restart. The double answers both the user-manager and the system-manager command
    forms, and the public-contract assertions verify that the configured manager selects the form.
    """

    def __init__(
        self,
        *,
        root: Path,
        unit: str,
        working_directory: Path | None = None,
        fail_step: str | None = None,
        listeners: tuple[tuple[str, str], ...] = (),
        admin_unit: str = _ADMIN_UNIT,
        admin_loaded: bool = True,
        admin_working_directory: Path | None = None,
        admin_launcher: Path | None = None,
        fail_admin_build: bool = False,
        fail_admin_restart: bool = False,
        restart_failures: int = 0,
        real_compose: bool = False,
    ) -> None:
        self.root = root
        self.unit = unit
        self.working_directory = root if working_directory is None else working_directory
        self.fail_step = fail_step
        self.listeners = listeners
        self.admin_unit = admin_unit
        self.admin_loaded = admin_loaded
        self.admin_working_directory = admin_working_directory
        self.admin_launcher = admin_launcher
        self.fail_admin_build = fail_admin_build
        self.fail_admin_restart = fail_admin_restart
        self.restart_failures = restart_failures
        self.calls: list[tuple[tuple[str, ...], float | None]] = []
        self.restarted = False
        self.admin_restart_queued = False
        self._delegate = mechanics.SubprocessRunner() if real_compose else None

    @property
    def restart_commands(self) -> list[tuple[str, ...]]:
        """Return every restart command this boundary attempted, in order."""
        return [command for command, _ in self.calls if self._is_restart(command)]

    def run(
        self,
        argv: Any,
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin_path: Path | None = None,
        stdout_path: Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        command = tuple(argv)
        self.calls.append((command, timeout))
        if command[:3] == ("systemctl", "--user", "show"):
            return self._completed(command, self._unit_properties(command[3]))
        if command[:2] == ("systemctl", "show"):
            return self._completed(command, self._unit_properties(command[2]))
        if command[:3] == ("systemctl", "--user", "restart"):
            self._maybe_fail_restart(command)
            self.restarted = True
            return self._completed(command, b"")
        if command[:4] == ("sudo", "-n", "/usr/bin/systemctl", "restart"):
            self._maybe_fail_restart(command)
            self.restarted = True
            return self._completed(command, b"")
        if command[:4] == ("systemctl", "--user", "--no-block", "restart"):
            if self.fail_admin_restart:
                self._fail(command)
            self.admin_restart_queued = True
            return self._completed(command, b"")
        if command[:2] == ("git", "branch"):
            return self._completed(command, b"synthetic-branch\n")
        if command[:2] == ("git", "rev-parse"):
            return self._completed(command, ("c" * 40 + "\n").encode())
        if command[0] == "npm":
            if "admin-web" in command and self.fail_admin_build:
                self._fail(command)
            if "admin-web" not in command and self.fail_step == "frontend":
                self._fail(command)
            return self._completed(command, b"")
        if any(command[: len(prefix)] == prefix for prefix in _COMPOSE_PREFIXES):
            if self._delegate is not None:
                return self._delegate.run(
                    command,
                    cwd=cwd,
                    env=env,
                    stdin_path=stdin_path,
                    stdout_path=stdout_path,
                    timeout=timeout,
                )
            if self.fail_step == "containers":
                self._fail(command)
            return self._completed(command, b"")
        if command[0] == "ss":
            return self._completed(command, self._listener_listing())
        raise AssertionError(f"the rebuild ran an unexpected process command: {command[0]}")

    def _maybe_fail_restart(self, command: tuple[str, ...]) -> None:
        """Fail one restart branch the caller already recognized as this unit's restart."""
        if self.fail_step == "restart":
            self._fail(command)
        if self.restart_failures > 0:
            self.restart_failures -= 1
            self._fail(command)

    def _is_restart(self, command: tuple[str, ...]) -> bool:
        if command[:4] == ("sudo", "-n", "/usr/bin/systemctl", "restart"):
            return len(command) == 5 and command[4] == self.unit
        if command[:3] == ("systemctl", "--user", "restart"):
            return len(command) == 4 and command[3] == self.unit
        return False

    def _fail(self, command: tuple[str, ...]) -> None:
        raise subprocess.CalledProcessError(
            1, list(command), output=_SENTINEL.encode(), stderr=_SENTINEL.encode()
        )

    def _completed(
        self, command: tuple[str, ...], stdout: bytes
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(list(command), 0, stdout=stdout, stderr=b"")

    def _unit_properties(self, unit: str) -> bytes:
        if unit == self.admin_unit:
            load_state = "loaded" if self.admin_loaded else "not-found"
            working_directory = (
                self.root if self.admin_working_directory is None else self.admin_working_directory
            )
            launcher = (
                self.root / "scripts" / "run_admin_web.sh"
                if self.admin_launcher is None
                else self.admin_launcher
            )
        else:
            load_state = "loaded"
            working_directory = self.working_directory
            launcher = self.root / "scripts" / "run_web.sh"
        return "".join(
            f"{name}={value}\n"
            for name, value in (
                ("LoadState", load_state),
                ("ActiveState", "active"),
                ("SubState", "running"),
                ("MainPID", str(_RESTARTED_PID if self.restarted else _MAIN_PID)),
                ("ActiveEnterTimestampMonotonic", "1000000"),
                ("WorkingDirectory", str(working_directory)),
                (
                    "ExecStart",
                    "{ path=/usr/bin/bash ; argv[]=/usr/bin/bash "
                    f"{launcher} ; ignore_errors=no ; "
                    "start_time=[n/a] ; stop_time=[n/a] }",
                ),
            )
        ).encode()

    def _listener_listing(self) -> bytes:
        return "".join(
            f"LISTEN 0 2048 {address} 0.0.0.0:* {owners.format(owner=_RESTARTED_PID)}\n"
            for address, owners in self.listeners
        ).encode()

    def labels(self) -> list[str]:
        """Return the recorded commands as their step labels, in execution order."""
        labels: list[str] = []
        for command, _ in self.calls:
            if command[:3] == ("systemctl", "--user", "show") or command[:2] == (
                "systemctl",
                "show",
            ):
                labels.append("unit")
            elif command[:3] == ("systemctl", "--user", "restart") or command[:4] == (
                "sudo",
                "-n",
                "/usr/bin/systemctl",
                "restart",
            ):
                labels.append("restart")
            elif command[:4] == ("systemctl", "--user", "--no-block", "restart"):
                labels.append("admin-restart")
            elif command[0] == "git":
                labels.append("git")
            elif command[0] == "npm" and "admin-web" in command:
                labels.append("admin-frontend")
            elif command[0] == "npm":
                labels.append("frontend")
            elif command[0] == "ss":
                labels.append("bind")
            else:
                labels.append("containers")
        return labels


def bind_promotion_http(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Route the dataset owner's HTTP client through one mock transport.

    The saved constructor keeps every argument the production helper supplies, including its
    timeout and its trust-environment choice. Only the transport is added.
    """
    real_client = httpx.Client

    def factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(datasets_module.httpx, "Client", factory)
