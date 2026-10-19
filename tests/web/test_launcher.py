"""Security tests for the web process environment handoff."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from course_explorer import configuration
from course_explorer.config import (
    ENVIRONMENT_ONLY_SETTINGS_SOURCE,
    SETTINGS_SOURCE_MARKER,
    DatabaseSettings,
    EmbeddingSettings,
    SearchSettings,
    WebSettings,
)
from course_explorer_web import __main__ as entry_point
from course_explorer_web import launch
from tests.support import write_example_config_tree

_EMBEDDING_ALIASES = frozenset(
    field.validation_alias
    for field in EmbeddingSettings.model_fields.values()
    if isinstance(field.validation_alias, str)
)


@pytest.mark.parametrize("embeddings_enabled", (False, True), ids=("off", "on"))
def test_web_launcher_excludes_operator_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, embeddings_enabled: bool
) -> None:
    """Hand only the required web aliases and the marker to a file-free child process."""
    root = tmp_path / "checkout"
    write_example_config_tree(root, include_derived=embeddings_enabled)
    local = root / ".env"
    local.write_text("POSTGRES_PASSWORD=synthetic-database-password\n", encoding="utf-8")
    local.chmod(0o600)
    monkeypatch.setattr(configuration, "repository_root", lambda: root)
    configuration.clear_configuration_caches()

    class ExecCaptured(Exception):
        pass

    observed: dict[str, str] = {}

    def capture_exec(_executable: str, _arguments: list[str], environment: dict[str, str]) -> None:
        observed.update(environment)
        raise ExecCaptured

    monkeypatch.setattr(os, "execve", capture_exec)
    monkeypatch.setattr(
        os,
        "environ",
        {
            "HOME": "/home/test",
            "PATH": "/usr/bin",
            "LANG": "C.UTF-8",
            "WEB_EMBEDDINGS_ENABLED": "1" if embeddings_enabled else "0",
            "WEB_INFERENCE_ENABLED": "1",
            "TRANSLATION_CONTROLLER_SSH_TARGET": "synthetic-worker",
            "SSH_AUTH_SOCK": "/tmp/synthetic-agent.sock",
            "UNRELATED_SECRET": "synthetic-unrelated-secret",
        },
    )

    with pytest.raises(ExecCaptured):
        launch.main()

    assert observed["POSTGRES_PASSWORD"] == "synthetic-database-password"
    assert observed["WEB_HOST"] == "127.0.0.1"
    assert observed["WEB_PORT"] == "8037"
    assert observed["WEB_WORKERS"] == "2"
    assert observed["WEB_EMBEDDINGS_ENABLED"] == ("1" if embeddings_enabled else "0")
    assert observed["WEB_INFERENCE_ENABLED"] == "1"
    assert {"HOME", "PATH", "LANG"} <= observed.keys()
    assert observed[SETTINGS_SOURCE_MARKER] == ENVIRONMENT_ONLY_SETTINGS_SOURCE
    assert (
        not {
            "TRANSLATION_CONTROLLER_SSH_TARGET",
            "SSH_AUTH_SOCK",
            "UNRELATED_SECRET",
        }
        & observed.keys()
    )
    # A site without embedding features hands over no embedding alias at all, so its child can
    # compose no embedding family and needs no hub artifact.
    if embeddings_enabled:
        assert "EMBEDDING_HUB_VECTOR" in observed
    else:
        assert not _EMBEDDING_ALIASES & observed.keys()

    # The captured child environment reconstructs its families without reopening any local file
    # and can never reach a worker or unrelated secret.
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the child environment must not read configuration files")

    monkeypatch.setattr(configuration, "read_public_configuration", forbidden)
    monkeypatch.setattr(configuration, "read_local_configuration", forbidden)
    monkeypatch.setattr(os, "environ", observed)
    assert DatabaseSettings().postgres_password.get_secret_value() == (
        "synthetic-database-password"
    )
    assert WebSettings().web_port == 8037
    assert WebSettings().web_workers == 2
    assert WebSettings().embeddings_enabled is embeddings_enabled
    assert WebSettings().inference_enabled is True
    # The handoff carries the search policy for one query embedding request as well.
    assert SearchSettings().search_embedding_request_timeout_seconds == 5
    assert SearchSettings().search_embedding_max_attempts == 1
    if embeddings_enabled:
        assert len(EmbeddingSettings().embedding_hub_vector) == 1024

    # Continue the same handoff through the actual entry point, binding only a temporary test port.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("WEB_PORT", str(port))
    started: dict[str, object] = {}

    def capture_uvicorn(application: str, **options: object) -> None:
        started.update(options)
        assert application == "course_explorer_web.app:app"
        with socket.fromfd(options["fd"], socket.AF_INET, socket.SOCK_STREAM) as listener:
            assert listener.getsockname() == ("127.0.0.1", port)
            assert listener.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) == 1

    monkeypatch.setattr(entry_point.uvicorn, "run", capture_uvicorn)
    entry_point.main()
    assert started["workers"] == 2
    assert started["host"] == "127.0.0.1"
    assert started["port"] == port
