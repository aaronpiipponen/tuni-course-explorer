"""Contracts for the explicit worker setup/update owner."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from course_explorer_admin import mechanics, provisioning, provisioning_worker
from tests.config._support import set_administrative_controller_environment

REVISION_A = "a" * 40
REVISION_B = "b" * 40


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, message: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            message,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class LocalWorkerTransport:
    """Transport fake that executes recorded worker commands in a real local checkout."""

    def __init__(self, worker_root: Path) -> None:
        self.worker_root = worker_root
        self.calls: list[tuple[str, ...]] = []
        self.provisioning: list[tuple[str, ...]] = []
        self.syncs: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, timeout=None, **kwargs):
        command = tuple(argv)
        if command[:2] == ("uv", "sync"):
            # Record the locked worker dependency sync without executing it in this local
            # checkout. It targets the real worker environment, not the test repository.
            self.syncs.append(command)
            return b""
        if command[:2] == ("uv", "run") or (
            command[:2] == ("bash", "-c") and "apt-get" in command[2]
        ):
            # Record the captured worker bootstrap and resource preparation without executing
            # them. They target the real worker host, not this local checkout.
            self.provisioning.append(command)
            return b""
        self.calls.append(command)
        if command[:2] == ("bash", "-c"):
            completed = subprocess.run(
                ["bash", "-c", command[2]], cwd=self.worker_root, capture_output=True, check=True
            )
        else:
            completed = subprocess.run(
                list(command), cwd=self.worker_root, capture_output=True, check=True
            )
        return completed.stdout

    def scripts(self) -> list[str]:
        return [command[2] for command in self.calls if command[:2] == ("bash", "-c")]


@pytest.fixture()
def git_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return (origin, server, worker) repos sharing one local bare origin."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )
    server = tmp_path / "server"
    subprocess.run(["git", "clone", str(origin), str(server)], check=True, capture_output=True)
    (server / "file.txt").write_text("one")
    _git(server, "add", "file.txt")
    _commit(server, "one")
    (server / "notes.txt").write_text("shared\n")
    _git(server, "add", "notes.txt")
    _commit(server, "notes")
    _git(server, "push", "origin", "main")
    _git(server, "checkout", "-b", "prerequisite-inference")
    (server / "file.txt").write_text("two")
    _git(server, "add", "file.txt")
    _commit(server, "two")
    _git(server, "push", "origin", "prerequisite-inference")
    _git(server, "checkout", "main")
    worker = tmp_path / "worker"
    subprocess.run(["git", "clone", str(origin), str(worker)], check=True, capture_output=True)
    return origin, server, worker


def _wire_setup(
    monkeypatch: pytest.MonkeyPatch,
    origin: Path,
    server: Path,
    worker: Path,
    transport: LocalWorkerTransport,
) -> None:
    monkeypatch.setattr(provisioning, "repository_root", lambda: server)
    monkeypatch.setattr(
        provisioning,
        "load_worker_setup_settings",
        lambda: SimpleNamespace(
            worker_setup_project_url=str(origin), worker_setup_timeout_seconds=60.0
        ),
    )
    monkeypatch.setattr(
        provisioning,
        "load_worker_connection_settings",
        lambda: SimpleNamespace(worker_project_root=worker),
    )
    set_administrative_controller_environment(
        monkeypatch, INGESTION_CONTROLLER_STATE_ROOT="ingestion-state"
    )
    monkeypatch.setattr(provisioning, "SshWslTransport", lambda *args: transport)


def test_code_update_is_ff_only_and_preserves_user_work(
    monkeypatch: pytest.MonkeyPatch, git_pair: tuple[Path, Path, Path]
) -> None:
    """Code update is ff-only on the selected branch, notifies drift, and refuses unsafe states."""
    origin, server, worker = git_pair
    transport = LocalWorkerTransport(worker)
    _wire_setup(monkeypatch, origin, server, worker, transport)

    default = provisioning.update_worker_code(runner=mechanics.SubprocessRunner())
    assert default.branch == "main"
    assert default.server_origin_differs is False
    # A successful code-only update syncs the locked environment exactly once, reinstalling the
    # repository's own editable project so the locked sync refreshes its install metadata.
    assert len(transport.syncs) == 1
    sync = transport.syncs[0]
    assert sync[:2] == ("uv", "sync")
    assert sync[sync.index("--reinstall-package") + 1] == provisioning._PROJECT_NAME

    # A local server commit that is not on its origin counterpart is a notice, not a blocker.
    (server / "file.txt").write_text("three")
    _git(server, "add", "file.txt")
    _commit(server, "three")
    drifted = provisioning.update_worker_code(runner=mechanics.SubprocessRunner())
    assert drifted.server_origin_differs is True

    # A tracked edit and an untracked file keep their bytes across the branch switch, and the
    # update succeeds.
    notes = worker / "notes.txt"
    notes.write_text("user edit\n")
    scratch = worker / "scratch.txt"
    scratch.write_text("work-in-progress")
    syncs_before = len(transport.syncs)
    preserved = provisioning.update_worker_code(
        branch="prerequisite-inference", runner=mechanics.SubprocessRunner()
    )
    assert preserved.branch == "prerequisite-inference"
    assert notes.read_text() == "user edit\n"
    assert scratch.read_text() == "work-in-progress"
    assert len(transport.syncs) == syncs_before + 1
    assert _git(worker, "branch", "--show-current").stdout.decode().strip() == (
        "prerequisite-inference"
    )

    # Git's own overwrite refusal protects a local edit to a file that differs between branches.
    edited_file = worker / "file.txt"
    original_file = edited_file.read_text()
    edited_file.write_text("local edit")
    head_before = _git(worker, "rev-parse", "HEAD").stdout.decode().strip()
    with pytest.raises(subprocess.CalledProcessError):
        provisioning.update_worker_code(branch="main", runner=mechanics.SubprocessRunner())
    assert _git(worker, "rev-parse", "HEAD").stdout.decode().strip() == head_before
    edited_file.write_text(original_file)

    # A code-only update safely selects the independently requested origin branch: the worker
    # switches back to main while the server is main, and syncs once.
    syncs_before_switch = len(transport.syncs)
    switched = provisioning.update_worker_code(branch="main", runner=mechanics.SubprocessRunner())
    assert switched.branch == "main"
    assert _git(worker, "branch", "--show-current").stdout.decode().strip() == "main"
    assert switched.revision == _git(worker, "rev-parse", "HEAD").stdout.decode().strip()
    assert _git(server, "branch", "--show-current").stdout.decode().strip() == "main"
    assert len(transport.syncs) == syncs_before_switch + 1
    assert notes.read_text() == "user edit\n"
    assert scratch.read_text() == "work-in-progress"

    # Full setup keeps its branch selection: the target branch is switched to and pulled. The
    # worker-resource read is stubbed because it is a separate external boundary this local
    # transport cannot execute.
    monkeypatch.setattr(
        provisioning,
        "_read_worker_resources",
        lambda transport, connection: provisioning.WorkerResourcesReport(ready=True, missing=[]),
    )
    prepared = provisioning.prepare_worker(
        branch="prerequisite-inference", runner=mechanics.SubprocessRunner()
    )
    assert prepared.code.branch == "prerequisite-inference"
    worker_head = _git(worker, "rev-parse", "HEAD").stdout.decode().strip()
    assert prepared.code.revision == worker_head
    # Both full-setup steps run on the captured transport path: the bootstrap script and the
    # worker-side `prepare` invocation are recorded rather than executed locally.
    assert any("apt-get" in command[2] for command in transport.provisioning)
    assert any(command[:2] == ("uv", "run") for command in transport.provisioning)

    # A same-branch code-only update fast-forwards without a checkout.
    synced = provisioning.update_worker_code(
        branch="prerequisite-inference", runner=mechanics.SubprocessRunner()
    )
    assert synced.branch == "prerequisite-inference"

    # No push, reset, clean, force, stash, bundle, or remote rewrite is ever emitted.
    joined = " ".join(" ".join(script.split()) for script in transport.scripts())
    for forbidden in ("push", "reset --hard", "clean -", "force", "stash", "bundle", "set-url"):
        assert forbidden not in joined

    # A local selected branch that is ahead of origin is refused without touching work.
    (worker / "file.txt").write_text("diverged")
    _git(worker, "add", "file.txt")
    _commit(worker, "diverged")
    diverged_head = _git(worker, "rev-parse", "HEAD").stdout.decode().strip()
    with pytest.raises(subprocess.CalledProcessError):
        provisioning.update_worker_code(
            branch="prerequisite-inference", runner=mechanics.SubprocessRunner()
        )
    assert _git(worker, "rev-parse", "HEAD").stdout.decode().strip() == diverged_head


class ScriptedWorkerRunner:
    """Worker process boundary scripted to one readiness read."""

    def __init__(self, *, missing_package: str | None = None, docker_ready: bool = True) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.interactive_calls: list[tuple[str, ...]] = []
        self.missing_package = missing_package
        self.docker_ready = docker_ready

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        if command[:1] == ("dpkg-query",):
            if command[-1] == self.missing_package:
                raise subprocess.CalledProcessError(1, list(command))
            return subprocess.CompletedProcess(list(command), 0, stdout=b"install ok installed\n")
        if command[:4] == ("sudo", "-n", "docker", "info"):
            if not self.docker_ready:
                raise subprocess.CalledProcessError(1, list(command))
            return subprocess.CompletedProcess(list(command), 0, stdout=b"")
        compose_prefix = provisioning_worker._sudo_compose_prefix()
        if command[: len(compose_prefix)] == compose_prefix:
            if command[-1] == "version":
                return subprocess.CompletedProcess(list(command), 0, stdout=b"")
            if "config" in command:
                return subprocess.CompletedProcess(list(command), 0, stdout=b"postgres:16\n")
        if command[:4] == ("sudo", "-n", "docker", "image"):
            return subprocess.CompletedProcess(list(command), 0, stdout=b"")
        if command[:2] == ("git", "-C"):
            directory = Path(command[2])
            if command[3:] == ("rev-parse", "HEAD"):
                revision = directory.name.removeprefix("runtime-")
                return subprocess.CompletedProcess(
                    list(command), 0, stdout=f"{revision}\n".encode()
                )
            if command[3:] == ("status", "--porcelain"):
                return subprocess.CompletedProcess(list(command), 0, stdout=b"")
        raise AssertionError(f"unexpected check command: {command}")

    def run_interactive(self, argv, *, cwd=None, env=None, timeout=None):
        """Record one streamed helper mutation and delegate to ``run`` for its external effect."""
        self.interactive_calls.append(tuple(argv))
        self.run(argv, cwd=cwd, env=env, timeout=timeout)


def _wire_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    translation: Path,
    generation: Path,
    rerank: Path,
    generation_url: str | None = "https://example.invalid/generation.gguf",
    artifact_sha256: str | None = None,
) -> None:
    monkeypatch.setattr(
        provisioning_worker,
        "load_translation_settings",
        lambda: SimpleNamespace(
            translation_artifact_path=translation,
            translation_artifact_sha256=artifact_sha256 or "1" * 64,
            translation_runtime_revision=REVISION_A,
        ),
    )
    monkeypatch.setattr(
        provisioning_worker,
        "load_inference_settings",
        lambda: SimpleNamespace(
            inference_primary_artifact_path=generation,
            inference_primary_artifact_sha256=artifact_sha256 or "2" * 64,
            inference_runtime_revision=REVISION_B,
            primary_artifact_url=generation_url,
        ),
    )
    monkeypatch.setattr(
        provisioning_worker,
        "load_inference_rerank_settings",
        lambda: SimpleNamespace(
            inference_rerank_artifact_path=rerank,
            inference_rerank_artifact_sha256=artifact_sha256 or "3" * 64,
            rerank_artifact_url="https://example.invalid/rerank.gguf",
        ),
    )
    monkeypatch.setattr(
        provisioning_worker,
        "load_worker_setup_settings",
        lambda: SimpleNamespace(worker_setup_timeout_seconds=60.0),
    )
    monkeypatch.setattr(
        mechanics,
        "runtime_checkout_directory",
        lambda revision: tmp_path / f"runtime-{revision}",
    )


def _wire_present_resources(
    monkeypatch: pytest.MonkeyPatch, root: Path, *, generation_present: bool = True
) -> None:
    """Wire one root whose configured artifacts and executable runtimes already exist."""
    digest = hashlib.sha256(b"tiny-artifact").hexdigest()
    translation = root / "translation.gguf"
    generation = root / "generation.gguf"
    rerank = root / "rerank.gguf"
    _wire_resources(
        monkeypatch,
        root,
        translation=translation,
        generation=generation,
        rerank=rerank,
        artifact_sha256=digest,
    )
    translation.write_bytes(b"tiny-artifact")
    rerank.write_bytes(b"tiny-artifact")
    if generation_present:
        generation.write_bytes(b"tiny-artifact")
    for revision in (REVISION_A, REVISION_B):
        executable = root / f"runtime-{revision}" / "build" / "bin" / "llama-server"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"")
        executable.chmod(0o700)


def test_worker_check_is_read_only_and_reports_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Check names fixed components without installing, downloading, or starting."""
    runner = ScriptedWorkerRunner(missing_package="cmake", docker_ready=False)
    _wire_resources(
        monkeypatch,
        tmp_path,
        translation=tmp_path / "translation.gguf",
        generation=tmp_path / "generation.gguf",
        rerank=tmp_path / "rerank.gguf",
    )

    report = provisioning_worker.check_worker_resources(runner=runner)

    assert report.ready is False
    assert report.missing == [
        "cmake",
        "docker",
        "translation-artifact",
        "generation-artifact",
        "rerank-artifact",
        "translation-runtime",
        "inference-runtime",
    ]
    assert all(
        command[0] not in {"curl", "apt-get", "git", "systemctl", "uv"} for command in runner.calls
    )

    # An all-present root with genuine tiny hashes and executable dummy runtimes is ready, and
    # check performs only captured read-only probes.
    present_root = tmp_path / "present"
    present_root.mkdir()
    _wire_present_resources(monkeypatch, present_root)
    present_runner = ScriptedWorkerRunner()
    present = provisioning_worker.check_worker_resources(runner=present_runner)
    assert present.ready is True
    assert present.missing == []
    assert present_runner.interactive_calls == []

    # A runtime file that exists but cannot be executed is not ready, and check never builds.
    inference_executable = present_root / f"runtime-{REVISION_B}" / "build" / "bin" / "llama-server"
    inference_executable.chmod(0o600)
    non_executable_runner = ScriptedWorkerRunner()
    non_executable = provisioning_worker.check_worker_resources(runner=non_executable_runner)
    assert non_executable.ready is False
    assert non_executable.missing == ["inference-runtime"]
    assert non_executable_runner.interactive_calls == []


def test_artifact_preparation_verifies_before_publish_and_preserves_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A bad download is never published and a mismatching installed artifact is left untouched."""
    installed = tmp_path / "translation.gguf"
    installed.write_bytes(b"installed-mismatch")
    runner = ScriptedWorkerRunner()
    _wire_resources(
        monkeypatch,
        tmp_path,
        translation=installed,
        generation=tmp_path / "generation.gguf",
        rerank=tmp_path / "rerank.gguf",
    )

    with pytest.raises(ValueError):
        provisioning_worker.prepare_worker_resources(runner=runner)
    assert installed.read_bytes() == b"installed-mismatch"

    class DownloadRunner(ScriptedWorkerRunner):
        def __init__(self, *, download_bytes: bytes = b"bad-download", **kwargs) -> None:
            super().__init__(**kwargs)
            self.download_bytes = download_bytes

        def run(self, argv, **kwargs):
            command = tuple(argv)
            if command[0] == "curl":
                self.calls.append(command)
                Path(command[command.index("--output") + 1]).write_bytes(self.download_bytes)
                return subprocess.CompletedProcess(list(command), 0, stdout=b"")
            return super().run(argv, **kwargs)

    download_runner = DownloadRunner()
    download_root = tmp_path / "download"
    download_root.mkdir()
    owner_scratch = download_root / "generation.gguf.download"
    owner_scratch.write_bytes(b"owner-bytes")
    _wire_resources(
        monkeypatch,
        download_root,
        translation=download_root / "translation.gguf",
        generation=download_root / "generation.gguf",
        rerank=download_root / "rerank.gguf",
    )
    with pytest.raises(ValueError):
        provisioning_worker.prepare_worker_resources(runner=download_runner)
    assert not (download_root / "generation.gguf").exists()
    assert owner_scratch.read_bytes() == b"owner-bytes"
    assert sorted(path.name for path in download_root.iterdir()) == ["generation.gguf.download"]
    assert any(command[0] == "curl" for command in download_runner.calls)

    # A valid download publishes to its configured target alone and leaves owner scratch untouched.
    success_root = tmp_path / "success"
    success_root.mkdir()
    success_scratch = success_root / "generation.gguf.download"
    success_scratch.write_bytes(b"owner-bytes")
    _wire_present_resources(monkeypatch, success_root, generation_present=False)
    success_runner = DownloadRunner(download_bytes=b"tiny-artifact")
    prepared = provisioning_worker.prepare_worker_resources(runner=success_runner)
    assert prepared.ready is True
    assert prepared.missing == []
    published = success_root / "generation.gguf"
    assert published.read_bytes() == b"tiny-artifact"
    assert (published.stat().st_mode & 0o777) == 0o600
    assert success_scratch.read_bytes() == b"owner-bytes"
    assert not any(path.name.startswith(".generation.gguf-") for path in success_root.iterdir())
