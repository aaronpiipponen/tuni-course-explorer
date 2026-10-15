"""Unified command and CLI contracts for course search."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from course_explorer.config import SearchSettings
from course_explorer.db import session as session_module
from course_explorer.search import commands as command_module
from tests.support import settings_factory

_CLI_SPEC = importlib.util.spec_from_file_location(
    "search", Path(__file__).parents[2] / "scripts" / "search.py"
)
assert _CLI_SPEC is not None and _CLI_SPEC.loader is not None
_CLI_MODULE = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(_CLI_MODULE)


def search_settings(semantic: float | str = "0.40", fuzzy: float | str = "80") -> SearchSettings:
    """Build the full required search policy used by composition tests."""
    return settings_factory(
        SearchSettings,
        SEMANTIC_SEARCH_MIN_SCORE=str(semantic),
        FUZZY_SEARCH_MIN_SCORE=str(fuzzy),
    )


def test_unified_search_command_wires_both_services_disposes_engine_and_reports_policy(
    monkeypatch,
) -> None:
    """One engine/provider, both composed services, one unified call, and the actual report policy."""
    engine = type(
        "Engine", (), {"disposed": False, "dispose": lambda self: setattr(self, "disposed", True)}
    )()
    factory = object()
    settings = search_settings(semantic="0.45", fuzzy="70")
    calls: list[tuple] = []

    class Lookup:
        def __init__(self, curriculum, search_settings):
            calls.append(("lookup", curriculum, search_settings))

    class Semantic:
        def __init__(self, curriculum, repository, provider, embedding_settings, search_settings):
            calls.append(("semantic", curriculum, repository, provider, search_settings))

    class Unified:
        def __init__(self, curriculum, semantic_search, course_lookup, search_settings):
            calls.append(("unified", curriculum, semantic_search, course_lookup, search_settings))

        def search(self, query, **kwargs):
            calls.append(("unified-search", query, kwargs))
            return ()

    class Repository:
        def __init__(self, value):
            calls.append(("repository", value))

    class Provider:
        def __init__(self, settings):
            calls.append(("provider", settings))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(command_module, "load_database_settings", lambda: object())
    monkeypatch.setattr(command_module, "load_embedding_settings", lambda: "embedding-settings")
    monkeypatch.setattr(command_module, "load_search_settings", lambda: settings)
    monkeypatch.setattr(session_module, "create_database_engine", lambda value: engine)
    monkeypatch.setattr(session_module, "create_session_factory", lambda value: factory)
    monkeypatch.setattr(command_module, "CurriculumRepository", lambda value: "curriculum")
    monkeypatch.setattr(command_module, "SemanticSearchRepository", Repository)
    monkeypatch.setattr(command_module, "EmbeddingProvider", Provider)
    monkeypatch.setattr(command_module, "CourseLookupService", Lookup)
    monkeypatch.setattr(command_module, "CourseSearchService", Semantic)
    monkeypatch.setattr(command_module, "UnifiedCourseSearchService", Unified)

    report = command_module.run_search_command("tensorit", display_language="fi")

    assert report.display_language == "fi"
    assert report.semantic_min_score == 0.45
    assert report.fuzzy_min_score == 70
    assert report.include_inactive is True
    assert report.tier_priority == settings.search_tier_priority
    assert report.results == ()
    assert ("repository", factory) in calls
    assert ("provider", "embedding-settings") in calls
    assert ("lookup", "curriculum", settings) in calls
    assert (
        "unified-search",
        "tensorit",
        {
            "display_language": "fi",
            "semantic_min_score": None,
            "fuzzy_min_score": None,
            "include_inactive": True,
        },
    ) in calls
    semantic_call = next(entry for entry in calls if entry[0] == "semantic")
    assert isinstance(semantic_call[3], Provider)
    assert semantic_call[4] is settings
    unified_call = next(entry for entry in calls if entry[0] == "unified")
    assert unified_call[1] == "curriculum"
    assert isinstance(unified_call[2], Semantic)
    assert isinstance(unified_call[3], Lookup)
    assert unified_call[4] is settings
    assert engine.disposed

    calls.clear()
    engine.disposed = False
    override = command_module.run_search_command(
        "tensorit",
        display_language="en",
        semantic_min_score=0.25,
        fuzzy_min_score=90,
        include_inactive=False,
    )
    assert override.semantic_min_score == 0.25
    assert override.fuzzy_min_score == 90
    assert override.include_inactive is False
    assert (
        "unified-search",
        "tensorit",
        {
            "display_language": "en",
            "semantic_min_score": 0.25,
            "fuzzy_min_score": 90,
            "include_inactive": False,
        },
    ) in calls
    assert engine.disposed

    # Invalid input is refused at the one public boundary before any settings or I/O. Reaching the
    # embedding settings load here would fail the test.
    calls.clear()
    monkeypatch.setattr(
        command_module, "load_embedding_settings", lambda: pytest.fail("settings load reached")
    )
    with pytest.raises(ValueError):
        command_module.run_search_command("   ", display_language="fi")
    with pytest.raises(ValueError):
        command_module.run_search_command("tensorit", display_language="fi", semantic_min_score=1.5)
    with pytest.raises(ValueError):
        command_module.run_search_command("tensorit", display_language="fi", fuzzy_min_score=101)
    assert calls == []


def test_search_cli_forwards_options_and_prints_one_report(monkeypatch, capsys) -> None:
    """CLI delegates once to the unified command, requires locale, and prints one unified report."""
    expected = command_module.UnifiedSearchReport(
        display_language="fi",
        semantic_min_score=0.40,
        fuzzy_min_score=80,
        include_inactive=True,
        tier_priority=("exact_code", "substring", "fuzzy_name", "semantic"),
        results=(),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        _CLI_MODULE,
        "run_search_command",
        lambda query, **kwargs: calls.append({"query": query, **kwargs}) or expected,
    )

    assert _CLI_MODULE.main(["COMP.CS", "--display-language", "fi"]) == 0
    assert calls[-1] == {
        "query": "COMP.CS",
        "display_language": "fi",
        "semantic_min_score": None,
        "fuzzy_min_score": None,
        "include_inactive": True,
    }
    assert capsys.readouterr().out == expected.model_dump_json() + "\n"

    assert (
        _CLI_MODULE.main(
            [
                "tensorit",
                "--display-language",
                "en",
                "--semantic-min-score",
                "0.25",
                "--fuzzy-min-score",
                "90",
                "--active-only",
            ]
        )
        == 0
    )
    assert calls[-1] == {
        "query": "tensorit",
        "display_language": "en",
        "semantic_min_score": 0.25,
        "fuzzy_min_score": 90,
        "include_inactive": False,
    }

    with pytest.raises(SystemExit):
        _CLI_MODULE.main(["tensorit"])
