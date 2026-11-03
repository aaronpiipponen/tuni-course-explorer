"""The one server-only status report behind the operator's Dashboard read.

This module owns the read-only server status report: the measured systemd state of this checkout's
web unit, the Compose services of the configured database and embedding runtimes, the database's own
size, connection count and migration head, the host's uptime, CPU usage, memory and disk facts, the
selected-dataset metadata the serving database resolves through, and the two embedding hub file
times of the artifact family's configured embedding directory on a site that serves the embedding
features. Every member states which kind of fact it is: measured, configured, a checkout identity, a
serving receipt, or a file time.

The report reads the local host and this checkout's own state. A running container whose database
read fails fails the whole report, and an absent service is reported as absent.
"""

from __future__ import annotations

import json
import shutil
import stat
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from course_explorer import administration
from course_explorer.administration import utc_now
from course_explorer.config import (
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    embedding_configuration_for_site,
    load_administrative_dataset_settings,
    load_administrative_site_settings,
    load_database_settings,
    load_embedding_runtime_settings,
    load_raw_database_settings,
    load_web_settings,
)
from course_explorer.datasets import dataset_pointer_path, dataset_state_refusal, read_dataset_role
from course_explorer.db.session import create_database_engine
from course_explorer.serving_artifacts import (
    HUB_CATALOGUE_FILE,
    HUB_OUTCOMES_FILE,
    configured_embedding_directory,
    serving_artifact_root,
    serving_key,
)
from course_explorer_admin import mechanics
from course_explorer_admin.datasets import admin_state_path, admin_state_root

# The one requested systemd property set. Only these properties are read, so no environment,
# credential or unit file text reaches the report.
_SITE_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "MainPID",
    "ActiveEnterTimestampMonotonic",
    "WorkingDirectory",
    "ExecStart",
)

# The one web entry point this checkout's web unit runs, relative to the checkout root.
_WEB_ENTRY_POINT = "scripts/run_web.sh"

# The two embedding hub files of a serving artifact build, in report order.
_HUB_FILES: tuple[tuple[Literal["catalogue", "outcomes"], str], ...] = (
    ("catalogue", HUB_CATALOGUE_FILE),
    ("outcomes", HUB_OUTCOMES_FILE),
)

# The two selected Compose services of the server-only report.
_DATABASE_SERVICE = "db"
_EMBEDDING_SERVICE = "embedding"

# The repository-relative directory totals the host member reports, and the member each fills.
_DIRECTORY_TOTALS = (
    ("data", "data_bytes"),
    ("models", "models_bytes"),
    ("data/backups", "backups_bytes"),
)

# The interval, in seconds, one host CPU usage sample covers.
_CPU_SAMPLE_SECONDS = 0.2


class _ServerModel(BaseModel):
    """Frozen, closed DTO base for the server status contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ContainerStatus(_ServerModel):
    """One selected Compose service as the listing reports it.

    ``state`` is the listing's own word, and ``absent`` is the one value this module supplies: a
    successful listing that does not contain the service. ``health`` and ``image`` are ``None``
    when the listing does not report them.
    """

    state: str
    health: str | None = None
    image: str | None = None


class WebsiteStatus(_ServerModel):
    """This checkout's web unit: its measured systemd state, its configured bind and its checkout.

    ``state``, ``substate``, ``main_pid``, ``started_at`` and ``uptime_seconds`` are measured from
    the unit, and a unit that is not active reports no start time and no uptime. ``host``, ``port``
    and ``configured_workers`` are the configured serving values, and not a measured worker count.
    ``entry_point`` is the checkout-relative script the unit runs. ``checkout_branch`` and
    ``checkout_revision`` are the identity of the checkout this report reads, never a claim about
    the revision of the running process.
    """

    unit: str
    state: str
    substate: str
    main_pid: int
    host: str
    port: int
    configured_workers: int
    entry_point: str
    started_at: datetime | None
    uptime_seconds: float | None
    checkout_branch: str
    checkout_revision: str


class HostStatus(_ServerModel):
    """The host's measured uptime, CPU usage, memory, disk and repository directory totals.

    ``cpu_usage_percent`` is the aggregate CPU time that was not idle or waiting for I/O over one
    short sample, on a scale from 0 to 100. A directory total is ``None`` when that directory is
    absent or is not a real directory of this checkout, and it is never a database size estimate.
    ``disk_total_bytes`` and ``disk_free_bytes`` describe the filesystem that holds the checkout.
    """

    uptime_seconds: float
    cpu_usage_percent: float
    memory_total_bytes: int
    memory_used_bytes: int
    data_bytes: int | None
    models_bytes: int | None
    backups_bytes: int | None
    disk_total_bytes: int
    disk_free_bytes: int


class DatabaseStatus(_ServerModel):
    """The configured database service and the live facts of the database it serves.

    ``name`` is the name the resolved settings carry, so it is the Selected dataset's database name
    when a pointer resolves one. ``expected_schema_revision`` is this checkout's
    single migration head, ``schema_revision`` is the database's own current revision, and
    ``at_head`` compares the two. ``shared_memory_bytes`` is the container's configured
    shared-memory size, which the service supplies whenever the listing carries its container. The
    size, the connection count and ``schema_revision`` are ``None`` while the service is not
    running, because no live database read ran.
    """

    container: ContainerStatus
    host: str
    port: int
    name: str
    schema_revision: str | None
    expected_schema_revision: str
    at_head: bool | None
    size_bytes: int | None
    connections: int | None
    shared_memory_bytes: int | None


class EmbeddingStatus(_ServerModel):
    """The configured embedding runtime and the container that serves it.

    ``artifact`` names the configured artifact path, which identifies the model the service loads.
    """

    container: ContainerStatus
    host: str
    port: int
    model: str
    artifact: str
    context_size: int
    threads: int
    pooling: str
    normalization: int


class ServingStatus(_ServerModel):
    """The site's served feature states and the Selected dataset metadata its database resolves through.

    ``embeddings_enabled`` is the site's embedding feature switch. Without a Selected pointer the
    process reads its configured database, so every receipt member is ``None``. With a pointer the
    members are the Selected receipt's own values and ``pointer`` is the repository-relative pointer
    file that named it. ``receipt_schema_revision`` is the database head the receipt's verification
    records, which is neither the live database's own revision nor this checkout's expected head.
    ``selection_enabled`` is ``None`` when the dataset state tree is redirected or not a directory,
    so the selection is unknown.
    """

    selection_enabled: bool | None
    embeddings_enabled: bool
    dataset_id: str | None = None
    kind: str | None = None
    predecessor_id: str | None = None
    pointer: str | None = None
    receipt_schema_revision: str | None = None


class HubStatus(_ServerModel):
    """One embedding hub file of the configured embedding directory: its name, path and file time.

    ``modified_at`` is ``None`` while the directory does not hold the file, and a path that names
    something other than a regular file fails the report. ``newer_than_web_start`` is ``None``
    while either that time or the measured web start is unknown. The comparison is a restart hint
    rather than proof of the process's in-memory values.
    """

    name: Literal["catalogue", "outcomes"]
    path: str
    modified_at: datetime | None
    newer_than_web_start: bool | None


class ServerStatusReport(_ServerModel):
    """One read-only server status report for the operator's Dashboard.

    ``hubs`` is empty on a site with the embedding features off, because its artifact build
    writes no hub file.
    """

    schema_version: Literal[1] = 1
    website: WebsiteStatus
    host: HostStatus
    database: DatabaseStatus
    embedding: EmbeddingStatus
    serving: ServingStatus
    hubs: tuple[HubStatus, ...]


def _unit_properties(
    runner: mechanics.ProcessRunner,
    unit: str,
    *,
    root: Path,
    scope: Literal["user", "system"] = "user",
) -> dict[str, str]:
    """Read the requested properties of one systemd unit from its manager."""
    manager = ("--user",) if scope == "user" else ()
    argv = (
        "systemctl",
        *manager,
        "show",
        unit,
        "--no-pager",
        *(argument for name in _SITE_PROPERTIES for argument in ("-p", name)),
    )
    output = runner.run(argv, cwd=root).stdout.decode("utf-8")
    properties: dict[str, str] = {}
    for line in output.splitlines():
        name, separator, value = line.partition("=")
        if separator:
            properties[name] = value
    missing = [name for name in _SITE_PROPERTIES if name not in properties]
    if missing:
        raise ValueError("the site unit must report every requested systemd property")
    return properties


def read_owned_site_unit(
    runner: mechanics.ProcessRunner,
    unit: str,
    *,
    root: Path,
    entry_point: str,
    scope: Literal["user", "system"] = "user",
) -> dict[str, str]:
    """Read one loaded systemd unit of this checkout and refuse a unit of another site.

    The unit must be loaded, must run from this checkout, and its command line must carry the exact
    ``<checkout>/<entry_point>`` token. Every owner that reports or mutates a site unit shares this
    one check, so no owner reads or restarts another application's unit. The scope selects the
    manager that owns the unit.
    """
    properties = _unit_properties(runner, unit, root=root, scope=scope)
    if properties["LoadState"] != "loaded":
        raise ValueError("the configured site unit must be loaded")
    if Path(properties["WorkingDirectory"]) != root:
        raise ValueError("the configured site unit must run from this checkout")
    if str(root / entry_point) not in properties["ExecStart"].split():
        raise ValueError("the configured site unit must execute this checkout's entry point")
    return properties


def read_web_service(*, runner: mechanics.ProcessRunner) -> WebsiteStatus:
    """Read this checkout's web unit and refuse a unit that belongs to another site.

    The unit must be loaded, must run from this checkout, and its command line must carry the exact
    ``<checkout>/scripts/run_web.sh`` token. The unit's configured manager scope selects the
    systemd manager the read addresses. A status read and the rebuild precondition share this one
    check, so neither reports nor restarts another application's or the administration service.
    """
    root = administration.repository_root()
    settings = load_administrative_site_settings()
    properties = read_owned_site_unit(
        runner,
        settings.web_service_unit,
        root=root,
        entry_point=_WEB_ENTRY_POINT,
        scope=settings.web_service_scope,
    )

    started_at: datetime | None = None
    uptime_seconds: float | None = None
    if properties["ActiveState"] == "active":
        entered_microseconds = int(properties["ActiveEnterTimestampMonotonic"])
        uptime_seconds = time.monotonic() - entered_microseconds / 1_000_000
        started_at = utc_now() - timedelta(seconds=uptime_seconds)

    web = load_web_settings()
    return WebsiteStatus(
        unit=settings.web_service_unit,
        state=properties["ActiveState"],
        substate=properties["SubState"],
        main_pid=int(properties["MainPID"]),
        host=web.web_host,
        port=web.web_port,
        configured_workers=web.web_workers,
        entry_point=_WEB_ENTRY_POINT,
        started_at=started_at,
        uptime_seconds=uptime_seconds,
        checkout_branch=runner.run(("git", "branch", "--show-current"), cwd=root)
        .stdout.decode()
        .strip(),
        checkout_revision=runner.run(("git", "rev-parse", "HEAD"), cwd=root)
        .stdout.decode()
        .strip(),
    )


def _required_text(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"the Compose listing must report a {key} for a selected service")
    return value


def _optional_text(entry: dict[str, object], key: str) -> str | None:
    value = entry.get(key)
    return value if isinstance(value, str) and value else None


def _compose_services(
    runner: mechanics.ProcessRunner, *, root: Path
) -> dict[str, dict[str, object]]:
    """Read the one Compose service listing, keyed by service name."""
    argv = (
        *mechanics.compose_prefix(non_interactive=True, interpreter=True),
        "ps",
        "--all",
        "--format",
        "{{json .}}",
    )
    output = runner.run(argv, cwd=root).stdout.decode("utf-8")
    services: dict[str, dict[str, object]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if not isinstance(entry, dict) or not isinstance(entry.get("Service"), str):
            raise ValueError("each Compose listing line must describe one service")
        services[entry["Service"]] = entry
    return services


def _container_status(services: dict[str, dict[str, object]], service: str) -> ContainerStatus:
    entry = services.get(service)
    if entry is None:
        return ContainerStatus(state="absent")
    return ContainerStatus(
        state=_required_text(entry, "State"),
        health=_optional_text(entry, "Health"),
        image=_optional_text(entry, "Image"),
    )


def _expected_schema_revision(root: Path) -> str:
    """Return this checkout's single Alembic head."""
    heads = ScriptDirectory.from_config(AlembicConfig(str(root / "alembic.ini"))).get_heads()
    if len(heads) != 1:
        raise ValueError("the repository must expose exactly one Alembic head")
    return heads[0]


def _container_shared_memory_bytes(
    entry: dict[str, object] | None, *, runner: mechanics.ProcessRunner, root: Path
) -> int | None:
    """Read one container's configured shared-memory size, or ``None`` without a container."""
    if entry is None:
        return None
    identifier = _required_text(entry, "ID")
    output = runner.run(
        (
            "sudo",
            "-n",
            "docker",
            "inspect",
            "--format",
            "{{.HostConfig.ShmSize}}",
            identifier,
        ),
        cwd=root,
    ).stdout
    text_value = output.decode("ascii", errors="strict").strip()
    if not text_value.isdigit():
        raise ValueError("the database container must report its shared-memory size as an integer")
    return int(text_value)


def _live_database_facts(settings: DatabaseSettings) -> tuple[int, int, str | None]:
    """Read the database's own size, connection count and current migration revision."""
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            size_bytes = int(
                connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
            )
            connections = int(
                connection.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
                ).scalar_one()
            )
            revisions = MigrationContext.configure(connection).get_current_heads()
    finally:
        engine.dispose()
    if len(revisions) > 1:
        raise ValueError("the serving database must expose at most one migration revision")
    return size_bytes, connections, revisions[0] if revisions else None


def _read_database(
    container: ContainerStatus,
    entry: dict[str, object] | None,
    *,
    runner: mechanics.ProcessRunner,
    root: Path,
    settings: DatabaseSettings,
) -> DatabaseStatus:
    """Compose the database member from the container state, one live read, and the configured name."""
    expected = _expected_schema_revision(root)
    shared_memory_bytes = _container_shared_memory_bytes(entry, runner=runner, root=root)
    schema_revision: str | None = None
    size_bytes: int | None = None
    connections: int | None = None
    if container.state == "running":
        size_bytes, connections, schema_revision = _live_database_facts(settings)
    return DatabaseStatus(
        container=container,
        host=settings.postgres_host,
        port=settings.postgres_port,
        name=settings.postgres_db,
        schema_revision=schema_revision,
        expected_schema_revision=expected,
        at_head=None if container.state != "running" else schema_revision == expected,
        size_bytes=size_bytes,
        connections=connections,
        shared_memory_bytes=shared_memory_bytes,
    )


def _read_embedding(
    container: ContainerStatus,
) -> EmbeddingStatus:
    """Compose the embedding member from its configured runtime contract and its container."""
    runtime = load_embedding_runtime_settings()
    return EmbeddingStatus(
        container=container,
        host=runtime.embedding_host,
        port=runtime.embedding_port,
        model=runtime.embedding_model,
        artifact=str(runtime.embedding_artifact_path),
        context_size=runtime.embedding_context_size,
        threads=runtime.embedding_threads,
        pooling=runtime.embedding_pooling,
        normalization=runtime.embedding_normalization,
    )


def _served_database_settings(*, state_available: bool) -> DatabaseSettings:
    """Read the Selected dataset's connection, or the configured database when its state is unknown.

    A redirected or non-directory dataset state tree resolves no Selected receipt, so the report
    names the configured database the connection settings carry.
    """
    if not state_available:
        return load_raw_database_settings()
    return load_database_settings(role="selected")


def _read_serving(*, state_available: bool, embeddings_enabled: bool) -> ServingStatus:
    """Project the Selected receipt when its pointer exists, else the configured database.

    A redirected or non-directory dataset state tree reports the unknown selection instead of
    reading through it.
    """
    if not state_available:
        return ServingStatus(selection_enabled=None, embeddings_enabled=embeddings_enabled)
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    receipt = read_dataset_role(root, "selected")
    if receipt is None:
        return ServingStatus(selection_enabled=False, embeddings_enabled=embeddings_enabled)
    return ServingStatus(
        selection_enabled=True,
        embeddings_enabled=embeddings_enabled,
        dataset_id=receipt.dataset_id,
        kind=receipt.kind,
        predecessor_id=receipt.predecessor_id,
        pointer=dataset_pointer_path(root, "selected")
        .relative_to(administration.repository_root())
        .as_posix(),
        receipt_schema_revision=receipt.verification.alembic_revision,
    )


def _read_memory_kibibytes() -> tuple[int, int]:
    """Return the kernel's total and available memory in kibibytes."""
    total: int | None = None
    available: int | None = None
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        name, separator, rest = line.partition(":")
        if not separator:
            continue
        field = rest.split()
        if not field:
            continue
        if name == "MemTotal":
            total = int(field[0])
        elif name == "MemAvailable":
            available = int(field[0])
    if total is None or available is None:
        raise ValueError("the kernel memory report must carry MemTotal and MemAvailable")
    return total, available


def _read_cpu_counters() -> tuple[int, int]:
    """Return the aggregate CPU's busy and total jiffies from the kernel's own report."""
    for line in Path("/proc/stat").read_text(encoding="ascii").splitlines():
        fields = line.split()
        if not fields or fields[0] != "cpu":
            continue
        counters = [int(field) for field in fields[1:9]]
        if len(counters) < 8:
            raise ValueError("the kernel CPU report must carry its aggregate counters")
        total = sum(counters)
        idle = counters[3] + counters[4]
        return total - idle, total
    raise ValueError("the kernel CPU report must carry its aggregate cpu line")


def _read_cpu_usage_percent() -> float:
    """Return the aggregate CPU use over one short sample, from 0 to 100."""
    busy_before, total_before = _read_cpu_counters()
    time.sleep(_CPU_SAMPLE_SECONDS)
    busy_after, total_after = _read_cpu_counters()
    elapsed = total_after - total_before
    if elapsed <= 0:
        raise ValueError("the CPU sample must advance")
    return round((busy_after - busy_before) / elapsed * 100, 1)


def _directory_bytes(root: Path, relative: str, *, runner: mechanics.ProcessRunner) -> int | None:
    """Return one fixed directory's total bytes, or ``None`` when it is absent.

    Every component from the supplied checkout root through the requested directory is inspected
    without resolving it, so a symlinked or non-directory component is not a total of this checkout
    and reports nothing. The read is a directory total rather than a database size or a content
    read.
    """
    path = root
    if path.is_symlink() or not path.is_dir():
        return None
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink() or not path.is_dir():
            return None
    output = runner.run(("du", "-sb", "--", str(path)), cwd=root).stdout.decode("utf-8")
    fields = output.split()
    if not fields or not fields[0].isdigit():
        raise ValueError("a directory total must be reported as one whole number of bytes")
    return int(fields[0])


def _read_host(root: Path, *, runner: mechanics.ProcessRunner) -> HostStatus:
    """Compose the host member from the kernel's own reports and the three directory totals."""
    total_kibibytes, available_kibibytes = _read_memory_kibibytes()
    cpu_usage_percent = _read_cpu_usage_percent()
    usage = shutil.disk_usage(root)
    totals: dict[str, int | None] = {}
    for relative, member in _DIRECTORY_TOTALS:
        totals[member] = _directory_bytes(root, relative, runner=runner)
    return HostStatus(
        uptime_seconds=float(Path("/proc/uptime").read_text(encoding="ascii").split()[0]),
        cpu_usage_percent=cpu_usage_percent,
        memory_total_bytes=total_kibibytes * 1024,
        memory_used_bytes=(total_kibibytes - available_kibibytes) * 1024,
        data_bytes=totals["data_bytes"],
        models_bytes=totals["models_bytes"],
        backups_bytes=totals["backups_bytes"],
        disk_total_bytes=usage.total,
        disk_free_bytes=usage.free,
    )


def _read_hubs(
    root: Path,
    settings: DatabaseSettings,
    website: WebsiteStatus,
    *,
    embedding: EmbeddingRuntimeSettings | None,
) -> tuple[HubStatus, ...]:
    """Stat both hub files of the configured embedding directory and compare their times.

    ``embedding`` is the resolved site configuration or ``None`` when the embedding features are
    off. Such a site writes no hub file, so the report holds no hub entry and no artifact path is
    resolved. An existing file must be a regular file, whose own modification time is reported. Any
    other metadata failure or a non-regular target fails the report.
    """
    if embedding is None:
        return ()
    family = serving_artifact_root(root / settings.admin_state_root, serving_key(settings))
    directory = configured_embedding_directory(family, embedding)
    hubs: list[HubStatus] = []
    for name, filename in _HUB_FILES:
        resolved = directory / filename
        try:
            metadata = resolved.stat()
        except FileNotFoundError:
            metadata = None
        modified_at: datetime | None = None
        if metadata is not None:
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("an embedding hub path must name a regular file")
            modified_at = datetime.fromtimestamp(metadata.st_mtime, tz=UTC)
        newer: bool | None = None
        if modified_at is not None and website.started_at is not None:
            newer = modified_at > website.started_at
        hubs.append(
            HubStatus(
                name=name,
                path=resolved.relative_to(root).as_posix()
                if resolved.is_relative_to(root)
                else resolved.as_posix(),
                modified_at=modified_at,
                newer_than_web_start=newer,
            )
        )
    return tuple(hubs)


def read_server_status(*, runner: mechanics.ProcessRunner) -> ServerStatusReport:
    """Read one server-only status report. It writes nothing and contacts no worker."""
    root = administration.repository_root()
    website = read_web_service(runner=runner)
    services = _compose_services(runner, root=root)
    administration_settings = load_administrative_dataset_settings()
    state_available = dataset_state_refusal(admin_state_path(administration_settings)) is None
    settings = _served_database_settings(state_available=state_available)
    web = load_web_settings()
    embedding = embedding_configuration_for_site(web)
    return ServerStatusReport(
        website=website,
        host=_read_host(root, runner=runner),
        database=_read_database(
            _container_status(services, _DATABASE_SERVICE),
            services.get(_DATABASE_SERVICE),
            runner=runner,
            root=root,
            settings=settings,
        ),
        embedding=_read_embedding(_container_status(services, _EMBEDDING_SERVICE)),
        serving=_read_serving(
            state_available=state_available, embeddings_enabled=web.embeddings_enabled
        ),
        hubs=_read_hubs(root, settings, website, embedding=embedding),
    )
