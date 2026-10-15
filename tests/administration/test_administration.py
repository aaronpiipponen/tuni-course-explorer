"""Contracts for the shared product-file administrative primitives."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
    session_directory,
)


class _Probe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    count: int


def test_administrative_json_and_model_round_trip(tmp_path: Path) -> None:
    """Canonical JSON is one sorted line and strict loaders reject foreign schemas and symlinks."""
    probe = _Probe(name="alpha", count=2)
    payload = administrative_json(probe)
    assert payload.endswith("\n") and payload.count("\n") == 1
    assert payload == '{"count":2,"name":"alpha"}\n'

    target = tmp_path / "probe.json"
    atomic_write_private_text(target, payload)
    assert load_private_model(target, _Probe) == probe

    foreign = tmp_path / "foreign.json"
    atomic_write_private_text(foreign, '{"count":2,"name":"alpha","extra":1}\n')
    with pytest.raises(ValueError):
        load_private_model(foreign, _Probe)

    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        load_private_model(link, _Probe)


def test_atomic_write_is_mode_0600_and_rejects_missing_parent(tmp_path: Path) -> None:
    """Publication is atomic, mode 0600, and refuses an absent parent."""
    target = tmp_path / "state.json"
    atomic_write_private_text(target, "payload\n")
    assert target.read_text(encoding="utf-8") == "payload\n"
    assert oct(target.stat().st_mode & 0o777) == "0o600"

    atomic_write_private_text(target, "replacement\n")
    assert target.read_text(encoding="utf-8") == "replacement\n"
    assert list(tmp_path.iterdir()) == [target]

    with pytest.raises(ValueError):
        atomic_write_private_text(tmp_path / "missing" / "state.json", "payload\n")


def test_session_directory_rejects_invalid_or_escaping_identity(tmp_path: Path) -> None:
    """Only a 32-lowercase-hex identity inside the state root produces a session path."""
    root = tmp_path / "state"
    root.mkdir()
    session_id = "0123456789abcdef0123456789abcdef"
    assert session_directory(root, session_id) == root / session_id

    with pytest.raises(ValueError):
        session_directory(root, "../" + session_id)

    # A symlinked state root is resolved to its real directory. The identity itself is the
    # only thing that could escape and it is restricted to hex.
    real = tmp_path / "outside"
    real.mkdir()
    linked = tmp_path / "state-link"
    linked.symlink_to(real)
    assert session_directory(linked, session_id) == real / session_id
