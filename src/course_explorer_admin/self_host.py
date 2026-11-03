"""The two self-host setup workflows and the startup lifetime they share.

``setup_example`` takes a fresh checkout from absent working files to a site that serves the bundled
example data without an enrolled dataset. ``setup_real_database`` then creates one named empty
database, enrolls it as Selected and serves it. Both accept their choices in memory, never prompt,
and emit fixed coarse step names through the supplied writer. One workflow copy owns absent template
materialization, generated credentials, the pinned embedding artifact, the preflight, the documented
build steps and the startup mode. The two backends run either from user units or as owned foreground
children of this command.
"""

from __future__ import annotations

import ctypes.util
import json
import os
import pwd
import re
import secrets
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy import inspect

from course_explorer import administration
from course_explorer import configuration as file_configuration
from course_explorer.administration import atomic_write_private_text
from course_explorer.config import (
    DatabaseSettings,
    WebAppSettings,
    embedding_configuration_for_site,
    load_admin_web_settings,
    load_administrative_dataset_settings,
    load_embedding_runtime_settings,
    load_feedback_settings,
    load_local_lifecycle_settings,
    load_raw_database_settings,
    load_web_settings,
)
from course_explorer.datasets import (
    DatasetDatabaseName,
    DatasetId,
    DatasetReceipt,
    dataset_pointer_path,
    has_dataset_enrollment_records,
)
from course_explorer.db.session import create_database_engine
from course_explorer.serving_build import build_serving_artifacts, dataset_settings
from course_explorer_admin import artifacts, configuration, credentials, mechanics, rebuild, server
from course_explorer_admin import datasets as dataset_owner

type StartupMode = Literal["user", "foreground"]

# The four user-unit templates the installation copies. The timer's paired service name is rendered
# from the checkout's own derived identity.
_UNIT_TEMPLATES = (
    "tuni-course-explorer-web.service.in",
    "tuni-course-explorer-admin-web.service.in",
    "tuni-course-explorer-feedback-sender.service.in",
    "tuni-course-explorer-feedback-sender.timer.in",
)

# The three loopback hosts a loopback URL may name.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# A checkout basename that also renders one valid systemd unit name.
_UNIT_SAFE_CHECKOUT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]*")


class _SelfHostModel(BaseModel):
    """Frozen, closed DTO base for the self-host setup contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExampleSetupInput(_SelfHostModel):
    """Everything one example workflow needs, supplied in memory without a prompt.

    ``app_url`` is the feature site's external root address. A null value keeps the example's
    configured address. Both credentials are hidden from the model's representation and its
    serialized form, and validation errors never echo their inputs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    app_url: str | None = None
    username: str
    password: SecretStr = Field(exclude=True, repr=False)
    mode: StartupMode
    confirm_download: bool = False
    publication_token: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_app_url(self) -> ExampleSetupInput:
        """Validate a supplied address through the shared web app settings owner."""
        if self.app_url is not None:
            WebAppSettings.validate_web_app_url(self.app_url)
        return self


class RealDatabaseSetupInput(_SelfHostModel):
    """Everything one real-database workflow needs: the new database name and the startup mode."""

    database_name: DatasetDatabaseName
    mode: StartupMode


class SelfHostReport(_SelfHostModel):
    """One transient workflow result: the address to open and the Selected dataset it enrolled."""

    app_url: str
    dataset_id: DatasetId | None


def _copy_example_files(root: Path) -> bool:
    """Materialize every absent working template and return whether this call created ``.env``.

    A present working path is kept byte for byte. A symlinked or non-regular destination is refused
    rather than followed. A present ``config/`` directory is an ordinary directory that the missing
    files join, never one that is replaced. The created environment file is published at mode 0600.
    """
    created_environment = False
    for relative, destination_relative in _template_pairs(root):
        source = root / relative
        destination = root / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError(
                f"working path {destination_relative} must be a regular non-symlink file"
            )
        if destination.exists():
            continue
        payload = source.read_bytes()
        if destination_relative == ".env":
            atomic_write_private_text(destination, payload.decode("utf-8"), mode=0o600)
            created_environment = True
        else:
            destination.write_bytes(payload)
    return created_environment


def _template_pairs(root: Path) -> tuple[tuple[str, str], ...]:
    """Return every tracked example template and the working path it belongs at."""
    config_root = root / "examples" / "config"
    pairs = [
        (f"examples/config/{path.name}", f"config/{path.name}")
        for path in sorted(config_root.iterdir())
        if path.is_file()
    ]
    pairs.extend(
        (
            ("examples/.env.example", ".env"),
            ("examples/docker-compose.yml", "docker-compose.yml"),
            ("examples/deploy/Caddyfile", "deploy/Caddyfile"),
        )
    )
    pairs.extend((f"examples/deploy/systemd/{name}", f"deploy/{name}") for name in _UNIT_TEMPLATES)
    return tuple(pairs)


def _require_working_files(root: Path) -> None:
    """Require every prepared working file a deployment keeps beside its tracked examples."""
    for _, destination_relative in _template_pairs(root):
        destination = root / destination_relative
        if destination.is_symlink() or not destination.is_file():
            raise ValueError(
                f"self-host setup needs the prepared working file {destination_relative}; "
                "run the example workflow first"
            )


def _require_native_libraries() -> None:
    """Require the two host native libraries the serving modules load at run time."""
    for name, label in (
        ("pq", "libpq"),
        ("stdc++", "libstdc++"),
    ):
        if ctypes.util.find_library(name) is None:
            raise ValueError(
                f"the host native library {label} is missing; install the prerequisites on the "
                "installation page and retry"
            )


def _port_is_free(host: str, port: int) -> bool:
    """Report whether one configured loopback port can be bound by this process."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        try:
            listener.bind((host, port))
        except OSError:
            return False
    return True


def _running_services(runner: mechanics.ProcessRunner, root: Path) -> set[str]:
    """Return the Compose services this project reports running."""
    return mechanics.running_compose_services(
        lambda argv: runner.run(tuple(argv), cwd=root).stdout, interpreter=True
    )


def _require_host_prerequisites(
    root: Path, runner: mechanics.ProcessRunner, write: Callable[[str], None]
) -> None:
    """Preflight the prepared environment, the host tools, the ports and the free disk space.

    The environment-preparation step owns dependency installation. This check refuses a host that
    lacks a prepared interpreter or frontend packages, an interpreter without the Linux
    shared-memory capability the server caches need, a version command that does not answer, a host
    native library, or a loopback port held by another process. A database or embedding port already
    served by this project's own Compose service is allowed.
    """
    interpreter = root / ".venv" / "bin" / "python"
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise ValueError(
            "the checkout has no executable .venv/bin/python; follow installation step two to "
            "prepare the environment"
        )
    try:
        runner.run(
            (
                str(interpreter),
                "-c",
                "import os, sys; assert sys.version_info[:2] >= (3, 14); "
                'descriptor = os.memfd_create("course-explorer-preflight", os.MFD_CLOEXEC); '
                "os.close(descriptor)",
            ),
            cwd=root,
            timeout=load_local_lifecycle_settings().stop_timeout_seconds,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            "the checkout's .venv/bin/python needs Linux CPython 3.14 or newer with "
            "os.memfd_create; recreate this checkout's environment with installation step two and "
            "`uv sync --locked --no-managed-python --python PATH_TO_CAPABLE_PYTHON`"
        ) from exc
    for frontend in ("web", "admin-web"):
        if not (root / frontend / "node_modules").is_dir():
            raise ValueError(
                f"the {frontend} packages are missing; run "
                f"`npm --prefix {frontend} ci --engine-strict --no-audit --no-fund`"
            )
    for argv, label in (
        (("node", "--version"), "Node 22"),
        (("npm", "--version"), "npm"),
        (("uv", "--version"), "uv"),
        (("curl", "--version"), "curl"),
        (("docker", "--version"), "Docker"),
        (("docker", "compose", "version"), "Docker Compose"),
    ):
        try:
            runner.run(argv, cwd=root)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise ValueError(f"{label} is not available; install it and retry") from exc
    _require_native_libraries()

    database = load_raw_database_settings()
    embedding = load_embedding_runtime_settings()
    web = load_web_settings()
    admin = load_admin_web_settings()
    services = _running_services(runner, root)
    for label, host, port, service in (
        ("feature web", web.web_host, web.web_port, None),
        ("administration", admin.admin_web_host, admin.admin_web_port, None),
        ("database", database.postgres_host, database.postgres_port, "db"),
        ("embedding", embedding.embedding_host, embedding.embedding_port, "embedding"),
    ):
        if not _port_is_free(host, port) and service not in services:
            raise ValueError(
                f"the configured {label} port {port} is used by another process; "
                "stop that listener and retry"
            )
    write(
        f"ports: web {web.web_host}:{web.web_port}, "
        f"administration {admin.admin_web_host}:{admin.admin_web_port}, "
        f"database {database.postgres_host}:{database.postgres_port}, "
        f"embedding {embedding.embedding_host}:{embedding.embedding_port}"
    )
    write(f"disk: {shutil.disk_usage(root).free} bytes free at {root}")


def _require_download_space(path: Path, url: str, write: Callable[[str], None]) -> None:
    """Display and check the reported download length against the target filesystem's free space."""
    timeout = load_local_lifecycle_settings().stop_timeout_seconds
    response = httpx.head(url, follow_redirects=True, timeout=timeout)
    response.raise_for_status()
    if response.url.scheme != "https":
        raise ValueError("the embedding artifact download must end at an HTTPS address")
    length = response.headers.get("content-length")
    if length is None:
        raise ValueError(
            "the embedding artifact download does not report its length; an unbounded download "
            "is unsupported"
        )
    required = int(length)
    directory = path.parent
    while not directory.exists():
        directory = directory.parent
    available = shutil.disk_usage(directory).free
    write(f"embedding download: {required} bytes required, {available} bytes available")
    if required > available:
        raise ValueError(
            f"the embedding download needs {required} bytes and {available} bytes are free"
        )


def _prepare_embedding_artifact(
    root: Path,
    runner: mechanics.ProcessRunner,
    *,
    confirm_download: bool,
    write: Callable[[str], None],
) -> None:
    """Check once for the pinned artifact, then download it only after an explicit confirmation."""
    runtime = load_embedding_runtime_settings()
    path = root / runtime.embedding_artifact_path
    if artifacts.artifact_present(path, runtime.embedding_artifact_sha256):
        return
    if not confirm_download:
        raise ValueError(
            "the pinned embedding model is absent; confirm the download before running the workflow"
        )
    _require_download_space(path, str(runtime.embedding_artifact_url), write)
    write(f"download the pinned embedding model to {runtime.embedding_artifact_path}")
    artifacts.download_artifact(
        runner,
        root,
        path,
        runtime.embedding_artifact_sha256,
        str(runtime.embedding_artifact_url),
        None,
    )


# The migration owner's own bookkeeping table, which is not a user table.
_VERSION_TABLE = "alembic_version"


def _existing_table_names(settings: DatabaseSettings) -> tuple[str, ...]:
    """Return the user tables of one short-lived database read."""
    engine = create_database_engine(settings)
    try:
        return tuple(name for name in inspect(engine).get_table_names() if name != _VERSION_TABLE)
    finally:
        engine.dispose()


def _conninfo(
    *, host: str, port: int, database: str, user: str, password: str, timeout: float
) -> str:
    """Build one psycopg connection string in memory from validated components."""
    return psycopg.conninfo.make_conninfo(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
        connect_timeout=max(1, int(timeout)),
    )


def _prepare_feedback_store(*, runner: mechanics.ProcessRunner) -> None:
    """Create the absent feedback role and database, prove the connection, then migrate the chain.

    Both connections must name the same local cluster as the curriculum settings, and the two
    database names must differ. An existing role or database is never reassigned, dropped or given a
    new password. Identifiers are composed through psycopg's SQL identifier and value quoting, and a
    failed creation reports one fixed error that carries no statement or credential.
    """
    raw = load_raw_database_settings()
    feedback = load_feedback_settings()
    if (feedback.feedback_postgres_host, feedback.feedback_postgres_port) != (
        raw.postgres_host,
        raw.postgres_port,
    ):
        raise ValueError(
            "the feedback store must be on the same local database cluster as the curriculum "
            "database"
        )
    if feedback.feedback_postgres_db == raw.postgres_db:
        raise ValueError("the feedback database name must differ from the curriculum database name")
    timeout = load_administrative_dataset_settings().database_operation_timeout_seconds
    role = feedback.feedback_postgres_user
    password = feedback.feedback_postgres_password.get_secret_value()
    admin_conninfo = _conninfo(
        host=raw.postgres_host,
        port=raw.postgres_port,
        database="postgres",
        user=raw.postgres_user,
        password=raw.postgres_password.get_secret_value(),
        timeout=timeout,
    )
    with psycopg.connect(admin_conninfo, autocommit=True) as connection:
        role_present = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
        ).fetchone()
        if role_present is None:
            try:
                connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
            except psycopg.Error:
                raise ValueError("the feedback database role could not be created") from None
        database_present = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (feedback.feedback_postgres_db,)
        ).fetchone()
        if database_present is None:
            try:
                connection.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(feedback.feedback_postgres_db), sql.Identifier(role)
                    )
                )
            except psycopg.Error:
                raise ValueError("the feedback database could not be created") from None

    feedback_conninfo = _conninfo(
        host=feedback.feedback_postgres_host,
        port=feedback.feedback_postgres_port,
        database=feedback.feedback_postgres_db,
        user=role,
        password=password,
        timeout=timeout,
    )
    with psycopg.connect(feedback_conninfo) as connection:
        connection.execute("SELECT 1")

    attachments = feedback.feedback_attachments_root.expanduser()
    if not attachments.is_absolute():
        attachments = administration.repository_root() / attachments
    attachments.mkdir(mode=0o700, parents=True, exist_ok=True)
    runner.run(
        (
            str(administration.repository_root() / ".venv" / "bin" / "python"),
            "-m",
            "alembic",
            "-c",
            "alembic_feedback.ini",
            "upgrade",
            "head",
        ),
        cwd=administration.repository_root(),
        timeout=timeout,
    )


def _loopback_url(host: str, port: int) -> str:
    """Return one loopback HTTP base URL, bracketing an IPv6 host."""
    return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"


def _prove_shells(*, root: Path) -> None:
    """Prove both loopback backends answer their built shell at their configured Host.

    One short-lived client retries only a connection that is not ready yet, exactly as the serving
    proof does, and requires status 200 and the built shell's exact bytes from each backend.
    """
    web = load_web_settings()
    admin = load_admin_web_settings()
    lifecycle = load_local_lifecycle_settings()
    web_shell = (root / "web" / "dist" / "index.html").read_bytes()
    admin_shell = (root / "admin-web" / "dist" / "index.html").read_bytes()
    web_host = urlsplit(web.web_app_url).netloc
    admin_host = urlsplit(admin.admin_web_origin).netloc

    def read(client: httpx.Client) -> bool | None:
        try:
            feature = client.get(
                f"{_loopback_url(web.web_host, web.web_port)}/",
                headers={"Accept-Encoding": "identity", "Host": web_host},
            )
            console = client.get(
                f"{_loopback_url(admin.admin_web_host, admin.admin_web_port)}/",
                headers={"Accept-Encoding": "identity", "Host": admin_host},
            )
        except httpx.ConnectError, httpx.ReadTimeout:
            return None
        feature.raise_for_status()
        console.raise_for_status()
        return feature.content == web_shell and console.content == admin_shell

    with httpx.Client(
        trust_env=False,
        follow_redirects=False,
        timeout=lifecycle.stop_timeout_seconds,
    ) as client:
        mechanics.await_state(
            lambda: read(client),
            lambda accepted: accepted is True,
            attempts=lifecycle.startup_attempts,
            interval=lifecycle.poll_interval_seconds,
            sleep=time.sleep,
        )


def _stop_children(children: Sequence[subprocess.Popen[bytes]], timeout: float) -> None:
    """Terminate and reap only the supplied children within one shared bound."""
    deadline = time.monotonic() + timeout
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        if child.poll() is None:
            try:
                child.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def _serve_foreground(
    *,
    root: Path,
    runner: mechanics.ProcessRunner,
    prove: Callable[[], None],
    write: Callable[[str], None],
) -> None:
    """Run both checkout launchers as owned foreground children until the operator stops them.

    A completed proof announces readiness. A child that exits before that stop is a failed setup.
    Ctrl-C during the post-readiness wait is a normal intentional stop and returns normally. Every
    path terminates and reaps only these two children within the configured stop timeout.
    """
    lifecycle = load_local_lifecycle_settings()
    children: list[subprocess.Popen[bytes]] = []
    try:
        children.append(
            runner.popen(
                ("/usr/bin/bash", str(root / "scripts" / "run_web.sh")),
                cwd=root,
                stdout_path=None,
                stderr_path=None,
            )
        )
        children.append(
            runner.popen(
                ("/usr/bin/bash", str(root / "scripts" / "run_admin_web.sh")),
                cwd=root,
                stdout_path=None,
                stderr_path=None,
            )
        )
        prove()
        write("the site is ready; press Ctrl-C to stop the two foreground servers")
        try:
            while True:
                for child in children:
                    if child.poll() is not None:
                        raise RuntimeError(
                            "a foreground server exited before the operator stopped it"
                        )
                time.sleep(lifecycle.poll_interval_seconds)
        except KeyboardInterrupt:
            pass
    finally:
        _stop_children(children, lifecycle.stop_timeout_seconds)
    write("the database and embedding services continue running")


def _user_unit_directory() -> Path:
    """Return the user manager's unit directory."""
    return Path.home() / ".config" / "systemd" / "user"


def _unit_names(root: Path) -> tuple[str, str, str]:
    """Derive the three owned user-unit names from the checkout's safe basename."""
    name = root.name
    if _UNIT_SAFE_CHECKOUT.fullmatch(name) is None:
        raise ValueError(
            "the checkout directory name must be a nonempty filesystem- and unit-safe basename"
        )
    prefix = f"course-explorer-{name}"
    return (
        f"{prefix}-web.service",
        f"{prefix}-admin-web.service",
        f"{prefix}-feedback-sender.service",
    )


def _render_unit(
    template: str, *, root: Path, uv_bin: Path, feedback_service: str | None = None
) -> str:
    """Render one unit template's checkout, uv path and paired timer service name."""
    rendered = template.replace("@CHECKOUT@", str(root)).replace("@UV_BIN@", str(uv_bin))
    if feedback_service is not None:
        rendered = rendered.replace(
            "tuni-course-explorer-feedback-sender.service", feedback_service
        )
    return rendered


def _install_user_units(root: Path, runner: mechanics.ProcessRunner) -> tuple[str, str, str]:
    """Render the four owned user units, reusing identical files and refusing any different one."""
    web_unit, admin_unit, feedback_unit = _unit_names(root)
    timer_unit = f"{feedback_unit.removesuffix('.service')}.timer"
    uv_bin = shutil.which("uv")
    if uv_bin is None:
        raise ValueError("uv is not available on PATH; install it and retry")
    directory = _user_unit_directory()
    directory.mkdir(parents=True, exist_ok=True)
    mappings = (
        ("tuni-course-explorer-web.service.in", web_unit, None),
        ("tuni-course-explorer-admin-web.service.in", admin_unit, None),
        ("tuni-course-explorer-feedback-sender.service.in", feedback_unit, None),
        (
            "tuni-course-explorer-feedback-sender.timer.in",
            timer_unit,
            feedback_unit,
        ),
    )
    for template_name, unit_name, feedback_service in mappings:
        template = (root / "deploy" / template_name).read_text(encoding="utf-8")
        rendered = _render_unit(
            template,
            root=root,
            uv_bin=Path(uv_bin).parent,
            feedback_service=feedback_service,
        )
        destination = directory / unit_name
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError(f"user unit {unit_name} must be a regular non-symlink file")
        if destination.exists():
            if destination.read_text(encoding="utf-8") != rendered:
                raise ValueError(
                    f"user unit {unit_name} exists with different contents; remove or restore it "
                    "before running this workflow"
                )
            continue
        atomic_write_private_text(destination, rendered, mode=0o644)
    runner.run(
        (
            "systemd-analyze",
            "--user",
            "verify",
            *(str(directory / unit) for unit in (web_unit, admin_unit, feedback_unit, timer_unit)),
        ),
        cwd=root,
    )
    runner.run(("systemctl", "--user", "daemon-reload"), cwd=root)
    runner.run(("systemctl", "--user", "enable", "--now", web_unit), cwd=root)
    runner.run(("systemctl", "--user", "enable", "--now", admin_unit), cwd=root)
    return web_unit, admin_unit, timer_unit


def _enable_feedback_timer(runner: mechanics.ProcessRunner, root: Path, timer_unit: str) -> None:
    """Enable the paired sender timer only after explicit publication setup succeeded."""
    runner.run(("systemctl", "--user", "enable", "--now", timer_unit), cwd=root)


def _explain_linger(
    runner: mechanics.ProcessRunner, root: Path, write: Callable[[str], None]
) -> None:
    """Explain the user-manager boot prerequisite when lingering is not enabled."""
    user = pwd.getpwuid(os.getuid()).pw_name
    output = (
        runner.run(("loginctl", "show-user", user, "--property=Linger"), cwd=root)
        .stdout.decode("utf-8", errors="replace")
        .strip()
    )
    if output != "Linger=yes":
        write(
            "the user manager starts these units at boot only with lingering; run "
            f"`loginctl enable-linger {user}`"
        )


def _show_origins(root: Path, write: Callable[[str], None]) -> None:
    """Show both configured origins and the explicit proxy prerequisite for an external address."""
    web = load_web_settings()
    admin = load_admin_web_settings()
    write(f"feature origin: {web.web_app_origin}")
    write(f"administration origin: {admin.admin_web_origin}")
    if urlsplit(web.web_app_origin).hostname not in _LOOPBACK_HOSTS:
        write(
            "an external feature address needs HTTPS; use the example deploy/Caddyfile with one "
            "certificate per domain, then point the proxy at the two loopback backends"
        )
        if urlsplit(admin.admin_web_origin).hostname in _LOOPBACK_HOSTS:
            write(
                "set the external administration origin with: uv run python scripts/admin.py "
                "config set config/admin_web.toml ADMIN_WEB_ORIGIN <origin>"
            )


def _require_publication_destination(root: Path) -> None:
    """Refuse publication while the feedback destination is still the example placeholder."""
    configured = configuration.read_configuration_file("config/feedback.toml").values[
        "FEEDBACK_GITHUB_REPOSITORY"
    ]
    example = file_configuration.read_public_configuration(
        root / "examples", aliases=("FEEDBACK_GITHUB_REPOSITORY",)
    )["FEEDBACK_GITHUB_REPOSITORY"]
    if configured == example:
        raise ValueError(
            "publication needs a real feedback repository; set it with `uv run python scripts/"
            "admin.py config set config/feedback.toml FEEDBACK_GITHUB_REPOSITORY OWNER/REPOSITORY` "
            "and see docs/backend/feedback-publication.md"
        )


def setup_example(
    options: ExampleSetupInput,
    *,
    runner: mechanics.ProcessRunner,
    write: Callable[[str], None],
) -> SelfHostReport:
    """Take a fresh checkout to a site that serves the bundled example data.

    Absent templates are materialized first. The enrollment and example preconditions are checked
    before any supplied key edit or fresh credential is written. The pinned model, both services,
    the example import, the feedback store, the documented builds and the chosen startup mode follow
    in that order, and the workflow proves both shells and the bootstrap serving identity before it
    returns. No dataset is enrolled.
    """
    root = administration.repository_root()
    write("copy absent working files")
    created_environment = _copy_example_files(root)
    raw = load_raw_database_settings()
    state_root = root / raw.admin_state_root
    if raw.postgres_db != raw.example_postgres_db:
        raise ValueError(
            "the example workflow requires POSTGRES_DB to equal EXAMPLE_POSTGRES_DB in "
            "config/database.toml"
        )
    if (
        has_dataset_enrollment_records(state_root)
        or (dataset_pointer_path(state_root, "selected")).exists()
        or (dataset_pointer_path(state_root, "selected")).is_symlink()
        or (dataset_pointer_path(state_root, "working")).exists()
        or (dataset_pointer_path(state_root, "working")).is_symlink()
    ):
        raise ValueError(
            "the example workflow requires a state root with no dataset pointers or records; "
            "this installation already holds dataset state"
        )

    write("apply device settings")
    if options.app_url is not None:
        configuration.set_configuration_value(
            "config/web.toml", "WEB_APP_URL", json.dumps(options.app_url)
        )
    if options.mode == "user":
        web_unit, admin_unit, _ = _unit_names(root)
        configuration.set_configuration_value(
            "config/admin_web.toml",
            "ADMIN_SITE_WEB_SERVICE_UNIT",
            json.dumps(web_unit),
        )
        configuration.set_configuration_value(
            "config/admin_web.toml",
            "ADMIN_SITE_ADMIN_SERVICE_UNIT",
            json.dumps(admin_unit),
        )
        configuration.set_configuration_value(
            "config/admin_web.toml",
            "ADMIN_SITE_WEB_SERVICE_SCOPE",
            json.dumps("user"),
        )
    if created_environment:
        for key in ("POSTGRES_PASSWORD", "FEEDBACK_POSTGRES_PASSWORD"):
            configuration.set_configuration_value(
                ".env", key, json.dumps(secrets.token_urlsafe(32))
            )
    publication = options.publication_token is not None
    if publication:
        if not created_environment:
            raise ValueError(
                "an existing environment file keeps its feedback sender credential; set it with "
                "`uv run python scripts/admin.py config set .env FEEDBACK_GITHUB_TOKEN '\"TOKEN\"'`"
            )
        _require_publication_destination(root)
        configuration.set_configuration_value(
            ".env",
            "FEEDBACK_GITHUB_TOKEN",
            json.dumps(options.publication_token.get_secret_value()),
        )

    write("create the administration account")
    credential_path = root / credentials.ADMIN_WEB_STATE_ROOT / credentials.PASSWORD_FILENAME
    if credential_path.is_symlink() or (credential_path.exists() and not credential_path.is_file()):
        raise ValueError("administration credential state must be a regular non-symlink file")
    if not credential_path.exists():
        credentials.set_admin_password(username=options.username, password=options.password)

    write("preflight the host")
    _require_host_prerequisites(root, runner, write)
    _show_origins(root, write)

    write("prepare the pinned embedding model")
    _prepare_embedding_artifact(
        root, runner, confirm_download=options.confirm_download, write=write
    )

    write("build and start the database and embedding services")
    timeout = load_administrative_dataset_settings().database_operation_timeout_seconds
    runner.run_interactive(
        (*mechanics.compose_prefix(interpreter=True), "build", "db", "embedding"),
        cwd=root,
        timeout=None,
    )
    runner.run(
        (*mechanics.compose_prefix(interpreter=True), "up", "-d", "--wait", "db", "embedding"),
        cwd=root,
        timeout=timeout,
    )
    write("prepare the example database")
    if _existing_table_names(load_raw_database_settings()):
        raise ValueError(
            "the example database already holds tables; use the real-database workflow or clear "
            "the example database explicitly"
        )

    write("migrate and load the example dataset")
    dataset_owner.migrate_configured_database(runner=runner)
    interpreter = str(root / ".venv" / "bin" / "python")
    runner.run((interpreter, "scripts/mock_data.py", "load"), cwd=root, timeout=None)
    runner.run((interpreter, "scripts/mock_data.py", "write-artifacts"), cwd=root, timeout=None)

    write("prepare the feedback store")
    _prepare_feedback_store(runner=runner)

    write("build the native libraries and frontends")
    runner.run(
        (interpreter, "scripts/build_native.py", "--non-interactive"), cwd=root, timeout=None
    )
    for argv in (
        ("npm", "--prefix", "web", "run", "build"),
        ("npm", "--prefix", "web", "run", "solver:build"),
        ("npm", "--prefix", "admin-web", "run", "build"),
    ):
        runner.run(argv, cwd=root, timeout=None)

    def prove() -> None:
        _prove_shells(root=root)
        dataset_owner.prove_serving_database(
            load_raw_database_settings(),
            previous_identity=None,
            port=load_web_settings().web_port,
        )

    write("start and prove the site")
    if options.mode == "user":
        _, _, timer_unit = _install_user_units(root, runner)
        if publication:
            _enable_feedback_timer(runner, root, timer_unit)
        _explain_linger(runner, root, write)
        prove()
    else:
        _serve_foreground(root=root, runner=runner, prove=prove, write=write)
    return SelfHostReport(app_url=load_web_settings().web_app_url, dataset_id=None)


def setup_real_database(
    options: RealDatabaseSetupInput,
    *,
    runner: mechanics.ProcessRunner,
    write: Callable[[str], None],
) -> SelfHostReport:
    """Create one named empty database, enroll it as Selected, and serve and prove it.

    Prepared working files, both Compose services and idle stages are required. In user mode the
    configured owned web unit and its serving identity are read before any mutation, and the same
    unit is restarted through the shared restart owner. In foreground mode both ports must be free
    and the operator is told to end the first workflow's pair. A repeat refuses inside the named
    enrollment owner before another database, migration or server start.
    """
    root = administration.repository_root()
    _require_working_files(root)
    web = load_web_settings()
    admin = load_admin_web_settings()
    if not {"db", "embedding"} <= _running_services(runner, root):
        raise ValueError(
            "the database and embedding services must already be running; run the example "
            "workflow first"
        )
    dataset_owner.require_stages_idle()

    if options.mode == "user":
        website = server.read_web_service(runner=runner)
        lifecycle = load_local_lifecycle_settings()
        with httpx.Client(
            trust_env=False,
            timeout=lifecycle.stop_timeout_seconds,
            follow_redirects=False,
        ) as client:
            previous_identity = dataset_owner.read_serving_identity(client, website.port)
        port = website.port

        def start(prove: Callable[[], None]) -> None:
            rebuild.restart_web(website, runner=runner)
            prove()

    else:
        for label, host, candidate in (
            ("feature web", web.web_host, web.web_port),
            ("administration", admin.admin_web_host, admin.admin_web_port),
        ):
            if not _port_is_free(host, candidate):
                raise ValueError(
                    f"the configured {label} port {candidate} is already in use; end the first "
                    "workflow's foreground pair with Ctrl-C before running this workflow"
                )
        write(
            "end the first workflow's foreground pair with Ctrl-C before this workflow starts "
            "its own pair"
        )
        previous_identity = None
        port = web.web_port

        def start(prove: Callable[[], None]) -> None:
            _serve_foreground(root=root, runner=runner, prove=prove, write=write)

    write("create the named empty database")
    receipt: DatasetReceipt = dataset_owner.create_empty_selected_dataset(
        options.database_name, runner=runner
    )

    write("build the selected serving artifacts")
    build_serving_artifacts(
        dataset_settings(receipt.dataset_id),
        embedding=embedding_configuration_for_site(web),
    )

    write("start and prove the selected site")

    def prove() -> None:
        _prove_shells(root=root)
        dataset_owner.prove_serving_dataset(receipt, previous_identity=previous_identity, port=port)

    start(prove)
    return SelfHostReport(app_url=web.web_app_url, dataset_id=receipt.dataset_id)


__all__ = [
    "ExampleSetupInput",
    "RealDatabaseSetupInput",
    "SelfHostReport",
    "StartupMode",
    "setup_example",
    "setup_real_database",
]
