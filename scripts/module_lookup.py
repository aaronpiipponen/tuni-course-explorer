"""Programme/module narrowing lookup: uncapped case-insensitive substring over a displayed name or code.

Usage:
    uv run python scripts/module_lookup.py "tietotekni" --display-language fi
"""

import argparse
from collections.abc import Sequence
from typing import get_args

from course_explorer.search.lookup import DisplayLanguage
from course_explorer.search.lookup_commands import run_module_lookup_command


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one query and locale, delegate once, and print one JSON report line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--display-language", choices=get_args(DisplayLanguage), required=True)
    args = parser.parse_args(argv)
    report = run_module_lookup_command(args.query, display_language=args.display_language)
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
