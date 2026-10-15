"""One owned, least-privilege worker runtime for translation, rerank, and generation.

This module owns the single recurring model-process launcher shared by the translation
worker and the inference worker. It has three parts: pure configured builders that turn
validated settings into the exact loopback ``llama-server`` argv, one :class:`OwnedWorkerRuntime`
that starts and stops exactly one child through one ``runtime.json`` identity record, and
one :class:`WorkerInferenceRuntime` that exposes the product
``activate``/``stop``/``start_rerank``/``stop_rerank``/``request_scope`` protocol over that owner.

Every fresh launch reuses the authoritative prepared-runtime checks (checkout revision, executable
readiness, and the pinned artifact SHA-256), so a fresh spawn verifies the artifact hash, while a
live same-spec reuse performs no further spawn, hash, or health loop. It downloads, builds, and
installs only through the explicit provisioning path, derives ownership from its own boot and argv
record, and signals only a process it proves it owns. An exited current child (including an unreaped
zombie) is not live and clears the handle on successful stop. Model children launch with a closed
environment allowlist so no ambient credential crosses into them, and the module reads
``/proc/<pid>/cmdline`` for identity.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
)
from course_explorer.config import (
    InferenceLocalVariantSettings,
    InferenceRerankSettings,
    InferenceSettings,
    TranslationSettings,
)
from course_explorer_admin import mechanics
from course_explorer_admin.provisioning_worker import require_prepared_runtime
from course_explorer_admin.reboot import WorkerGpuClock

_RECORD_NAME = "runtime.json"
_LOG_NAME = "runtime.log"


@dataclass(frozen=True)
class WorkerRuntimeSpec:
    """One configured runtime launch: mode, exact argv, pinned identity, and loopback binding."""

    mode: Literal["translation", "rerank", "generation"]
    argv: tuple[str, ...]
    revision: str
    artifact: Path
    artifact_sha256: str
    host: str
    port: int


def _runtime_binary(revision: str) -> str:
    """Return the one convention-owned llama-server binary for a runtime revision."""
    return str(mechanics.runtime_checkout_directory(revision) / "build" / "bin" / "llama-server")


def translation_runtime_spec(settings: TranslationSettings, root: Path) -> WorkerRuntimeSpec:
    """Return the configured translation runtime launch."""
    artifact = root / settings.translation_artifact_path
    return WorkerRuntimeSpec(
        mode="translation",
        argv=(
            _runtime_binary(settings.translation_runtime_revision),
            "--model",
            str(artifact),
            "--alias",
            settings.translation_model_alias,
            "--host",
            settings.translation_host,
            "--port",
            str(settings.translation_port),
            "--ctx-size",
            str(settings.translation_context_size),
            "--parallel",
            str(settings.translation_parallel),
            "--n-gpu-layers",
            settings.translation_gpu_layers,
            "--jinja",
            "--offline",
            "--no-webui",
        ),
        revision=settings.translation_runtime_revision,
        artifact=artifact,
        artifact_sha256=settings.translation_artifact_sha256,
        host=settings.translation_host,
        port=settings.translation_port,
    )


def rerank_runtime_spec(settings: InferenceRerankSettings, root: Path) -> WorkerRuntimeSpec:
    """Return the cross-encoder loopback launch contract."""
    artifact = root / settings.inference_rerank_artifact_path
    batch_size = str(settings.inference_rerank_batch_size)
    return WorkerRuntimeSpec(
        mode="rerank",
        argv=(
            _runtime_binary(settings.inference_runtime_revision),
            "--model",
            str(artifact),
            "--alias",
            settings.inference_rerank_model_alias,
            "--host",
            settings.inference_rerank_host,
            "--port",
            str(settings.inference_rerank_port),
            "--ctx-size",
            str(settings.inference_rerank_context_size),
            "--batch-size",
            batch_size,
            "--ubatch-size",
            batch_size,
            "--n-gpu-layers",
            "all",
            "--embedding",
            "--pooling",
            "rank",
            "--reranking",
            "--parallel",
            "1",
            "--fit",
            "off",
            "--offline",
            "--no-webui",
        ),
        revision=settings.inference_runtime_revision,
        artifact=artifact,
        artifact_sha256=settings.inference_rerank_artifact_sha256,
        host=settings.inference_rerank_host,
        port=settings.inference_rerank_port,
    )


def generation_runtime_spec(
    settings: InferenceSettings, variant: InferenceLocalVariantSettings, root: Path
) -> WorkerRuntimeSpec:
    """Return the generation launch for one selected ordered local fit key."""
    artifact = root / settings.inference_primary_artifact_path
    argv = [
        _runtime_binary(settings.inference_runtime_revision),
        "--model",
        str(artifact),
        "--alias",
        variant.alias,
        "--host",
        settings.inference_host,
        "--port",
        str(variant.port),
        "--ctx-size",
        str(variant.context_size),
        "--parallel",
        str(settings.inference_parallel),
        "--n-gpu-layers",
        settings.inference_gpu_layers,
        "--cache-type-k",
        variant.kv_cache_type,
        "--cache-type-v",
        variant.kv_cache_type,
        "--flash-attn",
        settings.inference_flash_attention,
        "--batch-size",
        str(variant.batch_size),
        "--ubatch-size",
        str(variant.ubatch_size),
        "--spec-type",
        variant.speculative_type,
    ]
    if variant.mtp_draft_n_max is not None:
        argv += ["--spec-draft-n-max", str(variant.mtp_draft_n_max)]
    argv += [
        "-t",
        str(settings.worker_runtime_threads),
        "--threads-batch",
        str(settings.worker_runtime_threads_batch),
        "--cache-ram",
        "0",
        "--ctx-checkpoints",
        "0",
        "--fit",
        "off",
        "--jinja",
        "--reasoning",
        "off",
        "--offline",
        "--no-webui",
        "--no-mmproj",
    ]
    return WorkerRuntimeSpec(
        mode="generation",
        argv=tuple(argv),
        revision=settings.inference_runtime_revision,
        artifact=artifact,
        artifact_sha256=settings.inference_primary_artifact_sha256,
        host=settings.inference_host,
        port=variant.port,
    )


class OwnedWorkerRuntime:
    """Own one loopback llama-server child through one boot/argv record.

    The one ``runtime.json`` is the process ownership record: it is read before any spawn, published
    before health polling, and removed only after the owned child's exit is proved. A foreign boot id
    or dead PID is retired without signalling anyone, a live foreign PID fails loudly and preserves
    evidence, and an occupied port is never adopted from a listener.
    """

    def __init__(
        self,
        runner: mechanics.ProcessRunner,
        *,
        root: Path,
        directory: Path,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._runner = runner
        self._root = root
        self._directory = directory
        self._sleep = sleep
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def pid(self) -> int | None:
        """Return the live current child's PID or the retained record's PID, else ``None``.

        A retained handle whose child has already exited (including an unreaped zombie) is not a
        live current child and reports ``None``. ``stop`` owns reaping that handle.
        """
        if self._process is not None:
            return None if self._process.poll() is not None else self._process.pid
        record = self._read_record()
        return None if record is None else record.pid

    def _record_path(self) -> Path:
        return self._directory / _RECORD_NAME

    def _read_record(self) -> mechanics.OwnedProcessRecord | None:
        path = self._record_path()
        if path.is_symlink():
            raise ValueError("runtime ownership record must not be a symlink")
        if not path.exists():
            return None
        return load_private_model(path, mechanics.OwnedProcessRecord)

    def _write_record(self, record: mechanics.OwnedProcessRecord) -> None:
        atomic_write_private_text(self._record_path(), administrative_json(record))

    def _remove_record(self) -> None:
        self._record_path().unlink(missing_ok=True)

    def _child_environment(self) -> dict[str, str]:
        """Return the closed model-child environment: HOME, PATH, optional lib path, and HSA flag."""
        home = os.environ.get("HOME")
        path = os.environ.get("PATH")
        if not home or not path:
            raise ValueError("worker runtime launch requires HOME and PATH in the environment")
        environment = {"HOME": home, "PATH": path, "HSA_ENABLE_DXG_DETECTION": "1"}
        library_path = os.environ.get("LD_LIBRARY_PATH")
        if library_path:
            environment["LD_LIBRARY_PATH"] = library_path
        return environment

    def start(
        self, spec: WorkerRuntimeSpec, *, attempts: int, interval: float, timeout: float
    ) -> int:
        """Start or reuse exactly one owned runtime for ``spec`` and return its PID.

        A live same-boot record with the identical argv is verified against ``/proc`` and reused
        without a further spawn, hash, or health loop. A live same-boot record with different argv, or
        a live PID whose command line differs from the record, fails without changing
        evidence. A dead or other-boot record is retired before a fresh prepared/occupied check.
        """
        record = self._read_record()
        if record is not None:
            boot_id = mechanics.current_boot_id()
            if record.boot_id == boot_id and mechanics.pid_is_alive(record.pid):
                command_line = mechanics.read_process_command_line(record.pid)
                if command_line != record.argv:
                    raise ValueError("recorded runtime process is not the owned runtime")
                if record.argv != spec.argv:
                    raise ValueError("a different owned runtime is already running")
                return record.pid
            self._remove_record()

        require_prepared_runtime(
            runner=self._runner,
            revision=spec.revision,
            artifact=spec.artifact,
            artifact_sha256=spec.artifact_sha256,
            timeout=timeout,
        )
        listeners = self._runner.run(
            ("ss", "-H", "-ltn", f"sport = :{spec.port}"), cwd=self._root
        ).stdout
        if listeners.strip():
            raise ValueError("configured runtime port is already occupied")

        boot_id = mechanics.current_boot_id()
        process = self._runner.popen(
            spec.argv,
            cwd=self._root,
            env=self._child_environment(),
            stdout_path=self._directory / _LOG_NAME,
            stderr_path=self._directory / _LOG_NAME,
            start_new_session=True,
            inherit_environment=False,
        )
        self._process = process
        published = False
        try:
            self._write_record(
                mechanics.OwnedProcessRecord(
                    schema_version=1, pid=process.pid, argv=spec.argv, boot_id=boot_id
                )
            )
            published = True
            self._await_health(spec, process, attempts=attempts, interval=interval)
        except Exception as exc:
            try:
                process.terminate()
                process.wait(timeout=timeout)
            except Exception as cleanup_exc:
                raise ExceptionGroup("runtime launch cleanup failure", [exc, cleanup_exc]) from exc
            if published:
                self._remove_record()
            self._process = None
            raise
        return process.pid

    def _await_health(
        self,
        spec: WorkerRuntimeSpec,
        process: subprocess.Popen[bytes],
        *,
        attempts: int,
        interval: float,
    ) -> None:
        """Poll the configured loopback health endpoint boundedly. A dead child fails at once."""
        url = f"http://{spec.host}:{spec.port}/health"
        for attempt in range(attempts):
            if process.poll() is not None:
                raise RuntimeError("owned runtime exited before becoming healthy")
            try:
                self._runner.run(
                    (
                        "curl",
                        "--disable",
                        "--fail",
                        "--silent",
                        "--max-time",
                        str(interval),
                        url,
                    ),
                    cwd=self._root,
                    timeout=interval,
                )
            except subprocess.CalledProcessError, subprocess.TimeoutExpired:
                if process.poll() is not None:
                    raise RuntimeError("owned runtime exited before becoming healthy")
                if attempt + 1 == attempts:
                    raise RuntimeError("runtime health polling ended without a result") from None
                self._sleep(interval)
            else:
                if process.poll() is not None:
                    raise RuntimeError("owned runtime exited before becoming healthy")
                return

    def stop(self, *, timeout: float, interval: float) -> None:
        """Stop the owned runtime, retiring only provable ownership and never a foreign PID.

        A dead or previous-boot record retires without signalling. A live same-boot record is
        validated against its exact ``/proc`` command line, then terminated through the retained
        child handle when available or by the shared liveness read otherwise. A live foreign PID or
        an unproved exit raises and preserves the record.
        """
        record = self._read_record()
        if record is None:
            if self._process is not None:
                self._stop_handle(self._process, timeout=timeout)
                self._process = None
            return
        boot_id = mechanics.current_boot_id()
        if record.boot_id != boot_id or not mechanics.pid_is_alive(record.pid):
            self._remove_record()
            self._process = None
            return
        if self._process is not None and self._process.pid == record.pid:
            self._stop_handle(self._process, timeout=timeout)
        else:
            command_line = mechanics.read_process_command_line(record.pid)
            if command_line != record.argv:
                raise ValueError("recorded runtime process is not the owned runtime")
            os.kill(record.pid, signal.SIGTERM)
            self._await_exit(record.pid, timeout=timeout, interval=interval)
        self._remove_record()
        self._process = None

    def _stop_handle(self, process: subprocess.Popen[bytes], *, timeout: float) -> None:
        process.terminate()
        process.wait(timeout=timeout)

    def _await_exit(self, pid: int, *, timeout: float, interval: float) -> None:
        """Wait under one monotonic deadline for a retained orphan to exit, else fail loudly."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not mechanics.pid_is_alive(pid):
                return
            self._sleep(interval)
        if not mechanics.pid_is_alive(pid):
            return
        raise RuntimeError("owned runtime process did not exit within the stop timeout")


class WorkerInferenceRuntime:
    """The concrete owned-runtime adapter over the product inference protocol.

    It caches the activated :class:`WorkerRuntimeSpec`.
    Repeated activate/start_rerank of the live same spec is idempotent. An unexpectedly dead current
    runtime fails rather than recovering a crashed model mid-job. A switch stops the current runtime
    before starting the next, and ``stop_rerank`` acts only in the cross-encoder mode.
    """

    def __init__(
        self,
        runner: mechanics.ProcessRunner,
        *,
        root: Path,
        directory: Path,
        settings: InferenceSettings,
        rerank_settings: InferenceRerankSettings,
        health_attempts: int,
        interval: float,
        stop_timeout_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
        gpu_clock: WorkerGpuClock | None = None,
    ) -> None:
        self._root = root
        self._settings = settings
        self._rerank_settings = rerank_settings
        self._health_attempts = health_attempts
        self._interval = interval
        self._stop_timeout_seconds = stop_timeout_seconds
        self._owner = OwnedWorkerRuntime(runner, root=root, directory=directory, sleep=sleep)
        self._active: WorkerRuntimeSpec | None = None
        self._active_variant: InferenceLocalVariantSettings | None = None
        self._gpu_clock = gpu_clock

    def _ensure(self, spec: WorkerRuntimeSpec) -> None:
        """Reuse the live same spec, or stop the current runtime and start ``spec``.

        A live same-spec reuse never resets the loaded-GPU segment. A real switch closes the loaded
        segment only after its stop is proved and opens the next one only after the fresh start is
        proved, so unloaded dwell between modes is excluded from the shared clock.
        """
        if self._active is not None and self._active.argv == spec.argv:
            pid = self._owner.pid
            if pid is None or not mechanics.pid_is_alive(pid):
                raise RuntimeError("the activated inference runtime is no longer running")
            return
        if self._active is not None:
            self._owner.stop(timeout=self._stop_timeout_seconds, interval=self._interval)
            if self._gpu_clock is not None:
                self._gpu_clock.unloaded()
        self._owner.start(
            spec,
            attempts=self._health_attempts,
            interval=self._interval,
            timeout=self._stop_timeout_seconds,
        )
        if self._gpu_clock is not None:
            self._gpu_clock.loaded()
        self._active = spec

    def activate(self, variant: InferenceLocalVariantSettings) -> None:
        """Load the configured local generation key, reusing the live same key."""
        if variant not in self._settings.inference_local_variants:
            raise ValueError("inference variant is not configured")
        self._ensure(generation_runtime_spec(self._settings, variant, self._root))
        self._active_variant = variant

    def active_variant(self) -> InferenceLocalVariantSettings | None:
        """Return the loaded local generation key, or ``None`` when none or the reranker is loaded."""
        return self._active_variant

    def stop(self) -> None:
        """Unload either activated mode."""
        self._owner.stop(timeout=self._stop_timeout_seconds, interval=self._interval)
        self._active = None
        self._active_variant = None
        if self._gpu_clock is not None:
            self._gpu_clock.unloaded()

    def start_rerank(self) -> None:
        """Load the cross-encoder key, reusing the live same key."""
        self._ensure(rerank_runtime_spec(self._rerank_settings, self._root))
        self._active_variant = None

    def stop_rerank(self) -> None:
        """Unload the cross-encoder only when it is the current mode."""
        if self._active is not None and self._active.mode == "rerank":
            self._owner.stop(timeout=self._stop_timeout_seconds, interval=self._interval)
            self._active = None
            self._active_variant = None
            if self._gpu_clock is not None:
                self._gpu_clock.unloaded()

    def request_scope(self, seconds: float) -> AbstractContextManager[None]:
        """Bound one model request by the shared elapsed-time alarm owner."""
        return mechanics.model_request_scope(seconds)
