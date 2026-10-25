"""Contracts for deterministic chunking, work keys, and chunk provenance."""

from __future__ import annotations

import pytest

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.embeddings.generation import (
    build_course_embedding_chunks,
    chunk_teaching_text,
    embedding_configuration_sha256,
)
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)
from course_explorer.teaching_text.service import teaching_text_sha256
from tests.embeddings._generation_support import (
    GENERATED_AT,
    HASH_A,
    course,
    settings,
    teaching_text,
    translation,
    version,
)


def test_chunk_teaching_text_is_deterministic_bounded_and_preserves_overlap() -> None:
    """Chunking is stable, respects the window, and omits wholly blank overlap windows."""
    assert chunk_teaching_text("short text", max_characters=20, overlap_characters=0) == (
        "short text",
    )
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = chunk_teaching_text(text, max_characters=10, overlap_characters=3)
    assert chunks == ("abcdefghij", "hijklmnopq", "opqrstuvwx", "vwxyz")

    spaced = chunk_teaching_text("aaaa      bbbb", max_characters=6, overlap_characters=0)
    assert all(chunk.strip() for chunk in spaced)


def test_build_chunks_preserves_field_language_origin_and_source_provenance() -> None:
    """Fields, languages, and origins are separate with exact provenance and no prereqs."""
    representative = version(
        "course-a-v1",
        name_fi="Lineaarialgebra",
        content_fi="Matriisit ja vektorit",
    )
    representative = representative.model_copy(
        update={
            "prerequisite_text_fi": "prereq-fi sentinel",
            "prerequisite_text_en": "prereq-en sentinel",
        }
    )
    rows = (
        translation(
            "course-a-v1",
            TeachingTextField.NAME,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Lineaarialgebra",
            "Linear algebra",
        ),
    )
    catalogue = teaching_text((course("course-a", representative),), rows).build_catalogue()
    config = settings()

    chunks = build_course_embedding_chunks(catalogue, config)

    keys = [(chunk.field, chunk.language, chunk.text_origin, chunk.chunk_index) for chunk in chunks]
    assert keys == [
        (TeachingTextField.NAME, TeachingTextLanguage.FI, TeachingTextOrigin.OFFICIAL, 0),
        (TeachingTextField.NAME, TeachingTextLanguage.EN, TeachingTextOrigin.DERIVED, 0),
        (TeachingTextField.CONTENT, TeachingTextLanguage.FI, TeachingTextOrigin.OFFICIAL, 0),
    ]
    derived = chunks[1]
    assert derived.text == "Linear algebra"
    assert derived.effective_text_hash == teaching_text_sha256("Linear algebra")
    assert derived.source_text_hash == teaching_text_sha256("Lineaarialgebra")
    assert derived.translation_method is TranslationMethod.MANUAL
    assert derived.translation_model is None
    assert derived.translation_generated_at == GENERATED_AT
    official = chunks[0]
    assert official.effective_text_hash == official.source_text_hash
    assert official.translation_method is None
    for chunk in chunks:
        assert chunk.representative_source_hash == HASH_A
        assert chunk.chunk_text_hash == teaching_text_sha256(chunk.text)
        assert chunk.embedding_model == config.embedding_model
        assert chunk.embedding_artifact_sha256 == config.embedding_artifact_sha256
        assert chunk.embedding_configuration_hash == embedding_configuration_sha256(config)
    assert all("prereq" not in chunk.text.lower() for chunk in chunks)

    scoped = build_course_embedding_chunks(catalogue, config, group_ids=["course-a"])
    assert scoped == chunks
    with pytest.raises(ValueError):
        build_course_embedding_chunks(catalogue, config, group_ids=["missing"])


def test_embedding_configuration_hash_tracks_only_vector_semantics() -> None:
    """Model/artifact/semantics change the hash. Batch/chunk policy and the fixed dimension do not."""
    base = settings()

    assert base.embedding_dimension == COURSE_EMBEDDING_DIMENSION
    assert embedding_configuration_sha256(base) != embedding_configuration_sha256(
        settings(EMBEDDING_MODEL="other/model")
    )
    assert embedding_configuration_sha256(base) != embedding_configuration_sha256(
        settings(EMBEDDING_POOLING="mean")
    )
    assert embedding_configuration_sha256(base) != embedding_configuration_sha256(
        settings(EMBEDDING_NORMALIZATION=1)
    )
    assert embedding_configuration_sha256(base) == embedding_configuration_sha256(
        settings(
            EMBEDDING_REQUEST_TIMEOUT_SECONDS=600,
            EMBEDDING_GENERATION_BATCH_SIZE=8,
            EMBEDDING_CHUNK_MAX_CHARACTERS=64,
            EMBEDDING_CHUNK_OVERLAP_CHARACTERS=8,
        )
    )
