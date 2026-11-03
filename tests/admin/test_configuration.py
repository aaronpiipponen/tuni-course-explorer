"""Contracts for the configuration editor: file reads, one-key saves and refused candidates."""

from __future__ import annotations

import difflib
import json
import secrets
from pathlib import Path

import pytest
from pydantic import ValidationError

from course_explorer import administration, configuration
from course_explorer.config import (
    SETTINGS_SOURCE_MARKER,
    load_feedback_sender_settings,
    load_feedback_settings,
)
from course_explorer_admin import configuration as editor
from tests.support import write_example_config_tree

# Synthetic environment file. The database password and the loopback web host are values a
# subsystem-file save validates against, and every remaining line exercises one binding shape.
_SYNTHETIC_ENVIRONMENT = (
    "POSTGRES_PASSWORD=synthetic-database-password\n"
    "FEEDBACK_POSTGRES_PASSWORD=synthetic-feedback-password\n"
    "web_host=127.0.0.1\n"
    'SEARCH_TIER_PRIORITY=\'["exact_code","substring","fuzzy_name","semantic"]\'\n'
    "UNRELATED_SECRET=plain value\n"
    'DOUBLE_QUOTED_KEY="initial value"\n'
    "export EXPORTED_KEY = initial  # keeps its trailing comment\n"
    "BARE_KEY\n"
    "# a comment line of its own\n"
    "\n"
    "LITERAL_KEY='initial'\n"
    "MULTILINE_KEY='one'\n"
)

_TIER_METHODS = ["semantic", "exact_code", "substring", "fuzzy_name"]

_LOCAL_VARIANTS = [
    {
        "alias": "synthetic-128k-mtp",
        "port": 18140,
        "context_size": 131072,
        "kv_cache_type": "q4_0",
        "batch_size": 256,
        "ubatch_size": 256,
        "speculative_type": "draft-mtp,ngram-mod",
        "mtp_draft_n_max": 2,
        "achieved_max_context": 131072,
    },
    {
        "alias": "synthetic-160k",
        "port": 18160,
        "context_size": 163840,
        "kv_cache_type": "q4_0",
        "batch_size": 1024,
        "ubatch_size": 1024,
        "speculative_type": "ngram-mod",
        "achieved_max_context": 163840,
    },
]


def _editor_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Bind the editor and the file-source owner to one temporary checkout.

    The tree is the committed example configuration plus one synthetic environment file, so every
    family a subsystem-file save validates has its values and no device file is read.
    """
    root = write_example_config_tree(tmp_path / "checkout")
    (root / ".env").write_text(_SYNTHETIC_ENVIRONMENT, encoding="utf-8")
    (root / ".env").chmod(0o600)
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    configuration.clear_configuration_caches()
    return root


def _changed_region_bytes(before: bytes, after: bytes) -> tuple[bytes, bytes]:
    """Return the changed byte region of two texts.

    The regions follow line opcodes, so a replacement may hold a different number of lines than the
    text it replaces. The shared head and tail compare as bytes, so every line ending outside the
    region compares equal.
    """
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    changed = [
        opcode
        for opcode in difflib.SequenceMatcher(
            a=before_lines, b=after_lines, autojunk=False
        ).get_opcodes()
        if opcode[0] != "equal"
    ]
    assert len(changed) == 1
    _, first, last, other_first, other_last = changed[0]
    assert b"".join(before_lines[:first]) == b"".join(after_lines[:other_first])
    assert b"".join(before_lines[last:]) == b"".join(after_lines[other_last:])
    return b"".join(before_lines[first:last]), b"".join(after_lines[other_first:other_last])


def _rewrite_line_endings(path: Path, newline: str) -> None:
    """Rewrite one fixture file's line endings to the requested style."""
    text = path.read_bytes().decode("utf-8")
    path.write_bytes(text.replace("\r\n", "\n").replace("\n", newline).encode("utf-8"))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    ("file", "key", "literal"),
    [
        ("config/curriculum.toml", "CURRENT_ACADEMIC_YEAR", json.dumps("2027-2028")),
        ("config/curriculum.toml", "CAPTURE_CHECKPOINT_RESPONSE_COUNT", json.dumps(250)),
        ("config/database.toml", "EXAMPLE_POSTGRES_DB", json.dumps("course_explorer_example")),
        ("config/search.toml", "COMPARISON_OVERLAP_FLOOR", json.dumps(0.25)),
        (
            "config/search.toml",
            "SEARCH_TIER_PRIORITY",
            json.dumps(["semantic", "exact_code", "substring", "fuzzy_name"]),
        ),
        ("config/inference.toml", "INFERENCE_LOCAL_VARIANTS", json.dumps(_LOCAL_VARIANTS)),
        ("config/worker.toml", "ADMIN_POLL_INTERVAL_SECONDS", json.dumps(1.5)),
        ("config/worker.toml", "TRANSLATION_CONTROLLER_SSH_TARGET", json.dumps("synthetic-worker")),
        (
            "config/admin_web.toml",
            "ADMIN_SITE_WEB_SERVICE_UNIT",
            json.dumps("synthetic-site-web.service"),
        ),
        (
            "config/admin_web.toml",
            "ADMIN_SITE_WEB_SERVICE_SCOPE",
            json.dumps("system"),
        ),
        ("config/admin_web.toml", "ADMIN_WEB_PORT", json.dumps(18027)),
        ("config/feedback.toml", "FEEDBACK_POSTGRES_PORT", json.dumps(15433)),
        (
            "config/feedback.toml",
            "FEEDBACK_GITHUB_REPOSITORY",
            json.dumps("synthetic-owner/synthetic-repository"),
        ),
        ("config/feedback.toml", "FEEDBACK_GITHUB_VISIBILITY", json.dumps("private")),
        ("config/web.toml", "WEB_PORT", json.dumps(18026)),
        ("config/web.toml", "WEB_APP_URL", json.dumps("http://localhost:18037/")),
        ("config/admission.toml", "ADMISSION_SCORE_HEADROOM", json.dumps(0.55)),
    ],
)
def test_toml_configuration_save_preserves_file_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    file: str,
    key: str,
    literal: str,
    newline: str,
) -> None:
    """One subsystem-file key saves through its owner, preserving every other byte and the mode.

    The fixture carries either line ending, and the editor reads it as bytes. The read report carries
    the file's own values, an inline-table value is reported as a table, and the save revalidates the
    candidate through the affected settings families. Every byte outside the chosen key's own region
    is as the file held it, the other key values, the key order and the mode hold, and the
    acknowledgment repeats no value.
    """
    root = _editor_root(monkeypatch, tmp_path)
    path = root / file
    path.chmod(0o640)
    _rewrite_line_endings(path, newline)
    documents = configuration.read_configuration_documents(root)
    expected = json.loads(literal)

    assert editor.list_configuration_files().files == (*configuration.PUBLIC_CONFIG_FILES, ".env")
    report = editor.read_configuration_file(file)
    assert report.file == file
    assert report.values == documents[file]
    assert report.values[key] != expected

    before_bytes = path.read_bytes()
    acknowledgment = editor.set_configuration_value(file, key, literal)

    assert acknowledgment.model_dump() == {"schema_version": 1, "file": file, "key": key}
    after_bytes = path.read_bytes()
    replaced, replacement = _changed_region_bytes(before_bytes, after_bytes)
    assert replaced.startswith(f"{key} =".encode())
    assert replacement.startswith(f"{key} =".encode())
    assert path.stat().st_mode & 0o777 == 0o640

    saved = configuration.read_configuration_documents(root)[file]
    assert saved[key] == expected
    assert list(saved) == list(documents[file])
    for name, value in documents[file].items():
        if name != key:
            assert saved[name] == value


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    ("key", "literal", "original_line", "saved_line"),
    [
        (
            "UNRELATED_SECRET",
            json.dumps("other value"),
            "UNRELATED_SECRET=plain value\n",
            "UNRELATED_SECRET='other value'\n",
        ),
        (
            "WEB_HOST",
            json.dumps("127.0.0.1"),
            "web_host=127.0.0.1\n",
            "web_host='127.0.0.1'\n",
        ),
        (
            "DOUBLE_QUOTED_KEY",
            json.dumps("replacement"),
            'DOUBLE_QUOTED_KEY="initial value"\n',
            "DOUBLE_QUOTED_KEY='replacement'\n",
        ),
        (
            "EXPORTED_KEY",
            json.dumps("replacement"),
            "export EXPORTED_KEY = initial  # keeps its trailing comment\n",
            "export EXPORTED_KEY = 'replacement'  # keeps its trailing comment\n",
        ),
        ("BARE_KEY", json.dumps("added value"), "BARE_KEY\n", "BARE_KEY='added value'\n"),
        (
            "LITERAL_KEY",
            json.dumps("a\\b'c #$ {}"),
            "LITERAL_KEY='initial'\n",
            "LITERAL_KEY='a\\\\b\\'c #$ {}'\n",
        ),
        (
            "MULTILINE_KEY",
            json.dumps("first line\nsecond line"),
            "MULTILINE_KEY='one'\n",
            "MULTILINE_KEY='first line\nsecond line'\n",
        ),
        (
            "SEARCH_TIER_PRIORITY",
            json.dumps(json.dumps(_TIER_METHODS, separators=(",", ":"))),
            'SEARCH_TIER_PRIORITY=\'["exact_code","substring","fuzzy_name","semantic"]\'\n',
            'SEARCH_TIER_PRIORITY=\'["semantic","exact_code","substring","fuzzy_name"]\'\n',
        ),
        ("GENERATED_PASSWORDS", "null", "", ""),
    ],
)
def test_environment_configuration_save_preserves_literal_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    key: str,
    literal: str,
    original_line: str,
    saved_line: str,
    newline: str,
) -> None:
    """One environment-file key saves as literal text, and the rest of the file is untouched.

    The fixture carries either line ending, and every comparison is a byte comparison. The read
    reports plain text. The chosen binding is located through the runtime's case-insensitive names,
    so a differently cased requested key saves the stored spelling. The chosen token alone changes,
    so the blank prefix, an optional ``export``, the key spelling, the surrounding whitespace, a
    trailing comment and the line ending all hold, and a literal hash, dollar, brace, backslash,
    quote or line break is literal. A value of an owned complex field is the JSON string the mapping
    source decodes, and publication is 0600.
    """
    root = _editor_root(monkeypatch, tmp_path)
    path = root / ".env"
    if key == "GENERATED_PASSWORDS":
        # The self-host workflow generates both database passwords and saves each through this same
        # owner. Every unrelated binding keeps its value, publication is 0600, and the
        # acknowledgment never echoes a generated secret.
        before = configuration.parse_local_configuration(path.read_text(encoding="utf-8"))
        generated = {
            name: secrets.token_urlsafe(32)
            for name in ("POSTGRES_PASSWORD", "FEEDBACK_POSTGRES_PASSWORD")
        }
        acknowledgments: list[object] = []
        for name, value in generated.items():
            acknowledgments.append(editor.set_configuration_value(".env", name, json.dumps(value)))
        after = configuration.parse_local_configuration(path.read_text(encoding="utf-8"))
        assert path.stat().st_mode & 0o777 == 0o600
        for name, value in generated.items():
            assert after[name] == value
            for acknowledgment in acknowledgments:
                assert value not in acknowledgment.model_dump_json()
        for name, value in before.items():
            if name not in generated:
                assert after[name] == value
        assert after["UNRELATED_SECRET"] == "plain value"
        return
    path.chmod(0o644)
    _rewrite_line_endings(path, newline)
    before_bytes = path.read_bytes()
    expected = json.loads(literal)

    acknowledgment = editor.set_configuration_value(".env", key, literal)

    after_bytes = path.read_bytes()
    assert after_bytes == before_bytes.replace(
        (original_line.removesuffix("\n") + newline).encode("utf-8"),
        (saved_line.removesuffix("\n") + newline).encode("utf-8"),
    )
    assert acknowledgment.model_dump() == {"schema_version": 1, "file": ".env", "key": key}
    assert path.stat().st_mode & 0o777 == 0o600

    values = editor.read_configuration_file(".env").values
    stored_key = next(name for name in values if name.lower() == key.lower())
    assert values[stored_key] == expected
    assert values == configuration.parse_local_configuration(after_bytes.decode("utf-8"))
    for name, value in configuration.parse_local_configuration(
        before_bytes.decode("utf-8")
    ).items():
        if name.lower() != key.lower():
            assert values[name] == value


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    ("key", "literal", "expected"),
    [
        (
            "FEEDBACK_POSTGRES_PASSWORD",
            json.dumps("synthetic-inserted-feedback-password"),
            "synthetic-inserted-feedback-password",
        ),
        (
            "FEEDBACK_GITHUB_TOKEN",
            json.dumps("synthetic-inserted-sender-token"),
            "synthetic-inserted-sender-token",
        ),
        ("FEEDBACK_POSTGRES_PASSWORD", json.dumps(""), None),
        ("FEEDBACK_GITHUB_TOKEN", json.dumps(""), None),
    ],
)
def test_environment_save_inserts_an_owned_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    key: str,
    literal: str,
    expected: str | None,
    newline: str,
) -> None:
    """One save appends an absent owned environment credential, and the owning family loads it.

    The fixture carries both database passwords and no sender token. The file holds either line
    ending, and every comparison is a byte comparison. The blank value is refused by the owning
    family before any file changes.
    """
    root = _editor_root(monkeypatch, tmp_path)
    path = root / ".env"
    _rewrite_line_endings(path, newline)
    payload = path.read_bytes().decode("utf-8")
    path.write_bytes(
        payload.replace(
            f"FEEDBACK_POSTGRES_PASSWORD=synthetic-feedback-password{newline}", ""
        ).encode("utf-8")
    )
    before_bytes = path.read_bytes()

    if expected is None:
        with pytest.raises(ValidationError):
            editor.set_configuration_value(".env", key, literal)
        assert path.read_bytes() == before_bytes
        return

    acknowledgment = editor.set_configuration_value(".env", key, literal)

    assert acknowledgment.model_dump() == {
        "schema_version": 1,
        "file": ".env",
        "key": key,
    }
    expected_bytes = before_bytes + (f"{key}='{expected}'" + newline).encode()
    assert path.read_bytes() == expected_bytes
    assert path.stat().st_mode & 0o777 == 0o600

    monkeypatch.delenv(SETTINGS_SOURCE_MARKER, raising=False)
    monkeypatch.delenv(key, raising=False)
    configuration.clear_configuration_caches()
    if key == "FEEDBACK_GITHUB_TOKEN":
        token = load_feedback_sender_settings().feedback_github_token
    else:
        token = load_feedback_settings().feedback_postgres_password
    assert token.get_secret_value() == expected


_REFUSED_CASES: dict[str, tuple[str, str, str]] = {
    "unlisted-file": ("config/wiki.json", "WEB_PORT", json.dumps(18026)),
    "traversal": ("../.env", "WEB_HOST", json.dumps("127.0.0.1")),
    "missing-key": ("config/web.toml", "NOT_A_CONFIGURED_KEY", json.dumps(1)),
    "json-null": ("config/web.toml", "WEB_PORT", "null"),
    "non-finite-number": ("config/web.toml", "WEB_PORT", "Infinity"),
    "boolean-for-port": ("config/web.toml", "WEB_PORT", "true"),
    "loopback-beside-local-value": ("config/web.toml", "WEB_HOST", json.dumps("0.0.0.0")),
    "loopback-beside-process-value": ("config/web.toml", "WEB_HOST", json.dumps("0.0.0.0")),
    "admin-non-loopback-beside-process-value": (
        "config/admin_web.toml",
        "ADMIN_WEB_HOST",
        json.dumps("0.0.0.0"),
    ),
    "stale-local-peer": ("config/web.toml", "WEB_PORT", json.dumps(18026)),
    "duplicate-local-for-toml": ("config/web.toml", "WEB_PORT", json.dumps(18026)),
    "lowercase-local-alias-for-toml": (
        "config/web.toml",
        "WEB_HOST",
        json.dumps("0.0.0.0"),
    ),
    "malformed-local-for-toml": ("config/web.toml", "WEB_PORT", json.dumps(18026)),
    "academic-year-order": (
        "config/curriculum.toml",
        "KORI_FIRST_ACADEMIC_YEAR",
        json.dumps("2027-2028"),
    ),
    "score-line-order": (
        "config/admission.toml",
        "ADMISSION_SCORE_RELEASE",
        json.dumps(1.10),
    ),
    "unstructured-tier-priority": (
        "config/search.toml",
        "SEARCH_TIER_PRIORITY",
        json.dumps(["exact_code", "substring", "fuzzy_name"]),
    ),
    "app-url-query-marker": (
        "config/web.toml",
        "WEB_APP_URL",
        json.dumps("https://example.org/?"),
    ),
    "app-url-fragment-marker": (
        "config/web.toml",
        "WEB_APP_URL",
        json.dumps("https://example.org/#"),
    ),
    "app-url-remote-plain-http": (
        "config/web.toml",
        "WEB_APP_URL",
        json.dumps("http://example.org/"),
    ),
    "lowercase-owned-invalid-environment-value": (
        ".env",
        "WEB_HOST",
        json.dumps("0.0.0.0"),
    ),
    "non-string-environment-value": (".env", "WEB_HOST", json.dumps(12)),
    "unowned-absent-environment-key": (".env", "UNOWNED_ABSENT_KEY", json.dumps("value")),
    "non-credential-environment-key": (".env", "WEB_PORT", json.dumps("18026")),
    "differently-cased-duplicate-binding": (
        ".env",
        "WEB_HOST",
        json.dumps("127.0.0.1"),
    ),
    "duplicate-environment-assignment": (".env", "WEB_HOST", json.dumps("127.0.0.1")),
    "symlinked-environment-file": (".env", "WEB_HOST", json.dumps("127.0.0.1")),
    "symlinked-directory": ("config/web.toml", "WEB_PORT", json.dumps(18026)),
}


@pytest.mark.parametrize("case", sorted(_REFUSED_CASES))
def test_configuration_write_refuses_invalid_or_unconfined_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    """One refused save per case leaves the file, an outside file and the directories as they were.

    The cases are an unlisted path, a traversal, a missing key, a JSON null, a non-finite number, a
    boolean for a port, a non-loopback host beside a valid local value and beside a valid process
    value, a non-loopback administration host beside a valid process value, a cached local value
    beside a changed file, a duplicated and a malformed local input, and a lowercase local alias
    that must not mask an invalid subsystem-file candidate. Further cases are an academic-year
    order, an invalid structured value, an App URL carrying a query or fragment marker or a remote
    plain-HTTP address, a non-string environment value, an unowned absent environment key, an owned
    non-credential environment key, a lowercase owned environment value that its validator refuses,
    a differently cased duplicate environment binding, a duplicated environment assignment, a
    symlinked environment file, a symlinked directory and a score line above a sibling line. Every
    case runs the real validators and files, refuses before publication, and leaves no temporary
    file behind. A subsystem-file save reads the local input freshly, so neither a cached value nor
    an ambiguous file can mask the candidate, and a malformed input reports nothing.
    """
    root = _editor_root(monkeypatch, tmp_path)
    file, key, literal = _REFUSED_CASES[case]
    outside = tmp_path / "outside-sentinel.txt"
    outside.write_text("OUTSIDE_SENTINEL=keep\n", encoding="utf-8")
    environment = root / ".env"
    if case == "loopback-beside-local-value":
        environment.write_text(
            environment.read_text(encoding="utf-8").replace(
                "web_host=127.0.0.1\n", "WEB_HOST=127.0.0.1\n"
            ),
            encoding="utf-8",
        )
    if case == "loopback-beside-process-value":
        monkeypatch.setenv("WEB_HOST", "127.0.0.1")
    if case == "admin-non-loopback-beside-process-value":
        monkeypatch.setenv("ADMIN_WEB_HOST", "127.0.0.1")
    if case == "stale-local-peer":
        configuration.read_local_configuration(root)
        environment.write_text(
            environment.read_text(encoding="utf-8").replace(
                "web_host=127.0.0.1\n", "web_host=0.0.0.0\n"
            ),
            encoding="utf-8",
        )
    if case == "duplicate-local-for-toml":
        environment.write_text(
            environment.read_text(encoding="utf-8") + "WEB_HOST=127.0.0.1\n", encoding="utf-8"
        )
    if case == "differently-cased-duplicate-binding":
        environment.write_text(
            environment.read_text(encoding="utf-8") + "WEB_HOST=127.0.0.2\n", encoding="utf-8"
        )
    if case == "malformed-local-for-toml":
        environment.write_text(
            environment.read_text(encoding="utf-8") + 'UNTERMINATED_VALUE="no closing quote\n',
            encoding="utf-8",
        )
    if case == "duplicate-environment-assignment":
        environment.write_text(
            environment.read_text(encoding="utf-8") + "WEB_HOST=127.0.0.2\nWEB_HOST=127.0.0.3\n",
            encoding="utf-8",
        )
    if case == "symlinked-environment-file":
        outside.write_text(environment.read_text(encoding="utf-8"), encoding="utf-8")
        environment.unlink()
        environment.symlink_to(outside)
    if case == "symlinked-directory":
        (root / "config").rename(root / "config-real")
        (root / "config").symlink_to(root / "config-real")

    sources = (*configuration.PUBLIC_CONFIG_FILES, ".env")
    before_bytes = {name: (root / name).read_bytes() for name in sources}
    before_outside = outside.read_text(encoding="utf-8")
    before_entries = sorted(entry.name for entry in root.iterdir())
    before_config = sorted(entry.name for entry in (root / "config").iterdir())

    with pytest.raises(ValueError) as refusal:
        editor.set_configuration_value(file, key, literal)
    if case == "non-credential-environment-key":
        assert "configuration key is not a credential" in str(refusal.value)

    assert {name: (root / name).read_bytes() for name in sources} == before_bytes
    assert outside.read_text(encoding="utf-8") == before_outside
    assert sorted(entry.name for entry in root.iterdir()) == before_entries
    assert sorted(entry.name for entry in (root / "config").iterdir()) == before_config
    if case == "symlinked-environment-file":
        assert (root / ".env").is_symlink()
    if case == "malformed-local-for-toml":
        captured = capsys.readouterr()
        assert captured.out == "" and captured.err == ""
        assert caplog.records == []
