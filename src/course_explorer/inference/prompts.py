"""Versioned baseline prompt pack for the complete-target-result inference pass.

The packed system prompt and curated real-catalogue examples are single-sourced versioned
artifacts below this package's module root. The pack's content hash is part of the
retained-session configuration hash, and a recorded run carries the prompt version. Callers
assemble a packet with ``examples_for_target``, which omits any example whose answer is the
target itself.
"""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, field_validator

from course_explorer.enums import TeachingTextOrigin
from course_explorer.hashing import parse_strict_json
from course_explorer.inference.domain import InferenceTargetResultV2
from course_explorer.validation import require_sha256 as _require_sha256
from course_explorer.validation import require_text as _require_text

_SUPPORTED_VERSIONS = ("v9",)


class _PromptModel(BaseModel):
    """Frozen, closed, strict DTO base for the versioned prompt contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PromptCourse(_PromptModel):
    """One target or candidate teaching descriptor supplied to the model.

    Only teaching fields with explicit official/derived provenance are retained. Official
    prerequisite text and additional-information fields are absent from this
    contract so a target's official answer can never enter a packet through a prompt model.
    """

    course_id: str
    course_code: str
    name: str
    name_origin: TeachingTextOrigin
    content: str
    content_origin: TeachingTextOrigin
    learning_outcomes: tuple[str, ...]
    learning_outcomes_origin: TeachingTextOrigin | None

    @field_validator("course_id", "course_code", "name", "content")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Require meaningful identity and teaching text."""
        return _require_text(value, "prompt course field")

    @field_validator("learning_outcomes")
    @classmethod
    def validate_learning_outcomes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require each provided learning outcome to be meaningful."""
        for outcome in value:
            _require_text(outcome, "learning outcome")
        return value

    def model_post_init(self, _context: object) -> None:
        """Require an origin exactly when learning outcomes are provided."""
        if self.learning_outcomes and self.learning_outcomes_origin is None:
            raise ValueError("provided learning outcomes require learning_outcomes_origin")
        if not self.learning_outcomes and self.learning_outcomes_origin is not None:
            raise ValueError("learning_outcomes_origin requires provided learning outcomes")


class PromptExample(_PromptModel):
    """One curated worked example: its target, candidates, and accepted complete result."""

    name: str
    explanation: str
    target: PromptCourse
    candidates: tuple[PromptCourse, ...]
    result: InferenceTargetResultV2

    @field_validator("name", "explanation")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Require meaningful example identity and explanation."""
        return _require_text(value, "prompt example field")

    @field_validator("candidates")
    @classmethod
    def validate_candidates(cls, value: tuple[PromptCourse, ...]) -> tuple[PromptCourse, ...]:
        """Require at least one candidate and unique candidate identities."""
        if not value:
            raise ValueError("prompt examples must provide at least one candidate")
        ids = [course.course_id for course in value]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate course ids must be unique within one example")
        codes = [course.course_code for course in value]
        if len(codes) != len(set(codes)):
            raise ValueError("candidate course codes must be unique within one example")
        return value

    def model_post_init(self, _context: object) -> None:
        """Reject a target repeated among its own candidates."""
        candidate_ids = {course.course_id for course in self.candidates}
        candidate_codes = {course.course_code for course in self.candidates}
        if self.target.course_id in candidate_ids:
            raise ValueError("the target course must not also be a candidate")
        if self.target.course_code in candidate_codes:
            raise ValueError("the target course code must not also be a candidate code")


class PromptPack(_PromptModel):
    """One content-hashed versioned prompt pack: system prompt plus curated examples."""

    version: str
    system_prompt: str
    examples: tuple[PromptExample, ...]
    content_sha256: str

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """Require a meaningful literal version identifier."""
        return _require_text(value, "prompt pack version")

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, value: str) -> str:
        """Require a meaningful system prompt."""
        return _require_text(value, "system prompt")

    @field_validator("content_sha256")
    @classmethod
    def validate_content_sha256(cls, value: str) -> str:
        """Require a full lowercase content digest."""
        return _require_sha256(value, "prompt pack content_sha256")

    @field_validator("examples")
    @classmethod
    def validate_examples(cls, value: tuple[PromptExample, ...]) -> tuple[PromptExample, ...]:
        """Require examples, unique names, and unique target identities across the pack."""
        if not value:
            raise ValueError("prompt packs must provide at least one example")
        names = [example.name for example in value]
        if len(names) != len(set(names)):
            raise ValueError("prompt example names must be unique")
        target_ids = [example.target.course_id for example in value]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("prompt example target ids must be unique")
        return value

    def examples_for_target(self, target_course_id: str) -> tuple[PromptExample, ...]:
        """Return file-ordered examples excluding any whose answer is the current target.

        Packet assembly must use this method rather than ``examples`` directly so the current
        target's curated answer never leaks into its own prompt.
        """
        _require_text(target_course_id, "target_course_id")
        return tuple(
            example for example in self.examples if example.target.course_id != target_course_id
        )


_EXAMPLES_ADAPTER = TypeAdapter(tuple[PromptExample, ...])


def _load_bytes(version: str, name: str) -> bytes:
    """Read one versioned prompt artifact from installed package resources, never from CWD."""
    resource = resources.files("course_explorer.inference").joinpath("prompts", version, name)
    if not isinstance(resource, Path):
        raise ValueError(f"prompt artifact {name} is not a readable package resource")
    return resource.read_bytes()


def _content_sha256(system_bytes: bytes, examples_bytes: bytes) -> str:
    """Return the recorded digest over both versioned prompt artifact byte sequences."""
    digest = hashlib.sha256()
    digest.update(system_bytes)
    digest.update(b"\0")
    digest.update(examples_bytes)
    return digest.hexdigest()


def load_prompt_pack(version: str) -> PromptPack:
    """Load one supported versioned prompt pack from package resources without repairing it."""
    if version not in _SUPPORTED_VERSIONS:
        raise ValueError(f"prompt pack version must be one of {_SUPPORTED_VERSIONS}")
    system_bytes = _load_bytes(version, "system.md")
    examples_bytes = _load_bytes(version, "examples.json")
    try:
        system_prompt = system_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("versioned system prompt must be UTF-8") from exc
    try:
        parsed = parse_strict_json(examples_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("versioned prompt examples are not valid JSON") from exc
    if not isinstance(parsed, list):
        raise ValueError("versioned prompt examples must be a top-level JSON array")
    try:
        examples = _EXAMPLES_ADAPTER.validate_json(examples_bytes, strict=True)
    except ValidationError as exc:
        raise ValueError("versioned prompt examples violate the prompt pack schema") from exc
    return PromptPack(
        version=version,
        system_prompt=system_prompt,
        examples=examples,
        content_sha256=_content_sha256(system_bytes, examples_bytes),
    )
