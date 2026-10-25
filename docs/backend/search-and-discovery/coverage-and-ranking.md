# Coverage and ranking

This page describes the services, reads, evaluators, and ordering keys that produce next courses and recommendations, and the tests that cover them.

## Next-course composition

`run_next_courses_command` in `src/course_explorer/next_courses/commands.py` is the one composition path for a discovery request:

1. It normalizes `basis` through `PrerequisiteCalculationBasis` and `mode` through `NextCourseMode`, and checks `display_language` against `DisplayLanguage`. A blank identity, an unknown basis, an unknown mode, and an unsupported language each raise `ValueError` before any settings load.
2. It loads `SearchSettings` and opens one `database_context`.
3. It resolves every selected and completed input through `CourseLookupService.resolve_courses`, which matches an outer-trimmed exact canonical `group_id` first and an exact current official code second, then reduces each side to a sorted set of canonical identities.
4. When no selected input was supplied the completed set becomes the selected set. Otherwise a completed identity outside the selected set raises `ValueError` naming the offenders.
5. It builds `PrerequisiteGraphCompiler(curriculum, inferred_sets, equivalence_groups)` over `CurriculumRepository`, `InferredPrerequisiteRepository`, and `InferredEquivalenceRepository` from the one session factory.
6. It forms the source identities, reads the candidate superset, and compiles it with `PrerequisiteGraphCompiler.compile_direct_many`.
7. When `include_inferred` is set it recompiles the eligible candidates with `include_inferred=False` and passes both compilations to the result service.
8. It returns `NextCoursesReport`.

The result models are frozen with `extra="forbid"`. `NextCourseMode` holds `ALL = "all"` and `AT_LEAST_ONE = "at_least_one"`. `NextCourseResult` holds `course`, `required_coverage`, `recommended_coverage`, and `depends_on_inferred`. `NextCoursesReport` holds `selected_group_ids`, `completed_group_ids`, `basis`, `mode`, `display_language`, `include_inferred`, `active_only`, and `results`.

`scripts/next_courses.py` is the `argparse` adapter. `--selected` and `--completed` repeat, `--basis` defaults to `completed`, `--mode` defaults to `all`, `--display-language` is required, `--include-inferred` is a flag, and the mutually exclusive `--active-only` and `--all-courses` set `active_only`. It prints `report.model_dump_json()` as one line. `POST /api/next-courses` applies the site's inference switch to `include_inferred` before it calls the command, so the flag reaches the command true only when the site serves the inference features and the request asks for it, and the route returns the report with the serving dataset identity.

## Candidate reads

`CurriculumDiscoveryRead` in `src/course_explorer/curriculum.py` states the two reverse reads, and both return sorted distinct canonical `group_id` strings rather than payloads or ORM entities.

`CurriculumRepository.get_substitution_source_group_ids(member_group_ids)` in `src/course_explorer/curriculum_repository.py` selects a canonical course when any member of one of its stored official substitution options names a requested course.

`CurriculumRepository.get_prerequisite_candidate_group_ids(source_group_ids, *, active_only)` selects a canonical course when its stored official prerequisite option names a requested course directly or names a module that can contain one. The module scope is one recursive CTE seeded from `ModuleRuleNode.node_type == ModuleRuleType.COURSE_UNIT_RULE` references and closed over `MODULE_RULE` references with `UNION`, so a cycle terminates. The `active_only` flag adds the stored activity condition.

`InferredPrerequisiteRepository.find_candidate_group_ids(source_group_ids)` in `src/course_explorer/prerequisite/repository.py` selects the active courses whose stored inferred expression contains any requested identity as a nested `course` leaf, through one `jsonb_path_exists` read over the current inferred-set store.

The command's source set starts as the chosen basis. With `include_inferred` set it adds the members of each basis course's current equivalence groups from `InferredEquivalenceRepository.read_for_members`, and it adds the substitution sources of the whole set through `get_substitution_source_group_ids`. The candidate set is the official reverse read, unioned with the inferred reverse read when inference is enabled, minus the chosen basis.

## Direct compilation and the satisfaction session

`PrerequisiteGraphCompiler.compile_direct_many(target_group_ids, *, include_inferred, active_only, retained_group_ids, read_context)` compiles one candidate's own direct options without course ancestors:

- Targets are sorted and deduplicated, and an empty request returns `()` before any read.
- One scoped `get_courses` loads the targets and the retained identities, from the supplied `DirectPrerequisiteReadContext` or from a fresh one. An unknown target raises `ValueError`, and a target whose course has no representative is omitted.
- Every compilation context sets `include_recommended=True` and `direct_only=True`, carries the request's `active_only` and `include_inferred`, and carries `retained_group_ids` as the chosen basis.
- Exclusions do not change a direct compilation, and each compilation carries the solver structure alone.
- Each result is a `DirectPrerequisiteCompilation` holding the authoritative `solver`, `required_use_id` and `recommended_use_id`, each use ID `None` when that category has no enabled contribution.

A supplied `DirectPrerequisiteReadContext` carries the raw course, module, inferred-set, and equivalence-group caches, so the inference-enabled pass and the official-only pass over the same request read each input once. Summaries, issues, coverage, and module boundaries are fresh per target and never cross the context boundary.

`PrerequisiteSatisfactionSession(structure, basis_group_ids)` in `src/course_explorer/prerequisite/satisfaction.py` evaluates the solver structure against one basis and memoizes piece results within the session. `evaluate` returns `PrerequisiteSatisfactionState`: `SATISFIED`, `UNSATISFIED`, or `UNRESOLVED`. Discovery builds one session per candidate over the chosen basis, so the coverage fold and the **All** root check share the memoized results.

`is_course_activity_eligible(structure, group_id, exception_group_ids, *, for_calculation=False)` in `src/course_explorer/prerequisite/graph.py` is the shared activity predicate. Discovery calls it for the candidate itself with an empty exception collection, so under active-only scope an inactive candidate is denied, while the retained basis identities satisfy requirement leaves.

## The coverage evaluator

`_CoverageEvaluator` in `src/course_explorer/next_courses/service.py` is a `PieceEvaluator[_Coverage]` fold over one native category root. `_Coverage` holds a canonical slot set plus an implicit unresolved slot count, and the fold memoizes one piece's coverage by owner and piece. An OR choice keeps the best-covered child, and the child's place in the ordered children breaks an equal fraction. One session serves the fold and the eligibility check.

| Piece kind | Coverage result |
|---|---|
| `course` | One slot keyed by `course_group_id`, covered when the session evaluates the piece as `SATISFIED`. |
| `expanded_course` | The union of the head and descendant coverage, summing unresolved positions. |
| `course_alternatives` | One slot keyed by the head course of the represented branch, covered only when the session satisfies the whole piece, so a partly met multi-course substitution covers nothing. |
| any `or` | The child with the greatest covered fraction, with the earlier child winning an equal fraction. |
| `and`, `cardinality` | The union of the children's slots, summing implicit unresolved positions including repeated child positions. |
| `module_block` | The fold over the inlined child alone. |
| `opaque_credits` | No slot, because a credit obligation names no course witness. |
| `unresolved` | One implicit unresolved position, counted without a canonical course key. |
| `credits`, `course_count` | The wrapped child's coverage passes through. |

`_Coverage.fraction` returns `covered / (canonical slots + unresolved slots)`, and `0.0` for an empty denominator.

## Eligibility and the inferred-dependence counterfactual

`_candidate_outcome(compilation, basis_group_ids, mode)` returns `(required_coverage, recommended_coverage)` or `None` for ineligible. It returns `None` when the root is a basis identity, when `is_course_activity_eligible(solver, root, ())` is false, when both category roots are `None`, or when both slot sets are empty. Each returned value is `covered / (canonical slots + implicit unresolved slots)`, and a category root that is `None` or whose denominator is zero yields `None` for that side rather than 0.0. `AT_LEAST_ONE` then needs one covered slot in the union of the two sets. `ALL` evaluates every non-`None` category root and needs `SATISFIED`, with `None` neutral.

`evaluate_next_course_outcomes(compilations, basis_group_ids, *, mode)` is the one outcome owner and records one entry per root, including `None`. `eligible_next_course_group_ids` returns the sorted roots whose entry is not `None` and consumes a supplied map directly. `next_courses_from_compilations` builds the results and sets `depends_on_inferred` on a result only when an official-only compilation of the same candidate is present and its entry from a map of the same owner is `None`, so a candidate that is eligible from official prerequisites alone is never marked.

The command bounds the second pass with `eligible_next_course_group_ids(first_pass, chosen, mode=..., candidate_outcomes=first_pass_outcomes)`, so the official-only compilation covers exactly the candidates that can appear. Without `include_inferred` no official-only compilation exists, every mark is `False`, and no second compile runs.

`_sorted_results` uses `name_code_key` and `official_display_name` from `src/course_explorer/search/lookup.py`. The key is `(display name missing, normalized display name, normalized code, group_id)`, and `official_display_name` falls back to the other language's name when the requested one is absent. `AT_LEAST_ONE` sorts by `(-required, -recommended, name_key)`, where `_ranked` reads an absent fraction as zero, and `ALL` sorts by `name_key` alone. The absent-fraction substitution applies to the order alone and never writes a value into the report.

```text
coverage(category) = covered slots of the best-covered option branch / slots of that branch
ALL          : every non-None category root evaluates to SATISFIED
AT_LEAST_ONE : at least one covered slot in required or recommended
depends_on_inferred = official-only compilation exists and its outcome is None
```

## Recommendation composition

`run_recommendations_command` in `src/course_explorer/recommendations/commands.py` is the one composition path:

1. It prepares the request and reads the discovery report through `_prepare_next_course_inputs` and `_read_next_courses`, so validation, basis choice, and the next-course list come from the one discovery path. A supplied prerequisite source-fact cache answers that step's raw course and module reads with the facts it retained for the dataset.
2. It selects the chosen basis identities from the next-course report, using `selected_group_ids` when the basis is `selected` and `completed_group_ids` otherwise, and returns an empty report for an empty basis before any recommendation read.
3. It loads `SearchSettings` and `EmbeddingSettings` and computes `embedding_configuration_sha256(embedding_settings)`.
4. It reads the basis records with `CurriculumRepository.get_represented_summaries` and their chunks with `TeachingEmbeddingRepository.get_chunks(..., descriptive_only=True, cache=chunk_cache)`, so the statement selects only `TeachingTextField.CONTENT` and `TeachingTextField.OUTCOMES` rows and a retained triple answers without a read. No basis chunk returns an empty report.
5. It excludes the chosen basis identities and the next-course identities, then calls `TeachingEmbeddingRepository.find_nearest_chunks`.
6. It reads the represented summaries of the hit identities, ranks them with `rank_recommendation_candidates`, reads the descriptive chunks of the surviving candidates through the same narrowed read and the same chunk cache, and ranks them with `recommendations_from_candidates` using `embedding_settings.embedding_hub_vector` and `embedding_settings.embedding_outcomes_hub_vector`.
7. It returns `RecommendationsReport(similarity_results=...)`.

`SimilarityRecommendation` holds `course`, `relatedness` (0 to 100), `score` (0 to 100), `overlap_with_basis` (0 to 100 or `None`), and `uses_derived_text`. `scripts/recommendations.py` forwards the same arguments as the next-course adapter. `POST /api/recommendations` applies the site's inference switch to `include_inferred`, so the next-course step behind the request reads official prerequisites alone on a site that serves no inference features. A site whose `WEB_EMBEDDINGS_ENABLED` is false answers that route with status 403 and the detail `Feature disabled` before the command runs. A served request returns the report with the serving dataset identity.

### The nearest read

`TeachingEmbeddingRepository.find_nearest_chunks(basis_chunks, *, embedding_configuration_hash, top_k, active_only, excluded_group_ids)` in `src/course_explorer/embeddings/read.py` builds one `values` table of `(query_index, language, embedding)` rows and joins a lateral subquery per basis query. That subquery requires a completed, non-null row under the exact configuration hash in `CONTENT` or `OUTCOMES`, the same language as its query, an identity outside `excluded_group_ids`, and, under active-only scope, `Course.is_active`, then orders by `CourseEmbeddingChunk.embedding.cosine_distance(query_embedding)` and limits to `top_k`. Row order follows the query index and the descending score. The vector column carries the `ix_course_embedding_chunks_embedding_hnsw` index with `vector_cosine_ops`, which [Tables and migrations](/docs/backend/catalogue/tables-and-migrations.md) lists.

### The descriptive chunk cache

`DescriptiveChunkCache` in the same module holds one served dataset's descriptive chunk tuples between requests. An entry is keyed by the read triple `(group_id, sisu_course_unit_id, representative_source_hash)` and holds the ordered `TeachingEmbeddingChunk` carriers that triple's read returned. The example sets `WEB_CHUNK_CACHE_ENTRIES` to 497 entries, and the store holds at most that many entries in least-recently-used order. An empty tuple is a retained entry, so a triple with no compatible descriptive row answers from the cache like a triple with rows. An entry lives until the bound evicts it, and one lock serializes every read and write. One instance belongs to one serving dataset identity.

A read with a cache looks each requested triple up and opens no session when every triple is retained. Only the missing triples reach `_read_batch`, in batches of `_REQUEST_BATCH_SIZE`, and every triple a batch reads is retained, an empty result included. A requested set holds one triple per canonical group, so concatenating each triple's ordered carriers in sorted-triple order returns the rows and the order of the uncached statement.

The all-field read passes no cache, and `get_chunks` raises `ValueError` when a call supplies a cache without `descriptive_only`. `ServingCaches.descriptive_chunks` owns the one instance of a serving dataset identity, and the two descriptive reads of the recommendation command share it.

## Ranking, the trimmed profile, and the near-duplicate rule

`rank_recommendation_candidates(neighbors, represented, *, excluded_group_ids, display_language, settings)` keeps a hit only when its group identity names a supplied representative record, the identity is not excluded, and the hit's `(sisu_course_unit_id, representative_source_hash)` equals the record's, so a stored chunk of a non-representative version is dropped. It keeps the greatest `neighbor.score` per candidate, maps it through `100 * clamp(score, 0, 1)`, and sorts the pool by that percentage in descending order, then by the name key. The percentage orders the pool alone and no cutoff compares it, so every hit the search returned that survives the identity checks reaches the measurement step.

A hit chooses a candidate identity, and the mapped percentage supplies the pool order. The values of every meter come from a second read: step 6 of the composition reads the chunks of the surviving candidates with `get_chunks`, so each candidate is measured over its complete compatible content and learning-outcomes text rather than the chunk that matched.

`recommendations_from_candidates(candidates, basis_chunks, candidate_chunks, *, display_language, settings, hub, outcomes_hub)` computes the meters from the centred vectors on float64 NumPy arrays.

`DESCRIPTIVE_TEACHING_TEXT_FIELDS` is `(CONTENT, OUTCOMES)`, and every vector is centred with `subtract_hub_for_field` from `src/course_explorer/embeddings/hub.py`, which selects the outcomes hub for an outcomes chunk and the embedding hub otherwise. Each centred chunk becomes one float64 row normalized to unit length, and a zero-length centred row raises `ValueError`. A course point is the unit mean of its chunk rows, so every chunk weights equally, unlike the character-weighted centroid of `src/course_explorer/comparison/service.py`. The profile, the relatedness and the overlap are computed with matrix products over those rows. The meters differ from a scalar evaluation of the same formula only in their last binary digits, so the retained set, the order, the exact ties, the median membership and the derived flag follow the formula alone.

```text
point(course)      = unit(mean of the centred unit chunk rows)
initial            = unit(mean of the basis course points)
consistency(c)     = dot(point(c), initial)
kept               = points with consistency >= median(consistency over the basis courses)
profile            = unit(mean of the kept points)      # a single basis course keeps its own point
relatedness        = 100 * max(0, dot(unit(mean of the candidate chunk rows), profile))
```

The candidate's point uses the candidate's own centred descriptive chunks. A candidate with no such chunk, or a basis with no descriptive chunk at all, contributes no result.

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

`overlap_percent(mean_cosine, *, floor, ceiling)` from `src/course_explorer/comparison/service.py` maps the configured floor to 0 and the ceiling to 100. A candidate is dropped when `relatedness` is below `recommendation_min_relatedness * 100` or when `strongest_course` reaches `recommendation_near_duplicate_percent`. `uses_derived_text` is true when any candidate chunk or any basis descriptive chunk carries `TeachingTextOrigin.DERIVED`. The final order is `(-score, -relatedness, name_key)`.

### Configuration keys

`SearchSettings` in `src/course_explorer/config.py` holds the recommendation policy, read from `config/search.toml`.

| Field | Key | Bounds | Example |
|---|---|---|---|
| `recommendation_chunk_top_k` | `RECOMMENDATION_CHUNK_TOP_K` | Greater than 0 | 40 |
| `recommendation_min_relatedness` | `RECOMMENDATION_MIN_RELATEDNESS` | 0 to 1 | 0.33 |
| `recommendation_near_duplicate_percent` | `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | 0 to 100 | 90 |
| `recommendation_overlap_penalty_weight` | `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | 0 to 1 | 0.0 |

The near-duplicate rule and the whole-basis overlap share `comparison_overlap_floor` and `comparison_overlap_ceiling`.

## Tests

| File | Covers |
|---|---|
| `tests/next_courses/test_next_courses.py` | Both modes and their orders over the real direct compiler, required and recommended coverage with an absent category reported as `None`, relationship-local official precedence, free-choice and nearest-version source shapes that keep a real slot, the omitted basis courses and slot-less candidates, a partly covered option that qualifies only in `AT_LEAST_ONE`, a multi-course substitution that needs every member, a basis that satisfies direct knowledge without its ancestors, the activity scope, and the retained inactive basis. |
| `tests/next_courses/test_next_courses_command.py` | Input refusal before any settings or database read, the CLI defaults and toggles, report round-tripping, and an empty basis that returns an empty report. |
| `tests/next_courses/test_next_courses_repository.py` | An opt-in PostgreSQL proof over a normalized catalogue: current direct, recommended, module, substitution, equivalence-only, and inferred-only routes, a stale stored version that the reverse read overselects and the compiler drops, the all-courses scope, the coverage order, partly covered substitutions, and the exclusion of the same-input next courses from recommendations. |
| `tests/recommendations/test_recommendations_service.py` | Ranking by the whole-basis profile, a course that duplicates one basis course being dropped, a course that points away from the profile falling below the floor, the derived-text flag, and the float64 scorer against a scalar reference of the same formula with an exact score tie, a multi-chunk candidate and both exclusion reasons. |
| `tests/recommendations/test_recommendations_command.py` | The adapter forwarding every argument once, validation before any read, the similarity-only report round-trip, and an empty basis that returns no results. |
| `tests/search/test_semantic_search_repository.py` | An opt-in PostgreSQL proof over a seeded chunk graph: the best-chunk score with the lifecycle and configuration scope, the descriptive subset in the full read's order, the retained descriptive triples that answer a repeated read with no statement, the nearest read, and the ranked candidate pool. |

The behaviour as the app presents it is described in [Next courses](/docs/backend/search-and-discovery/next-courses.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md).
