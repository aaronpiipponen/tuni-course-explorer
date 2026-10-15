"""Course comparison: two courses' summaries, similarity meters and verdict as one JSON report.

Usage:
    uv run python scripts/compare_courses.py <canonical-id-or-code> <canonical-id-or-code>

The script is an adapter over `course_explorer.comparison.commands.run_course_comparison_command`
and prints exactly one JSON report line carrying both shared official course summaries, the
overall/content/outcome percentage meters, the two directional overlap percentages and the
config-derived verdict. Each input is a canonical group id or an exact official code. An unknown or
ambiguous input fails loudly. It is read-only and runs in-process: participants are chosen through
search, and an explicitly chosen inactive course is visible.
"""

import argparse
from collections.abc import Sequence

from course_explorer.comparison.commands import run_course_comparison_command


def main(argv: Sequence[str] | None = None) -> int:
    """Parse two course identities, delegate once, and print one JSON report line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_a")
    parser.add_argument("course_b")
    args = parser.parse_args(argv)
    report = run_course_comparison_command(args.course_a, args.course_b)
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
