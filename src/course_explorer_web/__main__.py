"""Supervise one front router and its configured worker processes on loopback sockets.

The supervisor resolves the one settings bundle, opens the serving artifact set and both catalogue
response forms, opens the search embedding client when the site serves the embedding features, and
builds the lookup projection and shared cache regions before it creates signal handlers, listeners
or threads. The site's embedding switch is read once there and the resolved embedding configuration
is what the artifact opening and the settings bundle use. A site that serves the embedding features
thus opens the hub pair of its family's embedding directory, the shared stores and the packed search
row once. A site with them off needs the catalogue and the study fragments alone.
It then forks every worker from that inherited state. The supervisor owns every listening socket
for its whole life: the configured listener and one ephemeral loopback listener per worker. A worker
exit starts a forked replacement on the same descriptor and the inherited projection, so the port
never changes and the other workers keep serving. The router keeps its subprocess lifetime. When one
role exits the configured number of times inside the configured window, the supervisor stops every
child and returns nonzero for systemd's ``Restart=on-failure``. SIGTERM and SIGINT stop every child
and return zero without a replacement. No request is replayed, a replacement router starts with
fresh admission state, and only the exited process's in-flight requests fail.

The configured listener accepts connections from the moment it binds, so a client that connects
during startup waits in the kernel backlog. The router starts only after every initial worker
reports completed startup through a one-byte pipe owned by that worker's own fork. A worker
replacement gets a fresh pipe and its predecessor's readiness never releases the barrier. A full
restart of the unit closes the configured port before the replacement process binds it again.
"""

from __future__ import annotations

import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from types import FrameType

from course_explorer.config import (
    embedding_configuration_for_site,
    load_normalization_settings,
    load_search_settings,
    load_web_settings,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context
from course_explorer.embeddings.provider import embedding_client
from course_explorer.embeddings.query_cache import SharedQueryEmbeddingCache
from course_explorer.next_courses.report_cache import NextCourseReportCache
from course_explorer.search.projection import build_lookup_projection
from course_explorer_web import worker
from course_explorer_web.dataset import SERVING_GENERATION_ENV, resolve_serving_dataset
from course_explorer_web.router import TERMINATE_SECONDS
from course_explorer_web.serving_cache import (
    PreloadedSharedCaches,
    ServingSettings,
    preload_serving_artifacts,
    set_preloaded_lookup_projection,
    set_preloaded_serving_settings,
    set_preloaded_shared_caches,
)

_POLL_SECONDS = 0.5
# The one-byte startup protocol: worker._ReadyServer.startup writes this byte to its own pipe.
_READY_BYTE = b"1"


def _listener(host: str, port: int) -> socket.socket:
    """Bind and listen on one TCP socket with the serving options."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Uvicorn's inherited-socket path does not enable NODELAY through asyncio here.
    listener.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    listener.bind((host, port))
    # Listening queues connections made before the child that serves the socket is ready.
    listener.listen(socket.SOMAXCONN)
    return listener


@dataclass
class _Role:
    """One supervised role: its name, its listening descriptor and its exits.

    A worker role carries its forked pid and its own readiness pipe. The router keeps its subprocess
    lifetime. A replacement never inherits its predecessor's readiness.
    """

    name: str
    listener: socket.socket
    process: subprocess.Popen[bytes] | None = None
    pid: int | None = None
    exits: deque[float] = field(default_factory=deque)
    requires_readiness: bool = False
    ready: bool = False
    readiness_fd: int | None = None


def _spawn(role: _Role, command: list[str], environment: dict[str, str]) -> None:
    """Start the router child on its inherited descriptors."""
    role.process = subprocess.Popen(
        command,
        pass_fds=(role.listener.fileno(),),
        env=environment,
        close_fds=True,
    )


def _fork_worker(role: _Role, environment: dict[str, str], roles: list[_Role]) -> None:
    """Fork one worker from the preloaded supervisor on its own listener and readiness pipe."""
    del environment  # The fork inherits the supervisor's environment.
    if role.readiness_fd is not None:
        os.close(role.readiness_fd)
        role.readiness_fd = None
    role.ready = False
    readiness_read, readiness_write = os.pipe()
    os.set_blocking(readiness_read, False)
    pid = os.fork()
    if pid == 0:
        try:
            os.close(readiness_read)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            for other in roles:
                if other is role:
                    continue
                if other.readiness_fd is not None:
                    os.close(other.readiness_fd)
                other.listener.close()
            worker.main(
                listener_fd=role.listener.fileno(),
                readiness_fd=readiness_write,
            )
        except BaseException:
            traceback.print_exc()
            os._exit(1)
        os._exit(0)
    os.close(readiness_write)
    role.pid = pid
    role.readiness_fd = readiness_read


def _read_readiness(role: _Role) -> None:
    """Mark a worker ready when its own pipe carries the readiness byte.

    An empty read means the child closed the pipe without reporting completed startup. That is
    not readiness, so the descriptor is released and exit supervision handles the process.
    """
    if role.readiness_fd is None:
        return
    try:
        byte = os.read(role.readiness_fd, 1)
    except BlockingIOError:
        return
    os.close(role.readiness_fd)
    role.readiness_fd = None
    if byte == _READY_BYTE:
        role.ready = True


def _exhausted(role: _Role, *, limit: int, window_seconds: int) -> bool:
    """Record one exit and report whether the role reached its exit limit inside the window."""
    now = time.monotonic()
    while role.exits and now - role.exits[0] >= window_seconds:
        role.exits.popleft()
    role.exits.append(now)
    return len(role.exits) >= limit


def _wait_worker(role: _Role) -> int | None:
    """Reap one exited worker and return its code, or ``None`` when it still runs."""
    if role.pid is None:
        return None
    try:
        pid, status = os.waitpid(role.pid, os.WNOHANG)
    except ChildProcessError:
        return 0
    if pid == 0:
        return None
    role.pid = None
    return os.waitstatus_to_exitcode(status)


def _stop(roles: list[_Role]) -> None:
    """Terminate the children, then kill the ones that outlive the wait."""
    for role in roles:
        if role.requires_readiness:
            if role.pid is not None:
                try:
                    os.kill(role.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        elif role.process is not None and role.process.poll() is None:
            role.process.terminate()
    deadline = time.monotonic() + TERMINATE_SECONDS
    for role in roles:
        if role.requires_readiness:
            if role.pid is None:
                continue
            while time.monotonic() < deadline:
                if _wait_worker(role) is not None:
                    break
                time.sleep(0.01)
            if role.pid is not None:
                try:
                    os.kill(role.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _wait_worker(role)
        elif role.process is not None and role.process.poll() is None:
            try:
                role.process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
    for role in roles:
        if role.process is not None and role.process.poll() is None:
            role.process.kill()


def _preload_lookup_projection(serving) -> None:
    """Build the lookup projection before any child starts and dispose the dataset engine."""
    with database_context(serving.settings) as factory:
        projection = build_lookup_projection(CurriculumRepository(factory))
    set_preloaded_lookup_projection(projection)


def _preload_shared_caches(settings, embeddings_enabled: bool) -> PreloadedSharedCaches:
    """Create the shared report and query embedding regions before any child starts.

    The query embedding region is created only when ``embeddings_enabled`` is true. That mode is the
    one the supervisor resolved, so this preload reads no switch.
    """
    caches = PreloadedSharedCaches(
        next_course_reports=NextCourseReportCache.create(
            settings.web_next_course_report_cache_bytes
        ),
        query_embeddings=(
            None
            if not embeddings_enabled
            else SharedQueryEmbeddingCache.create(settings.web_query_embedding_cache_bytes)
        ),
    )
    set_preloaded_shared_caches(caches)
    return caches


def main() -> int:
    """Preload the artifacts, projection and shared caches, fork the workers, then start the
    router.
    """
    # One generation value per serving supervisor is inherited by every child, so all of them
    # report the same dataset identity for this process lifetime.
    os.environ[SERVING_GENERATION_ENV] = secrets.token_hex(16)
    settings = load_web_settings()
    serving = resolve_serving_dataset()
    # The site's embedding switch is read once here, and the resolved configuration is passed to
    # the artifact opening and the settings bundle.
    embedding = embedding_configuration_for_site(settings)
    search_settings = load_search_settings()
    search_embedding_client = (
        None
        if embedding is None
        else embedding_client(
            embedding,
            timeout=search_settings.search_embedding_request_timeout_seconds,
        )
    )
    set_preloaded_serving_settings(
        ServingSettings(
            web=settings,
            search=search_settings,
            embedding=embedding,
            academic_year_start=load_normalization_settings().current_academic_year_start,
            dataset=serving,
            search_embedding_client=search_embedding_client,
        )
    )
    preload_serving_artifacts()
    _preload_lookup_projection(serving)
    shared_caches = _preload_shared_caches(settings, embedding is not None)
    public = _listener(settings.web_host, settings.web_port)
    workers = [_listener(settings.web_host, 0) for _ in range(settings.web_workers)]
    worker_ports = [listener.getsockname()[1] for listener in workers]
    router = _Role("router", public)
    router_command = [
        sys.executable,
        "-m",
        "course_explorer_web.router",
        str(public.fileno()),
        *(str(port) for port in worker_ports),
    ]
    worker_roles = [
        _Role(f"worker {index}", listener, requires_readiness=True)
        for index, listener in enumerate(workers, start=1)
    ]
    roles = [router, *worker_roles]
    environment = os.environ.copy()
    stopping = False

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        stopping = True

    previous = {
        signum: signal.signal(signum, request_stop) for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        for role in worker_roles:
            _fork_worker(role, environment, roles)
        while not stopping:
            for role in worker_roles:
                code = _wait_worker(role)
                if code is None:
                    continue
                if stopping:
                    return 0
                if _exhausted(
                    role,
                    limit=settings.web_respawn_exit_limit,
                    window_seconds=settings.web_respawn_window_seconds,
                ):
                    print(
                        f"web supervisor: {role.name} exited with code {code} "
                        "too often; stopping the unit",
                        file=sys.stderr,
                        flush=True,
                    )
                    return code if code else 1
                _fork_worker(role, environment, roles)
                print(
                    f"web supervisor: {role.name} exited with code {code}; starting a replacement",
                    file=sys.stderr,
                    flush=True,
                )
            if router.process is not None:
                code = router.process.poll()
                if code is not None:
                    if stopping:
                        return 0
                    if _exhausted(
                        router,
                        limit=settings.web_respawn_exit_limit,
                        window_seconds=settings.web_respawn_window_seconds,
                    ):
                        print(
                            f"web supervisor: {router.name} exited with code {code} "
                            "too often; stopping the unit",
                            file=sys.stderr,
                            flush=True,
                        )
                        return code if code else 1
                    _spawn(router, router_command, environment)
                    print(
                        f"web supervisor: {router.name} exited with code {code}; "
                        "starting a replacement",
                        file=sys.stderr,
                        flush=True,
                    )
            for role in worker_roles:
                _read_readiness(role)
            if (
                not stopping
                and router.process is None
                and all(worker.ready for worker in worker_roles)
            ):
                _spawn(router, router_command, environment)
            time.sleep(_POLL_SECONDS)
        return 0
    finally:
        _stop(roles)
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        public.close()
        for listener in workers:
            listener.close()
        for role in roles:
            if role.readiness_fd is not None:
                os.close(role.readiness_fd)
                role.readiness_fd = None
        if search_embedding_client is not None:
            search_embedding_client.close()
        shared_caches.close()


if __name__ == "__main__":
    raise SystemExit(main())
