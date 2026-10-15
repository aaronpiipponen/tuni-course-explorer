"""Unified single-query course search across exact code, substring, fuzzy name, and semantic match.

Usage:
    uv run python scripts/search.py "COMP.CS" --display-language fi
    uv run python scripts/search.py "lineaarialgeba" --display-language fi
    uv run python scripts/search.py "tensorit" --display-language fi
    uv run python scripts/search.py "tensorit" --display-language en --semantic-min-score 0.42
    uv run python scripts/search.py "COMP.CS" --display-language fi --active-only
"""

import argparse
from collections.abc import Sequence
from typing import get_args

from course_explorer.search.commands import run_search_command
from course_explorer.search.lookup import DisplayLanguage


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one query and options, delegate once, and print one JSON report line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--display-language", choices=get_args(DisplayLanguage), required=True)
    parser.add_argument("--semantic-min-score", type=float, default=None)
    parser.add_argument("--fuzzy-min-score", type=float, default=None)
    parser.add_argument("--active-only", action="store_true")
    args = parser.parse_args(argv)
    report = run_search_command(
        args.query,
        display_language=args.display_language,
        semantic_min_score=args.semantic_min_score,
        fuzzy_min_score=args.fuzzy_min_score,
        include_inactive=not args.active_only,
    )
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
