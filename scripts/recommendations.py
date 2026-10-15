"""Machine-readable whole-basis course recommendations and complete next-course results.

Usage::
    uv run python scripts/recommendations.py --completed COMP.CS.100 --mode at_least_one --display-language en
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from course_explorer.recommendations.commands import run_recommendations_command


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one recommendation request, delegate once, and print one JSON line."""
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
    report = run_recommendations_command(
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
