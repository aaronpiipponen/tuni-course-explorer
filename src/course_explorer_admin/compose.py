"""One generated Compose environment bridge for the Docker Compose stack.

Docker Compose needs environment syntax for the set of interpolation keys in
``docker-compose.yml``. This module is the sole owner of that bridge: it projects the validated raw
database and embedding settings onto exactly those interpolation aliases, writes them into an
invocation-owned mode-0700 temporary directory as a mode-0600 file, runs the ``sudo docker compose``
command with that file, and removes the directory when the subprocess completes. The bridge carries
only those interpolation aliases. A caller-supplied Docker Compose project name is forwarded as an
explicit ``--project-name``.

It is invoked through ``mechanics.compose_prefix()`` on both the server and the worker, so each
host generates its own bridge locally.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from course_explorer.administration import repository_root
from course_explorer.config import (
    load_embedding_runtime_settings,
    load_raw_database_settings,
)

# Docker Compose's own process-level project selector. When the caller supplies it, the bridge
# forwards it as the explicit ``--project-name`` so one ephemeral namespace reaches initial setup,
# detached generation and cleanup without relying on ``sudo`` preserving the variable.
COMPOSE_PROJECT_NAME_ALIAS = "COMPOSE_PROJECT_NAME"


def compose_environment() -> dict[str, str]:
    """Project the raw database and embedding runtime settings onto the Compose interpolation aliases."""
    database = load_raw_database_settings()
    embedding = load_embedding_runtime_settings()
    return {
        "POSTGRES_DB": database.postgres_db,
        "POSTGRES_USER": database.postgres_user,
        "POSTGRES_PASSWORD": database.postgres_password.get_secret_value(),
        "POSTGRES_PORT": str(database.postgres_port),
        "EMBEDDING_SERVER_IMAGE": embedding.embedding_server_image,
        "EMBEDDING_RUNTIME_REVISION": embedding.embedding_runtime_revision,
        "EMBEDDING_ARTIFACT_SHA256": embedding.embedding_artifact_sha256,
        "EMBEDDING_MODEL": embedding.embedding_model,
        "EMBEDDING_HOST": embedding.embedding_host,
        "EMBEDDING_PORT": str(embedding.embedding_port),
        "EMBEDDING_THREADS": str(embedding.embedding_threads),
        "EMBEDDING_CONTEXT_SIZE": str(embedding.embedding_context_size),
        "EMBEDDING_POOLING": embedding.embedding_pooling,
        "EMBEDDING_NORMALIZATION": str(embedding.embedding_normalization),
        "EMBEDDING_ARTIFACT_PATH": str(embedding.embedding_artifact_path),
    }


def _quote_bridge_value(key: str, value: str) -> str:
    """Render one value in Compose dotenv literal single-quote syntax.

    A value carrying a line break cannot be represented in the file syntax, so it fails with a
    key-only error that renders no value text.
    """
    if "\n" in value or "\r" in value:
        raise ValueError(f"{key} must not contain a line break")
    return "'" + value.replace("'", "\\'") + "'"


def _render_bridge(values: Mapping[str, str]) -> str:
    return "".join(f"{key}={_quote_bridge_value(key, value)}\n" for key, value in values.items())


def _write_bridge(directory: Path, values: Mapping[str, str]) -> Path:
    bridge = directory / "compose.env"
    descriptor = os.open(bridge, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(_render_bridge(values))
    return bridge


def _split_arguments(argv: Sequence[str]) -> tuple[bool, list[str]]:
    """Split the optional non-interactive flag from the forwarded Compose arguments after ``--``."""
    arguments = list(argv)
    non_interactive = False
    if arguments and arguments[0] == "--non-interactive":
        non_interactive = True
        arguments.pop(0)
    if not arguments or arguments[0] != "--":
        raise ValueError("compose bridge requires -- before the forwarded Compose arguments")
    return non_interactive, arguments[1:]


def main(argv: Sequence[str] | None = None) -> int:
    """Run one Compose command with a locally generated temporary environment-file bridge.

    Docker Compose's process-level ``COMPOSE_PROJECT_NAME`` override, when the caller supplies one,
    is forwarded as an explicit ``--project-name`` before the caller's own arguments.
    """
    arguments = sys.argv[1:] if argv is None else argv
    non_interactive, compose_arguments = _split_arguments(arguments)
    root = repository_root()
    project_name = os.environ.get(COMPOSE_PROJECT_NAME_ALIAS)
    directory = Path(tempfile.mkdtemp(prefix="course-explorer-compose-"))
    os.chmod(directory, 0o700)
    try:
        bridge = _write_bridge(directory, compose_environment())
        sudo = ("sudo", "-n") if non_interactive else ("sudo",)
        command = (
            *sudo,
            "docker",
            "compose",
            "--project-directory",
            str(root),
            "--file",
            str(root / "docker-compose.yml"),
            *(() if not project_name else ("--project-name", project_name)),
            "--env-file",
            str(bridge),
            *compose_arguments,
        )
        completed = subprocess.run(command, check=False)
        return completed.returncode
    finally:
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
