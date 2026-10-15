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
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tomllib
from collections.abc import Collection, Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic_settings import EnvSettingsSource

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


def _resolve_hub_reference(root: Path, alias: str, value: object) -> object:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict) or set(value) != {"path"} or not isinstance(value["path"], str):
        raise ValueError(f"{alias} must reference a derived artifact by a single path key")
    reference = Path(value["path"])
    if reference.is_absolute():
        raise ValueError(f"{alias} derived artifact path must be repository-relative")
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
    merged: dict[str, object] = {}
    for relative in PUBLIC_CONFIG_FILES:
        for alias, value in _read_toml_file(root / relative).items():
            if alias in merged:
                raise ValueError(
                    f"public configuration alias is defined in more than one file: {alias}"
                )
            merged[alias] = value
    return merged


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
    if aliases is None:
        selected = dict(merged)
    else:
        requested = set(aliases)
        selected = {alias: value for alias, value in merged.items() if alias in requested}
    for alias in _HUB_REFERENCE_ALIASES:
        if alias in selected:
            selected[alias] = _resolve_hub_reference(root, alias, selected[alias])
    return selected


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
    case-insensitive, matching how the parent resolves an environment file.
    """

    def _load_env_vars(self) -> Mapping[str, str | None]:
        values = read_local_configuration(repository_root())
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
