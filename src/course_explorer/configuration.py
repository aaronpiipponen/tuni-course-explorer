"""Sole file-source owner for tracked public TOML and the device-local ignored ``.env``.

The repository keeps one TOML file per configuration subsystem under ``config/``. This module
reads those tracked files and the device's ignored ``.env`` once per process and hands the values
to the settings layer through the standard Pydantic settings source protocol. It owns no
validator, no settings class and no policy value: it only parses, checks the cross-file
disjointness rule, returns each caller's requested projection with any requested derived-hub
reference tables resolved, and serializes portable values
across a process boundary. Public files carry portable values, and the device-local file carries
secrets and machine identity.

Because the tracked TOML and the local ``.env`` are the runtime inputs, ordinary commands need no
manual sourcing. ``configuration shell`` serves the few one-time shell recipes that
need portable variables exported. It emits public portable aliases only.

The same owner reads one file's candidate text without touching the file, and holds one transient
candidate snapshot for a settings validation outside a process start.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tomllib
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from io import StringIO
from pathlib import Path
from typing import Any, NamedTuple

from dotenv import dotenv_values
from dotenv.parser import parse_stream
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource

from course_explorer.administration import repository_root

# Ordered public subsystem files. The web bind file is last so its one loopback policy is
# composed after the shared files.
PUBLIC_CONFIG_FILES: tuple[str, ...] = (
    "config/database.toml",
    "config/curriculum.toml",
    "config/search.toml",
    "config/translation.toml",
    "config/inference.toml",
    "config/worker.toml",
    "config/admin_web.toml",
    "config/web.toml",
)

# The only two public values that are references to a tracked derived artifact rather than inline
# policy. They live beside the TOML files as a bare JSON numeric array so the large embedding hubs
# stay reviewable configuration instead of one very long line.
_HUB_REFERENCE_ALIASES = ("EMBEDDING_HUB_VECTOR", "EMBEDDING_OUTCOMES_HUB_VECTOR")


def _read_toml_file(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"public configuration file is not readable: {path.name}") from exc
    try:
        return tomllib.loads(payload)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"public configuration file is not valid TOML: {path.name}") from exc


def _hub_reference_path(alias: str, value: object) -> Path:
    if not isinstance(value, dict) or set(value) != {"path"} or not isinstance(value["path"], str):
        raise ValueError(f"{alias} must reference a derived artifact by a single path key")
    reference = Path(value["path"])
    if reference.is_absolute():
        raise ValueError(f"{alias} derived artifact path must be repository-relative")
    return reference


def _resolve_hub_reference(root: Path, alias: str, value: object) -> object:
    if isinstance(value, list):
        return value
    reference = _hub_reference_path(alias, value)
    try:
        payload = (root / reference).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{alias} derived artifact is not readable") from exc
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{alias} derived artifact is not valid JSON") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"{alias} derived artifact must be a JSON numeric array")
    return parsed


@cache
def _read_merged_public_configuration_cached(root_text: str) -> dict[str, object]:
    """Read and merge every public TOML file beneath one root, rejecting duplicate aliases."""
    root = Path(root_text)
    documents = {relative: _read_toml_file(root / relative) for relative in PUBLIC_CONFIG_FILES}
    return _merge_configuration_documents(documents)


def _merge_configuration_documents(
    documents: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Merge parsed configuration documents, rejecting an alias defined in more than one."""
    merged: dict[str, object] = {}
    for document in documents.values():
        for alias, value in document.items():
            if alias in merged:
                raise ValueError(
                    f"public configuration alias is defined in more than one file: {alias}"
                )
            merged[alias] = value
    return merged


def _project_configuration(
    root: Path, values: Mapping[str, object], aliases: Collection[str] | None
) -> dict[str, object]:
    """Return one alias projection of merged values, resolving only the hub references requested."""
    if aliases is None:
        selected = dict(values)
    else:
        requested = set(aliases)
        selected = {alias: value for alias, value in values.items() if alias in requested}
    for alias in _HUB_REFERENCE_ALIASES:
        if alias in selected:
            selected[alias] = _resolve_hub_reference(root, alias, selected[alias])
    return selected


def read_public_configuration(
    root: Path, *, aliases: Collection[str] | None = None
) -> dict[str, object]:
    """Read and merge the tracked public TOML files beneath ``root`` as one requested projection.

    The merged raw TOML read is cached by checkout root for the process lifetime and a duplicate
    alias across files is rejected. Each call returns a
    fresh projection: ``aliases`` selects exactly the requested keys, so a runtime/generation reader
    never opens either derived similarity-hub artifact, while the default ``None`` returns every
    public value with both hub references resolved. Only hub aliases present in the projection are
    resolved, so a full similarity read fails loudly when its artifact is missing or malformed.
    No local value is read or rendered here.
    """
    merged = _read_merged_public_configuration_cached(str(root))
    return _project_configuration(root, merged, aliases)


def read_configuration_documents(
    root: Path, *, replacements: Mapping[str, str] | None = None
) -> dict[str, dict[str, object]]:
    """Read every public TOML file beneath ``root`` as its own parsed document.

    A supplied replacement text parses in place of that file's read, so a candidate edit validates
    against the same document set the runtime composition merges without writing the file. Every
    read is fresh, so a caller sees the files as they are at that moment.
    """
    replaced = dict(replacements or {})
    for relative in replaced:
        if relative not in PUBLIC_CONFIG_FILES:
            raise ValueError(f"replacement is not a registered configuration file: {relative}")
    documents: dict[str, dict[str, object]] = {}
    for relative in PUBLIC_CONFIG_FILES:
        if relative in replaced:
            try:
                documents[relative] = tomllib.loads(replaced[relative])
            except tomllib.TOMLDecodeError as exc:
                raise ValueError(
                    f"public configuration file is not valid TOML: {relative}"
                ) from exc
        else:
            documents[relative] = _read_toml_file(root / relative)
    return documents


def parse_local_configuration(payload: str) -> dict[str, str | None]:
    """Parse dotenv text into its assignments without interpolating any value.

    A blank or comment line carries no assignment and is skipped. A binding the parser marks as
    malformed and a key assigned more than once under the runtime's case-insensitive names both
    raise a content-free ``ValueError`` so a candidate edit refuses an ambiguous file. The mapping
    key keeps the spelling the file holds. A bare key holds ``None``.
    """
    values: dict[str, str | None] = {}
    assigned: set[str] = set()
    for binding in parse_stream(StringIO(payload)):
        if binding.error:
            raise ValueError("dotenv payload holds a malformed assignment")
        if binding.key is None:
            continue
        normalized = binding.key.lower()
        if normalized in assigned:
            raise ValueError("dotenv payload assigns one key more than once")
        assigned.add(normalized)
        values[binding.key] = binding.value
    return values


def read_candidate_local_configuration(root: Path) -> dict[str, str | None]:
    """Read the device-local file beneath ``root`` freshly as a strict candidate local mapping.

    An absent file supplies no value, so any required setting fails through its owning validator.
    Every read reaches the file and parses it through ``parse_local_configuration`` after decoding
    it as UTF-8 without newline translation, so a malformed binding and a key assigned more than once
    both raise a content-free ``ValueError``. Other read, decode and parse errors propagate.
    """
    try:
        payload = (root / ".env").read_bytes()
    except FileNotFoundError:
        return {}
    return parse_local_configuration(payload.decode("utf-8"))


def hub_reference_path(root: Path, alias: str) -> Path:
    """Return the repository-relative artifact path that one hub alias references.

    Only ``EMBEDDING_HUB_VECTOR`` and ``EMBEDDING_OUTCOMES_HUB_VECTOR`` are accepted. The referenced
    artifact is not opened, so the path is available before the file exists. An absent alias, an
    inline vector value or an absolute path raises ``ValueError``.
    """
    if alias not in _HUB_REFERENCE_ALIASES:
        raise ValueError(f"{alias} is not an embedding hub alias")
    merged = _read_merged_public_configuration_cached(str(root))
    if alias not in merged:
        raise ValueError(f"{alias} is not configured")
    return _hub_reference_path(alias, merged[alias])


@cache
def _read_local_configuration_cached(root_text: str) -> dict[str, str | None]:
    return dict(dotenv_values(Path(root_text) / ".env", encoding="utf-8", interpolate=False))


def read_local_configuration(root: Path) -> dict[str, str | None]:
    """Read the device-local ignored ``.env`` beneath ``root``, or no values when it is absent.

    The read is cached by checkout root for the process lifetime. Absent means no local values, so
    any required setting fails through its owning validator. The local file supplies values only and
    its values are never logged.
    """
    return _read_local_configuration_cached(str(root))


def clear_configuration_caches() -> None:
    """Clear the cached public and local file reads so a changed checkout root is re-read."""
    _read_merged_public_configuration_cached.cache_clear()
    _read_local_configuration_cached.cache_clear()


class CandidateConfiguration(NamedTuple):
    """One transient candidate configuration: its root, its merged public values, its local values."""

    root: Path
    public: Mapping[str, object]
    local: Mapping[str, str | None]


_CANDIDATE_CONFIGURATION: ContextVar[CandidateConfiguration | None] = ContextVar(
    "configuration_candidate", default=None
)


def _candidate_configuration() -> CandidateConfiguration | None:
    """Return the candidate snapshot this execution context holds, or ``None``."""
    return _CANDIDATE_CONFIGURATION.get()


@contextmanager
def configuration_candidate(
    root: Path,
    *,
    documents: Mapping[str, Mapping[str, object]],
    local: Mapping[str, str | None],
) -> Iterator[None]:
    """Hold one candidate configuration for the settings classes built inside the block.

    The documents merge through the shared duplicate-alias rule, so a candidate that repeats an
    alias fails here. The snapshot is transient: the token reset in the ``finally`` branch restores
    the previous state whatever the block raises.
    """
    token = _CANDIDATE_CONFIGURATION.set(
        CandidateConfiguration(
            root=root, public=_merge_configuration_documents(documents), local=local
        )
    )
    try:
        yield
    finally:
        _CANDIDATE_CONFIGURATION.reset(token)


def candidate_settings_sources(
    settings_cls: type[BaseSettings],
) -> tuple[PydanticBaseSettingsSource | Callable[[], dict[str, object]], ...] | None:
    """Return the candidate sources of one settings class, or ``None`` outside a candidate block.

    The candidate local mapping replaces the device-local file read, and the projected candidate
    public values replace the tracked-file read. No process environment is a source here, so only
    the caller's constructor inputs can precede the candidate values.
    """
    snapshot = _candidate_configuration()
    if snapshot is None:
        return None
    from course_explorer.config import _settings_aliases

    def public_values() -> dict[str, object]:
        return _project_configuration(
            snapshot.root, snapshot.public, _settings_aliases(settings_cls)
        )

    return (LocalConfigurationSource(settings_cls), public_values)


def environment_value(value: object) -> str:
    """Serialize one settings value for a process boundary.

    Lists, tuples and mappings become compact JSON. A boolean becomes ``1``/``0``. Any other scalar
    becomes its text form. This is the one shared serialization used where a short-lived launcher
    hands values to a long-lived child or a shell helper.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


class LocalConfigurationSource(EnvSettingsSource):
    """Pydantic settings source reading the device-local ignored ``.env`` instead of ``os.environ``.

    The inherited ``EnvSettingsSource`` owns alias projection and JSON decoding for complex fields.
    This subclass only replaces the value mapping. Names are lowercased when the inherited source is
    case-insensitive, matching how the parent resolves an environment file. Inside a candidate
    configuration block the held local mapping replaces the file read.
    """

    def _load_env_vars(self) -> Mapping[str, str | None]:
        snapshot = _candidate_configuration()
        values = (
            snapshot.local if snapshot is not None else read_local_configuration(repository_root())
        )
        if not self.case_sensitive:
            return {name.lower(): value for name, value in values.items()}
        return values


def _shell_exports() -> dict[str, str]:
    """Project the public portable values, preserving any intentional same-alias process override."""
    public = read_public_configuration(repository_root())
    return {
        alias: os.environ.get(alias, environment_value(value)) for alias, value in public.items()
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="configuration", description=__doc__)
    parser.add_argument("action", choices=["shell"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the one explicit action: print public portable shell exports for shell recipes."""
    args = _parser().parse_args(argv)
    if args.action == "shell":
        for alias, value in _shell_exports().items():
            print(f"export {alias}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
