"""Read-only float64 centroid and descriptive-chunk stores shared by every serving worker.

The store is one file pair per serving artifact build: a raw float64 centroid matrix with its
identity index, and a mapped descriptive chunk store with each chunk's carrier facts and float64
vector. Every worker maps the same files read-only, so the page cache holds one copy. A store with
no centroid row opens an empty read-only matrix of the fixed embedding dimension. A store is keyed
by the serving database and academic year and lives in its embedding configuration's directory, so
a mismatched key raises ``ValueError`` rather than serving a stale hit.
"""

from __future__ import annotations

import json
import mmap
import struct
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.embeddings.centroids import CourseCentroid
from course_explorer.embeddings.read import TeachingEmbeddingChunk
from course_explorer.enums import (
    DESCRIPTIVE_TEACHING_TEXT_FIELDS,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)

CENTROIDS_FILE = "centroids.f64"
CENTROIDS_META_FILE = "centroids.json"
CHUNKS_FILE = "chunks.f64.bin"

CHUNK_MAGIC = b"CSTCHNK1"
_CHUNK_HEADER = 8 + 4 + 4 + 4
_CHUNK_RECORD = 16 + 1 + 1 + 1 + 4 + 4

_BUILD_GUIDANCE = "run `scripts/admin.py serving-artifacts` to build the serving artifacts"


def _empty_centroid_matrix() -> numpy.ndarray:
    """Return the read-only fixed-dimension matrix of a store with no centroid row."""
    matrix = numpy.empty((0, COURSE_EMBEDDING_DIMENSION), dtype="<f8")
    matrix.flags.writeable = False
    return matrix


@dataclass(frozen=True)
class SharedServingStore:
    """One mapped centroid matrix and descriptive chunk store of one artifact build."""

    centroids: numpy.ndarray
    chunks: mmap.mmap
    chunk_index: dict[tuple[str, str, str], tuple[int, int]]
    centroid_index: dict[tuple[str, str, str], int]
    chunk_records_offset: int
    chunk_vectors_offset: int
    chunk_vectors: numpy.ndarray

    @classmethod
    def build(
        cls,
        root: Path,
        *,
        dataset_key: str,
        academic_year_start: int,
        centroids: Sequence[CourseCentroid],
        chunks: Sequence[TeachingEmbeddingChunk],
    ) -> SharedServingStore:
        """Write the centroid matrix and descriptive chunk store into one artifact build."""
        root.mkdir(parents=True, exist_ok=True)
        matrix = numpy.empty((len(centroids), COURSE_EMBEDDING_DIMENSION), dtype="<f8")
        rows = []
        for position, row in enumerate(centroids):
            matrix[position] = numpy.asarray(row.centroid, dtype="<f8")
            rows.append(
                {
                    "group_id": row.group_id,
                    "sisu_course_unit_id": row.sisu_course_unit_id,
                    "source_hash": row.representative_source_hash,
                }
            )
        centroid_path = root / CENTROIDS_FILE
        centroid_path.write_bytes(matrix.tobytes())
        (root / CENTROIDS_META_FILE).write_text(
            json.dumps(
                {
                    "dataset_key": dataset_key,
                    "academic_year_start": academic_year_start,
                    "dimension": COURSE_EMBEDDING_DIMENSION,
                    "rows": rows,
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        store_chunks = [
            chunk for chunk in chunks if chunk.field in DESCRIPTIVE_TEACHING_TEXT_FIELDS
        ]
        grouped: dict[tuple[str, str, str], list[TeachingEmbeddingChunk]] = {}
        for chunk in store_chunks:
            triple = (chunk.group_id, chunk.sisu_course_unit_id, chunk.representative_source_hash)
            grouped.setdefault(triple, []).append(chunk)
        index: list[list[object]] = []
        records = bytearray()
        vectors = bytearray()
        total = 0
        for triple in sorted(grouped):
            grouped_chunks = grouped[triple]
            start = total
            for chunk in grouped_chunks:
                records += chunk.chunk_id.bytes
                records += struct.pack(
                    "<BBBiI",
                    1 if chunk.field is TeachingTextField.OUTCOMES else 0,
                    1 if chunk.language is TeachingTextLanguage.EN else 0,
                    1 if chunk.text_origin is TeachingTextOrigin.DERIVED else 0,
                    chunk.chunk_index,
                    chunk.character_count,
                )
                vectors += numpy.asarray(chunk.embedding, dtype="<f8").tobytes()
                total += 1
            index.append([*triple, start, len(grouped_chunks)])
        index_bytes = json.dumps(index, separators=(",", ":")).encode()
        chunk_path = root / CHUNKS_FILE
        with chunk_path.open("wb") as out:
            out.write(
                CHUNK_MAGIC
                + struct.pack("<III", COURSE_EMBEDDING_DIMENSION, total, len(index_bytes))
            )
            out.write(index_bytes)
            out.write(records)
            out.write(vectors)
        return cls.open(root, dataset_key=dataset_key, academic_year_start=academic_year_start)

    @classmethod
    def open(cls, root: Path, *, dataset_key: str, academic_year_start: int) -> SharedServingStore:
        """Map the centroid matrix and the descriptive chunk file of one build directory.

        The centroid metadata in the directory supplies the dataset key, academic year and row
        identities. The key, the dimension, the counts and the byte lengths are validated once at
        open. A store with no centroid row opens an empty read-only matrix of
        ``COURSE_EMBEDDING_DIMENSION`` columns instead of mapping the zero-byte file. The chunk file
        carries its own index in its header.
        """
        centroid_meta_path = root / CENTROIDS_META_FILE
        if not centroid_meta_path.is_file():
            raise ValueError(f"shared serving store is missing at {root}; {_BUILD_GUIDANCE}")
        centroid_meta = json.loads(centroid_meta_path.read_text(encoding="utf-8"))
        if (
            centroid_meta["dataset_key"] != dataset_key
            or centroid_meta["academic_year_start"] != academic_year_start
        ):
            raise ValueError(
                f"shared serving store {root} belongs to another dataset or academic year; "
                f"{_BUILD_GUIDANCE}"
            )
        if int(centroid_meta["dimension"]) != COURSE_EMBEDDING_DIMENSION:
            raise ValueError(
                f"shared serving store {root} has an unexpected dimension; {_BUILD_GUIDANCE}"
            )
        rows = centroid_meta["rows"]
        centroid_path = root / CENTROIDS_FILE
        if centroid_path.stat().st_size != len(rows) * COURSE_EMBEDDING_DIMENSION * 8:
            raise ValueError(
                f"shared centroid store {root} has an inconsistent length; {_BUILD_GUIDANCE}"
            )
        centroids = (
            numpy.memmap(
                root / CENTROIDS_FILE,
                dtype="<f8",
                mode="r",
                shape=(len(rows), COURSE_EMBEDDING_DIMENSION),
            )
            if rows
            else _empty_centroid_matrix()
        )
        handle = (root / CHUNKS_FILE).open("rb")
        chunks = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        handle.close()
        if chunks[: len(CHUNK_MAGIC)] != CHUNK_MAGIC:
            raise ValueError(f"shared chunk store {root} has an invalid header")
        dimension, total, index_length = struct.unpack_from("<III", chunks, len(CHUNK_MAGIC))
        if dimension != COURSE_EMBEDDING_DIMENSION:
            raise ValueError(f"shared chunk store {root} has an unexpected dimension")
        index_start = _CHUNK_HEADER
        index = {
            (entry[0], entry[1], entry[2]): (int(entry[3]), int(entry[4]))
            for entry in json.loads(chunks[index_start : index_start + index_length])
        }
        records_offset = index_start + index_length
        vectors_offset = records_offset + total * _CHUNK_RECORD
        if vectors_offset + total * COURSE_EMBEDDING_DIMENSION * 8 != len(chunks):
            raise ValueError(f"shared chunk store {root} has an inconsistent length")
        vectors = numpy.ndarray(
            shape=(total, COURSE_EMBEDDING_DIMENSION),
            dtype="<f8",
            buffer=chunks,
            offset=vectors_offset,
        )
        return cls(
            centroids=centroids,
            chunks=chunks,
            chunk_index=index,
            centroid_index={
                (
                    row["group_id"],
                    row["sisu_course_unit_id"],
                    row["source_hash"],
                ): position
                for position, row in enumerate(rows)
            },
            chunk_records_offset=records_offset,
            chunk_vectors_offset=vectors_offset,
            chunk_vectors=vectors,
        )

    def position(
        self, group_id: str, sisu_course_unit_id: str, representative_source_hash: str
    ) -> int | None:
        """Return the centroid row index for one exact representative, or ``None``."""
        return self.centroid_index.get((group_id, sisu_course_unit_id, representative_source_hash))

    def centroid_rows(self, positions: Sequence[int]) -> numpy.ndarray:
        """Return the requested mapped centroid rows as one float64 matrix."""
        return self.centroids[numpy.asarray(positions, dtype=numpy.intp)]

    def chunk_span(self, triple: tuple[str, str, str]) -> tuple[int, int] | None:
        """Return one representative's first chunk offset and count, or ``None``."""
        return self.chunk_index.get(triple)

    def descriptive_rows(self, indices: numpy.ndarray) -> tuple[numpy.ndarray, ...]:
        """Return the requested descriptive chunk vectors and their native marshalling fields."""
        fields = numpy.empty(len(indices), dtype=numpy.int32)
        characters = numpy.empty(len(indices), dtype=numpy.int64)
        derived = numpy.empty(len(indices), dtype=numpy.uint8)
        for position, index in enumerate(indices):
            record = self.chunk_records_offset + int(index) * _CHUNK_RECORD
            field, _language, origin, _chunk_index, count = struct.unpack_from(
                "<BBBiI", self.chunks, record + 16
            )
            fields[position] = 1 if field else 0
            derived[position] = 1 if origin else 0
            characters[position] = count
        return (self.chunk_vectors[indices], fields, characters, derived)

    def chunks_for(self, represented: Sequence[object]) -> tuple[TeachingEmbeddingChunk, ...]:
        """Return every stored descriptive chunk of the requested representative triples."""
        requested = sorted(
            {
                (
                    record.summary.group_id,
                    record.sisu_course_unit_id,
                    record.source_hash,
                )
                for record in represented
            }
        )
        chunks: list[TeachingEmbeddingChunk] = []
        for triple in requested:
            entry = self.chunk_index.get(triple)
            if entry is None:
                continue
            start, count = entry
            for offset in range(start, start + count):
                record = self.chunk_records_offset + offset * _CHUNK_RECORD
                chunk_id = uuid.UUID(bytes=bytes(self.chunks[record : record + 16]))
                field, language, origin, chunk_index, characters = struct.unpack_from(
                    "<BBBiI", self.chunks, record + 16
                )
                chunks.append(
                    TeachingEmbeddingChunk(
                        chunk_id=chunk_id,
                        group_id=triple[0],
                        field=(TeachingTextField.OUTCOMES if field else TeachingTextField.CONTENT),
                        language=TeachingTextLanguage.EN if language else TeachingTextLanguage.FI,
                        chunk_index=chunk_index,
                        text_origin=(
                            TeachingTextOrigin.DERIVED if origin else TeachingTextOrigin.OFFICIAL
                        ),
                        character_count=characters,
                        embedding=numpy.frombuffer(
                            self.chunks,
                            dtype="<f8",
                            count=COURSE_EMBEDDING_DIMENSION,
                            offset=self.chunk_vectors_offset
                            + offset * COURSE_EMBEDDING_DIMENSION * 8,
                        ),
                        sisu_course_unit_id=triple[1],
                        representative_source_hash=triple[2],
                    )
                )
        return tuple(chunks)
