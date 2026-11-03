# Recommendation ranking

Recommendation ranking turns one chosen basis into the ordered recommendation list through a nearest-chunk read, a centroid prefilter, scoring formulas and a fixed order.

## Recommendation composition

`run_recommendations_command` in `src/course_explorer/recommendations/commands.py` is the one composition path:

1. It prepares the request and reads the discovery report through `prepare_next_course_inputs` and `read_next_courses`, so validation, basis choice, and the next-course list come from the one discovery path.
2. It answers the next-course step's course and module facts through the worker's native fact handle, and a supplied next-course report cache answers a repeated canonical request.
3. It selects the chosen basis identities from the next-course report, using `selected_group_ids` when the basis is `selected` and `completed_group_ids` otherwise, and returns an empty report for an empty basis before any recommendation read.
4. It loads `SearchSettings` and `EmbeddingRuntimeSettings`, takes the supervisor's embedding configuration identity and the opened serving artifact build's hub pair, and hashes the loaded settings only when the caller supplies no identity.
5. It reads the basis records through `_represented_records`, which answers from the supplied lookup projection when the caller holds one and otherwise from `CurriculumRepository.get_represented_summaries`. The web route always supplies the projection, and the basis records are read without an activity filter. Their chunks come from `TeachingEmbeddingRepository.get_chunks(..., descriptive_only=True, shared_store=shared_store)`, so a descriptive read selects only `TeachingTextField.CONTENT` and `TeachingTextField.OUTCOMES` entries and answers from the artifact store without a database read. No basis chunk returns an empty report.
6. It builds the exclusion set from the chosen basis identities and the next-course identities, and passes it to `TeachingEmbeddingRepository.find_nearest_chunks` with the request's activity scope, so the stored read removes both before it returns a row.
7. It prepares the basis with `prepare_recommendation_basis(basis_chunks, hub=hub, outcomes_hub=outcomes_hub)` and keeps the hits whose stored course centroid reaches the relatedness floor through `filter_neighbors_by_centroid(neighbors, centroid_cache, basis, settings=search_settings)`. When no hit survives, it returns an empty report. It then resolves the surviving hit identities through `_represented_records`, which filters to active records under the active-only scope and applies no activity filter otherwise. It builds the candidate pool with `rank_recommendation_candidates`, and measures and orders it with `recommendations_from_candidates` using the two hub vectors, the prepared `basis` and the shared store as the source of the candidate chunk rows.
8. It returns `RecommendationsReport(similarity_results=...)`.

`SimilarityRecommendation` holds `course`, `relatedness` (0 to 100), `score` (0 to 100), `overlap_with_basis` (0 to 100 or `None`), and `uses_derived_text`. `scripts/recommendations.py` forwards the same arguments as the next-course adapter. `POST /api/recommendations` applies the site's inference switch to `include_inferred`, so the next-course step behind the request reads official prerequisites alone on a site that serves no inference features. A site whose `WEB_EMBEDDINGS_ENABLED` is false answers that route with status 403 and the detail `Feature disabled` before the command runs. A served request returns the report with the serving dataset identity.

## The nearest read

`TeachingEmbeddingRepository.find_nearest_chunks(basis_chunks, *, embedding_configuration_hash, top_k, active_only, excluded_group_ids)` in `src/course_explorer/embeddings/read.py` reads the stored `course_embedding_neighbors` rows of each supplied basis chunk. Its `values` table carries `(query_index, query_chunk_id)`, and one statement joins the stored rows to their target chunk, version and course.

The statement keeps the target chunk's exact configuration hash, drops an identity in `excluded_group_ids`, and, under active-only scope, requires `Course.is_active`. It numbers each query chunk's surviving rows by descending stored score and then by target chunk id, and keeps the first `top_k`. The cutoff is deterministic, and the numbered rows follow the query index and the score.

One outer `GROUP BY` then reduces the numbered rows to one row per representative triple, so the aggregate, and not the Python caller, is the pool the prefilter and the scorer read. A group that several basis chunks reach appears once. The projection carries no score, and the read guarantees no order, because the native scorer orders the pool.

A dataset whose stored chunks carry no neighbour row fails when its artifact set opens, naming `scripts/admin.py serving-artifacts`, and this read does not re-verify the table's coverage. A request-specific exclusion set can leave fewer than `top_k` stored rows, because the stored set holds `SEARCH_NEIGHBOR_TABLE_ROWS_PER_CHUNK` rows per chunk and excludes no request identity at build time.

The table is written by `neighbors.replace_all` in `src/course_explorer/embeddings/neighbors.py`. It runs one nearest query per completed compatible descriptive chunk under `SEARCH_HNSW_ITERATIVE_SCAN` and `SEARCH_HNSW_MAX_SCAN_TUPLES`, stores up to `SEARCH_NEIGHBOR_TABLE_ROWS_PER_CHUNK` target chunks with their score, and returns the stored row count. On a site that serves the embedding features the serving-artifact command replaces the neighbour rows and the centroid rows in one transaction before it switches the current artifact build.

## The shared descriptive chunk store

`SharedServingStore` in `src/course_explorer/embeddings/shared_store.py` maps one read-only descriptive chunk file per serving artifact build. An entry holds the ordered `TeachingEmbeddingChunk` carriers of one representative triple, with each carrier's chunk identity, field, language, origin, character count and float64 vector. Every worker reads the mapping the supervisor inherited, so the page cache holds one copy. A descriptive read answers from the store and opens no database session. The all-field read that comparison uses keeps the database projection. The store records the artifact key and the academic year it was built for, and a key of another serving database or year raises `ValueError` naming the store path and the build command. The embedding configuration names the directory that holds the file, so a configuration whose directory is absent fails the artifact open. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md) describes the file the build writes.

## The centroid prefilter

`prepare_recommendation_basis(basis_chunks, *, hub, outcomes_hub)` in `src/course_explorer/recommendations/service.py` returns a `RecommendationBasis` holding the descriptive basis chunks, their hub-centred unit rows, the count of basis courses and the trimmed basis vector in its `profile` field. A basis without a descriptive chunk holds no basis vector.

`filter_neighbors_by_centroid(neighbors, lookup, basis, *, settings)` returns the hits whose stored course centroid reaches `settings.recommendation_min_relatedness` and preserves the input order. The stored-neighbour read applies the exclusion set and the activity scope before it returns a row. It resolves each distinct hit's row once by the exact representative triple `(group_id, sisu_course_unit_id, representative_source_hash)`, so a centroid of another representative identity is left out. It gathers those rows from the shared centroid matrix and multiplies them by the basis vector in one product, maps each value through `100 * max(0, row dot profile)`, and keeps the hits at or above the floor. A basis with no basis vector returns no hit.

`CourseCentroidCache` in `src/course_explorer/recommendations/centroid_cache.py` supplies the lookup. It delegates `position` and `centroids` to the shared store of the opened artifact build, which holds the mapped centroid matrix and its representative index. The store belongs to one artifact family and academic year, its files live in the family's embedding directory of the running embedding configuration, and `position` matches the exact representative triple, so a hit of another version finds no row.

On a site that serves the embedding features the build writes the centroid matrix, the descriptive chunk store and the hub pair together in the family's embedding directory, so the three describe the same chunk set. Opening the artifacts reads `hub-pair.json` and the two hub files it names from that directory, and reads the packed search meta row once for its group count. The store's centroid metadata records the dataset key and academic year it was built for, and opening it under another key or year is refused.

The shared store holds the chunk set its build read, and a running worker holds that mapped store until the full supervisor restart. The four preparation stages write the Working dataset, so they change neither the served chunk set nor that mapped store. A confirmed `datasets copy-to-selected` promotion builds a copy through the same owner, publishes it as Selected, restarts the web unit and proves the served catalogue, so the site then serves that copy's vectors, centroids and stored neighbours. [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states the promotion sequence and the restart.

## Ranking, the trimmed basis vector and the near-duplicate rule

`rank_recommendation_candidates(neighbors, represented)` keeps a hit only when its group identity names a supplied representative record and the hit's `(sisu_course_unit_id, representative_source_hash)` equals the record's, so a stored chunk of a non-representative version is dropped. It returns each surviving group once, in first-seen order, and the native scorer orders that pool. No cutoff compares the percentage, so every hit that survives the identity checks and the centroid prefilter reaches the measurement step.

The command applies the relatedness floor to the stored course centroids before it reads candidate summaries and chunks. A hit that survives the identity checks and the centroid floor reaches the scorer, which marshals the candidate chunk rows straight from the shared serving store, so each candidate is measured over its complete compatible content and learning-outcomes text rather than the chunk that matched.

`recommendations_from_candidates(candidates, basis_chunks, chunk_rows, *, display_language, settings, hub, outcomes_hub, basis=None)` passes the prepared basis rows, the trimmed basis vector and the candidate chunk rows as float64 NumPy arrays, together with both hub vectors, to the native scorer. `chunk_rows` is the shared serving store, which answers each candidate's chunk span and its descriptive rows without a database read. A supplied `basis` is the prepared basis the prefilter already used, so the prefilter and the scorer share one basis vector.

`DESCRIPTIVE_TEACHING_TEXT_FIELDS` is `(CONTENT, OUTCOMES)`, and every basis chunk is centred and normalized by `unit_rows` from `src/course_explorer/embeddings/vector_math.py`, which applies `subtract_hub_rows` from `src/course_explorer/embeddings/hub.py` with the outcomes hub for an outcomes chunk and the embedding hub otherwise. Each centred basis chunk becomes one float64 row normalized to unit length, and a zero-length centred row raises `ValueError`. A basis course point is the unit mean of its chunk rows, so every chunk weights equally, unlike the character-weighted centroid of `src/course_explorer/comparison/service.py`. The basis vector is computed from those points with matrix products.

The candidate chunks reach the scorer as their stored vectors, with their field, character count and origin. The native scorer subtracts the field's hub from each candidate chunk, normalizes the result and forms the candidate point, so the marshalling and the centring of a candidate happen in separate places. The relatedness and overlap values come from the native library.

The native scorer accumulates each dot product as four partial sums over the float64 components and combines them once. The kept results sort by score descending, then relatedness descending, then the ordering key: a named course before an unnamed one, then the normalized name, the code and the canonical group.

```text
point(course)      = unit(mean of the centred unit chunk rows)
initial            = unit(mean of the basis course points)
consistency(c)     = dot(point(c), initial)
kept               = points with consistency >= median(consistency over the basis courses)
basis_vector       = unit(mean of the kept points)      # a single basis course keeps its own point
relatedness        = 100 * max(0, dot(unit(mean of the candidate chunk rows), basis_vector))
```

The candidate's point uses the candidate's own centred descriptive chunks. A candidate with no such chunk, or a basis with no descriptive chunk at all, contributes no result.

The scorer reports the displayed percentage through the calibration described in [Recommendations](/docs/backend/search-and-discovery/recommendations.md): the recommendation floor keeps its own percentage and `RECOMMENDATION_RELATEDNESS_CEILING` reads as 100. The floor cut, near-duplicate test and order above all use the raw percentage.

Coverage multiplies the candidate chunk rows by every basis chunk row in one float64 product, and each candidate chunk takes its greatest dot product against the rows of one basis course. The character weight of the chunk scales that value.

```text
per candidate chunk and per basis course:
    course_best(c)  = max(dot(basis_unit, candidate_unit) for the units of course c)
    course_covered(c) += chunk.character_count * max(0, course_best(c))
    best            = max over c of course_best(c)
    covered_sum    += chunk.character_count * max(0, best)
strongest_course   = max(overlap_percent(course_covered(c) / total_characters) over c)
whole_basis        = overlap_percent(covered_sum / total_characters)   # None when total is 0
score              = 100 * max(0, relatedness / 100 - weight * (whole_basis or 0) / 100)
```

The native scorer's own `overlap_percent` in `native/scorer.cpp` maps the configured floor to 0 and the ceiling to 100, with the same mapping as `overlap_percent` in `src/course_explorer/comparison/service.py`. A candidate is dropped when `relatedness` is below `recommendation_min_relatedness * 100` or when `strongest_course` reaches `recommendation_near_duplicate_percent`. `uses_derived_text` is true when any candidate chunk or any basis descriptive chunk carries `TeachingTextOrigin.DERIVED`. The final order is `(-score, -relatedness, name_key)`.

### Configuration keys

`SearchSettings` in `src/course_explorer/config.py` holds the recommendation policy, read from `config/search.toml`. [Recommendations](/docs/backend/search-and-discovery/recommendations.md#configuration-keys) lists the keys and the example values.

The near-duplicate rule and the whole-basis overlap share `comparison_overlap_floor` and `comparison_overlap_ceiling`.

## Tests

| File | Covers |
|---|---|
| `tests/recommendations/test_recommendations_service.py` | Ranking by the trimmed basis vector, a course that duplicates one basis course being dropped, a course that points away from the basis vector falling below the floor, the derived-text flag, the centroid prefilter that keeps a hit above the floor and drops one below it, the prepared basis that the prefilter and the scorer share, and the native scorer's retained set, order and derived flag. |
| `tests/recommendations/test_recommendations_command.py` | The adapter forwarding every argument once, validation before any read, the similarity-only report round-trip, and an empty basis that returns no results. |
| `tests/search/test_semantic_search_repository.py` | An opt-in PostgreSQL proof over a seeded chunk graph: the exact packed search score with the lifecycle and configuration scope, the shared descriptive store read order, the nearest read, and the ranked candidate pool. |
| `tests/embeddings/test_nearest_chunk_fill.py` | An opt-in PostgreSQL proof that one basis chunk receives the configured limit under the active-only and exclusion filters when enough eligible chunks exist. |
| `tests/embeddings/test_shared_store.py` | The shared store opened under another dataset identity or another academic year is refused. |

The behaviour as the app presents it is described in [Recommendations](/docs/backend/search-and-discovery/recommendations.md), and the next-course step that fixes its candidate exclusion is described in [Next-course coverage](/docs/backend/search-and-discovery/next-course-coverage.md).
