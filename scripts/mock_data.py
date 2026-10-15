"""One-shot import and artifact writer for the fictional served mock dataset.

Usage:
    uv run python scripts/mock_data.py load-curriculum
    uv run python scripts/mock_data.py load
    uv run python scripts/mock_data.py write-artifacts --hubs-dir config/derived

This adapter parses one action and delegates once to
``course_explorer.mock_data.run_mock_data_command``. ``load-curriculum``
imports the fixture, ``load`` additionally imports the bundled fixture vectors, and
``write-artifacts`` writes the bundled vectors and both computed hub means from the real stored
compatible vectors.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from course_explorer.mock_data import run_mock_data_command


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one action and options, delegate once, and print one content-safe count report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["load-curriculum", "load", "write-artifacts"])
    parser.add_argument("--fixture-dir", type=Path, default=Path("data/mock"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/mock-import"))
    parser.add_argument("--hubs-dir", type=Path, default=Path("config/derived"))
    args = parser.parse_args(argv)
    report = run_mock_data_command(
        args.action,
        fixture_dir=args.fixture_dir,
        raw_root=args.raw_root,
        hubs_dir=args.hubs_dir,
    )
    if report is not None:
        print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
