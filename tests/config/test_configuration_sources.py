"""Contracts that tracked TOML and the device-local .env compose automatically."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from course_explorer import configuration
from course_explorer.config import (
    SETTINGS_SOURCE_MARKER,
    AdminWebSettings,
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    EmbeddingSettings,
    LocalLifecycleSettings,
    SearchSettings,
    UsageSettings,
    WebSettings,
    load_administrative_site_settings,
    load_worker_gpu_reboot_settings,
)
from course_explorer_admin import compose, mechanics
from tests.config._support import FIXTURE_VALUES, MACHINE_TEMPLATE_VALUES
from tests.support import write_example_config_tree


def _bind_checkout(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Point the file-source owner at one temporary checkout and drop cached reads."""
    monkeypatch.delenv(SETTINGS_SOURCE_MARKER, raising=False)
    for alias in FIXTURE_VALUES:
        monkeypatch.delenv(alias, raising=False)
    monkeypatch.setattr(configuration, "repository_root", lambda: root)
    configuration.clear_configuration_caches()


def test_automatic_configuration_and_override_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TOML loads natively, the local .env supplies secrets, and an explicit export wins."""
    root = tmp_path / "checkout"
    write_example_config_tree(root)
    (root / ".env").write_text(
        "POSTGRES_PASSWORD=synthetic-secret\n"
        "UNRELATED_SECRET=synthetic-unrelated-secret\n"
        "WEB_PORT=18026\n"
        + "".join(f"{key}={value}\n" for key, value in MACHINE_TEMPLATE_VALUES.items()),
        encoding="utf-8",
    )
    (root / ".env").chmod(0o600)
    _bind_checkout(monkeypatch, root)

    # Example TOML values load with no sourcing, and the local .env supplies the secret and
    # overrides the example web port.
    database = DatabaseSettings()
    assert database.postgres_db == "course_explorer"
    assert database.postgres_password.get_secret_value() == "synthetic-secret"
    assert database.selected_dataset_enabled is False
    assert WebSettings().web_port == 18026
    assert WebSettings().embeddings_enabled is True
    assert WebSettings().inference_enabled is True
    assert UsageSettings().usage_retention_days == 30
    # The administration family composes from its own registered subsystem file.
    assert AdminWebSettings().admin_web_port == 8039
    assert AdminWebSettings().admin_web_origin == "https://localhost:8039"
    assert AdminWebSettings().admin_web_session_idle_minutes == 30
    assert AdminWebSettings().admin_web_session_max_hours == 12
    assert AdminWebSettings().admin_web_anonymous_session_limit == 10
    assert AdminWebSettings().admin_web_anonymous_session_window_seconds == 60
    assert AdminWebSettings().admin_web_command_log_limit == 200
    assert AdminWebSettings().admin_web_poll_seconds == 60
    assert AdminWebSettings().admin_web_app_url == "http://localhost:8037/"
    assert (
        AdminWebSettings().admin_web_repository_url
        == "https://github.com/aaronpiipponen/tuni-course-explorer"
    )

    # Both 1024-component hubs resolve from the committed example derived artifacts before model
    # validation.
    embedding = EmbeddingSettings()
    assert embedding.embedding_port == 8081
    assert len(embedding.embedding_hub_vector) == 1024
    assert len(embedding.embedding_outcomes_hub_vector) == 1024
    assert embedding.embedding_hub_vector[:1] == (-0.04258320177679946,)
    assert embedding.embedding_outcomes_hub_vector[:1] == (-0.03813977011063868,)

    assert SearchSettings().comparison_overlap_floor == 0.20
    assert SearchSettings().search_embedding_request_timeout_seconds == 5
    assert SearchSettings().search_embedding_max_attempts == 1
    assert load_worker_gpu_reboot_settings().worker_gpu_reboot_interval_minutes == 120
    assert LocalLifecycleSettings().poll_interval_seconds == 0.5
    # Both site unit identities and the web unit's manager scope are machine identity, so they
    # compose from the environment file beside the worker connection values.
    assert load_administrative_site_settings().web_service_unit == "replace-with-web.service"
    assert load_administrative_site_settings().admin_service_unit == "replace-with-admin.service"
    assert load_administrative_site_settings().web_service_scope == "user"

    # An explicit process override wins over both files.
    monkeypatch.setenv("EMBEDDING_PORT", "18080")
    monkeypatch.setenv("COMPARISON_OVERLAP_CEILING", "0.5")
    monkeypatch.setenv("SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("SEARCH_EMBEDDING_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("WEB_PORT", "18028")
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "0")
    monkeypatch.setenv("WEB_INFERENCE_ENABLED", "0")
    monkeypatch.setenv("USAGE_RETENTION_DAYS", "7")
    monkeypatch.setenv("ADMIN_SITE_WEB_SERVICE_UNIT", "synthetic-site-web.service")
    monkeypatch.setenv("ADMIN_SITE_ADMIN_SERVICE_UNIT", "synthetic-site-admin.service")
    monkeypatch.setenv("ADMIN_SITE_WEB_SERVICE_SCOPE", "system")
    monkeypatch.setenv("ADMIN_WEB_PORT", "18027")
    monkeypatch.setenv("ADMIN_WEB_SESSION_IDLE_MINUTES", "5")
    monkeypatch.setenv("ADMIN_WEB_POLL_SECONDS", "3")
    assert EmbeddingSettings().embedding_port == 18080
    assert SearchSettings().comparison_overlap_ceiling == 0.5
    assert SearchSettings().search_embedding_request_timeout_seconds == 7
    assert SearchSettings().search_embedding_max_attempts == 2
    assert WebSettings().web_port == 18028
    assert WebSettings().embeddings_enabled is False
    assert WebSettings().inference_enabled is False
    assert UsageSettings().usage_retention_days == 7
    assert AdminWebSettings().admin_web_port == 18027
    assert AdminWebSettings().admin_web_session_idle_minutes == 5
    assert AdminWebSettings().admin_web_poll_seconds == 3
    assert load_administrative_site_settings().web_service_unit == "synthetic-site-web.service"
    assert load_administrative_site_settings().admin_service_unit == "synthetic-site-admin.service"
    assert load_administrative_site_settings().web_service_scope == "system"

    # A candidate configuration supplies its own WebSettings port in front of both files and in
    # front of the process override the handoff marker would otherwise admit.
    web_toml = (root / "config" / "web.toml").read_text(encoding="utf-8")
    candidate = web_toml.replace("WEB_PORT = 8037", "WEB_PORT = 18099")
    documents = configuration.read_configuration_documents(
        root, replacements={"config/web.toml": candidate}
    )
    with configuration.configuration_candidate(root, documents=documents, local={}):
        assert WebSettings().web_port == 18099
    # Leaving the candidate restores the ordinary source precedence.
    assert WebSettings().web_port == 18028

    # A candidate value the owning validator rejects fails despite the valid process override.
    invalid = web_toml.replace("WEB_PORT = 8037", "WEB_PORT = 70000")
    with pytest.raises(ValidationError):
        with configuration.configuration_candidate(
            root,
            documents=configuration.read_configuration_documents(
                root, replacements={"config/web.toml": invalid}
            ),
            local={},
        ):
            WebSettings()


def test_runtime_configuration_does_not_require_similarity_hubs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A complete example seed without hub artifacts loads runtime/Compose inputs and refuses sim reads."""
    root = tmp_path / "checkout"
    write_example_config_tree(root, include_derived=False)
    assert not (root / "config" / "derived").exists()
    _bind_checkout(monkeypatch, root)
    monkeypatch.setenv("POSTGRES_PASSWORD", "synthetic-password")

    runtime = EmbeddingRuntimeSettings()
    assert runtime.embedding_port == 8081
    assert runtime.embedding_model == "BAAI/bge-m3"
    environment = compose.compose_environment()
    assert environment["EMBEDDING_PORT"] == "8081"
    assert environment["POSTGRES_DB"] == "course_explorer"

    with pytest.raises(ValueError):
        EmbeddingSettings()
    # The hub writer resolves its target paths without the artifacts.
    assert configuration.hub_reference_path(root, "EMBEDDING_HUB_VECTOR") == Path(
        "config/derived/embedding-hub.json"
    )
    assert configuration.hub_reference_path(root, "EMBEDDING_OUTCOMES_HUB_VECTOR") == Path(
        "config/derived/embedding-outcomes-hub.json"
    )
    with pytest.raises(ValueError, match="not an embedding hub alias"):
        configuration.hub_reference_path(root, "EMBEDDING_PORT")


def test_public_configuration_rejects_duplicate_alias(tmp_path: Path) -> None:
    """A duplicate top-level alias across two public files fails before any settings succeed."""
    root = tmp_path / "checkout"
    write_example_config_tree(root)
    for relative, value in (("database.toml", "first"), ("curriculum.toml", "second")):
        path = root / "config" / relative
        path.write_text(
            f'DUPLICATE_ALIAS = "{value}"\n' + path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    configuration.clear_configuration_caches()

    with pytest.raises(ValueError, match="DUPLICATE_ALIAS"):
        configuration.read_public_configuration(root)


def test_compose_bridge_carries_interpolation_aliases_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The generated Compose bridge carries interpolation aliases and cleans itself up."""
    database = SimpleNamespace(
        postgres_db="synthetic-db",
        postgres_user="synthetic-user",
        postgres_password=SecretStr("syn'thetic-password"),
        postgres_port=5555,
    )
    embedding = SimpleNamespace(
        embedding_server_image="synthetic-image@sha256:" + "a" * 64,
        embedding_runtime_revision="b" * 40,
        embedding_artifact_sha256="c" * 64,
        embedding_model="synthetic/model",
        embedding_host="127.0.0.1",
        embedding_port=8080,
        embedding_threads=2,
        embedding_context_size=2048,
        embedding_pooling="cls",
        embedding_normalization=2,
        embedding_artifact_path="models/synthetic.gguf",
    )
    monkeypatch.setattr(compose, "load_raw_database_settings", lambda: database)
    monkeypatch.setattr(compose, "load_embedding_runtime_settings", lambda: embedding)
    monkeypatch.setattr(compose, "repository_root", lambda: tmp_path)
    monkeypatch.delenv(compose.COMPOSE_PROJECT_NAME_ALIAS, raising=False)

    captures: list[dict[str, object]] = []

    def fake_run(command, check):
        bridge = Path(command[command.index("--env-file") + 1])
        captures.append(
            {
                "command": tuple(command),
                "content": bridge.read_text(encoding="utf-8"),
                "file_mode": bridge.stat().st_mode & 0o777,
                "directory": bridge.parent,
                "directory_mode": bridge.parent.stat().st_mode & 0o777,
            }
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(compose.subprocess, "run", fake_run)

    assert compose.main(["--", "config", "--quiet"]) == 0
    # The typed Compose prefix carries its own extra arguments after the bridge module, and the
    # noninteractive choice places `--non-interactive` before its final `--`.
    non_interactive = list(mechanics.compose_prefix(non_interactive=True))
    assert non_interactive[-2:] == ["--non-interactive", "--"]
    assert non_interactive[: len(mechanics.compose_prefix()) - 1] == [
        *mechanics.compose_prefix()[:-1]
    ]
    assert compose.main([*non_interactive[-2:], "version"]) == 0
    # Docker Compose's own process-level project override is forwarded as an explicit argv option,
    # so one ephemeral namespace carries through sudo and the default
    # project name in docker-compose.yml is untouched.
    monkeypatch.setenv(compose.COMPOSE_PROJECT_NAME_ALIAS, "synthetic-proof-project")
    assert compose.main(["--", "version"]) == 0

    first, second, third = captures
    command = first["command"]
    assert command[:3] == ("sudo", "docker", "compose")
    assert ("--project-directory", str(tmp_path)) == command[3:5]
    assert ("--file", str(tmp_path / "docker-compose.yml")) == command[5:7]
    assert command[-2:] == ("config", "--quiet")
    assert second["command"][:2] == ("sudo", "-n")
    assert ("--project-name", "synthetic-proof-project") == third["command"][7:9]
    assert third["command"][-1] == "version"
    assert "COMPOSE_PROJECT_NAME" not in str(third["content"])

    values: dict[str, str] = {}
    for line in str(first["content"]).splitlines():
        key, _, quoted = line.partition("=")
        values[key] = quoted
    assert set(values) == {
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_PORT",
        "EMBEDDING_SERVER_IMAGE",
        "EMBEDDING_RUNTIME_REVISION",
        "EMBEDDING_ARTIFACT_SHA256",
        "EMBEDDING_MODEL",
        "EMBEDDING_HOST",
        "EMBEDDING_PORT",
        "EMBEDDING_THREADS",
        "EMBEDDING_CONTEXT_SIZE",
        "EMBEDDING_POOLING",
        "EMBEDDING_NORMALIZATION",
        "EMBEDDING_ARTIFACT_PATH",
    }
    assert values["POSTGRES_PASSWORD"] == "'syn\\'thetic-password'"
    assert first["file_mode"] == 0o600
    assert first["directory_mode"] == 0o700
    assert first["directory"] is not second["directory"]
    assert not first["directory"].exists() and not second["directory"].exists()


def test_unsourced_cli_loads_policy(tmp_path: Path) -> None:
    """The shell action exports example policy with no device or secret alias in a bare env."""
    root = tmp_path / "checkout"
    write_example_config_tree(root)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from course_explorer import configuration; "
            "configuration.repository_root = lambda: Path(sys.argv[1]); "
            "raise SystemExit(configuration.main(['shell']))",
            str(root),
        ],
        check=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")},
        text=True,
    )

    exported: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, _, quoted = line.removeprefix("export ").partition("=")
        exported[key] = shlex.split(quoted)[0]

    assert exported["POSTGRES_DB"] == "course_explorer"
    assert exported["EMBEDDING_PORT"] == "8081"
    assert exported["SEARCH_TIER_PRIORITY"] == '["exact_code","substring","fuzzy_name","semantic"]'
    assert exported["WORKER_GPU_REBOOT_INTERVAL_MINUTES"] == "120"
    assert exported["SELECTED_DATASET_ENABLED"] == "0"
    assert (
        not {
            "POSTGRES_PASSWORD",
            "UNRELATED_SECRET",
            "TRANSLATION_CONTROLLER_SSH_TARGET",
            "TRANSLATION_CONTROLLER_WSL_DISTRIBUTION",
            "TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT",
        }
        & exported.keys()
    )
