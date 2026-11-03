-- Expose the exact packed semantic scan over the course embedding block relation.
CREATE FUNCTION course_embedding_search_scan(regclass, vector, float8, int)
RETURNS TABLE(group_no int, score float8)
AS 'MODULE_PATHNAME', 'course_embedding_search_scan'
LANGUAGE C STRICT VOLATILE PARALLEL UNSAFE;
