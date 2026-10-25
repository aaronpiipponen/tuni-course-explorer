"""Supervise one front router and its configured worker processes on loopback sockets.

The supervisor owns every listening socket for its whole life: the public listener and one
ephemeral loopback listener per worker. A child exit starts a replacement for that role on the
same descriptor, so the port never changes and the other children keep serving. When one role
exits the configured number of times inside the configured window, the supervisor stops every
child and returns nonzero for systemd's ``Restart=on-failure``. SIGTERM and SIGINT stop every
child and return zero without a replacement. No request is replayed, a replacement router starts
with fresh admission state, and only the exited process's in-flight requests fail.

The public listener accepts connections from the moment it binds, so a client that connects
during startup waits in the kernel backlog. The router starts only after every initial worker
reports completed startup through a one-byte pipe owned by that worker's own spawn. A worker
replacement gets a fresh pipe and its predecessor's readiness never releases the barrier. A full
restart of the unit closes the public port before the replacement process binds it again.
"""

from __future__ import annotations

import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from types import FrameType

from course_explorer.config import load_web_settings
from course_explorer_web.dataset import SERVING_GENERATION_ENV
from course_explorer_web.router import TERMINATE_SECONDS

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
    """One supervised role: its name, its listening descriptor, its command and its exits.

    A role that requires readiness carries its own readiness state and the read end of the pipe its
    own spawn created, so a replacement never inherits its predecessor's readiness.
    """

    name: str
    listener: socket.socket
    command: list[str]
    process: subprocess.Popen[bytes] | None = None
    exits: deque[float] = field(default_factory=deque)
    requires_readiness: bool = False
    ready: bool = False
    readiness_fd: int | None = None


def _spawn(role: _Role, environment: dict[str, str]) -> None:
    """Start one child on the role's own inherited descriptors.

    A worker role receives a fresh readiness pipe as its last argument and only that pipe's write
    end and its listener. The parent keeps the read end nonblocking and reads it in the supervision
    loop. A spawn failure leaves the role without a readiness descriptor and propagates.
    """
    command = role.command
    pass_fds = [role.listener.fileno()]
    readiness_read: int | None = None
    readiness_write: int | None = None
    if role.requires_readiness:
        if role.readiness_fd is not None:
            os.close(role.readiness_fd)
            role.readiness_fd = None
        role.ready = False
        readiness_read, readiness_write = os.pipe()
        os.set_blocking(readiness_read, False)
        command = [*role.command, str(readiness_write)]
        pass_fds.append(readiness_write)
    try:
        role.process = subprocess.Popen(
            command,
            pass_fds=tuple(pass_fds),
            env=environment,
            close_fds=True,
        )
    except BaseException:
        if readiness_read is not None:
            os.close(readiness_read)
        raise
    finally:
        if readiness_write is not None:
            os.close(readiness_write)
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


def _stop(roles: list[_Role]) -> None:
    """Terminate the children, then kill the ones that outlive the wait."""
    children = [role.process for role in roles if role.process is not None]
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + TERMINATE_SECONDS
    for child in children:
        if child.poll() is None:
            try:
                child.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
    for child in children:
        if child.poll() is None:
            child.kill()


def main() -> int:
    """Start the worker children, then the router once every worker reports startup.

    The parent keeps the public listener and one ephemeral loopback listener per worker open for
    its whole life, passes each descriptor to its child and starts a replacement for a role that
    exits. One serving generation value reaches every child, and a replacement inherits it, so the
    reported dataset identity covers one supervisor lifetime. A worker reports completed startup
    through the write end of the pipe its own spawn created. The router starts after every worker
    reports readiness, and its exit handling matches the workers'. A crash loop stops every child
    and returns nonzero, which the unit's restart policy handles. A termination signal stops every
    child and returns zero.
    """
    settings = load_web_settings()
    # One generation value per serving supervisor is inherited by every child, so all of them
    # report the same dataset identity for this process lifetime.
    os.environ[SERVING_GENERATION_ENV] = secrets.token_hex(16)
    public = _listener(settings.web_host, settings.web_port)
    workers = [_listener(settings.web_host, 0) for _ in range(settings.web_workers)]
    worker_ports = [listener.getsockname()[1] for listener in workers]
    router = _Role(
        "router",
        public,
        [
            sys.executable,
            "-m",
            "course_explorer_web.router",
            str(public.fileno()),
            *(str(port) for port in worker_ports),
        ],
    )
    worker_roles = [
        _Role(
            f"worker {index}",
            listener,
            [
                sys.executable,
                "-m",
                "course_explorer_web.worker",
                str(listener.fileno()),
            ],
            requires_readiness=True,
        )
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
            _spawn(role, environment)
        while not stopping:
            for role in roles:
                if role.process is None:
                    continue
                code = role.process.poll()
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
                _spawn(role, environment)
                print(
                    f"web supervisor: {role.name} exited with code {code}; starting a replacement",
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
                _spawn(router, environment)
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


if __name__ == "__main__":
    raise SystemExit(main())
