"""Build the packed exact semantic search relation of one serving artifact build.

The repository reads every completed configuration-compatible chunk vector once, assigns one dense
group number per canonical representative triple, and writes 128-vector blocks of hub-centred
float32 payloads with their float64 squared norms and the one-row build meta. The serving search
read scans this relation through the database extension. This module is the only builder.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, delete, func, insert, select
from sqlalchemy.orm import Session

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseEmbeddingSearchBlock,
    CourseEmbeddingSearchGroup,
    CourseEmbeddingSearchMeta,
    CourseVersion,
)
from course_explorer.enums import CourseEmbeddingStatus

# Vectors in one packed search block, matching the block table's row bound.
BLOCK_SIZE = 128


class CourseEmbeddingSearchRepository:
    """Replace the packed search groups, blocks and meta row of one dataset build."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_all(
        self,
        *,
        embedding_configuration_hash: str,
        hub: Sequence[float],
    ) -> tuple[int, int]:
        """Replace every packed row and return the group count and the stored block count.

        The relation is cleared first, in the caller's transaction. An empty hub represents a
        dataset with no stored chunk vector, so it returns ``(0, 0)`` after the clearing and writes
        no group, block or meta row. The nonempty read keeps completed, non-null,
        exact-configuration rows. Every row belongs to one dense group number, and every group
        appears in the blocks. All blocks hold 128 vectors except the last.
        """
        self._session.execute(delete(CourseEmbeddingSearchBlock))
        self._session.execute(delete(CourseEmbeddingSearchGroup))
        self._session.execute(delete(CourseEmbeddingSearchMeta))
        if not hub:
            return 0, 0
        hub_parameter = bindparam(
            "hub_vector", value=list(hub), type_=Vector(COURSE_EMBEDDING_DIMENSION)
        )
        centred_embedding = CourseEmbeddingChunk.embedding - hub_parameter
        rows = self._session.execute(
            select(
                Course.group_id,
                CourseVersion.sisu_course_unit_id,
                CourseEmbeddingChunk.representative_source_hash,
                func.vector_send(centred_embedding).label("payload"),
                func.inner_product(centred_embedding, centred_embedding).label("squared_norm"),
            )
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(
                CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
                CourseEmbeddingChunk.embedding.is_not(None),
                CourseEmbeddingChunk.embedding_configuration_hash == embedding_configuration_hash,
            )
            .order_by(
                Course.group_id,
                CourseVersion.sisu_course_unit_id,
                CourseEmbeddingChunk.representative_source_hash,
                CourseEmbeddingChunk.id,
            )
        ).all()
        identities = sorted(
            {
                (group_id, sisu_course_unit_id, representative_source_hash)
                for group_id, sisu_course_unit_id, representative_source_hash, _payload, _norm in rows
            }
        )
        if not identities:
            raise ValueError("no completed compatible chunk vector exists for the search relation")
        group_numbers = {identity: number for number, identity in enumerate(identities)}
        blocks: list[dict[str, object]] = []
        for start in range(0, len(rows), BLOCK_SIZE):
            batch = rows[start : start + BLOCK_SIZE]
            vectors = bytearray()
            groups: list[int] = []
            norms: list[float] = []
            for (
                group_id,
                sisu_course_unit_id,
                representative_source_hash,
                payload,
                squared_norm,
            ) in batch:
                number = group_numbers[(group_id, sisu_course_unit_id, representative_source_hash)]
                vector = numpy.frombuffer(payload[4:], dtype=">f4")
                if vector.shape != (COURSE_EMBEDDING_DIMENSION,):
                    raise ValueError("stored chunk vector has an unexpected dimension")
                vectors += vector.astype("<f4").tobytes()
                groups.append(number)
                norms.append(float(squared_norm))
            blocks.append(
                {
                    "block_no": len(blocks),
                    "n": len(batch),
                    "groups": groups,
                    "norms": norms,
                    "vectors": bytes(vectors),
                }
            )
        self._session.execute(
            insert(CourseEmbeddingSearchGroup),
            [
                {
                    "group_no": number,
                    "group_id": identity[0],
                    "sisu_course_unit_id": identity[1],
                    "representative_source_hash": identity[2],
                }
                for identity, number in group_numbers.items()
            ],
        )
        self._session.execute(insert(CourseEmbeddingSearchBlock), blocks)
        self._session.execute(
            insert(CourseEmbeddingSearchMeta),
            [{"one_row": True, "group_count": len(identities)}],
        )
        return len(identities), len(blocks)
