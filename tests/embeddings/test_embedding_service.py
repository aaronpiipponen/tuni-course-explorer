"""Opt-in live contract test for the pinned loopback embedding service."""

import math
import os

import httpx
import pytest

from course_explorer.config import EmbeddingSettings
from course_explorer.embeddings.provider import EmbeddingProvider

pytestmark = pytest.mark.live


def test_live_embedding_service_contract() -> None:
    """Exercise Finnish/English embedding, dimension, normalization, and determinism."""
    if os.environ.get("COURSE_EXPLORER_RUN_LIVE_EMBEDDING_TESTS") != "1":
        pytest.skip("set COURSE_EXPLORER_RUN_LIVE_EMBEDDING_TESTS=1 to enable live embedding test")
    settings = EmbeddingSettings()
    assert settings.embedding_host == "127.0.0.1"

    with EmbeddingProvider(settings) as provider:
        first, second = provider.embed(
            ("tensorit koneoppimisessa", "tensor calculus in machine learning")
        )
        repeat = provider.embed(("tensorit koneoppimisessa",))[0]

    for vector in (first, second, repeat):
        assert len(vector) == settings.embedding_dimension
        assert all(math.isfinite(component) for component in vector)
        norm = math.sqrt(sum(component * component for component in vector))
        assert math.isclose(norm, 1.0, rel_tol=1e-6, abs_tol=1e-6)

    dot = sum(a * b for a, b in zip(first, repeat, strict=True))
    first_norm = math.sqrt(sum(component * component for component in first))
    repeat_norm = math.sqrt(sum(component * component for component in repeat))
    cosine = dot / (first_norm * repeat_norm)
    assert math.isclose(cosine, 1.0, rel_tol=1e-6, abs_tol=1e-6)


def test_live_embedding_service_accepts_token_dense_maximum_character_chunk() -> None:
    """Prove one production-shaped maximal character chunk embeds completely."""
    if os.environ.get("COURSE_EXPLORER_RUN_LIVE_EMBEDDING_TESTS") != "1":
        pytest.skip("set COURSE_EXPLORER_RUN_LIVE_EMBEDDING_TESTS=1 to enable live embedding test")
    settings = EmbeddingSettings()
    long_text = ("a " * settings.embedding_chunk_max_characters)[
        : settings.embedding_chunk_max_characters
    ]

    with httpx.Client(
        base_url=str(settings.base_url),
        timeout=settings.embedding_request_timeout_seconds,
        follow_redirects=False,
    ) as client:
        response = client.post("/tokenize", json={"content": long_text, "add_special": True})
        response.raise_for_status()
        payload = response.json()

    assert payload["tokens"]

    with EmbeddingProvider(settings) as provider:
        (vector,) = provider.embed((long_text,))

    assert len(vector) == settings.embedding_dimension
    assert all(math.isfinite(component) for component in vector)
    norm = math.sqrt(sum(component * component for component in vector))
    assert math.isclose(norm, 1.0, rel_tol=1e-6, abs_tol=1e-6)
