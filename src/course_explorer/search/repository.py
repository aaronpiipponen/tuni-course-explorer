"""Exact-cosine read over the packed course embedding search relation.

This is the sole search reader for the packing extension. It calls the installed scan function once
with the hub-centred query and the build's group count, joins the returned group numbers to their
canonical representative identities and the course activity state, applies the threshold, and
returns every qualifying version ordered by canonical group and version.
"""

from __future__ import annotations

from collections.abc import Sequence

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.embeddings.hub import subtract_hub
from course_explorer.search.service import SemanticCourseScore


class SemanticSearchRepository:
    """Read exact packed best-chunk cosine scores through the installed scan function."""

    def __init__(self, factory: sessionmaker[Session], *, group_count: int) -> None:
        self._factory = factory
        self._group_count = group_count

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        hub: Sequence[float],
        min_score: float,
        include_inactive: bool,
    ) -> tuple[SemanticCourseScore, ...]:
        """Return every exact-version best-chunk score at or above the threshold, unfiltered by rank.

        A build with zero retained groups returns no score before the hub subtraction, the SQL
        binding and the packed scan. A negative group count is unsupported.
        """
        if self._group_count == 0:
            return ()
        query_parameter = bindparam(
            "centred_query",
            value=list(subtract_hub(query_embedding, hub)),
            type_=Vector(COURSE_EMBEDDING_DIMENSION),
        )
        active_filter = "" if include_inactive else "AND c.is_active"
        statement = text(
            f"""
            SELECT g.group_id, g.sisu_course_unit_id, g.representative_source_hash, s.score
            FROM course_embedding_search_scan(
                'course_embedding_search_blocks'::regclass,
                :centred_query,
                inner_product(CAST(:centred_query AS vector), CAST(:centred_query AS vector)),
                :group_count
            ) AS s
            JOIN course_embedding_search_groups AS g ON g.group_no = s.group_no
            JOIN courses AS c ON c.group_id = g.group_id
            WHERE s.score >= :min_score {active_filter}
            ORDER BY g.group_id, g.sisu_course_unit_id
            """
        ).bindparams(query_parameter)
        with self._factory() as session:
            rows = tuple(
                session.execute(
                    statement,
                    {
                        "min_score": min_score,
                        "group_count": self._group_count,
                    },
                )
            )
        return tuple(
            SemanticCourseScore(
                group_id=group_id,
                sisu_course_unit_id=sisu_course_unit_id,
                representative_source_hash=representative_source_hash,
                score=float(score),
            )
            for group_id, sisu_course_unit_id, representative_source_hash, score in rows
        )
