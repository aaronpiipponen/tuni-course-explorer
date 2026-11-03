"""Dataset-role resolution from pointer presence, bootstrap and inconsistent enrollment."""

from __future__ import annotations

from pathlib import Path

import pytest

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_database_settings, load_database_settings_with_identity
from course_explorer.datasets import DatasetPointer, clear_dataset_cache
from tests.config._support import set_database_environment
from tests.datasets._support import INITIAL_ID, sample_receipt

WORKING_ID = "a" * 32


def _write_role(
    state: Path,
    role: str,
    dataset_id: str,
    *,
    database_name: str,
    kind: str = "initial",
) -> None:
    receipt = sample_receipt(
        dataset_id=dataset_id,
        database_name=database_name,
        kind=kind,  # type: ignore[arg-type]
        predecessor_id=INITIAL_ID if kind == "copied" else None,
        dump_sha256="b" * 64 if kind == "copied" else None,
    )
    directory = state / "datasets" / dataset_id
    directory.mkdir(mode=0o700, parents=True)
    atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))
    atomic_write_private_text(
        state / f"{role}-dataset.json",
        administrative_json(DatasetPointer(schema_version=1, dataset_id=dataset_id)),
    )


def test_dataset_roles_resolve_from_pointer_presence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Selected resolves from its pointer, bootstrap returns raw settings, and Working refuses absent."""
    state = tmp_path / "state"
    _write_role(state, "selected", INITIAL_ID, database_name="selected_db")

    set_database_environment(
        monkeypatch,
        POSTGRES_DB="raw_name",
        ADMIN_STATE_ROOT="state",
    )
    clear_dataset_cache()
    resolved, identity = load_database_settings_with_identity()
    assert resolved.postgres_db == "selected_db"
    assert identity == INITIAL_ID
    assert load_database_settings() == resolved

    # A Working role is optional while enrolled, and its absence names the copy command.
    with pytest.raises(FileNotFoundError, match="copy a dataset to Working"):
        load_database_settings_with_identity(role="working")

    _write_role(
        state,
        "working",
        WORKING_ID,
        database_name="working_db",
        kind="copied",
    )
    clear_dataset_cache()
    working, working_identity = load_database_settings_with_identity(role="working")
    assert working.postgres_db == "working_db"
    assert working_identity == WORKING_ID
    assert load_database_settings(role="selected").postgres_db == "selected_db"

    # A memoized Working receipt may not bypass the current Selected guard. Rewriting only the
    # Selected pointer, without clearing this process's cache, makes Working an alias of Selected.
    atomic_write_private_text(
        state / "selected-dataset.json",
        administrative_json(DatasetPointer(schema_version=1, dataset_id=WORKING_ID)),
    )
    with pytest.raises(ValueError):
        load_database_settings_with_identity(role="working")

    # The database name is the other half of the same guard, through the same cached role boundary.
    _write_role(
        state,
        "selected",
        "c" * 32,
        database_name="working_db",
        kind="copied",
    )
    with pytest.raises(ValueError):
        load_database_settings_with_identity(role="working")

    # Restoring a distinct Selected dataset lets the memoized Working receipt resolve again.
    atomic_write_private_text(
        state / "selected-dataset.json",
        administrative_json(DatasetPointer(schema_version=1, dataset_id=INITIAL_ID)),
    )
    clear_dataset_cache()
    assert load_database_settings_with_identity(role="working")[1] == WORKING_ID

    # A Selected pointer that disappears beside the Working receipt fails loudly, cached or not.
    (state / "selected-dataset.json").unlink()
    with pytest.raises(FileNotFoundError):
        load_database_settings_with_identity(role="working")
    with pytest.raises(FileNotFoundError):
        load_database_settings_with_identity()
    (state / "working-dataset.json").unlink()

    # A bootstrap root serves the raw configured database and creates nothing.
    empty = tmp_path / "empty"
    set_database_environment(
        monkeypatch,
        POSTGRES_DB="raw_name",
        ADMIN_STATE_ROOT="empty",
    )
    clear_dataset_cache()
    raw, raw_identity = load_database_settings_with_identity()
    assert raw.postgres_db == "raw_name"
    assert raw_identity is None
    assert load_database_settings().postgres_db == "raw_name"
    assert not empty.exists()

    # A pointer to a missing or invalid receipt fails instead of falling back to the raw name.
    broken = tmp_path / "broken"
    broken.mkdir()
    atomic_write_private_text(
        broken / "selected-dataset.json",
        administrative_json(DatasetPointer(schema_version=1, dataset_id="f" * 32)),
    )
    set_database_environment(
        monkeypatch,
        POSTGRES_DB="raw_name",
        ADMIN_STATE_ROOT="broken",
    )
    clear_dataset_cache()
    with pytest.raises(ValueError):
        load_database_settings_with_identity()
