"""Machine-readable "What Can I Study Next?" discovery for a selected/completed course basis.

Usage:
    uv run python scripts/next_courses.py --completed COMP.CS.100 --display-language en
    uv run python scripts/next_courses.py --completed COMP.CS.100 --mode at_least_one --display-language fi
    uv run python scripts/next_courses.py --selected COMP.CS.100 --selected COMP.CS.110 --basis selected --display-language en
    uv run python scripts/next_courses.py --completed COMP.CS.100 --include-inferred --all-courses --display-language en

The script is an adapter over `course_explorer.next_courses.commands.run_next_courses_command`
and prints exactly one JSON report line. `--selected`/`--completed` accept canonical group IDs or
exact official codes. Without `--selected` the completed set is also the selected set, and
`--basis selected` then uses it. The default basis is the completed subset, the default mode is
`all`, and the default activity scope is active courses only (`--all-courses` returns inactive
courses labelled). `--include-inferred` lets accepted inferred prerequisites participate exactly
like official ones. Every listed course has at least one enabled prerequisite. The proposal omits
basis courses. The command is read-only and runs in-process.
"""

import argparse
from collections.abc import Sequence

from course_explorer.next_courses.commands import run_next_courses_command


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one discovery request, delegate once, and print one JSON report line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected", action="append", default=[])
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--basis", choices=("completed", "selected"), default="completed")
    parser.add_argument("--mode", choices=("all", "at_least_one"), default="all")
    parser.add_argument("--display-language", choices=("fi", "en"), required=True)
    parser.add_argument("--include-inferred", action="store_true")
    activity = parser.add_mutually_exclusive_group()
    activity.add_argument("--active-only", dest="active_only", action="store_true")
    activity.add_argument("--all-courses", dest="active_only", action="store_false")
    parser.set_defaults(active_only=True)
    args = parser.parse_args(argv)
    report = run_next_courses_command(
        selected_courses=args.selected,
        completed_courses=args.completed,
        basis=args.basis,
        mode=args.mode,
        display_language=args.display_language,
        include_inferred=args.include_inferred,
        active_only=args.active_only,
    )
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
