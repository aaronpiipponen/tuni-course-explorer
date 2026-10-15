"""Opt-in PostgreSQL proofs for exact-cosine semantic search over representative chunks."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from course_explorer.comparison import commands as comparison_commands
from course_explorer.comparison.commands import CourseComparisonReport
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import session_scope
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.read import TeachingEmbeddingRepository
from course_explorer.enums import TeachingTextField, TeachingTextLanguage, TeachingTextOrigin
from course_explorer.recommendations.service import rank_recommendation_candidates
from course_explorer.search.repository import SemanticSearchRepository
from course_explorer.search.service import CourseSearchService
from tests.search._repository_support import (
    QUERY_VECTOR,
    FakeQueryProvider,
    _add_chunk,
    _seed_derived_and_obsolete,
    _seed_semantic_courses,
    embedding_settings,
    search_settings,
)

pytestmark = [
    pytest.mark.integration,
]

# A zero hub keeps centring an identity so the raw-cosine expectations below stay provable.
ZERO_HUB = (0.0,) * COURSE_EMBEDDING_DIMENSION


def test_exact_cosine_uses_best_completed_compatible_chunk_without_cap(
    database: tuple[Engine, object],
) -> None:
    """Best chunk, threshold, lifecycle/config exclusion, inactive scope, and no cap all hold."""
    seeded = _seed_semantic_courses(database)
    _, factory = database
    with session_scope(factory) as session:
        _add_chunk(
            session,
            version_id=seeded["group_b_version"],
            source_hash="2" * 64,
            field=TeachingTextField.OUTCOMES,
            language=TeachingTextLanguage.FI,
            chunk_index=1,
            text="outcomes b",
            cosine=0.85,
        )
        _add_chunk(
            session,
            version_id=seeded["group_b_version"],
            source_hash="2" * 64,
            field=TeachingTextField.NAME,
            language=TeachingTextLanguage.FI,
            chunk_index=2,
            text="name b",
            cosine=0.49,
        )
    repository = SemanticSearchRepository(factory)

    scores = repository.search(
        QUERY_VECTOR,
        hub=ZERO_HUB,
        min_score=0.5,
        embedding_configuration_hash=embedding_configuration_sha256(embedding_settings()),
        include_inactive=True,
    )
    by_group = {score.group_id: score for score in scores}
    assert set(by_group) == {"group-a", "group-b"}
    # The group score is the best matching chunk's 0.8. The seeded chunk average is 0.7.
    assert by_group["group-a"].score == pytest.approx(0.8)
    assert by_group["group-a"].sisu_course_unit_id == "source-a"
    assert by_group["group-b"].score == pytest.approx(0.9)

    active_only = repository.search(
        QUERY_VECTOR,
        hub=ZERO_HUB,
        min_score=0.5,
        embedding_configuration_hash=embedding_configuration_sha256(embedding_settings()),
        include_inactive=False,
    )
    assert {score.group_id for score in active_only} == {"group-a"}

    above_all = repository.search(
        QUERY_VECTOR,
        hub=ZERO_HUB,
        min_score=0.97,
        embedding_configuration_hash=embedding_configuration_sha256(embedding_settings()),
        include_inactive=True,
    )
    assert above_all == ()

    # The scoped vector read returns only the requested current representatives' completed,
    # compatible chunks: the inactive group-b is retained while the incompatible group-c and
    # pending group-d rows are absent, and an empty request opens no session.
    curriculum = CurriculumRepository(factory)
    represented = curriculum.list_represented_summaries()
    requested = tuple(
        record
        for record in represented
        if record.summary.group_id in {"group-a", "group-b", "group-c", "group-d"}
    )
    configuration_hash = embedding_configuration_sha256(embedding_settings())
    chunks = TeachingEmbeddingRepository(factory).get_chunks(
        requested, embedding_configuration_hash=configuration_hash
    )
    assert (
        TeachingEmbeddingRepository(factory).get_chunks(
            (), embedding_configuration_hash=configuration_hash
        )
        == ()
    )
    assert {
        (chunk.group_id, chunk.field, chunk.language, chunk.chunk_index) for chunk in chunks
    } == {
        ("group-a", TeachingTextField.CONTENT, TeachingTextLanguage.FI, 0),
        ("group-a", TeachingTextField.CONTENT, TeachingTextLanguage.EN, 1),
        ("group-b", TeachingTextField.CONTENT, TeachingTextLanguage.EN, 0),
        ("group-b", TeachingTextField.OUTCOMES, TeachingTextLanguage.FI, 1),
        ("group-b", TeachingTextField.NAME, TeachingTextLanguage.FI, 2),
    }
    a_fi = next(
        chunk
        for chunk in chunks
        if chunk.group_id == "group-a" and chunk.language == TeachingTextLanguage.FI
    )
    assert a_fi.character_count == len("chunk a0")
    assert a_fi.text_origin is TeachingTextOrigin.OFFICIAL
    assert len(a_fi.embedding) == COURSE_EMBEDDING_DIMENSION
    assert a_fi.embedding == (0.6, 0.8) + (0.0,) * (COURSE_EMBEDDING_DIMENSION - 2)

    a_en = next(
        chunk
        for chunk in chunks
        if chunk.group_id == "group-a" and chunk.language is TeachingTextLanguage.EN
    )
    basis = (a_en, a_fi)
    neighbors = TeachingEmbeddingRepository(factory).find_nearest_chunks(
        basis,
        embedding_configuration_hash=configuration_hash,
        top_k=1,
        active_only=False,
        excluded_group_ids=("group-a",),
    )
    assert [(hit.query_index, hit.group_id, hit.score) for hit in neighbors] == [
        (0, "group-b", pytest.approx(0.9815, abs=0.001)),
        (1, "group-b", pytest.approx(0.932, abs=0.01)),
    ]
    assert (
        TeachingEmbeddingRepository(factory).find_nearest_chunks(
            (),
            embedding_configuration_hash=configuration_hash,
            top_k=1,
            active_only=True,
        )
        == ()
    )
    active_neighbors = TeachingEmbeddingRepository(factory).find_nearest_chunks(
        (a_en,),
        embedding_configuration_hash=configuration_hash,
        top_k=10,
        active_only=True,
    )
    assert {hit.group_id for hit in active_neighbors} == {"group-a", "group-e"}


def test_service_returns_current_summary_for_derived_only_match_and_ignores_obsolete_version(
    database: tuple[Engine, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A derived-only English match returns the current official summary, never obsolete text."""
    _seed_derived_and_obsolete(database)
    _, factory = database
    provider = FakeQueryProvider()
    curriculum = CurriculumRepository(factory)
    service = CourseSearchService(
        curriculum,
        SemanticSearchRepository(factory),
        provider,
        embedding_settings(),
        search_settings(0.5),
    )

    results = service.search_courses("english text query")

    assert provider.calls == [("english text query",)]
    assert len(results) == 1
    result = results[0]
    assert result.course.group_id == "group-current"
    # The scored chunk is the current derived row at 0.6. The obsolete version's row holds 0.95.
    assert result.score == pytest.approx(0.6)
    assert result.course.code == "CUR.1"
    assert result.course.name_fi == "Nykyinen kurssi"
    assert result.course.name_en is None  # derived text never appears as an official summary name

    # The scoped read keeps only the current representative's own compatible chunk: both the
    # stale-source-hash cell on the current version and the obsolete version's chunk are absent.
    configuration_hash = embedding_configuration_sha256(embedding_settings())
    current = next(
        record
        for record in curriculum.list_represented_summaries()
        if record.summary.group_id == "group-current"
    )
    scoped = TeachingEmbeddingRepository(factory).get_chunks(
        (current,), embedding_configuration_hash=configuration_hash
    )
    assert [
        (chunk.field, chunk.language, chunk.chunk_index, chunk.text_origin) for chunk in scoped
    ] == [(TeachingTextField.CONTENT, TeachingTextLanguage.EN, 0, TeachingTextOrigin.DERIVED)]
    neighbors = TeachingEmbeddingRepository(factory).find_nearest_chunks(
        scoped,
        embedding_configuration_hash=configuration_hash,
        top_k=10,
        active_only=True,
    )
    assert {(hit.sisu_course_unit_id, hit.representative_source_hash) for hit in neighbors} == {
        ("source-current", "1" * 64),
        ("source-current", "3" * 64),
        ("source-obsolete", "2" * 64),
    }
    ranked = rank_recommendation_candidates(
        neighbors,
        (current,),
        excluded_group_ids=(),
        display_language="en",
        settings=search_settings(0.5),
    )
    assert [(record.summary.group_id, relatedness) for record, relatedness in ranked] == [
        ("group-current", pytest.approx(100.0))
    ]

    # The real comparison command composes the shared resolver, the scoped read and the pure
    # meters/verdict owner over the test database. A self-comparison scores 100 where text exists.
    monkeypatch.setattr(comparison_commands, "load_search_settings", lambda: search_settings(0.5))
    monkeypatch.setattr(comparison_commands, "load_embedding_settings", embedding_settings)
    report = comparison_commands.run_course_comparison_command("CUR.1", "group-current")

    assert report.course_a.group_id == "group-current"
    assert report.course_b.group_id == "group-current"
    assert report.course_a.code == "CUR.1"
    assert report.course_a.name_fi == "Nykyinen kurssi"
    assert report.course_a.name_en is None
    assert report.uses_derived_text is True
    assert report.meters.content_similarity == pytest.approx(100.0)
    assert report.meters.learning_outcome_similarity is None
    assert report.meters.overall_relatedness == pytest.approx(100.0)
    assert report.meters.overlap.a_in_b == pytest.approx(100.0)
    assert report.meters.overlap.b_in_a == pytest.approx(100.0)
    assert report.verdict == "heavily_overlapping"
    assert CourseComparisonReport.model_validate_json(report.model_dump_json()) == report
