"""Test-only bootstrap that runs the actual worker/server/remote owners locally.

It installs only the external model/runtime/clock and transport boundaries and delegates to the
real product owners: server mode runs the real ``run_lifecycle_worker``, worker mode runs the
real stage ``main`` (or the real ``run_worker_session`` for ``run`` on the subprocess main thread),
and remote mode delegates to the real ``remote.main``. The real product owners provide the worker
state machine and every state/control/import/return/receipt DTO.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from course_explorer_admin import mechanics
from tests.admin._remote_support import (
    LocalWorkerTransport,
    fake_state_path,
    model_response_released,
    read_fake,
)


class _Patcher:
    """Monkeypatch shim for the bootstrap subprocess."""

    def __init__(self) -> None:
        self._saved: list[tuple[object, str, object]] = []
        self._env: list[tuple[str, str | None]] = []

    def setattr(self, target: object, name: str, value: object) -> None:
        self._saved.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def setenv(self, name: str, value: str) -> None:
        self._env.append((name, os.environ.get(name)))
        os.environ[name] = value


def _redirect_repository_root(root: Path) -> None:
    import course_explorer.administration as administration
    import course_explorer_admin.datasets as datasets_module
    import course_explorer_admin.lifecycle as lifecycle
    import course_explorer_admin.local_stages as local_stages
    import course_explorer_admin.remote as remote
    from course_explorer import configuration

    # Import the configuration owner before any redirect so its file reads stay bound to the real
    # prepared checkout: the tracked TOML and the device-local ignored ``.env`` live there, never under
    # this process's temporary worker/state root. The redirected owners below own only session state.
    configuration.read_public_configuration(administration.repository_root())

    administration.repository_root = lambda: root
    datasets_module.repository_root = lambda: root
    lifecycle.repository_root = lambda: root
    local_stages.repository_root = lambda: root
    remote.repository_root = lambda: root


def _install_cwd_runner(patcher: _Patcher, checkout: Path) -> None:
    """Redirect only git and Compose command cwd to the real prepared checkout.

    The worker/server data roots are temporary, so their relative tracked Compose/config files
    resolve against the real checkout with the same dump/restore/create/drop and checkout reads.
    """
    real_run = mechanics.SubprocessRunner.run

    def run(self, argv, **kwargs):
        command = tuple(argv)
        prefix = mechanics.compose_prefix()
        if command[:1] == ("git",) or command[: len(prefix)] == prefix:
            kwargs["cwd"] = checkout
        return real_run(self, argv, **kwargs)

    patcher.setattr(mechanics.SubprocessRunner, "run", run)


def _install_boot_identity(patcher: _Patcher, boundary_path: Path) -> None:
    from uuid import UUID

    def current_boot_id() -> UUID:
        return UUID(
            str(read_fake(boundary_path).get("wsl_boot", "00000000-0000-4000-8000-000000000001"))
        )

    patcher.setattr(mechanics, "current_boot_id", current_boot_id)


def _external_monotonic(boundary_path: Path):
    def monotonic() -> float:
        return float(read_fake(boundary_path).get("monotonic_seconds", 0.0))

    return monotonic


def _install_inference_boundaries(patcher: _Patcher, boundary_path: Path) -> None:
    from course_explorer.config import load_inference_settings
    from course_explorer_admin import runtime
    from tests.inference._http_support import InferenceHttpBoundary, install_inference_http

    boundary = InferenceHttpBoundary(load_inference_settings(), prompt_tokens=1000)
    real_handle = boundary.handle

    def gated_handle(request):
        while not model_response_released(boundary_path):
            time.sleep(0.02)
        time.sleep(0.5)
        return real_handle(request)

    boundary.handle = gated_handle  # type: ignore[method-assign]
    install_inference_http(patcher, boundary)
    patcher.setattr(runtime, "OwnedWorkerRuntime", _recording_owner_factory())


def _recording_owner_factory():
    from tests.admin.inference._worker_support import RecordingOwner

    pid = os.getpid()

    def factory(runner, *, root, directory, sleep=time.sleep):
        return RecordingOwner(runner, root=root, directory=directory, sleep=sleep, pid=pid)

    return factory


def _install_translation_boundaries(patcher: _Patcher, boundary_path: Path) -> None:
    import httpx

    from course_explorer.translation import commands as translation_commands
    from tests.admin.translation._worker_support import _valid_chat_response

    def handler(request):
        while not model_response_released(boundary_path):
            time.sleep(0.02)
        time.sleep(0.5)
        return httpx.Response(200, json=_valid_chat_response())

    transport = httpx.MockTransport(handler)
    real_provider = translation_commands.TranslationProvider

    def provider(settings, **kwargs):
        return real_provider(settings, transport=transport, **kwargs)

    patcher.setattr(translation_commands, "TranslationProvider", provider)


def install_worker_boundaries(
    monkeypatch: Any, *, root: Path, boundary_path: Path, stage: str
) -> None:
    """Install only the boundary substitutions and delegate to the product owners."""
    checkout = Path(os.environ["TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT"])
    _redirect_repository_root(root)
    _install_cwd_runner(monkeypatch, checkout)
    _install_boot_identity(monkeypatch, boundary_path)
    import course_explorer_admin.remote_stages as remote_stages
    import course_explorer_admin.runtime as runtime
    import course_explorer_admin.worker_session as worker_session

    monkeypatch.setattr(
        remote_stages,
        "_transport",
        lambda runner, connection: LocalWorkerTransport(boundary_path),
    )
    # The shared runtime-process boundary for every owner reference.
    factory = _recording_owner_factory()
    monkeypatch.setattr(runtime, "OwnedWorkerRuntime", factory)
    monkeypatch.setattr(worker_session, "OwnedWorkerRuntime", factory)
    if stage == "inference":
        _install_inference_boundaries(monkeypatch, boundary_path)
    else:
        from course_explorer_admin.translation import controller_worker as translation_worker

        monkeypatch.setattr(translation_worker, "OwnedWorkerRuntime", factory)
        _install_translation_boundaries(monkeypatch, boundary_path)


def _stage_object(stage: str, factory: Callable[[str], object] | None = None):
    if stage == "inference":
        if factory is not None:
            return factory(stage)
        from course_explorer_admin.inference.controller_worker import InferenceWorkerStage

        return InferenceWorkerStage()
    from course_explorer_admin.translation.controller_worker import TranslationWorkerStage

    return TranslationWorkerStage()


def _stage_module(stage: str):
    if stage == "inference":
        from course_explorer_admin.inference import controller_worker

        return controller_worker
    from course_explorer_admin.translation import controller_worker

    return controller_worker


def _run_worker(
    stage: str,
    subcommand: str,
    session_id: str,
    boundary_path: Path,
    *,
    stage_factory: Callable[[str], object] | None = None,
    entry: Callable[[str, list[str]], int] | None = None,
) -> int:
    from course_explorer_admin import worker_session

    if subcommand == "run":
        return worker_session.run_worker_session(
            _stage_object(stage, stage_factory),
            session_id,
            runner=mechanics.SubprocessRunner(),
            monotonic=_external_monotonic(boundary_path),
        )
    if entry is not None:
        return entry(stage, [subcommand, session_id])
    return _stage_module(stage).main([subcommand, session_id])


def _run_remote(subcommand: str, session_id: str) -> int:
    from course_explorer_admin import remote

    return remote.main([subcommand, session_id])


def main(
    argv: list[str] | None = None,
    *,
    server_stage_factory: Callable[[str], object] | None = None,
    worker_stage_factory: Callable[[str], object] | None = None,
    worker_entry: Callable[[str, list[str]], int] | None = None,
) -> int:
    """Run one bootstrap mode, using the caller's explicit factories/entries when supplied.

    An absent callback retains the base default, so the same bootstrap drives both the
    base lifecycle and a wrapper that owns an explicit additional route.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("mode", choices=("server", "worker", "remote"))
    parser.add_argument("stage", choices=("translation", "inference"))
    parser.add_argument("subcommand")
    parser.add_argument("session_id")
    args = parser.parse_args(argv)
    root = Path(args.root)
    boundary_path = fake_state_path(root)
    target_root = root if args.mode == "server" else Path(os.environ["S7D_WORKER_DATA_ROOT"])

    patcher = _Patcher()
    install_worker_boundaries(
        patcher, root=target_root, boundary_path=boundary_path, stage=args.stage
    )
    try:
        if args.mode == "server":
            from course_explorer_admin import lifecycle
            from course_explorer_admin.worker import make_stage, run_lifecycle_worker

            resolve = server_stage_factory if server_stage_factory is not None else make_stage
            stage = resolve(args.stage)
            state_root = lifecycle.stage_state_root(args.stage)
            status = run_lifecycle_worker(
                stage, state_root, args.session_id, runner=mechanics.SubprocessRunner()
            )
            print(status.model_dump_json())
            return 0
        if args.mode == "worker":
            return _run_worker(
                args.stage,
                args.subcommand,
                args.session_id,
                boundary_path,
                stage_factory=worker_stage_factory,
                entry=worker_entry,
            )
        return _run_remote(args.subcommand, args.session_id)
    except Exception as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
