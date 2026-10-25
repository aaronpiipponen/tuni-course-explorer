"""Minimal official catalogue: canonical courses and eligible module identities as one JSON report.

Usage:
    uv run python scripts/catalogue.py
"""

import argparse
from collections.abc import Sequence

from course_explorer.search.lookup_commands import run_catalogue_command


def main(argv: Sequence[str] | None = None) -> int:
    """Parse no arguments, delegate once, and print one JSON report line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    report = run_catalogue_command()
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
