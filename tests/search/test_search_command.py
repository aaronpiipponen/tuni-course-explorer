"""Unified command and CLI contracts for course search."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

from course_explorer.config import SearchSettings
from course_explorer.db import session as session_module
from course_explorer.search import commands as command_module
from tests.search._service_support import embedding_settings
from tests.support import (
    FakeCurriculum,
    course,
    represented_rows,
    settings_factory,
    version,
)

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


def test_unified_search_command_wires_the_services_disposes_engine_and_returns_the_report(
    monkeypatch,
) -> None:
    """One engine/provider, both composed services, one unified call, and its report returned as-is."""
    engine = type(
        "Engine", (), {"disposed": False, "dispose": lambda self: setattr(self, "disposed", True)}
    )()
    factory = object()
    settings = search_settings(semantic="0.45", fuzzy="70")
    embedding = embedding_settings()
    calls: list[tuple] = []

    class Lookup:
        def __init__(self, curriculum, search_settings, *, projection_cache=None):
            calls.append(("lookup", curriculum, search_settings))

    class Semantic:
        def __init__(self, curriculum, repository, provider, embedding_settings, search_settings):
            calls.append(
                ("semantic", curriculum, repository, provider, embedding_settings, search_settings)
            )

    class Unified:
        def __init__(self, curriculum, semantic_search, course_lookup, search_settings):
            calls.append(("unified", curriculum, semantic_search, course_lookup, search_settings))

        def search(self, query, **kwargs):
            calls.append(("unified-search", query, kwargs))
            return expected

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

    expected = command_module.UnifiedSearchReport(
        display_language="fi",
        semantic_min_score=0.45,
        fuzzy_min_score=70,
        include_inactive=True,
        semantic_available=False,
        tier_priority=settings.search_tier_priority,
        results=(),
    )

    monkeypatch.setattr(command_module, "load_database_settings", lambda: object())
    monkeypatch.setattr(command_module, "load_embedding_settings", lambda: embedding)
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

    assert report is expected
    assert ("repository", factory) in calls
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
    # The provider gets the query-local projection, and every similarity consumer keeps the
    # stage's own embedding settings.
    query_embedding_settings = next(entry[1] for entry in calls if entry[0] == "provider")
    assert query_embedding_settings is not embedding
    assert query_embedding_settings.embedding_request_timeout_seconds == (
        settings.search_embedding_request_timeout_seconds
    )
    assert query_embedding_settings.embedding_max_attempts == settings.search_embedding_max_attempts
    assert query_embedding_settings.embedding_model == embedding.embedding_model
    assert query_embedding_settings.embedding_hub_vector == embedding.embedding_hub_vector
    assert embedding.embedding_request_timeout_seconds == 30
    assert embedding.embedding_max_attempts == 3
    assert semantic_call[4] is embedding
    assert semantic_call[5] is settings
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
    assert override is expected
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


def test_search_command_limits_query_embedding_to_one_short_attempt(monkeypatch) -> None:
    """One query embedding request carries the configured short timeout, and one attempt suffices."""
    engine = type(
        "Engine", (), {"disposed": False, "dispose": lambda self: setattr(self, "disposed", True)}
    )()
    settings = search_settings()
    embedding = embedding_settings()
    records = represented_rows(
        (
            course(
                "group-target",
                version("source-target", code="COMP.CS.100", name_en="Data Structures"),
            ),
        )
    )
    attempts: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.extensions["timeout"]["read"])
        raise httpx.ReadTimeout("synthetic query embedding timeout", request=request)

    provider_class = command_module.EmbeddingProvider

    def provider(configured):
        return provider_class(configured, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(command_module, "EmbeddingProvider", provider)
    monkeypatch.setattr(command_module, "load_database_settings", lambda: object())
    monkeypatch.setattr(command_module, "load_embedding_settings", lambda: embedding)
    monkeypatch.setattr(command_module, "load_search_settings", lambda: settings)
    monkeypatch.setattr(session_module, "create_database_engine", lambda value: engine)
    monkeypatch.setattr(session_module, "create_session_factory", lambda value: object())
    monkeypatch.setattr(
        command_module,
        "CurriculumRepository",
        lambda value: FakeCurriculum((), summaries_by_activity={None: records}),
    )
    monkeypatch.setattr(command_module, "SemanticSearchRepository", lambda value: object())

    report = command_module.run_search_command("COMP.CS.100", display_language="fi")

    assert attempts == [settings.search_embedding_request_timeout_seconds]
    assert attempts == [5.0]
    assert report.semantic_available is False
    assert [result.course.group_id for result in report.results] == ["group-target"]
    assert report.results[0].match_sources == ("exact_code", "substring")
    assert report.results[0].semantic_score is None
    assert engine.disposed


def test_search_without_semantic_preserves_lexical_results(monkeypatch) -> None:
    """A semantic-free command serves the real lexical methods with no embedding composition."""
    engine = type(
        "Engine", (), {"disposed": False, "dispose": lambda self: setattr(self, "disposed", True)}
    )()
    settings = search_settings()
    records = represented_rows(
        (
            course(
                "group-target",
                version("source-target", code="COMP.CS.100", name_en="Data Structures"),
            ),
        )
    )

    def refuse_reached(name: str):
        def refuse(*_args, **_kwargs):
            raise AssertionError(f"{name} must not be reached without semantic search")

        return refuse

    monkeypatch.setattr(command_module, "load_database_settings", lambda: object())
    monkeypatch.setattr(command_module, "load_search_settings", lambda: settings)
    monkeypatch.setattr(
        command_module, "load_embedding_settings", refuse_reached("embedding settings")
    )
    monkeypatch.setattr(command_module, "EmbeddingProvider", refuse_reached("embedding provider"))
    monkeypatch.setattr(
        command_module, "SemanticSearchRepository", refuse_reached("semantic repository")
    )
    monkeypatch.setattr(session_module, "create_database_engine", lambda value: engine)
    monkeypatch.setattr(session_module, "create_session_factory", lambda value: object())
    monkeypatch.setattr(
        command_module,
        "CurriculumRepository",
        lambda value: FakeCurriculum((), summaries_by_activity={None: records}),
    )

    report = command_module.run_search_command(
        "COMP.CS.100", display_language="fi", include_semantic=False
    )

    assert [result.course.group_id for result in report.results] == ["group-target"]
    assert report.results[0].match_sources == ("exact_code", "substring")
    assert report.results[0].fuzzy_score is None
    assert report.results[0].semantic_score is None
    assert report.semantic_available is False
    assert report.tier_priority == ("exact_code", "substring", "fuzzy_name")
    assert engine.disposed


def test_search_cli_forwards_options_and_prints_one_report(monkeypatch, capsys) -> None:
    """CLI delegates once to the unified command, requires locale, and prints one unified report."""
    expected = command_module.UnifiedSearchReport(
        display_language="fi",
        semantic_min_score=0.40,
        fuzzy_min_score=80,
        include_inactive=True,
        semantic_available=False,
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
    printed = capsys.readouterr().out
    assert printed == expected.model_dump_json() + "\n"
    assert '"semantic_available":false' in printed

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
