"""One owner of the pinned model artifact check and download mechanics.

The worker setup and the self-host workflows both acquire the same pinned model file: a temporary
download beside its configured path, a SHA-256 check of the received bytes, and an atomic move into
place. This module owns that one path so neither caller repeats it. It holds no policy value: the
caller supplies the configured path, digest, address and timeout.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from course_explorer.administration import sha256_file
from course_explorer_admin import mechanics


def artifact_present(path: Path, digest: str) -> bool:
    """Report whether one configured artifact is installed at its exact pinned bytes."""
    if path.is_symlink():
        raise ValueError("configured artifact must not be a symlink")
    if not path.exists():
        return False
    if not path.is_file():
        raise ValueError("configured artifact must be a regular file")
    if sha256_file(path) != digest:
        raise ValueError("installed artifact checksum does not match configuration")
    return True


def download_artifact(
    runner: mechanics.ProcessRunner,
    root: Path,
    path: Path,
    digest: str,
    url: str,
    timeout: float | None,
) -> None:
    """Download one missing public artifact to a fresh temporary, verify it, and publish it.

    The transfer uses the one HTTPS-only curl invocation with its visible progress. Received bytes
    are checked against the configured digest before the temporary is moved into place. The
    temporary is removed on every failure, interruption included, and a published destination is
    never deleted.
    """
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
            cwd=root,
            timeout=timeout,
        )
        if sha256_file(temporary) != digest:
            raise ValueError("downloaded artifact checksum does not match configuration")
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
