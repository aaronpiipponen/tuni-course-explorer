"""Worker-side explicit setup inspection and preparation helper.

This module runs on the already-provisioned worker host (invoked as
``python -m course_explorer_admin.provisioning_worker check|prepare``) and owns the one
readiness read plus the one mutation of missing pinned worker resources: the configured Ubuntu
packages, the Docker Compose ``db`` image, the pinned GGUFs, and the pinned llama.cpp runtimes.
``check`` performs only the readiness read. The ``prepare`` action owns the installs, downloads,
builds, and service start. ``_inspect_worker_resources``
loads the translation, inference and rerank settings to inspect the pinned resources. Both actions run
Compose through the shared
``course_explorer_admin.compose`` bridge, which consumes the validated database credentials into a
mode-0600 temporary file removed on exit. Its report carries fixed component names alone.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from course_explorer.administration import sha256_file
from course_explorer.config import (
    load_inference_rerank_settings,
    load_inference_settings,
    load_translation_settings,
    load_worker_setup_settings,
)
from course_explorer_admin import mechanics

# One fixed ordered package-name list for the already-provisioned worker. The versioned ROCm apt
# source owns its pin, so this list holds package names only.
SYSTEM_PACKAGES = (
    "build-essential",
    "ca-certificates",
    "cmake",
    "curl",
    "git",
    "iproute2",
    "libcurl4-openssl-dev",
    "pkg-config",
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin",
    "rocm",
    "rocdxg-roct",
)

_RUNTIME_CLONE_URL = "https://github.com/ggml-org/llama.cpp.git"
_TRANSLATION_GUIDANCE = (
    "missing translation artifact: reproduce it with the remote-worker runbook "
    "(docs/getting-started/remote-worker.md section 8); no automated converter is provided"
)


class WorkerResourcesReport(BaseModel):
    """Ordinary frozen readiness report naming only fixed component tokens."""

    model_config = ConfigDict(frozen=True)

    ready: bool
    missing: list[str]


def check_worker_resources(*, runner: mechanics.ProcessRunner) -> WorkerResourcesReport:
    """Read worker readiness only, mutating nothing and reporting fixed component names."""
    return _inspect_worker_resources(runner, prepare=False)


def prepare_worker_resources(*, runner: mechanics.ProcessRunner) -> WorkerResourcesReport:
    """Verify or acquire the configured packages, db image, artifacts, and runtimes."""
    return _inspect_worker_resources(runner, prepare=True)


def _inspect_worker_resources(
    runner: mechanics.ProcessRunner, *, prepare: bool
) -> WorkerResourcesReport:
    worker_root = Path.cwd()
    translation = load_translation_settings()
    inference = load_inference_settings()
    rerank = load_inference_rerank_settings()
    timeout = load_worker_setup_settings().worker_setup_timeout_seconds

    missing: list[str] = list(_missing_packages(runner, worker_root))

    if prepare:
        _start_docker_service(runner, worker_root)
    if not _docker_ready(runner, worker_root):
        missing.append("docker")
    elif not _docker_compose_ready(runner, worker_root):
        missing.append("docker-compose")
    else:
        image = _db_image_name(runner, worker_root)
        if not _db_image_present(runner, worker_root, image):
            if prepare:
                runner.run_interactive(
                    ("sudo", "docker", "pull", image), cwd=worker_root, timeout=timeout
                )
            if not _db_image_present(runner, worker_root, image):
                missing.append("db-image")

    artifacts = (
        (
            worker_root / translation.translation_artifact_path,
            translation.translation_artifact_sha256,
            "translation-artifact",
            None,
        ),
        (
            worker_root / inference.inference_primary_artifact_path,
            inference.inference_primary_artifact_sha256,
            "generation-artifact",
            str(inference.primary_artifact_url),
        ),
        (
            worker_root / rerank.inference_rerank_artifact_path,
            rerank.inference_rerank_artifact_sha256,
            "rerank-artifact",
            str(rerank.rerank_artifact_url),
        ),
    )
    for path, digest, token, url in artifacts:
        if _artifact_present(path, digest):
            continue
        if prepare and url is not None:
            _download_artifact(runner, worker_root, path, digest, url, timeout)
            if _artifact_present(path, digest):
                continue
        missing.append(token)

    runtimes: dict[str, list[str]] = {}
    runtimes.setdefault(translation.translation_runtime_revision, []).append("translation-runtime")
    runtimes.setdefault(inference.inference_runtime_revision, []).append("inference-runtime")
    for revision, tokens in runtimes.items():
        missing.extend(_runtime_missing(runner, revision, tokens, prepare=prepare, timeout=timeout))

    return WorkerResourcesReport(ready=not missing, missing=missing)


def _missing_packages(runner: mechanics.ProcessRunner, worker_root: Path) -> list[str]:
    missing: list[str] = []
    for package in SYSTEM_PACKAGES:
        try:
            status = (
                runner.run(("dpkg-query", "-W", "-f=${Status}", package), cwd=worker_root)
                .stdout.decode("utf-8", errors="replace")
                .strip()
            )
        except subprocess.CalledProcessError:
            missing.append(package)
        else:
            if status != "install ok installed":
                missing.append(package)
    return missing


def _start_docker_service(runner: mechanics.ProcessRunner, worker_root: Path) -> None:
    if _docker_ready(runner, worker_root):
        return
    runner.run(("sudo", "systemctl", "start", "docker"), cwd=worker_root)


def _docker_ready(runner: mechanics.ProcessRunner, worker_root: Path) -> bool:
    try:
        runner.run(("sudo", "-n", "docker", "info"), cwd=worker_root)
    except subprocess.CalledProcessError:
        return False
    return True


def _sudo_compose_prefix() -> tuple[str, ...]:
    prefix = mechanics.compose_prefix()
    return (*prefix[:-1], "--non-interactive", prefix[-1])


def _docker_compose_ready(runner: mechanics.ProcessRunner, worker_root: Path) -> bool:
    try:
        runner.run((*_sudo_compose_prefix(), "version"), cwd=worker_root)
    except subprocess.CalledProcessError:
        return False
    return True


def _db_image_name(runner: mechanics.ProcessRunner, worker_root: Path) -> str:
    output = runner.run(
        (*_sudo_compose_prefix(), "config", "--images", "db"), cwd=worker_root
    ).stdout.decode("utf-8")
    image = output.strip()
    if not image:
        raise ValueError("configured db service image is blank")
    return image


def _db_image_present(runner: mechanics.ProcessRunner, worker_root: Path, image: str) -> bool:
    try:
        runner.run(("sudo", "-n", "docker", "image", "inspect", image), cwd=worker_root)
    except subprocess.CalledProcessError:
        return False
    return True


def _artifact_present(path: Path, digest: str) -> bool:
    if path.is_symlink():
        raise ValueError("configured artifact must not be a symlink")
    if not path.exists():
        return False
    if not path.is_file():
        raise ValueError("configured artifact must be a regular file")
    if sha256_file(path) != digest:
        raise ValueError("installed artifact checksum does not match configuration")
    return True


def _download_artifact(
    runner: mechanics.ProcessRunner,
    worker_root: Path,
    path: Path,
    digest: str,
    url: str,
    timeout: float,
) -> None:
    """Download one missing public artifact to a fresh invocation-owned temporary and verify it."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}-", suffix=".download"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        runner.run_interactive(
            (
                "curl",
                "--disable",
                "--fail",
                "--location",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--output",
                str(temporary),
                url,
            ),
            cwd=worker_root,
            timeout=timeout,
        )
        if sha256_file(temporary) != digest:
            raise ValueError("downloaded artifact checksum does not match configuration")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _runtime_executable_ready(executable: Path) -> bool:
    """Report whether one prepared runtime executable exists and can actually be executed."""
    return executable.is_file() and os.access(executable, os.X_OK)


def _runtime_missing(
    runner: mechanics.ProcessRunner,
    revision: str,
    tokens: list[str],
    *,
    prepare: bool,
    timeout: float,
) -> list[str]:
    worker_root = Path.cwd()
    directory = mechanics.runtime_checkout_directory(revision)
    executable = directory / "build" / "bin" / "llama-server"
    if directory.exists():
        require_runtime_checkout(runner, directory, revision, timeout)
        if _runtime_executable_ready(executable):
            return []
        if not prepare:
            return list(tokens)
        _build_runtime(runner, directory, timeout)
        return [] if _runtime_executable_ready(executable) else list(tokens)
    if not prepare:
        return list(tokens)
    runner.run_interactive(
        ("git", "clone", _RUNTIME_CLONE_URL, str(directory)),
        cwd=worker_root,
        timeout=timeout,
    )
    runner.run_interactive(
        ("git", "-C", str(directory), "checkout", "--detach", revision),
        cwd=worker_root,
        timeout=timeout,
    )
    _build_runtime(runner, directory, timeout)
    return [] if _runtime_executable_ready(executable) else list(tokens)


def require_runtime_checkout(
    runner: mechanics.ProcessRunner, directory: Path, revision: str, timeout: float
) -> None:
    """Require a runtime checkout at the exact clean configured revision."""
    head = (
        runner.run(
            ("git", "-C", str(directory), "rev-parse", "HEAD"), cwd=directory, timeout=timeout
        )
        .stdout.decode("utf-8")
        .strip()
    )
    if head != revision:
        raise ValueError("runtime checkout revision does not match configuration")
    dirty = runner.run(
        ("git", "-C", str(directory), "status", "--porcelain"), cwd=directory, timeout=timeout
    ).stdout.decode("utf-8")
    if dirty.strip():
        raise ValueError("runtime checkout must be clean")


def require_prepared_runtime(
    *,
    runner: mechanics.ProcessRunner,
    revision: str,
    artifact: Path,
    artifact_sha256: str,
    timeout: float,
) -> None:
    """Require an already-prepared pinned runtime and artifact.

    This is the recurring fresh-launch readiness read: it reuses the one checkout convention and the
    executable and pinned artifact-SHA-256 checks, so every fresh launch verifies the
    authoritative checkout revision, executable, and artifact hash. A live same-spec reuse in
    ``OwnedWorkerRuntime.start`` reuses the running process. The explicit setup/update path owns
    every download, clone, build, and install. A missing component raises fixed setup/update guidance.
    A present but mismatching component fails through the checkout/checksum errors.
    """
    directory = mechanics.runtime_checkout_directory(revision)
    if not directory.exists():
        raise ValueError("worker runtime is not prepared; run explicit setup/update")
    require_runtime_checkout(runner, directory, revision, timeout)
    if not _runtime_executable_ready(directory / "build" / "bin" / "llama-server"):
        raise ValueError("worker runtime executable is not ready; run explicit setup/update")
    if not _artifact_present(artifact, artifact_sha256):
        raise ValueError("worker model artifact is not prepared; run explicit setup/update")


def _build_runtime(runner: mechanics.ProcessRunner, directory: Path, timeout: float) -> None:
    script = (
        "set -euo pipefail; "
        f"cd {shlex.quote(str(directory))}; "
        'HIPCXX="$(hipconfig -l)/clang" HIP_PATH="$(hipconfig -R)" '
        "cmake -B build -S . -DCMAKE_BUILD_TYPE=Release -DGGML_HIP=ON -DGPU_TARGETS=gfx1201; "
        'cmake --build build --config Release --target llama-server -j "$(nproc)"'
    )
    runner.run_interactive(("bash", "-c", script), cwd=directory, timeout=timeout)


def _print_translation_guidance(report: WorkerResourcesReport) -> None:
    if "translation-artifact" in report.missing:
        print(_TRANSLATION_GUIDANCE, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Expose the ``check`` and ``prepare`` actions."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for name in ("check", "prepare"):
        subparsers.add_parser(name)
    args = parser.parse_args(argv)
    runner = mechanics.SubprocessRunner()
    if args.action == "prepare":
        report = prepare_worker_resources(runner=runner)
    else:
        report = check_worker_resources(runner=runner)
    _print_translation_guidance(report)
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
