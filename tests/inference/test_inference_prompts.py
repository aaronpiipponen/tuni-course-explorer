"""Network-free contract tests for the versioned prompt pack."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from course_explorer.inference.domain import (
    parse_target_result,
)
from course_explorer.inference.prompts import load_prompt_pack

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "course_explorer" / "inference"
V9_PACK_DIGEST = "ca5941d8979e694e68181940e3466cf4e8878e3cbb91497fb84021ed09870eb3"


def test_prompt_packs_load_hashed_resources_independent_of_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Loading is package-relative, content-hashed, and independent of the process working directory."""
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "prompts").exists()

    system_path = PACKAGE_ROOT / "prompts" / "v9" / "system.md"
    examples_path = PACKAGE_ROOT / "prompts" / "v9" / "examples.json"
    pack = load_prompt_pack("v9")

    assert pack.version == "v9"
    assert pack.system_prompt.strip()
    assert pack.examples
    assert (
        pack.content_sha256
        == hashlib.sha256(system_path.read_bytes() + b"\0" + examples_path.read_bytes()).hexdigest()
    )
    assert pack.content_sha256 == V9_PACK_DIGEST
    for raw_example in json.loads(examples_path.read_text(encoding="utf-8")):
        parse_target_result(json.dumps(raw_example["result"], ensure_ascii=False), "v2")

    with pytest.raises(ValueError):
        load_prompt_pack("v99")


def test_prompt_contract_excludes_current_target_official_labels() -> None:
    """No prompt model, example, or system text carries an official-target label field."""
    pack = load_prompt_pack("v9")
    forbidden = ("official_prerequisite", "official_prerequisites", "prerequisite_text")
    serialized = pack.system_prompt + "".join(
        example.model_dump_json() for example in pack.examples
    )
    for name in forbidden:
        assert name not in serialized


def test_prompt_examples_for_target_omits_matching_answer() -> None:
    """The first dev target sees the other examples in file order. Unknown targets see all."""
    pack = load_prompt_pack("v9")
    all_ids = [example.target.course_id for example in pack.examples]
    target_id = all_ids[0]

    returned = pack.examples_for_target(target_id)
    assert [example.target.course_id for example in returned] == [
        other for other in all_ids if other != target_id
    ]

    assert pack.examples_for_target("unknown-course") == pack.examples
