"""Settings boundary tests for the configuration families."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from course_explorer.config import (
    AdminWebSettings,
    EmbeddingRuntimeSettings,
    EmbeddingSettings,
    InferenceRerankSettings,
    InferenceSettings,
    TranslationSettings,
    WebSettings,
)
from tests.config._support import (
    ADMIN_WEB_KEYS,
    WEB_KEYS,
    _set_environment,
    set_embedding_environment,
    set_inference_environment,
    set_translation_environment,
)


def test_local_services_reject_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each local family, including the hub-less embedding runtime, rejects non-loopback exposure."""
    set_embedding_environment(monkeypatch, EMBEDDING_HOST="0.0.0.0")
    with pytest.raises(ValidationError):
        EmbeddingRuntimeSettings()
    with pytest.raises(ValidationError):
        EmbeddingSettings()

    set_translation_environment(monkeypatch, TRANSLATION_HOST="0.0.0.0")
    with pytest.raises(ValidationError):
        TranslationSettings()

    set_inference_environment(monkeypatch, INFERENCE_HOST="0.0.0.0")
    with pytest.raises(ValidationError):
        InferenceSettings()

    _set_environment(monkeypatch, WEB_KEYS, {"WEB_HOST": "0.0.0.0"})
    with pytest.raises(ValidationError):
        WebSettings()

    _set_environment(monkeypatch, ADMIN_WEB_KEYS, {"ADMIN_WEB_HOST": "0.0.0.0"})
    with pytest.raises(ValidationError):
        AdminWebSettings()

    set_inference_environment(monkeypatch, INFERENCE_RERANK_HOST="0.0.0.0")
    with pytest.raises(ValidationError):
        InferenceRerankSettings()
