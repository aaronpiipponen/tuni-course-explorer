"""Immutable raw-capture envelopes, versioned manifests, and verified replay."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Collection, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
)
from course_explorer.hashing import json_sha256
from course_explorer.ingestion.source import (
    CapturedResponse,
    CurriculumPeriodRef,
    SourceObject,
)
from course_explorer.validation import SHA256_PATTERN as _SHA256

_RESPONSE_PATH = re.compile(r"^responses/[0-9a-f]{64}-[0-9a-f]{64}\.json\.gz$")


def _require_nonblank(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _require_sha256(value: str, field_name: str) -> str:
    _require_nonblank(value, field_name)
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hash")
    return value


def _require_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != datetime.min.replace(tzinfo=UTC).utcoffset():
        raise ValueError(f"{field_name} must be an aware UTC datetime")
    return value


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapturedObjectRecord(_ManifestModel):
    """Position and identity/hash evidence for one raw source object."""

    object_type: SourceObjectType
    source_object_id: str
    source_group_id: str
    response_item_index: int = Field(ge=0)
    source_hash: str

    _source_object_id = field_validator("source_object_id")(
        lambda value: _require_nonblank(value, "source_object_id")
    )
    _source_group_id = field_validator("source_group_id")(
        lambda value: _require_nonblank(value, "source_group_id")
    )
    _source_hash = field_validator("source_hash")(
        lambda value: _require_sha256(value, "source_hash")
    )


class CapturedResponseRecord(_ManifestModel):
    """Request identity, envelope identity, and contained object records."""

    request_path: str
    request_params: tuple[tuple[str, str], ...]
    response_path: str
    body_sha256: str
    body_size: int = Field(ge=0)
    object_type: SourceObjectType | None
    objects: tuple[CapturedObjectRecord, ...]

    _request_path = field_validator("request_path")(
        lambda value: _require_nonblank(value, "request_path")
    )

    @field_validator("response_path")
    @classmethod
    def validate_response_path(cls, value: str) -> str:
        if _RESPONSE_PATH.fullmatch(value) is None:
            raise ValueError("response_path must use the versioned response envelope format")
        return value

    _body_sha256 = field_validator("body_sha256")(
        lambda value: _require_sha256(value, "body_sha256")
    )

    @field_validator("request_params")
    @classmethod
    def validate_request_params(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        for key, parameter in value:
            _require_nonblank(key, "request parameter key")
            if not isinstance(parameter, str):
                raise ValueError("request parameter values must be strings")
        return value

    @field_validator("objects")
    @classmethod
    def validate_object_positions(
        cls, value: tuple[CapturedObjectRecord, ...]
    ) -> tuple[CapturedObjectRecord, ...]:
        positions = [record.response_item_index for record in value]
        if len(positions) != len(set(positions)):
            raise ValueError("response object positions must be unique")
        return value

    @model_validator(mode="after")
    def validate_object_type(self) -> Self:
        if self.object_type is None and self.objects:
            raise ValueError("evidence-only responses cannot contain object records")
        if any(record.object_type is not self.object_type for record in self.objects):
            raise ValueError("response object records must match response object type")
        return self


class CaptureManifest(_ManifestModel):
    """Versioned manifest authoritative for one immutable capture run and seed scope."""

    format_version: Literal[2]
    run_id: UUID
    status: IngestionRunStatus
    started_at: datetime
    finished_at: datetime | None
    raw_root_path: str
    periods: tuple[CurriculumPeriodRef, ...]
    responses: tuple[CapturedResponseRecord, ...]
    unresolved_course_group_ids: tuple[str, ...]
    unresolved_module_group_ids: tuple[str, ...]
    failure_type: str | None
    course_version_limit: int | None = Field(ge=1)
    seed_course_version_ids: tuple[str, ...]
    seed_selection_complete: bool

    _raw_root_path = field_validator("raw_root_path")(
        lambda value: _require_nonblank(value, "raw_root_path")
    )
    _started_at = field_validator("started_at")(lambda value: _require_utc(value, "started_at"))

    @field_validator("finished_at")
    @classmethod
    def validate_finished_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value, "finished_at")

    @field_validator("periods")
    @classmethod
    def validate_periods(
        cls, value: tuple[CurriculumPeriodRef, ...]
    ) -> tuple[CurriculumPeriodRef, ...]:
        period_ids = [period.id for period in value]
        if any(not isinstance(period.id, str) or not period.id.strip() for period in value):
            raise ValueError("period IDs must not be blank")
        if len(period_ids) != len(set(period_ids)):
            raise ValueError("period IDs must be unique")
        return value

    @field_validator("unresolved_course_group_ids", "unresolved_module_group_ids")
    @classmethod
    def validate_unresolved_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not isinstance(identifier, str) or not identifier.strip() for identifier in value):
            raise ValueError("unresolved group IDs must not be blank")
        if tuple(sorted(set(value))) != value:
            raise ValueError("unresolved group IDs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if (
            self.course_version_limit is not None
            or self.seed_course_version_ids
            or self.seed_selection_complete
        ):
            raise ValueError("bounded or seeded capture manifests are not supported")

        if self.status is IngestionRunStatus.RUNNING:
            if self.finished_at is not None or self.failure_type is not None:
                raise ValueError("running manifests cannot have finish or failure fields")
        elif self.status is IngestionRunStatus.COMPLETED:
            if self.finished_at is None or self.failure_type is not None:
                raise ValueError("completed manifests require only finished_at")
        elif self.status is IngestionRunStatus.FAILED:
            if self.finished_at is None or not self.failure_type:
                raise ValueError("failed manifests require finished_at and failure_type")

        request_keys: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        response_paths: set[str] = set()
        object_hashes: dict[tuple[SourceObjectType, str], str] = {}
        for response in self.responses:
            request_key = (response.request_path, response.request_params)
            if request_key in request_keys:
                raise ValueError("manifest contains duplicate request keys")
            request_keys.add(request_key)
            if response.response_path in response_paths:
                raise ValueError("manifest contains duplicate response paths")
            response_paths.add(response.response_path)
            for record in response.objects:
                object_key = (record.object_type, record.source_object_id)
                previous_hash = object_hashes.setdefault(object_key, record.source_hash)
                if previous_hash != record.source_hash:
                    raise ValueError("object identity has conflicting source hashes")
        return self


class ReplayedSourceObject(_ManifestModel):
    """One verified source object paired with its manifest provenance record."""

    record: CapturedObjectRecord
    response_path: str
    value: SourceObject


class ReplayedResponse(_ManifestModel):
    """One verified captured response paired with its manifest record."""

    record: CapturedResponseRecord
    body: bytes


def _request_hash(request_path: str, request_params: tuple[tuple[str, str], ...]) -> str:
    """Hash one ordered request identity for content-addressed envelope paths."""
    return hashlib.sha256(
        json.dumps(
            [request_path, request_params], separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def _object_hash(value: SourceObject) -> str:
    return json_sha256(value, ensure_ascii=False)


def _relative_posix(path: Path) -> str:
    return Path(os.path.relpath(path, Path.cwd())).as_posix()


def _resolve_raw_root(raw_data_root: Path) -> Path:
    """Resolve configured storage while rejecting symlinked path components."""
    configured = Path.cwd() / raw_data_root
    current = Path(configured.anchor)
    for part in configured.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError("raw data root must not contain symlinked path components")
    return configured.resolve()


def _resolve_manifest_path(raw_root: Path, manifest_path: Path) -> Path:
    """Resolve a manifest only after checking every user-supplied path component."""
    configured = Path.cwd() / manifest_path
    try:
        relative_parts = configured.relative_to(raw_root).parts
    except ValueError as exc:
        raise ValueError("manifest must be below configured raw data root") from exc
    current = raw_root
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            raise ValueError("manifest path must not contain symlinked components")
    resolved = configured.resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError as exc:
        raise ValueError("manifest must be below configured raw data root") from exc
    return resolved


def _manifest_json_bytes(manifest: CaptureManifest) -> bytes:
    value = {
        "format_version": manifest.format_version,
        "run_id": str(manifest.run_id),
        "status": manifest.status.value,
        "started_at": manifest.started_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "finished_at": (
            None
            if manifest.finished_at is None
            else manifest.finished_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ),
        "raw_root_path": manifest.raw_root_path,
        "periods": [
            {"id": period.id, "academic_year_start": period.academic_year_start}
            for period in manifest.periods
        ],
        "responses": [
            {
                "request_path": response.request_path,
                "request_params": [list(parameter) for parameter in response.request_params],
                "response_path": response.response_path,
                "body_sha256": response.body_sha256,
                "body_size": response.body_size,
                "object_type": None if response.object_type is None else response.object_type.value,
                "objects": [
                    {
                        "object_type": record.object_type.value,
                        "source_object_id": record.source_object_id,
                        "source_group_id": record.source_group_id,
                        "response_item_index": record.response_item_index,
                        "source_hash": record.source_hash,
                    }
                    for record in response.objects
                ],
            }
            for response in manifest.responses
        ],
        "unresolved_course_group_ids": list(manifest.unresolved_course_group_ids),
        "unresolved_module_group_ids": list(manifest.unresolved_module_group_ids),
        "failure_type": manifest.failure_type,
        "course_version_limit": manifest.course_version_limit,
        "seed_course_version_ids": list(manifest.seed_course_version_ids),
        "seed_selection_complete": manifest.seed_selection_complete,
    }
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


class RawCaptureStore:
    """Own immutable response envelopes and atomic versioned manifest publication."""

    def __init__(
        self,
        raw_root: Path,
        run_root: Path,
        manifest_path: Path,
        manifest: CaptureManifest,
        *,
        manifest_sha256: str,
    ):
        self._raw_root = raw_root
        self._run_root = run_root
        self._manifest_path = manifest_path
        self._manifest = manifest
        self._manifest_sha256 = manifest_sha256
        self._verified_manifest: CaptureManifest | None = None
        self._verified_response_count: int = 0

    @classmethod
    def create(
        cls,
        raw_data_root: Path,
        *,
        run_id: UUID | None = None,
        started_at: datetime | None = None,
    ) -> Self:
        raw_root = _resolve_raw_root(raw_data_root)
        raw_root.mkdir(parents=True, exist_ok=True)
        run_id = run_id or uuid4()
        started_at = started_at or datetime.now(UTC)
        started_at = _require_utc(started_at, "started_at")
        run_root = raw_root / f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}-{run_id}"
        run_root.mkdir()
        manifest_path = run_root / "manifest.json"
        manifest = CaptureManifest(
            format_version=2,
            run_id=run_id,
            status=IngestionRunStatus.RUNNING,
            started_at=started_at,
            finished_at=None,
            raw_root_path=_relative_posix(raw_root),
            periods=(),
            responses=(),
            unresolved_course_group_ids=(),
            unresolved_module_group_ids=(),
            failure_type=None,
            course_version_limit=None,
            seed_course_version_ids=(),
            seed_selection_complete=False,
        )
        manifest_sha256 = cls._write_manifest(manifest_path, manifest)
        return cls(
            raw_root,
            run_root,
            manifest_path,
            manifest,
            manifest_sha256=manifest_sha256,
        )

    @classmethod
    def open(cls, raw_data_root: Path, manifest_path: Path) -> Self:
        raw_root = _resolve_raw_root(raw_data_root)
        resolved_manifest = _resolve_manifest_path(raw_root, manifest_path)
        if resolved_manifest.name != "manifest.json":
            raise ValueError("manifest path must name manifest.json")
        try:
            payload = resolved_manifest.read_bytes()
        except OSError as exc:
            raise ValueError("manifest cannot be read") from exc
        manifest = CaptureManifest.model_validate_json(payload)
        if manifest.raw_root_path != _relative_posix(raw_root):
            raise ValueError("manifest raw root does not match configured raw data root")
        store = cls(
            raw_root,
            resolved_manifest.parent,
            resolved_manifest,
            manifest,
            manifest_sha256=hashlib.sha256(payload).hexdigest(),
        )
        return store

    @property
    def manifest(self) -> CaptureManifest:
        return self._manifest

    @property
    def manifest_sha256(self) -> str:
        """Return the digest of the published manifest bytes."""
        return self._manifest_sha256

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    @property
    def manifest_relative_path(self) -> str:
        return _relative_posix(self._manifest_path)

    @property
    def run_root(self) -> Path:
        return self._run_root

    @staticmethod
    def _write_manifest(manifest_path: Path, manifest: CaptureManifest) -> str:
        """Publish one manifest atomically and return the digest of its payload."""
        payload = _manifest_json_bytes(manifest)
        descriptor, temporary_path = tempfile.mkstemp(
            dir=manifest_path.parent, prefix=".manifest-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, manifest_path)
            directory_fd = os.open(manifest_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise
        return hashlib.sha256(payload).hexdigest()

    def _replace_manifest(self, **changes: object) -> None:
        candidate = CaptureManifest.model_validate(
            {**self._manifest.model_dump(mode="python"), **changes}
        )
        self._manifest_sha256 = self._write_manifest(self._manifest_path, candidate)
        previous = self._manifest
        self._manifest = candidate
        if self._verified_manifest is None:
            return
        if candidate.responses == previous.responses and candidate.status is previous.status:
            self._verified_manifest = candidate
        else:
            self._verified_manifest = None

    @staticmethod
    def _response_record(
        captured: CapturedResponse,
        response_path: str,
        body_sha256: str,
        object_type: SourceObjectType | None,
        objects: tuple[CapturedObjectRecord, ...],
    ) -> CapturedResponseRecord:
        return CapturedResponseRecord(
            request_path=captured.request_path,
            request_params=captured.request_params,
            response_path=response_path,
            body_sha256=body_sha256,
            body_size=len(captured.body),
            object_type=object_type,
            objects=objects,
        )

    @staticmethod
    def _object_records(
        body: bytes, object_type: SourceObjectType | None, objects: Sequence[SourceObject]
    ) -> tuple[CapturedObjectRecord, ...]:
        if object_type is None:
            if objects:
                raise ValueError("objects require an object type")
            return ()
        try:
            raw_objects = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("object response body must be valid JSON") from exc
        if not isinstance(raw_objects, list):
            raise ValueError("object response body must be a JSON list")
        records = RawCaptureStore._records_from_raw(raw_objects, object_type)
        expected: Counter[tuple[str, str]] = Counter()
        for value in objects:
            if not isinstance(value, dict):
                raise ValueError("source objects must be JSON objects")
            identifier = value.get("id")
            group_id = value.get("groupId")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError("source object ID must be non-blank")
            if not isinstance(group_id, str) or not group_id.strip():
                raise ValueError("source object groupId must be non-blank")
            expected[(identifier, group_id)] += 1
        actual = Counter((record.source_object_id, record.source_group_id) for record in records)
        if actual != expected:
            raise ValueError("raw object identity set does not match source response value")
        return records

    @staticmethod
    def _records_from_raw(
        raw_objects: list[object], object_type: SourceObjectType
    ) -> tuple[CapturedObjectRecord, ...]:
        """Build manifest records from complete raw items in their stored order."""
        records: list[CapturedObjectRecord] = []
        for index, value in enumerate(raw_objects):
            if not isinstance(value, dict):
                raise ValueError("raw object response item must be an object")
            identifier = value.get("id")
            group_id = value.get("groupId")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError("raw object ID must be non-blank")
            if not isinstance(group_id, str) or not group_id.strip():
                raise ValueError("raw object groupId must be non-blank")
            records.append(
                CapturedObjectRecord(
                    object_type=object_type,
                    source_object_id=identifier,
                    source_group_id=group_id,
                    response_item_index=index,
                    source_hash=_object_hash(value),
                )
            )
        return tuple(records)

    @staticmethod
    def _compressed_envelope(body: bytes) -> bytes:
        return gzip.compress(body, compresslevel=9, mtime=0)

    def _response_directory(self) -> Path:
        response_dir = self._run_root / "responses"
        if response_dir.is_symlink() or (response_dir.exists() and not response_dir.is_dir()):
            raise ValueError("response path is not a trusted directory")
        return response_dir

    def _prepare_checkpoint_record(
        self,
        captured: CapturedResponse,
        object_type: SourceObjectType | None,
        objects: Sequence[SourceObject],
    ) -> tuple[CapturedResponseRecord, str, bytes]:
        """Build one validated checkpoint record, its request hash, and deterministic envelope."""
        body_hash = hashlib.sha256(captured.body).hexdigest()
        request_hash = _request_hash(captured.request_path, captured.request_params)
        record = self._response_record(
            captured,
            f"responses/{request_hash}-{body_hash}.json.gz",
            body_hash,
            object_type,
            self._object_records(captured.body, object_type, objects),
        )
        return record, request_hash, self._compressed_envelope(captured.body)

    def _publish_envelope(
        self, request_hash: str, envelope_path: Path, expected_envelope: bytes
    ) -> None:
        """Write one exact content-addressed envelope, refusing a conflicting request body."""
        response_dir = self._response_directory()
        conflicting_paths = tuple(
            path for path in response_dir.glob(f"{request_hash}-*.json.gz") if path != envelope_path
        )
        if conflicting_paths:
            raise ValueError("request already has an envelope with different response bytes")
        try:
            with envelope_path.open("xb") as envelope:
                envelope.write(expected_envelope)
                envelope.flush()
                os.fsync(envelope.fileno())
        except FileExistsError:
            if envelope_path.read_bytes() != expected_envelope:
                raise ValueError("content-addressed envelope already contains different bytes")

    def checkpoint_responses(
        self,
        responses: Sequence[
            tuple[CapturedResponse, SourceObjectType | None, Sequence[SourceObject]]
        ],
        *,
        unresolved_course_group_ids: Collection[str] | None = None,
        unresolved_module_group_ids: Collection[str] | None = None,
    ) -> tuple[CapturedResponseRecord, ...]:
        """Write exact envelopes, then publish one validated response checkpoint."""
        if self._manifest.status is IngestionRunStatus.COMPLETED:
            raise ValueError("completed capture cannot accept responses")
        inputs = tuple(responses)
        request_keys = [
            (captured.request_path, captured.request_params) for captured, _, _ in inputs
        ]
        if len(request_keys) != len(set(request_keys)):
            raise ValueError("checkpoint contains duplicate request keys")
        existing_by_request = {
            (response.request_path, response.request_params): response
            for response in self._manifest.responses
        }
        records: list[CapturedResponseRecord] = []
        new_records: list[CapturedResponseRecord] = []
        published_directory = False
        for captured, object_type, objects in inputs:
            record, request_hash, expected_envelope = self._prepare_checkpoint_record(
                captured, object_type, objects
            )
            existing = existing_by_request.get((record.request_path, record.request_params))
            envelope_path = self._run_root / record.response_path
            if existing is not None:
                if existing != record:
                    raise ValueError("recorded request response metadata changed")
                self._verify_envelope(existing)
                records.append(existing)
                continue

            if not published_directory:
                self._response_directory().mkdir(exist_ok=True)
                published_directory = True
            self._publish_envelope(request_hash, envelope_path, expected_envelope)
            records.append(record)
            new_records.append(record)

        changes: dict[str, object] = {}
        if new_records:
            changes["responses"] = self._manifest.responses + tuple(new_records)
        if unresolved_course_group_ids is not None:
            changes["unresolved_course_group_ids"] = tuple(sorted(set(unresolved_course_group_ids)))
        if unresolved_module_group_ids is not None:
            changes["unresolved_module_group_ids"] = tuple(sorted(set(unresolved_module_group_ids)))
        if changes and any(
            value != getattr(self._manifest, field_name) for field_name, value in changes.items()
        ):
            self._replace_manifest(**changes)
        return tuple(records)

    def set_periods(self, periods: Sequence[CurriculumPeriodRef]) -> None:
        """Record selected source periods once and require exact equality on resume."""
        value = tuple(periods)
        if not value:
            raise ValueError("selected curriculum periods must not be empty")
        if self._manifest.periods:
            if self._manifest.periods != value:
                raise ValueError("selected curriculum periods changed on resume")
            return
        self._replace_manifest(periods=value)

    def mark_running(self) -> None:
        """Resume a failed run. An initial or running run is returned as-is."""
        if self._manifest.status is IngestionRunStatus.RUNNING:
            return
        if self._manifest.status is not IngestionRunStatus.FAILED:
            raise ValueError("only failed captures can return to running")
        self._replace_manifest(
            status=IngestionRunStatus.RUNNING, finished_at=None, failure_type=None
        )

    def mark_failed(self, error: BaseException) -> None:
        """Record failure lifecycle with exception type only."""
        failure_type = f"{type(error).__module__}.{type(error).__qualname__}"
        if self._manifest.status is IngestionRunStatus.FAILED:
            if self._manifest.failure_type == failure_type:
                return
            raise ValueError("failed capture has a different failure type")
        if self._manifest.status is not IngestionRunStatus.RUNNING:
            raise ValueError("only running captures can fail")
        self._replace_manifest(
            status=IngestionRunStatus.FAILED,
            finished_at=datetime.now(UTC),
            failure_type=failure_type,
        )

    def mark_completed(self) -> None:
        """Complete a running capture with one UTC finish timestamp."""
        if self._manifest.status is IngestionRunStatus.COMPLETED:
            return
        if self._manifest.status is not IngestionRunStatus.RUNNING:
            raise ValueError("only running captures can complete")
        self._replace_manifest(status=IngestionRunStatus.COMPLETED, finished_at=datetime.now(UTC))

    def _verify_envelope(self, response: CapturedResponseRecord) -> bytes:
        path = self._run_root / response.response_path
        if path.is_symlink():
            raise ValueError("referenced response envelope is a symlink")
        expected_path = (
            f"responses/{_request_hash(response.request_path, response.request_params)}"
            f"-{response.body_sha256}.json.gz"
        )
        if response.response_path != expected_path:
            raise ValueError("referenced response path hash does not match manifest")
        try:
            path.relative_to(self._run_root)
            compressed = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise ValueError("referenced response envelope is missing") from exc
        try:
            body = gzip.decompress(compressed)
        except (OSError, EOFError) as exc:
            raise ValueError("referenced response envelope is corrupt") from exc
        if compressed != self._compressed_envelope(body):
            raise ValueError("referenced response envelope is not deterministic gzip")
        if (
            len(body) != response.body_size
            or hashlib.sha256(body).hexdigest() != response.body_sha256
        ):
            raise ValueError("referenced response envelope hash or size does not match manifest")
        if response.object_type is not None:
            try:
                raw_objects = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("typed object response body is not valid JSON") from exc
            if not isinstance(raw_objects, list):
                raise ValueError("typed object response body must be a JSON list")
            records = self._records_from_raw(raw_objects, response.object_type)
            if records != response.objects:
                raise ValueError("referenced response object positions or hashes do not match")
        return body

    def _verify_response_directory(self, expected_paths: set[str]) -> None:
        """Check the response directory, orphan envelopes, and completed final-set identity."""
        response_dir = self._response_directory()
        final_paths: set[str] = set()
        if response_dir.exists():
            if not response_dir.is_dir():
                raise ValueError("response path is not a directory")
            for path in response_dir.iterdir():
                if path.is_symlink() or not path.is_file():
                    raise ValueError("response directory contains non-file evidence")
                if path.suffixes[-2:] != [".json", ".gz"]:
                    if self._manifest.status is IngestionRunStatus.COMPLETED:
                        raise ValueError("completed manifest has an unexpected non-envelope file")
                    continue
                relative = path.relative_to(self._run_root).as_posix()
                if _RESPONSE_PATH.fullmatch(relative) is None:
                    raise ValueError("response directory contains an invalid envelope path")
                final_paths.add(relative)
                if relative not in expected_paths:
                    if self._manifest.status is IngestionRunStatus.COMPLETED:
                        raise ValueError("completed manifest has an unreferenced envelope")
                    compressed = path.read_bytes()
                    try:
                        body = gzip.decompress(compressed)
                    except (OSError, EOFError) as exc:
                        raise ValueError("orphan response envelope is corrupt") from exc
                    if compressed != self._compressed_envelope(body):
                        raise ValueError("orphan response envelope is not deterministic gzip")
                    body_hash = path.name.removesuffix(".json.gz").split("-", maxsplit=1)[-1]
                    if hashlib.sha256(body).hexdigest() != body_hash:
                        raise ValueError("orphan response envelope body hash does not match path")
        if self._manifest.status is IngestionRunStatus.COMPLETED and final_paths != expected_paths:
            raise ValueError("completed manifest envelope set does not match filesystem")

    def verify(
        self,
        *,
        start_response_index: int = 0,
        before_response: Callable[[int, int], bool] | None = None,
    ) -> bool:
        """Verify manifest envelopes cooperatively from one response index.

        The requested offset is clamped to this instance's already checked contiguous prefix, so a
        reopened store checks from zero regardless of durable progress while a same-invocation
        caller resumes past envelopes this instance already verified. ``before_response(completed,
        total)`` is consulted before each envelope, and a ``False`` gate returns ``False`` without
        touching evidence. The response-directory, orphan, and final-set checks run only when every
        response was verified. A successful pass binds the store's invocation-local verified
        snapshot. An incomplete or failed pass leaves it unset.
        """
        self._verified_manifest = None
        responses = self._manifest.responses
        total = len(responses)
        if not 0 <= start_response_index <= total:
            raise ValueError("verification start index must be within the response list")
        actual_start = min(start_response_index, self._verified_response_count)
        self._verified_response_count = actual_start
        for index in range(actual_start, total):
            if before_response is not None and not before_response(index, total):
                return False
            self._verify_envelope(responses[index])
            self._verified_response_count = index + 1
        self._verify_response_directory({response.response_path for response in responses})
        self._verified_manifest = self._manifest
        return True

    def iter_objects(
        self, object_type: SourceObjectType | None = None
    ) -> Iterator[ReplayedSourceObject]:
        """Verify then replay source objects in raw response order."""
        for replayed_response in self.iter_responses():
            response = replayed_response.record
            body = replayed_response.body
            if not response.objects:
                continue
            raw_objects = json.loads(body)
            by_position = {index: value for index, value in enumerate(raw_objects)}
            for record in response.objects:
                if object_type is None or record.object_type is object_type:
                    yield ReplayedSourceObject(
                        record=record,
                        response_path=response.response_path,
                        value=by_position[record.response_item_index],
                    )

    def _read_envelope(self, response: CapturedResponseRecord) -> bytes:
        """Decompress one already-verified envelope without repeating trust checks."""
        return gzip.decompress((self._run_root / response.response_path).read_bytes())

    def iter_responses(self, *, request_path: str | None = None) -> Iterator[ReplayedResponse]:
        """Verify the current manifest once, then replay complete response envelopes in order."""
        if self._verified_manifest is not self._manifest:
            self.verify(start_response_index=self._verified_response_count)
        for response in self._manifest.responses:
            if request_path is not None and response.request_path != request_path:
                continue
            yield ReplayedResponse(record=response, body=self._read_envelope(response))


def discover_capture_manifests(raw_data_root: Path) -> tuple[Path, ...]:
    """Locate direct run manifests under the configured raw root without choosing one.

    Only ``<raw root>/<run>/manifest.json`` regular non-symlink files are candidates. Every
    candidate is strictly opened so an invalid manifest fails here. The returned paths use the
    same current-working-directory-relative form as ``RawCaptureStore.manifest_relative_path``
    so a caller can pass one straight back to ``RawCaptureStore.open``. This function only
    locates evidence: it never selects work, replays envelopes, writes provenance, or deletes
    anything.
    """
    raw_root = _resolve_raw_root(raw_data_root)
    if not raw_root.is_dir():
        return ()
    manifests: list[Path] = []
    for entry in raw_root.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            raise ValueError("raw data root contains a non-directory run entry")
        manifest_path = entry / "manifest.json"
        if manifest_path.is_symlink():
            raise ValueError("run manifest must not be a symlink")
        if not manifest_path.is_file():
            continue
        relative = Path(_relative_posix(manifest_path))
        RawCaptureStore.open(raw_data_root, relative)
        manifests.append(relative)
    return tuple(sorted(manifests, key=str))


def _path_contains(parent: Path, child: Path) -> bool:
    """Return whether ``child`` is ``parent`` or lies below it."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def prune_capture_runs(raw_data_root: Path, *, retained_manifest: Path | None) -> None:
    """Delete every owned capture run directory except the one retained manifest's directory.

    The configured raw root owns its direct run directories, so a nonretained directory is
    disposable regardless of its manifest's age or format. This never reads a manifest, an
    envelope or PostgreSQL. A supplied ``retained_manifest`` must name one direct run's
    ``manifest.json`` and preserves that whole directory, whether it holds capture-completed,
    failed or unfinished resumable work. The ``data/backups`` tree is never touched and an
    overlapping raw root is refused. Every immediate entry is validated as a non-symlink
    directory before anything is removed, so unsafe ownership fails loudly without partial
    deletion. The raw root itself is never removed. An absent root is an empty cleanup.
    """
    raw_root = _resolve_raw_root(raw_data_root)
    backups_root = (Path.cwd() / "data" / "backups").resolve()
    if _path_contains(backups_root, raw_root) or _path_contains(raw_root, backups_root):
        raise ValueError("raw data root must not overlap data/backups")
    if not raw_root.exists():
        return
    if not raw_root.is_dir():
        raise ValueError("raw data root must be a directory")

    retained_root: Path | None = None
    if retained_manifest is not None:
        resolved_manifest = _resolve_manifest_path(raw_root, retained_manifest)
        if resolved_manifest.name != "manifest.json":
            raise ValueError("retained manifest path must name manifest.json")
        parent = resolved_manifest.parent
        if parent.parent != raw_root:
            raise ValueError("retained manifest must be one direct capture run directory")
        retained_root = parent

    entries = list(raw_root.iterdir())
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            raise ValueError("raw data root contains a non-directory run entry")
    for entry in entries:
        if entry == retained_root:
            continue
        shutil.rmtree(entry)
