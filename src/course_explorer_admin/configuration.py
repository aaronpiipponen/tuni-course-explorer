"""Edit one validated key of a subsystem file or environment file.

This module lists the configuration files, reads every key of one file as that file holds it, and
replaces one key with one validated candidate. A write renders only the chosen key's text, preserves
every other byte, comment and line ending of the file, validates the whole candidate through the
settings owner's own families with the local values read freshly from their file, and publishes the
file atomically. The read report is the one operator output, and the write acknowledgment carries the
file and the key alone.
"""

from __future__ import annotations

import json
import math
import re
from io import StringIO
from pathlib import Path
from typing import Literal

import tomlkit
from dotenv.parser import Reader as DotenvReader
from dotenv.parser import parse_stream, parse_value
from pydantic import BaseModel, ConfigDict, JsonValue
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Array, InlineTable, Item
from tomlkit.toml_document import TOMLDocument

from course_explorer.administration import atomic_write_private_text, repository_root
from course_explorer.config import (
    CONFIGURATION_SETTINGS_FAMILIES,
    ConfiguredSettings,
    _settings_aliases,
)
from course_explorer.configuration import (
    PUBLIC_CONFIG_FILES,
    clear_configuration_caches,
    configuration_candidate,
    parse_local_configuration,
    read_candidate_local_configuration,
    read_configuration_documents,
)

_ENVIRONMENT_FILE = ".env"
# The editable set is the registered subsystem-file order plus the device-local file.
_CONFIGURATION_FILES: tuple[str, ...] = (*PUBLIC_CONFIG_FILES, _ENVIRONMENT_FILE)

# The two environment-file announcements the installed dotenv reader accepts before a key: an
# optional `export`, and a key that is single-quoted or unquoted.
_ENVIRONMENT_KEY = r"(?:'(?:[^']+)'|[^=#\s]+)"
_ENVIRONMENT_ASSIGNMENT = re.compile(
    rf"^(?P<prefix>\s*(?:export[^\S\r\n]+)?{_ENVIRONMENT_KEY}[^\S\r\n]*=[^\S\r\n]*)"
)
_ENVIRONMENT_BARE_KEY = re.compile(rf"^(?P<key>\s*(?:export[^\S\r\n]+)?{_ENVIRONMENT_KEY})")


class _ConfigurationModel(BaseModel):
    """Frozen, closed DTO base for the configuration-editor contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfigurationFilesReport(_ConfigurationModel):
    """The editable configuration files in composition order, with the environment file last."""

    schema_version: Literal[1] = 1
    files: tuple[str, ...]


class ConfigurationFileReport(_ConfigurationModel):
    """Every key of one configuration file as that file holds its value."""

    schema_version: Literal[1] = 1
    file: str
    values: dict[str, JsonValue]


class ConfigurationWriteReport(_ConfigurationModel):
    """One saved key of one configuration file, stated without repeating its value."""

    schema_version: Literal[1] = 1
    file: str
    key: str


def _require_listed_file(file: str) -> str:
    """Return the exact listed file name, refusing a path the editor does not own."""
    if file not in _CONFIGURATION_FILES:
        raise ValueError("configuration file must be one of the listed files")
    return file


def _confined_path(root: Path, relative: str) -> Path:
    """Return one configuration path beneath ``root``, refusing a redirected ancestor."""
    path = root / relative
    location = root
    for part in Path(relative).parts[:-1]:
        location = location / part
        if location.is_symlink() or not location.is_dir():
            raise ValueError("configuration path must not traverse a symlink or non-directory")
    return path


def _require_regular_file(path: Path) -> None:
    """Refuse a missing, symlinked or non-regular configuration file."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("configuration file must be a regular non-symlink file")


def _require_source_files(root: Path) -> None:
    """Refuse a redirected or special configuration source path before any source read.

    Every registered subsystem file must be present, because the runtime composition reads all of
    them. The device-local file may be absent, and an absent file supplies no local value.
    """
    for relative in _CONFIGURATION_FILES:
        path = _confined_path(root, relative)
        if relative == _ENVIRONMENT_FILE and not path.exists():
            continue
        _require_regular_file(path)


def _read_text(path: Path) -> str:
    """Read one configuration file as UTF-8 text with its line endings as the file holds them."""
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            return stream.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("configuration file is not readable UTF-8 text") from exc


def _read_toml_document(payload: str) -> TOMLDocument:
    """Parse one TOML document with its comments and key order intact."""
    try:
        return tomlkit.parse(payload)
    except TOMLKitError as exc:
        raise ValueError("configuration file is not valid TOML") from exc


def _decode_json_value(payload: str) -> JsonValue:
    """Decode one JSON literal, refusing JSON null and any non-finite number.

    The literal is the only value syntax a write accepts, so a caller cannot pass a bare word, a
    shell fragment, or a value the file's own type does not carry.
    """
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("configuration value must be one JSON literal") from exc
    if decoded is None:
        raise ValueError("configuration value must not be JSON null")
    _require_finite_numbers(decoded)
    return decoded


def _require_finite_numbers(value: JsonValue) -> None:
    """Refuse a NaN or an infinite number anywhere in one decoded value."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("configuration value must hold finite numbers")
    if isinstance(value, list):
        for item in value:
            _require_finite_numbers(item)
    elif isinstance(value, dict):
        for item in value.values():
            _require_finite_numbers(item)


def _require_retained_type(existing: JsonValue, decoded: JsonValue) -> None:
    """Require the decoded value to hold the broad type the key holds."""
    if isinstance(existing, bool):
        if not isinstance(decoded, bool):
            raise ValueError("configuration value must keep the key's boolean type")
        return
    if isinstance(existing, int):
        if isinstance(decoded, bool) or not isinstance(decoded, int):
            raise ValueError("configuration value must keep the key's integer type")
        return
    if isinstance(existing, float):
        if isinstance(decoded, bool) or not isinstance(decoded, (int, float)):
            raise ValueError("configuration value must keep the key's numeric type")
        return
    if isinstance(existing, str):
        if not isinstance(decoded, str):
            raise ValueError("configuration value must keep the key's string type")
        return
    if isinstance(existing, list):
        if not isinstance(decoded, list):
            raise ValueError("configuration value must keep the key's array type")
        return
    if isinstance(existing, dict):
        if not isinstance(decoded, dict):
            raise ValueError("configuration value must keep the key's table type")
        return
    raise ValueError("configuration key holds a value this editor does not accept")


def _toml_item(value: JsonValue) -> Item:
    """Build one TOML item, and write every mapping as an inline table."""
    if isinstance(value, dict):
        table: InlineTable = tomlkit.inline_table()
        for name, entry in value.items():
            table[name] = _toml_item(entry)
        return table
    if isinstance(value, list):
        array: Array = tomlkit.array()
        for entry in value:
            array.append(_toml_item(entry))
        return array
    if isinstance(value, (bool, int, float, str)):
        return tomlkit.item(value)
    raise ValueError("configuration value must be a boolean, number, string, array or table")


def _render_toml(document: TOMLDocument, key: str, value: JsonValue) -> str:
    """Return the TOML text with only the chosen key's value replaced.

    The parsed document holds every other key, its comments and its order, and an inline table is
    written as an inline table, so a replaced mapping value neither gains a section header nor
    detaches the keys that follow it.
    """
    document[key] = _toml_item(value)
    return tomlkit.dumps(document)


def _quote_environment_value(value: str) -> str:
    """Render one environment-file value in the single-quoted form the dotenv reader decodes."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _render_environment_binding(text: str, value: str) -> str:
    """Return one binding's text with its value token replaced and every other byte as it is.

    The installed dotenv reader reports where a quoted value ends. An unquoted value holds its
    literal text and the reader strips a trailing comment from the value it returns, so the returned
    value's own length marks the end of its token. A bare key gains its assignment before any
    trailing whitespace and comment.
    """
    quoted = _quote_environment_value(value)
    assignment = _ENVIRONMENT_ASSIGNMENT.match(text)
    if assignment is None:
        bare = _ENVIRONMENT_BARE_KEY.match(text)
        if bare is None:
            raise ValueError("environment-file assignment is not readable")
        return f"{text[: bare.end()]}={quoted}{text[bare.end() :]}"
    prefix = assignment.group("prefix")
    remainder = text[len(prefix) :]
    reader = DotenvReader(StringIO(remainder))
    parsed = parse_value(reader)
    if remainder[:1] in {"'", '"'}:
        token_end = len(prefix) + reader.position.chars
    else:
        token_end = len(prefix) + len(parsed)
    return f"{prefix}{quoted}{text[token_end:]}"


def _render_environment(payload: str, key: str, value: str) -> str:
    """Return the environment-file text with the one key's value replaced.

    The binding is located through the runtime's case-insensitive name, so a requested key of
    another case reaches the stored binding. Every other binding holds its exact bytes. The edited
    binding holds its leading blank lines, its optional ``export``, its key spelling, its
    surrounding whitespace, its trailing comment and its line ending.
    """
    offset = 0
    normalized = key.lower()
    for binding in parse_stream(StringIO(payload)):
        text = binding.original.string
        if binding.key is not None and binding.key.lower() == normalized:
            rendered = _render_environment_binding(text, value)
            return f"{payload[:offset]}{rendered}{payload[offset + len(text) :]}"
        offset += len(text)
    raise ValueError(f"configuration key is not present in {_ENVIRONMENT_FILE}")


def _owning_families(
    key: str, settings_families: tuple[type[ConfiguredSettings], ...]
) -> tuple[type[ConfiguredSettings], ...]:
    """Return every settings family whose validation aliases contain the edited key by name.

    The runtime lowercases environment names, so the comparison ignores case while the settings
    classes and every TOML document keep their spelling.
    """
    families = (*CONFIGURATION_SETTINGS_FAMILIES, *settings_families)
    normalized = key.lower()
    return tuple(
        family
        for family in families
        if normalized in {alias.lower() for alias in _settings_aliases(family)}
    )


def _validate_candidate(
    root: Path,
    *,
    file: str,
    key: str,
    documents: dict[str, dict[str, object]],
    local: dict[str, str | None],
    settings_families: tuple[type[ConfiguredSettings], ...],
) -> None:
    """Validate one candidate configuration, or refuse an unowned key.

    Only the families that own the edited key are built, so a candidate outside their aliases needs
    no unrelated value. A key of the environment file that no family owns carries its string and file
    grammar alone, and a key of a subsystem file that no family owns fails instead of claiming a
    validation.
    """
    families = _owning_families(key, settings_families)
    if not families:
        if file != _ENVIRONMENT_FILE:
            raise ValueError("configuration key is not owned by a settings family")
        return
    with configuration_candidate(root, documents=documents, local=local):
        for family in families:
            family()


def list_configuration_files() -> ConfigurationFilesReport:
    """Return the editable configuration files in composition order, reading nothing."""
    return ConfigurationFilesReport(files=_CONFIGURATION_FILES)


def read_configuration_file(file: str) -> ConfigurationFileReport:
    """Return every key of one listed configuration file as that file holds its value.

    A subsystem file is parsed as TOML, so a hub reference is returned as its table rather than
    resolved. The environment file is parsed into its assignments, and a bare key reports no value.
    Every value is reported as the file spells it.
    """
    listed = _require_listed_file(file)
    root = repository_root()
    path = _confined_path(root, listed)
    _require_regular_file(path)
    payload = _read_text(path)
    values: dict[str, JsonValue]
    if listed == _ENVIRONMENT_FILE:
        values = dict(parse_local_configuration(payload))
    else:
        values = dict(_read_toml_document(payload).unwrap())
    return ConfigurationFileReport(file=listed, values=values)


def set_configuration_value(
    file: str,
    key: str,
    value: str,
    *,
    settings_families: tuple[type[ConfiguredSettings], ...] = (),
) -> ConfigurationWriteReport:
    """Save one key of one listed configuration file after validating the candidate.

    ``value`` is one JSON literal over the broad type the key holds. Only the chosen key's text
    changes. A subsystem file is published with its own permission bits, and the environment file as
    mode 0600. A refused candidate writes no file. The acknowledgment names the file and the key.
    """
    listed = _require_listed_file(file)
    root = repository_root()
    path = _confined_path(root, listed)
    _require_regular_file(path)
    _require_source_files(root)
    payload = _read_text(path)
    decoded = _decode_json_value(value)
    if listed == _ENVIRONMENT_FILE:
        existing = parse_local_configuration(payload)
        stored_key = next((name for name in existing if name.lower() == key.lower()), None)
        if stored_key is None:
            raise ValueError(f"configuration key is not present in {_ENVIRONMENT_FILE}")
        if not isinstance(decoded, str):
            raise ValueError("an environment-file value must be a JSON string")
        rendered = _render_environment(payload, stored_key, decoded)
        candidate_local = parse_local_configuration(rendered)
        documents = read_configuration_documents(root)
    else:
        document = _read_toml_document(payload)
        values = document.unwrap()
        if key not in values:
            raise ValueError(f"configuration key is not present in {listed}")
        _require_retained_type(values[key], decoded)
        rendered = _render_toml(document, key, decoded)
        # The edited alias leaves the local mapping, so a local value cannot hide an invalid
        # subsystem-file candidate. The local mapping comes from the file itself, so a value a
        # runtime cache holds cannot stand in for the file's text. The comparison ignores case,
        # matching the runtime's lowercase environment names.
        normalized = key.lower()
        candidate_local = {
            name: entry
            for name, entry in read_candidate_local_configuration(root).items()
            if name.lower() != normalized
        }
        documents = read_configuration_documents(root, replacements={listed: rendered})
    _validate_candidate(
        root,
        file=listed,
        key=key,
        documents=documents,
        local=candidate_local,
        settings_families=settings_families,
    )
    mode = 0o600 if listed == _ENVIRONMENT_FILE else path.stat().st_mode & 0o777
    atomic_write_private_text(path, rendered, mode=mode)
    clear_configuration_caches()
    return ConfigurationWriteReport(file=listed, key=key)
