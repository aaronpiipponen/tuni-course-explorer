"""Enter the run's cgroups before the serving supervisor creates any worker.

Usage:
    python tools/load/_bootstrap.py

Environment:
    TCE_LOAD_CHECKOUT       the disposable checkout that holds the product package
    TCE_LOAD_CPU_CGROUP     the CPU cgroup directory that receives this process
    TCE_LOAD_MEMORY_CGROUP  the memory cgroup directory that receives this process

The launcher starts this script with those variables set. The module writes its own process
identifier into both controllers and only then imports the product entry point, so every fork of
the supervisor inherits the enforcement.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    """Move this process into its cgroups and run the product supervisor."""
    checkout = Path(os.environ["TCE_LOAD_CHECKOUT"])
    for name in ("TCE_LOAD_CPU_CGROUP", "TCE_LOAD_MEMORY_CGROUP"):
        (Path(os.environ[name]) / "cgroup.procs").write_text(str(os.getpid()), encoding="utf-8")
    sys.path.insert(0, str(checkout / "src"))
    from course_explorer_web.__main__ import main as serve

    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
