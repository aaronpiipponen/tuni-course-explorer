"""Course comparison: two courses' summaries, similarity meters and verdict as one JSON report.

Usage:
    uv run python scripts/compare_courses.py <canonical-id-or-code> <canonical-id-or-code>

The script is an adapter over `course_explorer.comparison.commands.run_course_comparison_command`
and prints exactly one JSON report line carrying both shared official course summaries, the
overall/content/outcome percentage meters, the two directional overlap percentages and the
config-derived verdict. It opens the serving artifact set for the site's embedding switch and passes
the hub pair of the family's embedding directory to the command. A site with the embedding features
off fails with the build guidance. Each input is a canonical group id or an exact official code. An
unknown or ambiguous input fails loudly. It is read-only and runs in-process: participants are
chosen through search, and an explicitly chosen inactive course is visible.
"""

import argparse
from collections.abc import Sequence

from _checkout_source import install


def main(argv: Sequence[str] | None = None) -> int:
    """Parse two course identities, delegate once, and print one JSON report line."""
    install()
    from course_explorer.comparison.commands import run_course_comparison_command
    from course_explorer.config import (
        embedding_configuration_for_site,
        load_database_settings,
        load_web_settings,
    )
    from course_explorer.serving_artifacts import ServingArtifacts

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_a")
    parser.add_argument("course_b")
    args = parser.parse_args(argv)
    settings = load_database_settings()
    embedding = embedding_configuration_for_site(load_web_settings())
    embeddings = ServingArtifacts.open(settings, embedding=embedding).embedding_reads()
    report = run_course_comparison_command(
        args.course_a,
        args.course_b,
        database_settings=settings,
        embedding_settings=embedding,
        hub=embeddings.hubs[0],
        outcomes_hub=embeddings.hubs[1],
    )
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
