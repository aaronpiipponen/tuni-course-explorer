"""Contracts for the shared owned worker runtime and its configured builders."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import InferenceRerankSettings, InferenceSettings, TranslationSettings
from course_explorer_admin import mechanics
from course_explorer_admin import runtime as runtime_module
from course_explorer_admin.runtime import (
    OwnedWorkerRuntime,
    WorkerInferenceRuntime,
    WorkerRuntimeSpec,
    generation_runtime_spec,
    rerank_runtime_spec,
    translation_runtime_spec,
)
from tests.config._support import (
    TRANSLATION_KEYS,
    set_inference_environment,
)

REVISION = "e" * 40
ARTIFACT_BYTES = b"pinned-artifact"


def _runtime_directory(home: Path) -> Path:
    return home / ".local" / "src" / f"llama.cpp-{REVISION}"


def _prepare_runtime(home: Path) -> Path:
    """Create the one prepared runtime directory with an executable llama-server."""
    directory = _runtime_directory(home)
    (directory / "build" / "bin").mkdir(parents=True)
    executable = directory / "build" / "bin" / "llama-server"
    executable.write_bytes(b"binary")
    executable.chmod(0o755)
    return directory


def _artifact(home: Path) -> tuple[Path, str]:
    artifact = home / "models" / "model.gguf"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(ARTIFACT_BYTES)
    return artifact, hashlib.sha256(ARTIFACT_BYTES).hexdigest()


def _spec(home: Path, *, port: int = 18081) -> WorkerRuntimeSpec:
    artifact, digest = _artifact(home)
    return WorkerRuntimeSpec(
        mode="translation",
        argv=(
            str(_runtime_directory(home) / "build" / "bin" / "llama-server"),
            "--model",
            str(artifact),
        ),
        revision=REVISION,
        artifact=artifact,
        artifact_sha256=digest,
        host="127.0.0.1",
        port=port,
    )


class FakeProcess:
    """A live-then-terminated process double with a stable PID."""

    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.terminated = False
        self.waited = False
        self._alive = True

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False

    def wait(self, timeout=None) -> int:
        self.waited = True
        return 0

    def poll(self) -> int | None:
        return None if self._alive else 0


class FakeRunner:
    """Scripted process runner for the owned-runtime start/health/stop paths."""

    def __init__(self, *, directory: Path, listener: bytes = b"", health: str = "ok") -> None:
        self.directory = directory
        self.listener = listener
        self.health = health
        self.calls: list[tuple[str, ...]] = []
        self.popen_kwargs: dict | None = None
        self.process = FakeProcess()
        self.record_present_at_first_probe = False
        self._probed = False

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        if command[:2] == ("git", "-C"):
            if command[-2:] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(
                    list(command), 0, stdout=(REVISION + "\n").encode(), stderr=b""
                )
            return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
        if command[:1] == ("ss",):
            return subprocess.CompletedProcess(list(command), 0, stdout=self.listener, stderr=b"")
        if command[:1] == ("curl",):
            if not self._probed:
                self._probed = True
                self.record_present_at_first_probe = (self.directory / "runtime.json").is_file()
            if self.health == "fail":
                raise subprocess.CalledProcessError(1, list(command))
            return subprocess.CompletedProcess(list(command), 0, stdout=b"{}", stderr=b"")
        raise AssertionError(f"unexpected command {command}")

    def popen(
        self,
        argv,
        *,
        cwd=None,
        env=None,
        stdin_path=None,
        stdout_path,
        stderr_path,
        start_new_session=False,
        inherit_environment=True,
    ):
        self.popen_kwargs = {
            "env": env,
            "start_new_session": start_new_session,
            "inherit_environment": inherit_environment,
        }
        return self.process


class FakeOwner:
    """A recording stand-in for OwnedWorkerRuntime inside the inference adapter."""

    def __init__(self, runner, *, root, directory, sleep=time.sleep):
        self.starts: list[WorkerRuntimeSpec] = []
        self.stops = 0
        self.pid = os.getpid()

    def start(self, spec, *, attempts, interval, timeout):
        self.starts.append(spec)
        return self.pid

    def stop(self, *, timeout, interval):
        self.stops += 1


def test_configured_runtime_builders_and_inference_mode_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Builders emit the exact configured flags. The adapter reuses/switches keys and delegates."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    translation = TranslationSettings(**TRANSLATION_KEYS)
    set_inference_environment(monkeypatch)
    inference = InferenceSettings()
    rerank = InferenceRerankSettings()
    first, second = inference.inference_local_variants

    translation_spec = translation_runtime_spec(translation, tmp_path)
    assert translation_spec.mode == "translation"
    assert translation_spec.artifact == tmp_path / translation.translation_artifact_path
    assert translation_spec.artifact_sha256 == translation.translation_artifact_sha256
    assert translation_spec.revision == translation.translation_runtime_revision
    assert translation_spec.host == translation.translation_host
    assert translation_spec.port == translation.translation_port

    rerank_spec = rerank_runtime_spec(rerank, tmp_path)
    rerank_argv = rerank_spec.argv
    assert rerank_spec.mode == "rerank"
    assert rerank_spec.artifact == tmp_path / rerank.inference_rerank_artifact_path
    assert rerank_spec.artifact_sha256 == rerank.inference_rerank_artifact_sha256
    assert rerank_spec.revision == rerank.inference_runtime_revision
    assert rerank_spec.host == rerank.inference_rerank_host
    assert rerank_spec.port == rerank.inference_rerank_port

    first_spec = generation_runtime_spec(inference, first, tmp_path)
    assert first_spec.mode == "generation"
    assert first_spec.port == first.port
    assert first_spec.artifact == tmp_path / inference.inference_primary_artifact_path
    assert first_spec.artifact_sha256 == inference.inference_primary_artifact_sha256
    assert first_spec.revision == inference.inference_runtime_revision
    assert first_spec.host == inference.inference_host
    assert "--spec-draft-n-max" in first_spec.argv
    assert first_spec.argv[first_spec.argv.index("--spec-draft-n-max") + 1] == str(
        first.mtp_draft_n_max
    )
    second_spec = generation_runtime_spec(inference, second, tmp_path)
    assert "--spec-draft-n-max" not in second_spec.argv
    for argv in (translation_spec.argv, rerank_argv, first_spec.argv):
        joined = " ".join(argv)
        for forbidden in ("--api-key", "--host 0.0.0.0", "--model-url", "--webui"):
            assert forbidden not in joined

    owners: list[FakeOwner] = []

    def owner_factory(*args, **kwargs) -> FakeOwner:
        owner = FakeOwner(*args, **kwargs)
        owners.append(owner)
        return owner

    monkeypatch.setattr(runtime_module, "OwnedWorkerRuntime", owner_factory)
    adapter = WorkerInferenceRuntime(
        FakeRunner(directory=tmp_path),
        root=tmp_path,
        directory=tmp_path,
        settings=inference,
        rerank_settings=rerank,
        health_attempts=3,
        interval=0.01,
        stop_timeout_seconds=5.0,
        sleep=lambda seconds: None,
    )
    owner = owners[0]
    adapter.activate(first)
    assert len(owner.starts) == 1 and owner.stops == 0
    adapter.activate(first)
    assert len(owner.starts) == 1 and owner.stops == 0
    adapter.start_rerank()
    assert owner.stops == 1 and owner.starts[-1].mode == "rerank"
    adapter.start_rerank()
    assert owner.stops == 1 and len(owner.starts) == 2
    adapter.stop_rerank()
    assert owner.stops == 2
    adapter.stop_rerank()
    assert owner.stops == 2
    foreign = first.model_copy(update={"alias": "foreign-key"})
    with pytest.raises(ValueError):
        adapter.activate(foreign)
    assert owner.stops == 2
    adapter.stop()
    assert owner.stops == 3


def test_owned_runtime_start_stop_and_unhealthy_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The record precedes health, the child is least-privilege, and cleanup follows failure."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    directory = _prepare_runtime(tmp_path)
    spec = _spec(tmp_path)

    # Scripted liveness from the fake process itself, never the host process table.
    bound: list[FakeProcess] = []
    monkeypatch.setattr(
        runtime_module.mechanics,
        "pid_is_alive",
        lambda pid: any(process.pid == pid and process.poll() is None for process in bound),
    )

    runner = FakeRunner(directory=directory)
    bound[:] = [runner.process]
    owner = OwnedWorkerRuntime(runner, root=tmp_path, directory=directory, sleep=lambda s: None)
    assert owner.start(spec, attempts=3, interval=0.01, timeout=5.0) == 4242
    assert runner.record_present_at_first_probe
    assert runner.popen_kwargs is not None
    assert runner.popen_kwargs["inherit_environment"] is False
    assert runner.popen_kwargs["start_new_session"] is True
    assert set(runner.popen_kwargs["env"]) == {"HOME", "PATH", "HSA_ENABLE_DXG_DETECTION"}
    assert runner.popen_kwargs["env"]["HSA_ENABLE_DXG_DETECTION"] == "1"
    record = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
    assert record["pid"] == 4242
    assert tuple(record["argv"]) == spec.argv
    owner.stop(timeout=5.0, interval=0.01)
    assert runner.process.terminated and runner.process.waited
    assert not (directory / "runtime.json").exists()

    unhealthy = FakeRunner(directory=directory, health="fail")
    bound[:] = [unhealthy.process]
    failing = OwnedWorkerRuntime(
        unhealthy, root=tmp_path, directory=directory, sleep=lambda s: None
    )
    with pytest.raises(RuntimeError):
        failing.start(spec, attempts=3, interval=0.01, timeout=5.0)
    assert unhealthy.process.terminated and unhealthy.process.waited
    assert not (directory / "runtime.json").exists()


def test_inference_runtime_rejects_exited_owned_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A crashed current child (an unreaped zombie) is rejected on repeat activation."""
    set_inference_environment(monkeypatch)
    inference = InferenceSettings()
    rerank = InferenceRerankSettings()
    first = inference.inference_local_variants[0]
    directory = tmp_path / "runtime"
    directory.mkdir()
    spec = WorkerRuntimeSpec(
        mode="generation",
        argv=(sys.executable, "-c", "import signal; signal.pause()"),
        revision=REVISION,
        artifact=tmp_path / "model.gguf",
        artifact_sha256="0" * 64,
        host="127.0.0.1",
        port=18099,
    )
    monkeypatch.setattr(runtime_module, "generation_runtime_spec", lambda *a, **k: spec)
    monkeypatch.setattr(runtime_module, "require_prepared_runtime", lambda **k: None)

    class SyntheticRunner:
        """Fake ss/curl success and a real detached synthetic child for popen."""

        def __init__(self) -> None:
            self.spawns = 0
            self.child: subprocess.Popen[bytes] | None = None

        def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
            command = tuple(argv)
            if command[:1] == ("ss",):
                return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
            if command[:1] == ("curl",):
                return subprocess.CompletedProcess(list(command), 0, stdout=b"{}", stderr=b"")
            raise AssertionError(f"unexpected command {command}")

        def popen(
            self,
            argv,
            *,
            cwd=None,
            env=None,
            stdin_path=None,
            stdout_path,
            stderr_path,
            start_new_session=False,
            inherit_environment=True,
        ):
            self.spawns += 1
            self.child = mechanics.SubprocessRunner().popen(
                argv,
                cwd=cwd,
                env=env,
                stdin_path=stdin_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                start_new_session=start_new_session,
                inherit_environment=inherit_environment,
            )
            return self.child

    runner = SyntheticRunner()
    adapter = WorkerInferenceRuntime(
        runner,
        root=tmp_path,
        directory=directory,
        settings=inference,
        rerank_settings=rerank,
        health_attempts=3,
        interval=0.01,
        stop_timeout_seconds=5.0,
        sleep=lambda seconds: None,
    )
    try:
        adapter.activate(first)
        assert runner.spawns == 1
        child = runner.child
        assert child is not None
        child.terminate()
        # Observe the exit without reaping, so the child is an unreaped zombie.
        os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
        with pytest.raises(RuntimeError):
            adapter.activate(first)
        assert runner.spawns == 1
    finally:
        adapter.stop()
    assert not (directory / "runtime.json").exists()


def test_owned_runtime_refuses_occupied_or_foreign_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An occupied port spawns nothing. A reused foreign PID is never signalled or overwritten."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    directory = _prepare_runtime(tmp_path)
    spec = _spec(tmp_path)

    occupied = FakeRunner(
        directory=directory,
        listener=b"LISTEN 0 4096 127.0.0.1:18081 0.0.0.0:*\n",
    )
    owner = OwnedWorkerRuntime(occupied, root=tmp_path, directory=directory, sleep=lambda s: None)
    with pytest.raises(ValueError):
        owner.start(spec, attempts=3, interval=0.01, timeout=5.0)
    assert occupied.popen_kwargs is None

    record = mechanics.OwnedProcessRecord(
        schema_version=1,
        pid=os.getpid(),
        argv=("foreign", "runtime"),
        boot_id=mechanics.current_boot_id(),
    )
    atomic_write_private_text(directory / "runtime.json", administrative_json(record))
    before = (directory / "runtime.json").read_bytes()
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr("os.kill", lambda pid, sig: signals.append((pid, sig)))
    reused = OwnedWorkerRuntime(
        FakeRunner(directory=directory), root=tmp_path, directory=directory, sleep=lambda s: None
    )
    with pytest.raises(ValueError):
        reused.stop(timeout=5.0, interval=0.01)
    assert [sig for _, sig in signals if sig != 0] == []
    assert (directory / "runtime.json").read_bytes() == before
    with pytest.raises(ValueError):
        reused.start(spec, attempts=3, interval=0.01, timeout=5.0)
    assert (directory / "runtime.json").read_bytes() == before


def test_old_boot_record_never_signals_reused_pid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After a simulated reboot, stop retires only its own record and signals no live PID."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    directory = _prepare_runtime(tmp_path)
    old_boot = uuid4()
    assert old_boot != mechanics.current_boot_id()
    record = mechanics.OwnedProcessRecord(
        schema_version=1, pid=os.getpid(), argv=("old", "runtime"), boot_id=old_boot
    )
    atomic_write_private_text(directory / "runtime.json", administrative_json(record))
    checkpoint = directory / "checkpoint.json"
    checkpoint.write_bytes(b"unrelated-durable-checkpoint")

    signals: list[tuple[int, int]] = []
    monkeypatch.setattr("os.kill", lambda pid, sig: signals.append((pid, sig)))
    owner = OwnedWorkerRuntime(
        FakeRunner(directory=directory), root=tmp_path, directory=directory, sleep=lambda s: None
    )
    owner.stop(timeout=5.0, interval=0.01)
    assert signals == []
    assert not (directory / "runtime.json").exists()
    assert checkpoint.read_bytes() == b"unrelated-durable-checkpoint"
