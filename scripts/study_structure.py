"""Official structure of studies: one programme/module's typed rule tree as one JSON report.

Usage:
    uv run python scripts/study_structure.py <group_id-from-module-lookup>
"""

import argparse
from collections.abc import Sequence

from course_explorer.study_structure.commands import run_study_structure_command


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one canonical root identity, delegate once, and print one JSON report line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root_group_id")
    args = parser.parse_args(argv)
    report = run_study_structure_command(args.root_group_id)
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
