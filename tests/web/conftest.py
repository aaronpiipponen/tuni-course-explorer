"""Shared synthetic serving generation and retained-cache scope for web tests."""

from __future__ import annotations

import pytest

import course_explorer_web.serving_cache as serving_cache

SYNTHETIC_SERVING_GENERATION = "f" * 32


@pytest.fixture(autouse=True)
def _synthetic_serving_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply one synthetic generation value, so no test needs a running serving parent."""
    monkeypatch.setenv("COURSE_EXPLORER_WEB_GENERATION", SYNTHETIC_SERVING_GENERATION)


@pytest.fixture(autouse=True)
def _fresh_serving_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no retained cache, so one test's projection answers no other test."""
    monkeypatch.setattr(serving_cache, "_current", None)
