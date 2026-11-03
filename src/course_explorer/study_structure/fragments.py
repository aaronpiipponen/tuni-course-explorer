"""Disk fragments of the projected study-structure roots of one serving artifact build.

The fragment file stores one entry per canonical module root: the projected root payload, an
unavailable marker, or a version-selection marker. It is keyed by the serving dataset and academic
year, written by the artifact build, and mapped read-only by every worker. A root that
the file does not hold, or a request that supplies explicit module versions, is read through the
batched service instead.
"""

from __future__ import annotations

import json
import mmap
import os
import struct
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from course_explorer.study_structure.service import (
    StudyStructureBatch,
    StudyStructureModule,
    StudyStructureService,
)

# Fragment file identity: the magic bytes and format version the reader checks, and the name the
# artifact build writes under its build directory.
MAGIC = b"CSTFRAG1"
FORMAT_VERSION = 1
FILE_NAME = "study-fragments.bin"

_ROOT = 0
_UNAVAILABLE = 1
_SELECTION = 2


class StudyFragmentBuildReport(BaseModel):
    """The fragment file's root composition, size and build cost."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    roots: int
    projectable: int
    unavailable: int
    selection_required: int
    bytes: int
    build_wall_seconds: float
    build_core_seconds: float


@dataclass(frozen=True)
class _Entry:
    kind: int
    offset: int
    length: int


def _write_text(buffer: bytearray, value: str) -> None:
    encoded = value.encode()
    buffer += struct.pack("<I", len(encoded))
    buffer += encoded


class StudyFragmentStore:
    """One opened fragment file mapped read-only with its per-root entry index.

    Every worker maps the same file, so the page cache holds one copy instead of one Python bytes
    copy per worker. A decoded root payload is materialized only when a request asks for that root.
    """

    def __init__(self, data: mmap.mmap, entries: dict[str, _Entry]) -> None:
        self._data = data
        self._entries = entries

    @classmethod
    def build(
        cls,
        service: StudyStructureService,
        root_group_ids: Collection[str],
        *,
        dataset_key: str,
        academic_year_start: int,
        path: Path,
    ) -> StudyFragmentBuildReport:
        """Project every requested root, write one fragment entry per root and replace the file."""
        started_wall = time.perf_counter()
        started_cpu = time.process_time()
        roots = tuple(dict.fromkeys(root_group_ids))
        body = bytearray(MAGIC + struct.pack("<Ii", FORMAT_VERSION, academic_year_start))
        _write_text(body, dataset_key)
        body += struct.pack("<I", len(roots))
        entries: dict[str, _Entry] = {}
        projectable = 0
        unavailable = 0
        selection_required = 0
        for start in range(0, len(roots), 1000):
            batch = roots[start : start + 1000]
            result = service.read_many(batch, allow_unavailable=True)
            by_root = {root.module.group_id: root for root in result.roots}
            absent = set(result.unavailable_root_group_ids)
            needing_selection = set(result.version_selection_required)
            for root in batch:
                if root in by_root:
                    payload = by_root[root].model_dump_json().encode()
                    kind = _ROOT
                    projectable += 1
                elif root in needing_selection:
                    payload = b""
                    kind = _SELECTION
                    selection_required += 1
                elif root in absent:
                    payload = b""
                    kind = _UNAVAILABLE
                    unavailable += 1
                else:
                    raise ValueError(
                        f"study structure root {root} was neither projected nor reported "
                        "unavailable"
                    )
                entries[root] = _Entry(kind, len(body), len(payload))
                body += payload
        index = json.dumps(
            {root: [entry.kind, entry.offset, entry.length] for root, entry in entries.items()},
            separators=(",", ":"),
        ).encode()
        body += index
        body += struct.pack("<I", len(index))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        temporary.write_bytes(body)
        os.replace(temporary, path)
        return StudyFragmentBuildReport(
            path=path.as_posix(),
            roots=len(roots),
            projectable=projectable,
            unavailable=unavailable,
            selection_required=selection_required,
            bytes=len(body),
            build_wall_seconds=time.perf_counter() - started_wall,
            build_core_seconds=time.process_time() - started_cpu,
        )

    @classmethod
    def open(cls, path: Path, *, dataset_key: str, academic_year_start: int) -> StudyFragmentStore:
        """Map one fragment file read-only and refuse another dataset or academic year."""
        with path.open("rb") as handle:
            try:
                data = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            except ValueError as exc:
                raise ValueError(f"study fragment file {path} is empty") from exc
        try:
            if len(data) < len(MAGIC) + 12 or data[: len(MAGIC)] != MAGIC:
                raise ValueError(f"study fragment file {path} has an invalid header")
            version, year = struct.unpack_from("<Ii", data, len(MAGIC))
            if version != FORMAT_VERSION:
                raise ValueError(f"study fragment file {path} has an unsupported format version")
            offset = len(MAGIC) + 8
            (length,) = struct.unpack_from("<I", data, offset)
            offset += 4
            key = data[offset : offset + length].decode()
            offset += length
            if year != academic_year_start or key != dataset_key:
                raise ValueError(
                    f"study fragment file {path} belongs to another dataset or academic year"
                )
            (root_count,) = struct.unpack_from("<I", data, offset)
            offset += 4
            index_length = struct.unpack_from("<I", data, len(data) - 4)[0]
            index_start = len(data) - 4 - index_length
            raw_index = json.loads(data[index_start : index_start + index_length])
            entries = {
                root: _Entry(int(value[0]), int(value[1]), int(value[2]))
                for root, value in raw_index.items()
            }
            if len(entries) != root_count:
                raise ValueError(f"study fragment file {path} has an inconsistent root count")
        except BaseException:
            data.close()
            raise
        return cls(data, entries)

    def read(
        self,
        root_group_ids: Collection[str],
        *,
        allow_unavailable: bool,
        module_versions: Mapping[str, str] | None,
    ) -> StudyStructureBatch | None:
        """Return the fragment batch, or ``None`` when a root or version selection needs the
        service."""
        requested = tuple(dict.fromkeys(root_group_ids))
        if module_versions:
            return None
        if any(root not in self._entries for root in requested):
            return None
        roots: list[StudyStructureModule] = []
        unavailable: list[str] = []
        selection: list[str] = []
        for root in requested:
            entry = self._entries[root]
            if entry.kind == _ROOT:
                payload = self._data[entry.offset : entry.offset + entry.length]
                roots.append(StudyStructureModule.model_validate_json(payload))
            elif entry.kind == _UNAVAILABLE:
                if not allow_unavailable:
                    return None
                unavailable.append(root)
            else:
                selection.append(root)
        return StudyStructureBatch(
            roots=tuple(roots),
            unavailable_root_group_ids=tuple(unavailable),
            version_selection_required=tuple(selection),
        )
