"""Build the stored per-chunk nearest-neighbour rows of one selected dataset.

The build runs one nearest query per completed compatible descriptive chunk and stores up to
`rows_per_chunk` targets of that chunk. The caller owns the transaction that replaces the
rows, so the neighbour table and the course centroids are replaced together. Every write lands in
the neighbour table.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, insert, literal, select, text
from sqlalchemy.orm import Session

from course_explorer.db.models import CourseEmbeddingChunk, CourseEmbeddingNeighbor
from course_explorer.enums import (
    DESCRIPTIVE_TEACHING_TEXT_FIELDS,
    CourseEmbeddingStatus,
    TeachingTextLanguage,
)

# The number of query chunks one batch reads before it runs their nearest queries.
_QUERY_BATCH_SIZE = 1000


def replace_all(
    session: Session,
    *,
    embedding_configuration_hash: str,
    rows_per_chunk: int,
    hnsw_iterative_scan: str,
    hnsw_max_scan_tuples: int,
) -> int:
    """Replace every neighbour row in the caller's transaction and return the stored row count.

    `rows_per_chunk` must be positive, and the two scan values are the validated nearest-read
    settings. The statement before the first query loads the vector extension and sets the scan
    bounds for the transaction.
    """
    if rows_per_chunk <= 0:
        raise ValueError("neighbour rows per chunk must be positive")
    if hnsw_iterative_scan not in {"relaxed_order", "strict_order"}:
        raise ValueError("hnsw iterative scan must be relaxed_order or strict_order")
    if hnsw_max_scan_tuples <= 0:
        raise ValueError("hnsw max scan tuples must be positive")
    session.execute(
        text(
            "SELECT NULL::vector; "
            f"SET LOCAL hnsw.iterative_scan = '{hnsw_iterative_scan}'; "
            f"SET LOCAL hnsw.max_scan_tuples = {hnsw_max_scan_tuples}"
        )
    )
    session.execute(delete(CourseEmbeddingNeighbor))
    last_id = None
    while True:
        statement = (
            select(
                CourseEmbeddingChunk.id,
                CourseEmbeddingChunk.language,
                CourseEmbeddingChunk.embedding,
            )
            .where(
                CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
                CourseEmbeddingChunk.embedding.is_not(None),
                CourseEmbeddingChunk.embedding_configuration_hash == embedding_configuration_hash,
                CourseEmbeddingChunk.field.in_(DESCRIPTIVE_TEACHING_TEXT_FIELDS),
            )
            .order_by(CourseEmbeddingChunk.id)
            .limit(_QUERY_BATCH_SIZE)
        )
        if last_id is not None:
            statement = statement.where(CourseEmbeddingChunk.id > last_id)
        rows = session.execute(statement).all()
        if not rows:
            break
        for row in rows:
            _insert_nearest(
                session,
                query_chunk_id=row.id,
                language=row.language,
                embedding=row.embedding,
                embedding_configuration_hash=embedding_configuration_hash,
                rows_per_chunk=rows_per_chunk,
            )
        last_id = rows[-1].id
    return int(session.scalar(select(func.count()).select_from(CourseEmbeddingNeighbor)) or 0)


def _insert_nearest(
    session: Session,
    *,
    query_chunk_id: uuid.UUID,
    language: TeachingTextLanguage,
    embedding: Sequence[float],
    embedding_configuration_hash: str,
    rows_per_chunk: int,
) -> None:
    """Insert the nearest eligible targets of one query chunk."""
    distance = CourseEmbeddingChunk.embedding.cosine_distance(list(embedding))
    candidates = (
        select(
            CourseEmbeddingChunk.id.label("target_chunk_id"),
            (1 - distance).label("score"),
        )
        .where(
            CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
            CourseEmbeddingChunk.embedding.is_not(None),
            CourseEmbeddingChunk.embedding_configuration_hash == embedding_configuration_hash,
            CourseEmbeddingChunk.field.in_(DESCRIPTIVE_TEACHING_TEXT_FIELDS),
            CourseEmbeddingChunk.language == language,
        )
        .order_by(distance)
        .limit(rows_per_chunk)
        .subquery("nearest")
    )
    statement = insert(CourseEmbeddingNeighbor).from_select(
        ("query_chunk_id", "target_chunk_id", "score"),
        select(
            literal(query_chunk_id),
            candidates.c.target_chunk_id,
            candidates.c.score,
        ),
    )
    session.execute(statement)
