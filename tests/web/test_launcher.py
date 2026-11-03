"""Contracts for the web process environment handoff and the supervisor's worker and router child
wiring."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import course_explorer
from course_explorer import administration, configuration
from course_explorer.config import (
    ENVIRONMENT_ONLY_SETTINGS_SOURCE,
    SETTINGS_SOURCE_MARKER,
    AdmissionSettings,
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    FeedbackIntakeSettings,
    FeedbackSettings,
    SearchSettings,
    WebSettings,
)
from course_explorer_web import launch
from tests.support import write_example_config_tree

_EMBEDDING_ALIASES = frozenset(
    field.validation_alias
    for field in EmbeddingRuntimeSettings.model_fields.values()
    if isinstance(field.validation_alias, str)
)


@pytest.mark.parametrize("embeddings_enabled", (False, True), ids=("off", "on"))
def test_web_launcher_excludes_operator_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, embeddings_enabled: bool
) -> None:
    """Hand only the required web aliases and the marker to a file-free child process."""
    root = tmp_path / "checkout"
    write_example_config_tree(root)
    local = root / ".env"
    local.write_text(
        "POSTGRES_PASSWORD=synthetic-database-password\n"
        "FEEDBACK_POSTGRES_PASSWORD=synthetic-feedback-password\n",
        encoding="utf-8",
    )
    local.chmod(0o600)
    monkeypatch.setattr(administration, "repository_root", lambda: root)
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
            "WEB_APP_URL": "https://feedback.example.org/",
            "TRANSLATION_CONTROLLER_SSH_TARGET": "synthetic-worker",
            "TRANSLATION_CONTROLLER_WSL_DISTRIBUTION": "synthetic-distribution",
            "TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT": "/home/synthetic/checkout",
            "ADMIN_SITE_WEB_SERVICE_UNIT": "synthetic-web.service",
            "ADMIN_SITE_ADMIN_SERVICE_UNIT": "synthetic-admin.service",
            "ADMIN_SITE_WEB_SERVICE_SCOPE": "system",
            "ADMIN_WEB_ORIGIN": "https://admin.example.org",
            "SSH_AUTH_SOCK": "/tmp/synthetic-agent.sock",
            "FEEDBACK_GITHUB_TOKEN": "synthetic-feedback-token",
            "FEEDBACK_GITHUB_TIMEOUT_SECONDS": "45",
            "UNRELATED_SECRET": "synthetic-unrelated-secret",
        },
    )

    with pytest.raises(ExecCaptured):
        launch.main()

    assert observed["POSTGRES_PASSWORD"] == "synthetic-database-password"
    assert observed["WEB_HOST"] == "127.0.0.1"
    assert observed["WEB_PORT"] == "8037"
    assert observed["WEB_WORKERS"] == "4"
    assert observed["WEB_EMBEDDINGS_ENABLED"] == ("1" if embeddings_enabled else "0")
    assert observed["WEB_INFERENCE_ENABLED"] == "1"
    assert observed["WEB_APP_URL"] == "https://feedback.example.org/"
    assert observed["ADMISSION_ENABLED"] == "1"
    assert observed["MALLOC_ARENA_MAX"] == "2"
    assert {"HOME", "PATH", "LANG"} <= observed.keys()
    # The launcher sets the child's PYTHONPATH to the source directory of the package it loaded.
    assert observed["PYTHONPATH"] == str(Path(course_explorer.__file__).resolve().parent.parent)
    assert observed[SETTINGS_SOURCE_MARKER] == ENVIRONMENT_ONLY_SETTINGS_SOURCE
    assert (
        not {
            "TRANSLATION_CONTROLLER_SSH_TARGET",
            "TRANSLATION_CONTROLLER_WSL_DISTRIBUTION",
            "TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT",
            "ADMIN_SITE_WEB_SERVICE_UNIT",
            "ADMIN_SITE_ADMIN_SERVICE_UNIT",
            "ADMIN_SITE_WEB_SERVICE_SCOPE",
            "ADMIN_WEB_ORIGIN",
            "SSH_AUTH_SOCK",
            "FEEDBACK_GITHUB_TOKEN",
            "FEEDBACK_GITHUB_TIMEOUT_SECONDS",
            "UNRELATED_SECRET",
        }
        & observed.keys()
    )
    # A site without embedding features hands over no embedding alias at all, so its child can
    # compose no embedding family.
    if embeddings_enabled:
        assert _EMBEDDING_ALIASES <= observed.keys()
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
    assert observed["WEB_RESPAWN_EXIT_LIMIT"] == "3"
    assert observed["WEB_RESPAWN_WINDOW_SECONDS"] == "60"
    assert WebSettings().web_port == 8037
    assert WebSettings().web_workers == 4
    assert WebSettings().web_malloc_arena_max == 2
    assert WebSettings().web_respawn_exit_limit == 3
    assert WebSettings().web_respawn_window_seconds == 60
    assert WebSettings().web_app_url == "https://feedback.example.org/"
    assert WebSettings().embeddings_enabled is embeddings_enabled
    assert WebSettings().inference_enabled is True
    assert AdmissionSettings().admission_enabled is True
    # The handed feedback families reconstruct from the closed environment alone, and the one app
    # address supplies the exact feedback origin without its root slash.
    assert FeedbackSettings().feedback_postgres_port == 5433
    assert FeedbackSettings().feedback_postgres_password.get_secret_value() == (
        "synthetic-feedback-password"
    )
    assert FeedbackIntakeSettings().web_app_url == "https://feedback.example.org/"
    assert FeedbackIntakeSettings().web_app_origin == "https://feedback.example.org"
    assert FeedbackIntakeSettings().feedback_github_repository == "example-owner/example-repository"
    assert FeedbackIntakeSettings().feedback_github_visibility == "public"
    assert FeedbackIntakeSettings().feedback_browser_submissions_per_hour == 5
    assert FeedbackIntakeSettings().feedback_site_submissions_per_hour == 30
    assert FeedbackIntakeSettings().feedback_max_request_bytes == 25165824
    # The handoff carries the search policy for one query embedding request as well.
    assert SearchSettings().search_embedding_request_timeout_seconds == 5
    assert SearchSettings().search_embedding_max_attempts == 1


@pytest.mark.integration
def test_web_router_waits_for_all_workers(
    database: tuple[object, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Run the real supervisor, router and four forked workers and replace a killed worker.

    The site has the embedding features off, so its build holds the catalogue and the study
    fragments alone. The supervisor starts and answers a request with no hub pair, shared store or
    packed search row present.
    """
    from course_explorer.config import load_database_settings
    from course_explorer.serving_artifacts import serving_artifact_root, serving_key
    from course_explorer.study_structure.fragments import StudyFragmentStore

    repository = Path(__file__).resolve().parents[2]
    # The supervisor resolves its repository root from the imported package, so a disposable copy
    # of the two serving packages and the configuration gives the launched stack its own data root.
    root = tmp_path / "launcher"
    (root / "src").mkdir(parents=True)
    shutil.copytree(repository / "src" / "course_explorer", root / "src" / "course_explorer")
    shutil.copytree(
        repository / "src" / "course_explorer_web", root / "src" / "course_explorer_web"
    )
    shutil.copytree(repository / "config", root / "config")
    (root / "native").symlink_to(repository / "native", target_is_directory=True)
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "0")
    settings = load_database_settings()
    key = serving_key(settings)
    admin_state = "data/admin-tests"
    family = serving_artifact_root(root / admin_state, key)
    family.mkdir(parents=True, exist_ok=True)
    build = family / "test-build"
    build.mkdir()
    (build / "catalogue.json").write_bytes(b'{"courses":[],"modules":[]}')
    StudyFragmentStore.build(
        object(),
        (),
        dataset_key=key.key,
        academic_year_start=key.academic_year_start,
        path=build / "study-fragments.bin",
    )
    os.symlink("test-build", family / "current")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": str(root / "src"),
            "ADMIN_STATE_ROOT": admin_state,
            "WEB_HOST": "127.0.0.1",
            "WEB_PORT": str(port),
            "WEB_WORKERS": "4",
            "WEB_EMBEDDINGS_ENABLED": "0",
            "WEB_INFERENCE_ENABLED": "1",
            "COURSE_EXPLORER_WEB_GENERATION": "launcher-test",
            "POSTGRES_PASSWORD": settings.postgres_password.get_secret_value(),
        }
    )
    supervisor = subprocess.Popen(
        [sys.executable, "-m", "course_explorer_web"],
        cwd=root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    request_body = json.dumps({"query": "COMP.CS", "display_language": "en"}).encode()

    def worker_pids() -> list[int]:
        children = subprocess.run(
            ["pgrep", "-P", str(supervisor.pid)], check=True, text=True, capture_output=True
        ).stdout.split()
        result = []
        for pid in children:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
            if (
                b"course_explorer_web.router" not in command
                and b"multiprocessing.resource_tracker" not in command
            ):
                result.append(int(pid))
        return sorted(result)

    def request_once() -> bytes:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/search",
            data=request_body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            return response.read()

    def retry_request(timeout: float = 30.0) -> bytes:
        deadline = time.monotonic() + timeout
        while True:
            try:
                return request_once()
            except urllib.error.URLError, ConnectionError, TimeoutError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)

    try:
        first = retry_request()
        pids = worker_pids()
        assert len(pids) == 4
        os.kill(pids[0], signal.SIGTERM)
        deadline = time.monotonic() + 30.0
        while len(worker_pids()) != 4:
            if time.monotonic() > deadline:
                raise AssertionError("the supervisor did not replace the killed worker")
            time.sleep(0.1)
        second = retry_request()
    finally:
        supervisor.terminate()
        supervisor.wait(timeout=20)
        shutil.rmtree(root / admin_state, ignore_errors=True)
    assert first == second
