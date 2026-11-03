"""Unified single-query course search across exact code, substring, fuzzy name, and semantic match.

Usage:
    uv run python scripts/search.py "COMP.CS" --display-language fi
    uv run python scripts/search.py "lineaarialgeba" --display-language fi
    uv run python scripts/search.py "tensorit" --display-language fi
    uv run python scripts/search.py "tensorit" --display-language en --semantic-min-score 0.42
    uv run python scripts/search.py "COMP.CS" --display-language fi --active-only

Arguments:
    query                        the query text.
Options:
    --display-language {fi,en}   the language of the official names the search compares.
    --semantic-min-score SCORE   hub-centred cosine floor for semantic matches, -1 to 1.
    --fuzzy-min-score SCORE      fuzzy name score floor, 0 to 100.
    --active-only                restrict the results to active courses.
"""

import argparse
from collections.abc import Sequence
from typing import get_args

from _checkout_source import install


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one query and options, delegate once, and print one JSON report line."""
    install()
    from course_explorer.config import (
        embedding_configuration_for_site,
        load_database_settings,
        load_web_settings,
    )
    from course_explorer.curriculum_repository import CurriculumRepository
    from course_explorer.db.session import database_context
    from course_explorer.search.commands import run_search_command
    from course_explorer.search.lookup import DisplayLanguage
    from course_explorer.search.projection import build_lookup_projection
    from course_explorer.serving_artifacts import ServingArtifacts

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--display-language", choices=get_args(DisplayLanguage), required=True)
    parser.add_argument("--semantic-min-score", type=float, default=None)
    parser.add_argument("--fuzzy-min-score", type=float, default=None)
    parser.add_argument("--active-only", action="store_true")
    args = parser.parse_args(argv)
    settings = load_database_settings()
    embedding = embedding_configuration_for_site(load_web_settings())
    artifacts = ServingArtifacts.open(settings, embedding=embedding)
    embeddings = artifacts.embeddings
    with database_context(settings) as factory:
        projection = build_lookup_projection(CurriculumRepository(factory))
        report = run_search_command(
            args.query,
            display_language=args.display_language,
            semantic_min_score=args.semantic_min_score,
            fuzzy_min_score=args.fuzzy_min_score,
            include_inactive=not args.active_only,
            include_semantic=embeddings is not None,
            database_settings=settings,
            embedding_settings=embedding,
            hub=None if embeddings is None else embeddings.hubs[0],
            projection=projection,
            search_group_count=(None if embeddings is None else embeddings.search.group_count),
            session_factory=factory,
        )
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
