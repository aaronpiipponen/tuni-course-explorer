"""Validated machine configuration for the serving load tooling.

The file holds the disposable stack's loopback bind and container values and the k6 load client's
host, paths and SSH local forward. The tool refuses a missing or incomplete file and a non-loopback
stack address rather than guessing a machine value.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

SYNTHETIC_DATABASE_PASSWORD = "synthetic-measure-password"


@dataclass(frozen=True)
class StackConfig:
    """One disposable stack's bind, database, embedding and cgroup values."""

    web_host: str
    web_port: int
    web_workers: int
    web_memory_mib: int
    database_host: str
    database_port: int
    database_user: str
    embedding_host: str
    embedding_port: int
    database_container: str
    embedding_container: str
    cpu_cgroup_root: Path
    memory_cgroup_root: Path

    @property
    def database_password(self) -> str:
        """Return the disposable cluster's password, overridable by one process value."""
        return os.environ.get("TCE_LOAD_DATABASE_PASSWORD") or SYNTHETIC_DATABASE_PASSWORD


@dataclass(frozen=True)
class WorkerConfig:
    """The k6 client host, its paths and the SSH local forward it opens to the stack."""

    host: str
    user: str
    directory: str
    k6: str
    tunnel_host: str
    tunnel_user: str
    tunnel_port: int
    forward_port: int

    @property
    def target_base_url(self) -> str:
        """Return the loopback address the client reaches through its own forward."""
        return f"http://127.0.0.1:{self.forward_port}"


@dataclass(frozen=True)
class MachineConfig:
    """The stack and worker sections of one machine configuration file."""

    stack: StackConfig
    worker: WorkerConfig


def load_machine_config(path: Path) -> MachineConfig:
    """Load and validate one machine configuration file."""
    if not path.is_file():
        raise ValueError(f"machine configuration file is missing: {path}")
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    stack = document.get("stack")
    worker = document.get("worker")
    if not isinstance(stack, dict):
        raise ValueError("the machine configuration is missing its [stack] section")
    if not isinstance(worker, dict):
        raise ValueError("the machine configuration is missing its [worker] section")
    required_stack = (
        "web_host",
        "web_port",
        "web_workers",
        "web_memory_mib",
        "database_host",
        "database_port",
        "database_user",
        "embedding_host",
        "embedding_port",
        "database_container",
        "embedding_container",
        "cpu_cgroup_root",
        "memory_cgroup_root",
    )
    missing = [key for key in required_stack if key not in stack]
    if missing:
        raise ValueError(f"the [stack] section is missing {missing}")
    required_worker = (
        "host",
        "user",
        "directory",
        "k6",
        "tunnel_host",
        "tunnel_user",
        "tunnel_port",
        "forward_port",
    )
    missing = [key for key in required_worker if key not in worker]
    if missing:
        raise ValueError(f"the [worker] section is missing {missing}")
    for key in ("web_host", "database_host", "embedding_host"):
        if str(stack[key]) != "127.0.0.1":
            raise ValueError(f"{key} must be 127.0.0.1")
    for key in ("web_port", "database_port", "embedding_port"):
        port = int(stack[key])
        if not 1 <= port <= 65535:
            raise ValueError(f"{key} is not a TCP port")
    if not 1 <= int(worker["forward_port"]) <= 65535:
        raise ValueError("forward_port is not a TCP port")
    if not 1 <= int(worker["tunnel_port"]) <= 65535:
        raise ValueError("tunnel_port is not a TCP port")
    if int(stack["web_workers"]) < 1:
        raise ValueError("web_workers must be at least 1")
    if int(stack["web_memory_mib"]) < 512:
        raise ValueError("web_memory_mib must be at least 512")
    return MachineConfig(
        stack=StackConfig(
            web_host=str(stack["web_host"]),
            web_port=int(stack["web_port"]),
            web_workers=int(stack["web_workers"]),
            web_memory_mib=int(stack["web_memory_mib"]),
            database_host=str(stack["database_host"]),
            database_port=int(stack["database_port"]),
            database_user=str(stack["database_user"]),
            embedding_host=str(stack["embedding_host"]),
            embedding_port=int(stack["embedding_port"]),
            database_container=str(stack["database_container"]),
            embedding_container=str(stack["embedding_container"]),
            cpu_cgroup_root=Path(stack["cpu_cgroup_root"]),
            memory_cgroup_root=Path(stack["memory_cgroup_root"]),
        ),
        worker=WorkerConfig(
            host=str(worker["host"]),
            user=str(worker["user"]),
            directory=str(worker["directory"]),
            k6=str(worker["k6"]),
            tunnel_host=str(worker["tunnel_host"]),
            tunnel_user=str(worker["tunnel_user"]),
            tunnel_port=int(worker["tunnel_port"]),
            forward_port=int(worker["forward_port"]),
        ),
    )
