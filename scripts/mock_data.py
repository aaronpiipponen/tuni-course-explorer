"""One-shot import and artifact writer for the fictional example dataset.

Usage:
    uv run python scripts/mock_data.py load-curriculum
    uv run python scripts/mock_data.py load
    uv run python scripts/mock_data.py write-artifacts
    uv run python scripts/mock_data.py write-bundle

This adapter parses one action and delegates once to
``course_explorer.mock_data.run_mock_data_command``. ``load-curriculum``
imports the fixture, ``load`` additionally imports the bundled fixture vectors, and
``write-artifacts`` builds the serving artifact set for the site's embedding switch.
``write-bundle`` regenerates the tracked bundled vectors as explicit fixture maintenance. It is not
part of any build or deploy path. The adapter loads the package of the checkout that contains it, so
a copy writes only into that copy.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from _checkout_source import install


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one action and options, delegate once, and print the returned content-safe report.

    ``write-bundle`` returns no report, so that action prints nothing.
    """
    install()
    from course_explorer.mock_data import run_mock_data_command

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["load-curriculum", "load", "write-artifacts", "write-bundle"]
    )
    parser.add_argument("--fixture-dir", type=Path, default=Path("data/mock"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/mock-import"))
    args = parser.parse_args(argv)
    report = run_mock_data_command(
        args.action,
        fixture_dir=args.fixture_dir,
        raw_root=args.raw_root,
    )
    if report is not None:
        print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
