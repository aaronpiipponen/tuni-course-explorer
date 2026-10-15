"""Machine-readable prerequisite graph or minimum-new-credit route for one official course.

Usage:
    uv run python scripts/prerequisites.py COMP.CS.500
    uv run python scripts/prerequisites.py COMP.CS.500 --completed COMP.CS.100
    uv run python scripts/prerequisites.py COMP.CS.500 --completed COMP.CS.100 --completed MATH.1
    uv run python scripts/prerequisites.py COMP.CS.500 --include-recommended --include-inferred
    uv run python scripts/prerequisites.py COMP.CS.500 --active-only
    uv run python scripts/prerequisites.py COMP.CS.500 --selected COMP.CS.100
    uv run python scripts/prerequisites.py COMP.CS.500 --selected COMP.CS.100 --basis selected
    uv run python scripts/prerequisites.py COMP.CS.500 --excluded COMP.CS.100
    uv run python scripts/prerequisites.py COMP.CS.500 --route

Inputs may be canonical group IDs (which take precedence) or exact official course codes. The script
is an adapter over `course_explorer.prerequisite.commands` and prints exactly one JSON result
line for the one operation it dispatches. By default it prints the graph report with the authoritative
calculation tree and the minimized drawing graph. `--route` prints the minimum-new-credit result
instead: the exact-default route, or an explicitly marked approximate route, or
`approximation_failed` with a `search_too_large` root problem, and no drawing graph. Defaults are
required official prerequisites only. `--include-recommended` and `--include-inferred` independently
add their category to both the graph and the calculation. An inlined official module or degree
prerequisite is reported as one graph node identified by its canonical `group_id` and selected
version, with its official member course cards in the graph's module-node list. Its inlined rule drives
the calculation. The default activity scope is all courses. `--active-only` hides
unretained inactive graph courses and excludes them from route candidates. `--completed` courses form
the default calculation basis. `--basis selected` computes from the retained `--selected` display set
instead, and without `--selected` it uses the completed set. Each repeatable `--excluded` code stays
visible as its ordinary graph course node or as a module member card, while the canonical exclusion
blocks the calculation from routing through or charging it, even when it is completed or
selected: a required branch with no other usable route yields `no_solution` and reports the excluded
courses that blocked it. Excluding the opened root blocks the whole request with a located
`no_solution`. Graph-only completion and exclusion flags also apply to non-course nodes, without
changing shared course completion state. It is read-only and runs in-process.
"""

import argparse
from collections.abc import Sequence

from course_explorer.prerequisite.commands import (
    run_minimum_route_command,
    run_prerequisite_command,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one course and its options, delegate once, and print one JSON report line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_code")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--selected", action="append", default=[])
    parser.add_argument("--excluded", action="append", default=[])
    parser.add_argument("--completed-node", action="append", default=[])
    parser.add_argument("--excluded-node", action="append", default=[])
    parser.add_argument("--include-recommended", action="store_true")
    parser.add_argument("--include-inferred", action="store_true")
    parser.add_argument("--active-only", action="store_true")
    parser.add_argument("--basis", choices=("completed", "selected"), default="completed")
    parser.add_argument(
        "--route",
        action="store_true",
        help="print the minimum-new-credit route result instead of the graph report",
    )
    args = parser.parse_args(argv)
    options = {
        "completed_codes": args.completed,
        "selected_codes": args.selected,
        "excluded_codes": args.excluded,
        "include_recommended": args.include_recommended,
        "include_inferred": args.include_inferred,
        "active_only": args.active_only,
        "basis": args.basis,
        "completed_node_keys": args.completed_node,
        "excluded_node_keys": args.excluded_node,
    }
    if args.route:
        print(run_minimum_route_command(args.course_code, **options).model_dump_json())
    else:
        print(run_prerequisite_command(args.course_code, **options).model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
