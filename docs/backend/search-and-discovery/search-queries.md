# Search queries and merge

The search package turns one query into ordered course summaries through the four match methods, one merge, and one shared read of the represented courses.

## The package and its services

| Module | Symbols |
|---|---|
| `src/course_explorer/search/lookup.py` | `CourseLookupService`, `ModuleLookupService`, `DisplayLanguage`, `FuzzyCourseResult`, `official_display_name`, `name_code_key`, `_normalized`, `_substring_matches`, `_fuzzy_name_scores`, `_alphabetical_key` |
| `src/course_explorer/search/service.py` | `CourseSearchService`, `SemanticCourseScore`, `CourseSearchResult`, `SemanticSearchRead` |
| `src/course_explorer/search/unified.py` | `UnifiedCourseSearchService`, `UnifiedCourseSearchResult`, `UnifiedSearchReport` |
| `src/course_explorer/search/repository.py` | `SemanticSearchRepository` |
| `src/course_explorer/search/commands.py` | `run_search_command` |
| `src/course_explorer/search/lookup_commands.py` | `run_course_lookup_command`, `run_module_lookup_command`, `run_course_summaries_command`, `CourseLookupReport`, `ModuleLookupReport`, `CourseSummariesReport`, `_validate_lookup_input` |

`UnifiedCourseSearchService` holds a `CurriculumRead`, a `CourseSearchService`, a `CourseLookupService`, and `SearchSettings`. `CourseSearchService` holds the same `CurriculumRead`, a `SemanticSearchRead` repository, an `EmbeddingProvider`, `EmbeddingSettings`, and `SearchSettings`. `CourseLookupService` holds a `CurriculumRead` and `SearchSettings`, and `ModuleLookupService` holds a `CurriculumRead` and the current academic year.

Every result DTO is frozen and closed: `FuzzyCourseResult(course, score)`, `CourseSearchResult(course, score)`, `SemanticCourseScore(group_id, sisu_course_unit_id, representative_source_hash, score)`, and `UnifiedCourseSearchResult(course, match_sources, fuzzy_score, semantic_score)`. `UnifiedSearchReport` carries the display language, the two effective thresholds, the activity scope, `semantic_available`, the configured tier order, and the merged results.

## Normalization and ordering

`_normalized(value)` is `unicodedata.normalize("NFKC", value).casefold().strip()`, so case, compatibility forms, and outer whitespace never decide a match. `official_display_name(summary, display_language)` returns the official name of the requested language and falls back to the other official name only when the requested one is absent, so a hidden second name is never matched.

`name_code_key(summary, display_name)` orders by `(display_name is None, _normalized(display_name), _normalized(code), summary.group_id)`, using `""` where a name or code is absent. `_alphabetical_key` prepends `not course.is_active`, and `exact_code_search` and `substring_search` both sort with it.

`exact_code_search` splits the query with `re.split(r"[,\s]+", query.strip())`, normalizes every token into a set, and matches a represented course whose `_normalized(code)` is in that set, so a repeated or unmatched token changes nothing. `substring_search` matches `_substring_matches(normalized_query, display_name, code)`, which tests code containment first and then displayed-name containment.

`fuzzy_name_search` skips a course with no displayed name, collects the normalized displayed names of the rest, calls `_fuzzy_name_scores` once for the whole sequence, keeps `score >= threshold`, and sorts by `(not is_active, -score, _normalized(display_name), _normalized(code), group_id)`. The cutoff is `SearchSettings.fuzzy_search_min_score` unless the caller supplies `min_score`, and the token weight is `SearchSettings.fuzzy_token_match_weight`.

`_fuzzy_name_scores(query, names, *, threshold, token_weight)` returns one `0-100` score per name in one call, reads no database, and holds no state beyond that call:

1. One `process.extract(query, names, scorer=fuzz.WRatio, processor=None, score_cutoff=threshold, limit=None)` call scores every name against the whole query and fills the entries at or above the cutoff of a zero-initialized list.
2. `re.findall(r"\w+", query)` gives the query tokens. With no token, or with `threshold > 100 * token_weight`, only the whole-name scores are returned, because token coverage can then never reach the cutoff.
3. Each name is split into tokens by the same expression, and the distinct tokens of all names form one request-local vocabulary.
4. `token_cutoff = max(0.0, len(query_tokens) * threshold / token_weight - 100 * (len(query_tokens) - 1))`. Below that bound even a perfect match for every other query token cannot reach the cutoff, so `process.extract(token, vocabulary, scorer=fuzz.ratio, processor=None, score_cutoff=token_cutoff, limit=None)` maps each distinct query token to the vocabulary tokens that reach that bound.
5. A name whose whole-name score is above `100 * token_weight`, or that has no token, is scored by its whole-name score. Every other name is scored by `max(whole_name_score, token_weight * total / len(query_tokens))`, where `total` sums, over every query token, that token's best `fuzz.ratio` against the name's tokens. The loop stops when `total` plus the best possible score for the remaining tokens falls below `required = len(query_tokens) * max(threshold, whole_name_score) / token_weight`, so a name that cannot reach the cutoff is scored by its whole-name score.

`WRatio` and `fuzz.ratio` both return a `0-100` score, so `FuzzyCourseResult.score` never mixes with the semantic scale. Token coverage reaches `100 * token_weight` at most, so a whole-name match at 100 outranks every token-only score while the weight is below 1.

`CourseSearchService.search_courses` sorts by `(not course.is_active, -score, course.group_id)`.

## The semantic read and the service

`SemanticSearchRepository.search` builds one statement over `CourseEmbeddingChunk`, `CourseVersion`, and `Course`, with the hub bound as a vector and the query bound in the pre-centred form `subtract_hub(query_embedding, hub)`. Its equivalent SQL is:

```sql
SELECT courses.group_id,
       course_versions.sisu_course_unit_id,
       course_embedding_chunks.representative_source_hash,
       max(1 - ((course_embedding_chunks.embedding - :hub_vector) <=> :centred_query)) AS score
FROM course_embedding_chunks
JOIN course_versions ON course_versions.id = course_embedding_chunks.course_version_id
JOIN courses ON courses.id = course_versions.course_id
WHERE course_embedding_chunks.status = 'completed'
  AND course_embedding_chunks.embedding IS NOT NULL
  AND course_embedding_chunks.embedding_configuration_hash = :configuration_hash
GROUP BY courses.group_id,
         course_versions.sisu_course_unit_id,
         course_embedding_chunks.representative_source_hash
HAVING max(1 - ((course_embedding_chunks.embedding - :hub_vector) <=> :centred_query)) >= :min_score
ORDER BY courses.group_id, course_versions.sisu_course_unit_id
```

When `include_inactive` is false the statement adds `AND courses.is_active IS TRUE`. One row per `(group_id, sisu_course_unit_id, representative_source_hash)` carries the greatest centred cosine of that version's chunks, and every row at or above the threshold is returned.

`SemanticSearchRead` is the protocol of that read, and it declares the `hub` keyword beside the query embedding, the threshold, the configuration hash, and the activity scope. The service call and the concrete repository therefore share one signature, so a read that needs a hub cannot be reached without one.

`CourseSearchService.search_courses` then:

1. Resolves the threshold from `min_score` or `SearchSettings.semantic_search_min_score`.
2. Embeds the query once: `provider.embed((query,))[0]`.
3. Computes `embedding_configuration_sha256(embedding_settings)`.
4. Calls the repository with the query vector, `hub`, the threshold, the configuration hash, and `include_inactive`.
5. Reads `list_represented_summaries(active_only=None if include_inactive else True)` unless the caller supplies `represented`, and maps the records by `summary.group_id`.
6. Keeps a score only when its `sisu_course_unit_id` and `representative_source_hash` equal the record's, so a score whose stored version or representative source hash differs from the record's is dropped.
7. Returns `CourseSearchResult` rows sorted by `(not is_active, -score, group_id)`.

The caller-supplied `represented` sequence is what lets one unified query read the represented courses once. `tests/search/test_search_service.py` proves the identity filtering, the supplied-summary reuse, the configured and overridden thresholds, the active-only scope, and the absence of a result cap.

## The merge

`UnifiedCourseSearchService.search` performs one `list_represented_summaries` read and passes the result to all four methods as `represented`. It then calls `exact_code_search`, `substring_search`, and `fuzzy_name_search` once each with the same query, display language, `include_inactive`, and the optional score overrides. It calls `search_courses` with the same inputs inside a `try` block that catches `EmbeddingRequestError` alone: that exception leaves an empty semantic tuple and `semantic_available` false, and every other failure propagates. A returned semantic tuple leaves availability true, whether or not it holds a result.

The call resolves the two effective thresholds from the supplied override or from `SearchSettings`, and returns one `UnifiedSearchReport` with the display language, the effective thresholds, the activity scope, availability, the configured tier order, and the merged results. `_merge` walks the four tuples in that fixed order and registers each entry:

- `summaries.setdefault(group_id, summary)` keeps the first summary registered for a canonical group. Every method carries the same shared `CourseSummary` for a group, so the choice of registration order does not change the merged course.
- `sources.setdefault(group_id, {})[method] = position` records the method and the entry's index in that method's own result list.
- `fuzzy_scores[group_id]` and `semantic_scores[group_id]` take the entry's score from its method.

For each merged group, `_merge` builds `tier_position = {method: index}` from `search_tier_priority`, orders the group's sources with `tuple(sorted(group_sources, key=tier_position.__getitem__))`, and takes the first one as the primary source. The sort key is `(tier_position[primary], not summary.is_active, group_sources[primary])`, and the merged list is sorted on that key. The merged entry carries `match_sources` in configured tier order, `fuzzy_score` when the fuzzy method matched, and `semantic_score` when the semantic method matched, in two separate optional fields so the `0-100` and cosine scales stay apart. A failed query embedding request leaves every `semantic_score` null, because no semantic match source exists in that report.

`UnifiedCourseSearchService.search` is the one owner of the report, and `run_search_command` returns that same report from inside the provider and database context.

## Commands and validation

`run_search_command` is the one validation boundary for a unified query. It raises `ValueError` for a query whose `strip()` is empty, for a display language outside `("fi", "en")`, for a semantic override outside the field's `-1` to `1` range, and for a fuzzy override outside `0` to `100`. It validates before it loads any settings or opens a database context.

The override ranges are read from the model metadata rather than repeated: `_SEMANTIC_SCORE_ADAPTER` and `_FUZZY_SCORE_ADAPTER` are `TypeAdapter`s built from `Annotated[float, *SearchSettings.model_fields[name].metadata]`, so a change to the `Field` bounds in `SearchSettings` changes the overrides the command allows too. `tests/search/test_search_command.py` proves that an invalid input reaches no settings load and no I/O.

After validation, the command loads the embedding and search settings and copies the two search query policy fields onto the embedding settings as one query-local projection: `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` and `SEARCH_EMBEDDING_MAX_ATTEMPTS` replace the loaded timeout and attempt count on a `model_copy` of the validated object. It opens one database context, composes the curriculum repository, the semantic repository, the lookup service, the semantic service, and the unified service, and constructs the one `EmbeddingProvider` of the request with that projection, so the query embedding request follows the search policy. The semantic service receives the loaded embedding settings, so the configuration hash and the hub vector the read uses come from those loaded settings. The hash covers the embedding model, the artifact hash, the dimension, the pooling, the normalization, and the runtime revision, so the two projected values do not enter it. The command returns the service's report. The engine lifetime of a request therefore holds one provider and one database context.

`_validate_lookup_input(query, display_language)` refuses a query whose `_normalized` form is empty and a display language outside `("fi", "en")` before the lookup commands load settings. `run_course_lookup_command` and `run_module_lookup_command` each call it, and `run_course_summaries_command` returns an empty report for an empty input without loading anything.

`scripts/search.py`, `scripts/course_lookup.py`, and `scripts/module_lookup.py` are thin `argparse` adapters over those commands. The search adapter maps `--active-only` to `include_inactive=not args.active_only` and prints `report.model_dump_json()`. The web API adapters `POST /api/search`, `POST /api/course-lookup`, `POST /api/module-lookup`, and `POST /api/course-summaries` do the same through their request models.

## Resolving identities and modules

`CourseLookupService.resolve_courses` materializes the identifiers and returns `()` for an empty input before any read. Otherwise it runs `_resolve_represented_records`:

1. One scoped `get_represented_summaries` read over the outer-trimmed identifiers fills `by_group_id`, and each identifier that matches a canonical group id resolves there. An all-canonical call skips the code projection entirely.
2. For each other identifier, one `list_course_code_identities` read collects the `(group_id, code)` pairs of the whole catalogue, a shared `_normalized` comparison collects the candidate canonical ids, and a second scoped `get_represented_summaries` read loads only those candidates.
3. `by_normalized_code` maps each candidate's current representative code to its record, so a stored version's code is not matched on its own.
4. Each input resolves in caller order, and a repeated input repeats the same record object. An unknown input raises `ValueError` naming the identifier, and a code held by more than one canonical course raises `ValueError` listing the canonical ids.

`ModuleLookupService.substring_search` reads `list_module_lookup()` once, selects each canonical module's eligible versions through `module_version_candidates(versions, academic_year_start=...)`, skips a module with no candidate, matches `_substring_matches` over the displayed name and code of the candidates, and raises `ValueError` when the eligible set holds more than one version and any of them matches. It builds one `ModuleSummary` per match and sorts by `(module_type is not ModuleType.DEGREE_PROGRAMME, *name_code_key(...))`, so degree programmes come first.

## Tests

| File | Covers |
|---|---|
| `tests/search/test_unified_search.py` | One dispatch per method with identical inputs, the single shared represented read, per-method source tagging with both scores kept apart, the configured tier order over activity and primary-method position, a reordered `SEARCH_TIER_PRIORITY`, the absence of a cap, the effective thresholds of the report, the partial report of a failed query embedding request with its lexical matches kept, and the propagation of every other failure from the semantic seam. |
| `tests/search/test_search_service.py` | The shared summary mapping, the configured threshold, the one provider call, current-representative identity filtering, active-first order, the override and active-only forwarding, and the supplied-summary path that reads nothing. |
| `tests/search/test_course_lookup.py` | The fuzzy cutoff, the token-coverage score of a misspelled query, the whole-name score above a token-only score, the fuzzy ordering, hidden-name exclusion, the exact multi-code split, substring name and code containment without a cap, the canonical-first resolver with its order, repeats and failures, and the module lookup with programmes first and ambiguity failing. |
| `tests/search/test_search_command.py` | The composition of both services in one engine lifetime, the query-local embedding projection the provider receives while the semantic service is composed with the loaded settings, the command returning the service's own report object, the single short-timeout query embedding request, and the validation that reaches no settings load. |
| `tests/search/test_lookup_commands.py` | Both lookup commands refusing blank and unsupported input before settings, the empty summary request, both CLI adapters, and the API rejection of a blank query. |
| `tests/search/test_semantic_search_repository.py` | Opt-in PostgreSQL proofs of the exact best-chunk read, the lifecycle and configuration filters, the inactive scope, the threshold, the scoped vector read, and the comparison command over the same data. |

`tests/search/_service_support.py`, `_lookup_support.py`, and `_repository_support.py` supply the recording fakes and the catalogue builders the tests share.

## Where to change a behavior

- Adding a match method to the package: add the token to `SearchMethod` and `_SEARCH_METHODS` in `src/course_explorer/config.py` for the tier order, dispatch it in `UnifiedCourseSearchService.search`, and register it in `_merge`.
- The merged order: `_merge` in `src/course_explorer/search/unified.py`.
- The semantic statement and its filters: `SemanticSearchRepository.search` in `src/course_explorer/search/repository.py`.
- Name or code normalization and the string methods: `_normalized`, `official_display_name`, and the three methods of `CourseLookupService` in `src/course_explorer/search/lookup.py`.
- Caller input rules: `run_search_command` in `src/course_explorer/search/commands.py` and `_validate_lookup_input` in `src/course_explorer/search/lookup_commands.py`.
- The query embedding request policy: the two `SEARCH_EMBEDDING_*` fields of `SearchSettings` in `src/course_explorer/config.py` and the projection `run_search_command` builds from them.

The four methods, the tier order, and the three reads over official identity are described in [Search](/docs/backend/search-and-discovery/search.md).
