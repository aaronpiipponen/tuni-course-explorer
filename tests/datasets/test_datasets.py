"""Selected-dataset resolution and opt-out contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

import course_explorer.administration as administration
from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_database_settings
from course_explorer.datasets import SelectedDatasetPointer
from tests.config._support import set_database_environment
from tests.datasets._support import INITIAL_ID, sample_receipt


def _write_selection(state: Path, *, database_name: str) -> None:
    receipt = sample_receipt(database_name=database_name)
    directory = state / "datasets" / INITIAL_ID
    directory.mkdir(mode=0o700, parents=True)
    atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))
    atomic_write_private_text(
        state / "selected-dataset.json",
        administrative_json(SelectedDatasetPointer(schema_version=1, dataset_id=INITIAL_ID)),
    )


def test_selected_dataset_default_and_explicit_opt_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The loader resolves the selected receipt. The opt-out returns the raw name as-is."""
    state = tmp_path / "state"
    _write_selection(state, database_name="selected_db")
    monkeypatch.setattr(administration, "repository_root", lambda: tmp_path)

    set_database_environment(
        monkeypatch,
        POSTGRES_DB="raw_name",
        SELECTED_DATASET_ENABLED="1",
        ADMIN_STATE_ROOT="state",
    )
    resolved = load_database_settings()
    assert resolved.postgres_db == "selected_db"

    set_database_environment(
        monkeypatch,
        POSTGRES_DB="raw_name",
        SELECTED_DATASET_ENABLED="0",
        ADMIN_STATE_ROOT="state",
    )
    assert load_database_settings().postgres_db == "raw_name"

    # An absent pointer refuses rather than falling back to the raw name, and writes nothing.
    empty = tmp_path / "empty"
    set_database_environment(
        monkeypatch,
        POSTGRES_DB="raw_name",
        SELECTED_DATASET_ENABLED="1",
        ADMIN_STATE_ROOT="empty",
    )
    with pytest.raises(FileNotFoundError):
        load_database_settings()
    assert not empty.exists()

    # A pointer to a missing or invalid receipt fails instead of falling back to the raw name.
    broken = tmp_path / "broken"
    broken.mkdir()
    atomic_write_private_text(
        broken / "selected-dataset.json",
        administrative_json(SelectedDatasetPointer(schema_version=1, dataset_id="f" * 32)),
    )
    set_database_environment(
        monkeypatch,
        POSTGRES_DB="raw_name",
        SELECTED_DATASET_ENABLED="1",
        ADMIN_STATE_ROOT="broken",
    )
    with pytest.raises(ValueError):
        load_database_settings()
