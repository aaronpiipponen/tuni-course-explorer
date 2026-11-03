"""Contracts that the subsystem files and the device-local .env compose automatically."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from course_explorer import administration, configuration
from course_explorer.config import (
    SETTINGS_SOURCE_MARKER,
    AdminWebSettings,
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    FeedbackIntakeSettings,
    FeedbackSenderSettings,
    FeedbackSettings,
    SearchSettings,
    UsageSettings,
    WebSettings,
    WorkerConnectionSettings,
    load_administrative_site_settings,
)
from course_explorer_admin import compose
from tests.config._support import FIXTURE_VALUES
from tests.support import write_example_config_tree


def _bind_checkout(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Point the file-source owner at one temporary checkout and drop cached reads."""
    monkeypatch.delenv(SETTINGS_SOURCE_MARKER, raising=False)
    for alias in FIXTURE_VALUES:
        monkeypatch.delenv(alias, raising=False)
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    configuration.clear_configuration_caches()


def test_loads_automatic_configuration_and_applies_override_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The example TOML values load without sourcing, the environment file supplies the database
    password, and an explicit process value wins.
    """
    root = tmp_path / "checkout"
    write_example_config_tree(root)
    (root / ".env").write_text(
        "POSTGRES_PASSWORD=synthetic-secret\n"
        "FEEDBACK_POSTGRES_PASSWORD=synthetic-feedback-secret\n"
        "UNRELATED_SECRET=synthetic-unrelated-secret\n",
        encoding="utf-8",
    )
    (root / ".env").chmod(0o600)
    _bind_checkout(monkeypatch, root)

    # Example TOML values load with no sourcing, and the local .env supplies the secrets.
    database = DatabaseSettings()
    assert database.postgres_db == "course_explorer"
    assert database.postgres_password.get_secret_value() == "synthetic-secret"
    assert database.example_postgres_db == "course_explorer"
    assert WebSettings().web_port == 8037
    assert WebSettings().embeddings_enabled is True
    assert WebSettings().inference_enabled is True
    # The six site and worker identities load from their owning subsystem files.
    worker = WorkerConnectionSettings()
    assert worker.ssh_target == "replace-with-ssh-target"
    assert worker.wsl_distribution == "replace-with-wsl-distribution"
    assert worker.worker_project_root == Path("/home/replace-with-user/tuni-course-explorer")
    site = load_administrative_site_settings()
    assert site.web_service_unit == "replace-with-web.service"
    assert site.admin_service_unit == "replace-with-admin.service"
    assert site.web_service_scope == "user"
    # One app address supplies both consumers, and the feedback origin drops its root slash.
    assert WebSettings().web_app_url == "http://localhost:8037/"
    assert AdminWebSettings().web_app_url == "http://localhost:8037/"
    feedback = FeedbackSettings()
    assert feedback.feedback_postgres_db == "course_explorer_feedback"
    assert feedback.feedback_postgres_port == 5433
    assert feedback.feedback_attachments_root == Path("data/attachments")
    assert feedback.feedback_postgres_password.get_secret_value() == "synthetic-feedback-secret"
    intake = FeedbackIntakeSettings()
    assert intake.web_app_url == "http://localhost:8037/"
    assert intake.web_app_origin == "http://localhost:8037"
    assert intake.feedback_github_repository == "example-owner/example-repository"
    assert intake.feedback_github_visibility == "public"
    assert intake.feedback_browser_submissions_per_hour == 5
    assert intake.feedback_site_submissions_per_hour == 30
    assert intake.feedback_max_request_bytes == 25165824
    # The intake family reads the destination without a sender credential, while the full sender
    # refuses its absence.
    with pytest.raises(ValidationError):
        FeedbackSenderSettings()
    monkeypatch.setenv("FEEDBACK_GITHUB_TOKEN", "synthetic-sender-token")
    sender = FeedbackSenderSettings()
    assert sender.feedback_github_repository == "example-owner/example-repository"
    assert sender.feedback_github_visibility == "public"
    assert sender.feedback_github_timeout_seconds == 120.0

    # An explicit process override wins over both files.
    monkeypatch.setenv("EMBEDDING_PORT", "18080")
    monkeypatch.setenv("COMPARISON_OVERLAP_CEILING", "0.5")
    monkeypatch.setenv("SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("SEARCH_EMBEDDING_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("WEB_PORT", "18028")
    monkeypatch.setenv("WEB_APP_URL", "http://localhost:18037/")
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "0")
    monkeypatch.setenv("WEB_INFERENCE_ENABLED", "0")
    monkeypatch.setenv("USAGE_RETENTION_DAYS", "7")
    monkeypatch.setenv("FEEDBACK_POSTGRES_PORT", "15432")
    monkeypatch.setenv("FEEDBACK_BROWSER_SUBMISSIONS_PER_HOUR", "9")
    monkeypatch.setenv("FEEDBACK_GITHUB_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("ADMIN_SITE_WEB_SERVICE_UNIT", "synthetic-site-web.service")
    monkeypatch.setenv("ADMIN_SITE_ADMIN_SERVICE_UNIT", "synthetic-site-admin.service")
    monkeypatch.setenv("ADMIN_SITE_WEB_SERVICE_SCOPE", "system")
    monkeypatch.setenv("ADMIN_WEB_PORT", "18027")
    monkeypatch.setenv("ADMIN_WEB_SESSION_IDLE_MINUTES", "5")
    monkeypatch.setenv("ADMIN_WEB_POLL_SECONDS", "3")
    assert EmbeddingRuntimeSettings().embedding_port == 18080
    assert SearchSettings().comparison_overlap_ceiling == 0.5
    assert SearchSettings().search_embedding_request_timeout_seconds == 7
    assert SearchSettings().search_embedding_max_attempts == 2
    assert WebSettings().web_port == 18028
    assert WebSettings().web_app_url == "http://localhost:18037/"
    assert AdminWebSettings().web_app_url == "http://localhost:18037/"
    assert FeedbackIntakeSettings().web_app_origin == "http://localhost:18037"
    assert WebSettings().embeddings_enabled is False
    assert WebSettings().inference_enabled is False
    assert UsageSettings().usage_retention_days == 7
    assert FeedbackSettings().feedback_postgres_port == 15432
    assert FeedbackIntakeSettings().feedback_browser_submissions_per_hour == 9
    assert FeedbackSenderSettings().feedback_github_timeout_seconds == 45.0
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
    with configuration.configuration_candidate(documents=documents, local={}):
        assert WebSettings().web_port == 18099
    # Leaving the candidate restores the ordinary source precedence.
    assert WebSettings().web_port == 18028

    # A candidate value the owning validator rejects fails despite the valid process override.
    invalid = web_toml.replace("WEB_PORT = 8037", "WEB_PORT = 70000")
    with pytest.raises(ValidationError):
        with configuration.configuration_candidate(
            documents=configuration.read_configuration_documents(
                root, replacements={"config/web.toml": invalid}
            ),
            local={},
        ):
            WebSettings()


def test_public_configuration_rejects_duplicate_alias(tmp_path: Path) -> None:
    """A duplicate top-level alias across two subsystem files fails before any settings succeed."""
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
    """The Compose command writes a Compose environment file in a temporary directory and removes
    that directory.
    """
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
    monkeypatch.setattr(administration, "repository_root", lambda: tmp_path)
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
    # The noninteractive flag before the final `--` is accepted and the call exits 0.
    assert compose.main(["--non-interactive", "--", "version"]) == 0
    # Docker Compose's own process-level project override is forwarded as an explicit argv option,
    # so one ephemeral namespace carries through sudo and the default
    # project name in docker-compose.yml is untouched.
    monkeypatch.setenv(compose.COMPOSE_PROJECT_NAME_ALIAS, "synthetic-proof-project")
    assert compose.main(["--", "version"]) == 0

    first, second, third = captures
    assert ("--project-name", "synthetic-proof-project") == third["command"][7:9]
    assert "COMPOSE_PROJECT_NAME" not in str(third["content"])

    values: dict[str, str] = {}
    for line in str(first["content"]).splitlines():
        key, _, quoted = line.partition("=")
        values[key] = quoted
    assert values["POSTGRES_PASSWORD"] == "'syn\\'thetic-password'"
    assert first["file_mode"] == 0o600
    assert first["directory_mode"] == 0o700
    assert first["directory"] is not second["directory"]
    assert not first["directory"].exists() and not second["directory"].exists()


def test_unsourced_cli_loads_policy(tmp_path: Path) -> None:
    """The shell action exports the composed example non-secret values, and credential aliases do
    not appear in the exports.
    """
    root = tmp_path / "checkout"
    write_example_config_tree(root)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; "
            "from course_explorer import administration, configuration; "
            "administration.repository_root = lambda: Path(sys.argv[1]); "
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
    assert exported["EXAMPLE_POSTGRES_DB"] == "course_explorer"
    assert exported["WEB_APP_URL"] == "http://localhost:8037/"
    # The worker and site identities are non-secret subsystem values, so the shell exports them.
    assert exported["TRANSLATION_CONTROLLER_SSH_TARGET"] == "replace-with-ssh-target"
    assert exported["TRANSLATION_CONTROLLER_WSL_DISTRIBUTION"] == "replace-with-wsl-distribution"
    assert (
        exported["TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT"]
        == "/home/replace-with-user/tuni-course-explorer"
    )
    assert exported["ADMIN_SITE_WEB_SERVICE_UNIT"] == "replace-with-web.service"
    assert exported["ADMIN_SITE_ADMIN_SERVICE_UNIT"] == "replace-with-admin.service"
    assert exported["ADMIN_SITE_WEB_SERVICE_SCOPE"] == "user"
    assert (
        not {
            "POSTGRES_PASSWORD",
            "FEEDBACK_POSTGRES_PASSWORD",
            "FEEDBACK_GITHUB_TOKEN",
            "UNRELATED_SECRET",
        }
        & exported.keys()
    )
