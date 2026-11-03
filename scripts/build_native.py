"""Build the native libraries in the matched container image and copy them into ``native/``.

Usage::

    ./.venv/bin/python scripts/build_native.py [--non-interactive] [--fixtures]

``--non-interactive`` passes ``-n`` to sudo, so sudo never prompts for a credential and a caller
without a cached one fails. ``--fixtures`` adds the test-only fixture library
``libcourse_prerequisite_fixtures.so``. The default builds only the three serving libraries.

The build runs in ``docker/native/Dockerfile``, so the host needs no compiler, libpq headers or
PostgreSQL server headers. The script builds into the ``native/`` directory of the checkout that
contains it, derived from the script's own path, so a copy built with a shared virtual environment
writes only into that copy. It writes ``native/libcourse_recommendation.so``,
``native/libcourse_prerequisite.so`` and ``native/libcourse_lookup.so``, plus the fixture library
when requested. It stages every produced output before replacing any. A build that produces no
library changes nothing. Each staged library is then replaced independently, so a failed
replacement can leave the libraries replaced before it in place.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

LIBRARIES = (
    "libcourse_recommendation.so",
    "libcourse_prerequisite.so",
    "libcourse_lookup.so",
)
FIXTURE_LIBRARIES = ("libcourse_prerequisite_fixtures.so",)
CHECKOUT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    """Build the native libraries and copy the produced shared objects into ``native/``."""
    parser = argparse.ArgumentParser(description="Build the native serving libraries.")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="pass -n to sudo, so a missing cached credential fails instead of prompting",
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="also build the test-only prerequisite fixture library",
    )
    args = parser.parse_args(argv)
    sudo = ("sudo", "-n") if args.non_interactive else ("sudo",)
    names = LIBRARIES + (FIXTURE_LIBRARIES if args.fixtures else ())
    make_targets = "all fixtures" if args.fixtures else "all"
    root = CHECKOUT
    target = root / "native"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="course-explorer-native-") as directory:
        subprocess.run(
            (
                *sudo,
                "docker",
                "build",
                "--target",
                "output",
                "--build-arg",
                f"NATIVE_TARGETS={make_targets}",
                "--output",
                f"type=local,dest={directory}",
                "-f",
                str(root / "docker" / "native" / "Dockerfile"),
                str(root),
            ),
            check=True,
        )
        produced = tuple(Path(directory) / name for name in names)
        missing = [path.name for path in produced if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"native build did not produce {', '.join(missing)}; installed libraries stay"
            )
        staged: list[tuple[Path, Path]] = []
        try:
            for source, name in zip(produced, names, strict=True):
                temporary = target / f"{name}.tmp"
                shutil.copyfile(source, temporary)
                staged.append((temporary, target / name))
            for temporary, destination in staged:
                temporary.replace(destination)
        finally:
            for temporary, _destination in staged:
                temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
