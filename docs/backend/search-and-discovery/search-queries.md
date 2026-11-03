# Search queries and merge

The search package merges the match methods into ordered course summaries from a lookup projection the caller builds: the supervisor before it forks its workers, or the search command.

## The package and its services

| Module | Symbols |
|---|---|
| `src/course_explorer/search/lookup.py` | `CourseLookupService`, `DisplayLanguage`, `FuzzyCourseResult`, `official_display_name`, `name_code_key`, `_substring_matches`, `_fuzzy_name_scores`, `_alphabetical_key` |
| `src/course_explorer/search/projection.py` | `normalized_text`, `CourseLookupRow`, `LookupProjection`, `build_lookup_rows`, `build_lookup_projection`, `official_name` |
| `src/course_explorer/search/resolver.py` | `CourseResolver` |
| `src/course_explorer/search/tokens.py` | `LookupTokenTable`, `title_tokens`, `build_token_table` |
| `src/course_explorer/search/native_lookup.py` | `apply_token_coverage`, which loads the native fuzzy-name coverage library |
| `src/course_explorer/search/service.py` | `CourseSearchService`, `SemanticCourseScore`, `CourseSearchResult`, `SemanticSearchRead` |
| `src/course_explorer/search/unified.py` | `UnifiedCourseSearchService`, `UnifiedCourseSearchResult`, `UnifiedSearchReport` |
| `src/course_explorer/search/repository.py` | `SemanticSearchRepository`, which calls the installed packed scan function |
| `src/course_explorer/search/commands.py` | `run_search_command` |
| `src/course_explorer/search/lookup_commands.py` | `run_catalogue_command`, `run_course_summaries_command`, `CatalogueReport`, `NarrowingCourse`, `NarrowingModule`, `NarrowingModuleVersion`, `CourseSummariesReport` |

`UnifiedCourseSearchService` holds a `CourseSearchService` or `None` when the site serves no semantic matching, a `CourseLookupService`, and `SearchSettings`. `CourseSearchService` holds a `SemanticSearchRead` repository, an `EmbeddingProvider`, the opened build's catalogue hub, and `SearchSettings`. `CourseLookupService` holds `SearchSettings` and the required `LookupProjection` that the caller builds, either the supervisor before it forks the workers or the search command.

Every result DTO is frozen and closed: `FuzzyCourseResult(course, score)`, `CourseSearchResult(course, score)`, `SemanticCourseScore(group_id, sisu_course_unit_id, representative_source_hash, score)`, and `UnifiedCourseSearchResult(course, match_sources, fuzzy_score, semantic_score)`. `UnifiedSearchReport` carries the display language, the two effective thresholds, the activity scope, `semantic_available`, the effective tier order, and the merged results.

## Normalization and ordering

`normalized_text(value)` in `src/course_explorer/search/projection.py` is `unicodedata.normalize("NFKC", value).casefold().strip()`, so case, compatibility forms, and outer whitespace never decide a match. `build_lookup_rows(summaries)` retains one `CourseLookupRow(summary, code_key, name_fi_key, name_en_key)` per summary, so a matcher normalizes each name and code once per dataset. A row carries no position, because a matcher reaches a row through the name list its projection stores and the position array beside it. `official_name(name_fi, name_en, display_language)` returns the official name of the requested language and falls back to the other official name only when the requested one is absent, so a hidden second name is never matched. `official_display_name(summary, display_language)` is the same rule over a `CourseSummary`.

`name_code_key(summary, display_name)` orders by `(display_name is None, normalized display name, normalized code, summary.group_id)`, using `""` where a name is absent. `_alphabetical_key` prepends `not row.summary.is_active`, and `exact_code_search` and `substring_search` both sort with it.

```text
query = normalized_text(input)
row   = CourseLookupRow(summary, code_key, name_fi_key, name_en_key)
```

`exact_code_search` splits the query with `re.split(r"[,\s]+", query.strip())`, normalizes every token into a set, and matches a row whose retained `code_key` is in that set, so a repeated or unmatched token changes nothing. `substring_search` matches `_substring_matches(normalized_query, display_name_key, code_key)`, which tests code containment first and then displayed-name containment.

`fuzzy_name_search` scores the projection's normalized name list for the display language. It reads that language's `name_keys` and `name_positions` under the all-courses scope, or the `active_name_keys` and `active_name_positions` pair under active only, and reuses the projection's token table. It calls `_fuzzy_name_scores` once for the whole sequence, keeps `score >= threshold`, maps each kept index back to its row through the position array, and sorts by `(not is_active, -score, normalized display name, code key, group_id)`. The cutoff is `SearchSettings.fuzzy_search_min_score` unless the caller supplies `min_score`, the token weight is `SearchSettings.fuzzy_token_match_weight`, and the tie-break weight is `SearchSettings.fuzzy_score_tie_break_weight`.

The projection keeps both activity scopes. `courses` and `active_courses` hold the row tuples, `by_group_id` and `active_by_group_id` hold the represented records, and each display language has its `name_keys` with `name_positions` beside an `active_` pair, so a query of either scope reads its own list and the fuzzy method maps a score back to a row without rebuilding a list.

`_fuzzy_name_scores(query, names, positions, table, *, threshold, token_weight, tie_break_weight)` returns one `numpy` score array of 0 to 100 values aligned with `names`, reads no database, and holds no state beyond that call:

1. One `process.cdist([query], names, scorer=JaroWinkler.normalized_similarity, dtype=numpy.float64)` call scores every name against the whole query, multiplied by 100 into a zero-initialized similarity array. Jaro-Winkler is symmetric and rewards a shared prefix, so a longer query does not raise a shorter, unrelated name the way a partial whole-string ratio does.
2. `title_tokens(query)` gives the query tokens. With a token and a cutoff at or below `100 * token_weight`, `native_lookup.apply_token_coverage` fills a second 0 to 100 array over the same name list.
3. `table` holds one display language's token table: each title's token positions, the distinct vocabulary, and every token's code points. The projection builds one table per display language, so a query tokenizes no title. `positions` maps each score entry back to its index in the row tuple, and the projection's arrays make that a direct read.
4. The native matcher computes the normalized Indel similarity of each query token against every vocabulary token. That value is the same `fuzz.ratio` score, `100 * (1 - distance / (length_a + length_b))`, and it is kept only when it reaches `token_cutoff = max(0.0, len(query_tokens) * threshold / token_weight - 100 * (len(query_tokens) - 1))`.
5. A name's coverage is `token_weight * total / len(query_tokens)`, where `total` sums, over every query token, that token's best similarity against the name's tokens. The loop stops when `total` plus the best possible score for the remaining tokens falls below `required = len(query_tokens) * max(threshold, whole_name_score) / token_weight`, so a name that cannot reach the cutoff or beat its own whole-name score scores no coverage and keeps its whole-name score. A name whose whole-name score exceeds `100 * token_weight` skips the coverage loop, because its coverage cannot exceed that bound.
6. The stronger of the two arrays decides membership: a name is kept when `max(coverage, similarity) >= threshold`. Its score is `stronger + tie_break_weight * weaker * (100 - stronger) / 100`, which stays within 0 to 100 and cannot fall below the stronger value, so the tie-break orders matches without filtering one. Every name below the cutoff takes 0.

Jaro-Winkler times 100 and the native similarity both return a `0-100` score, so `FuzzyCourseResult.score` never mixes with the semantic scale. Token coverage reaches `100 * token_weight` at most, so a whole-name match at 100 outranks every token-only score while the weight is below 1.

`CourseSearchService.search_courses` sorts by `(not course.is_active, -score, course.group_id)`.

## The semantic read and the service

`SemanticSearchRepository.search` calls the installed packed scan function once with the hub-centred query and the build's group count. It joins the returned group number to the canonical representative identity and the course activity state, applies the threshold, and returns every qualifying identity order by canonical group and version. Its equivalent SQL is:

```sql
SELECT g.group_id, g.sisu_course_unit_id, g.representative_source_hash, s.score
FROM course_embedding_search_scan(
    'course_embedding_search_blocks'::regclass,
    :centred_query,
    inner_product(CAST(:centred_query AS vector), CAST(:centred_query AS vector)),
    :group_count
) AS s
JOIN course_embedding_search_groups AS g ON g.group_no = s.group_no
JOIN courses AS c ON c.group_id = g.group_id
WHERE s.score >= :min_score
ORDER BY g.group_id, g.sisu_course_unit_id
```

When `include_inactive` is false the statement adds `AND c.is_active`. The scan returns one row per stored group, and one group is one `(group_id, sisu_course_unit_id, representative_source_hash)` with the greatest centred cosine of its chunks. The scan function takes the vector dimension from the query vector it receives and checks every block payload against that dimension, so a block must hold that many float32 vectors. The artifact set reads the packed meta row once when it opens and keeps the group count alone in `ServingSearchMeta`, so no request reads or verifies that row.

`SemanticSearchRead` is the protocol of that read. It declares the query embedding, the hub, the threshold and the activity scope. The service call and the concrete repository share one signature, so a read that needs a hub cannot be reached without one. The embedding configuration is fixed by the `embedding-<configuration hash>` directory the opened set maps, and the build writes the packed relation from the completed rows of that same configuration, so a vector of another configuration takes no part in the scan.

`CourseSearchService.search_courses` then:

1. Resolves the threshold from `min_score` or `SearchSettings.semantic_search_min_score`.
2. Embeds the query once: `provider.embed((query,))[0]`.
3. Calls the repository with the query vector, `hub`, the threshold and `include_inactive`.
4. Maps the caller-supplied `represented` records by `summary.group_id`.
5. Keeps a score only when its `sisu_course_unit_id` and `representative_source_hash` equal the record's, so a score whose stored version or representative source hash differs from the record's is dropped.
6. Returns `CourseSearchResult` rows sorted by `(not is_active, -score, group_id)`.

`search_courses` requires the `represented` sequence, which is how one unified query pairs the semantic scores with the current representatives. `tests/search/test_search_service.py` proves the identity filtering, the exact-identity pairing of a supplied sequence, the configured and overridden thresholds, the active-only scope, and the absence of a result cap.

## The merge

`UnifiedCourseSearchService.search` takes the represented records from `CourseLookupService.represented_index(include_inactive=...)` once when it holds a semantic service, so that method can pair its scores with the current representatives. The projection's group index answers that call without a catalogue read. `exact_code_search` and `substring_search` each read their scoped rows from the projection through `lookup_rows`.

`fuzzy_name_search` takes no row set. It scores the projection's name list, name positions and token table for the requested activity scope, so it reads no catalogue row. A site without a semantic service takes no represented index for pairing.

It then calls `exact_code_search`, `substring_search`, and `fuzzy_name_search` once each with the same query, display language, `include_inactive`, and the optional score overrides. Its semantic tuple and availability start empty and false, and it calls `search_courses` with the same inputs, inside a `try` block that catches `EmbeddingRequestError` alone, only when it holds a semantic service: that exception leaves an empty semantic tuple and `semantic_available` false, every other failure propagates, and a returned semantic tuple leaves availability true, whether or not it holds a result.

The call resolves the two effective thresholds from the supplied override or from `SearchSettings`, and returns one `UnifiedSearchReport` with the display language, the effective thresholds, the activity scope, availability, the effective tier order, and the merged results. Without a semantic service the effective tier order is the configured `search_tier_priority` without its `semantic` member, while the configured tuple itself holds the validated four members. `_merge` registers the method tuples in a fixed sequence, exact code, substring, fuzzy name, then semantic, whatever order the configured tier priority holds. The configured order decides the order of each result's sources, which source is primary, and the tier position that sorts the merged results. Registration works as follows:

- `summaries.setdefault(group_id, summary)` keeps the first summary registered for a canonical group. Every method carries the same shared `CourseSummary` for a group, so the choice of registration order does not change the merged course.
- `sources.setdefault(group_id, {})[method] = position` records the method and the entry's index in that method's own result list.
- `fuzzy_scores[group_id]` and `semantic_scores[group_id]` take the entry's score from its method.

For each merged group, `_merge` builds `tier_position = {method: index}` from `search_tier_priority`, orders the group's sources with `tuple(sorted(group_sources, key=tier_position.__getitem__))`, and takes the first one as the primary source. The sort key is `(tier_position[primary], not summary.is_active, group_sources[primary])`, and the merged list is sorted on that key. The merged entry carries `match_sources` in configured tier order, `fuzzy_score` when the fuzzy method matched, and `semantic_score` when the semantic method matched, in two separate optional fields so the `0-100` and cosine scales stay apart. A failed query embedding request leaves every `semantic_score` null, because no semantic match source exists in that report. A search without a semantic service leaves them null for the same reason, and the semantic member of the configured tier order then contributes no source.

`UnifiedCourseSearchService.search` is the one owner of the report, and `run_search_command` returns that same report from inside the provider and database context.

## Commands and validation

`run_search_command` is the one validation boundary for a unified query. It raises `ValueError` for a query whose `strip()` is empty, for a display language outside `("fi", "en")`, for a semantic override outside the field's `-1` to `1` range, and for a fuzzy override outside `0` to `100`. It validates before it loads any settings or opens a database context.

The override ranges are read from the model metadata rather than repeated: `_SEMANTIC_SCORE_ADAPTER` and `_FUZZY_SCORE_ADAPTER` are `TypeAdapter`s built from `Annotated[float, *SearchSettings.model_fields[name].metadata]`, so a change to the `Field` bounds in `SearchSettings` changes the overrides the command allows too. `tests/search/test_search_command.py` proves that an invalid input reaches no settings load and no I/O.

After validation, the command loads the search settings and opens one database context. It composes the lookup service around the required projection and the unified service, so every lexical method reads the projection's rows and token tables and issues no catalogue read.

Only when `include_semantic` is true does it load the embedding settings, build the semantic repository and the semantic service, and enter the request's one `EmbeddingProvider` through an `ExitStack` that owns the provider lifetime. A command run with `include_semantic` false therefore loads no embedding settings, builds no provider, reads no stored vector, and hands the unified service no semantic service.

When the provider is composed it receives the query-local projection: `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` and `SEARCH_EMBEDDING_MAX_ATTEMPTS` replace the loaded timeout and attempt count on a `model_copy` of the validated embedding settings, so the query embedding request follows the search policy. The serving route supplies the supervisor's one embedding client under `embedding_client`, and the provider leaves that client open because its owner holds it for the process lifetime. A caller that supplies none lets the provider create and close its own client.

When the caller supplies a query-embedding cache, the provider also receives the embedding configuration identity, so a cached vector belongs to the running configuration and an exact query text returns it without an HTTP request. The semantic service receives the opened build's catalogue hub, and the command takes the embedding configuration identity the caller supplies or hashes the loaded embedding runtime settings when the caller supplies none. The hash covers the embedding model, the artifact hash, the dimension, the pooling, the normalization, and the runtime revision, so the two projected values do not enter it. The command returns the service's report, and the engine lifetime of a request holds at most one provider and one database context.

`run_course_summaries_command` returns an empty report for an empty input without loading anything, and a supplied projection answers its resolution without a database read. `run_catalogue_command` reads the configured academic year once, then either takes the course rows and module identities of a supplied lookup projection or reads the represented summaries and the projected module identities once inside one database lifetime. It maps only the narrowing fields, and selects each module's strict candidates through `module_version_candidates`.

`scripts/search.py` and `scripts/catalogue.py` are thin `argparse` adapters over those commands. The search adapter maps `--active-only` to `include_inactive=not args.active_only` and prints `report.model_dump_json()`, and the catalogue adapter takes no argument and prints its report. The web API adapters `POST /api/search`, `POST /api/catalogue`, and `POST /api/course-summaries` do the same through their request models.

## Identity resolution and browser narrowing

`CourseResolver` in `src/course_explorer/search/resolver.py` is the one identity resolution. `resolve_courses(identifiers)` materializes the identifiers and returns `()` for an empty input before any read. It matches an outer-trimmed exact canonical `group_id` first and an exact current official code second, and it returns one `RepresentedCourseSummary` per input in caller order, so a repeated input repeats the same record.

A supplied `LookupProjection` answers both steps from its `by_group_id` and `by_code` maps. `by_group_id` holds every represented record by canonical group, and `by_code` maps one normalized current representative code to the canonical groups that carry it. Without a projection, one scoped `get_represented_summaries` read over the outer-trimmed identifiers fills `by_group_id`, and each identifier that matches a canonical group id resolves there. An all-canonical call skips the code projection entirely.

For each other identifier on the read path, one `list_course_code_identities` read collects the `(group_id, code)` pairs of the whole catalogue, a shared `normalized_text` comparison collects the candidate canonical ids, and a second scoped `get_represented_summaries` read loads only those candidates. `by_normalized_code` maps each candidate's current representative code to its record, so a stored version's code is not matched on its own. A code shared by more than one canonical course raises `ValueError` listing the canonical ids, and a code that matches no represented course raises the unknown-code error. There is no fuzzy, name, substring or multi-code matching.

Every command that resolves a caller identity builds one `CourseResolver` over its `CurriculumRepository` and the supplied projection: the catalogue summary command, the comparison command, the prerequisite and route commands, and the next-course command. `CourseLookupService` answers the rows, the represented index and the fuzzy, exact-code and substring methods from its projection, and it performs no identity resolution.

`web/src/shared/course/narrowing.ts` ports that matching to the browser over the catalogue. `narrowCourses` applies the same NFKC, casefold and trim rule through `normalizeLookup`, the displayed-name fallback and the `(not is_active, *name_code_key)` order with a code-point comparison. `narrowModules` returns one row per canonical group that has a matching eligible candidate. The row holds the group's full eligible candidate list and the displayed candidate's kind, code and names, which follow the displayed-name and code order with the exact version identity as the tie-break, so no version is guessed and a matching sibling never narrows the group. The local filter never caps the result.

## Tests

| File | Covers |
|---|---|
| `tests/search/test_unified_search.py` | One dispatch per method with identical inputs, the one lookup-service represented access that the semantic pairing reuses, per-method source tagging with both scores kept apart, the configured tier order over activity and primary-method position, a reordered `SEARCH_TIER_PRIORITY`, the absence of a cap, the effective thresholds of the report, the partial report of a failed query embedding request with its lexical matches kept, and the propagation of every other failure from the semantic seam. |
| `tests/search/test_search_service.py` | The shared summary mapping, the configured threshold, the one provider call, current-representative identity filtering, active-first order, the override and active-only forwarding, exact-identity pairing of a supplied represented sequence, and the absence of a result cap. |
| `tests/search/test_course_lookup.py` | The fuzzy cutoff, the token-coverage score of a misspelled query, the whole-name score above a token-only score, the fuzzy ordering, hidden-name exclusion, the exact multi-code split, substring name and code containment without a cap, the canonical-first resolver with its order, repeats and failures, and the catalogue's strict module candidate selection. |
| `tests/search/test_search_command.py` | The composition of both services in one engine lifetime, the query-local embedding projection the provider receives while the semantic service is composed with the loaded settings, the command returning the service's own report object, the single short-timeout query embedding request, the lexical-only run that reaches no embedding settings, provider or semantic repository and reports an effective tier order without semantic, and the validation that reaches no settings load. |
| `tests/search/test_lookup_commands.py` | The catalogue command's minimal projection and module kind, the no-argument catalogue adapter, and the empty summary request. |
| `tests/search/test_semantic_search_repository.py` | Opt-in PostgreSQL proofs of the exact packed read, the lifecycle and configuration scope, the inactive filter, the threshold, the shared descriptive store order, and the comparison command over the same data. |

`tests/search/_service_support.py`, `_lookup_support.py`, and `_repository_support.py` supply the recording fakes and the catalogue builders the tests share.

## Where to change a behavior

- Adding a match method to the package: add the token to `SearchMethod` and `_SEARCH_METHODS` in `src/course_explorer/config.py` for the tier order, dispatch it in `UnifiedCourseSearchService.search`, and register it in `_merge`.
- The merged order: `_merge` in `src/course_explorer/search/unified.py`.
- The semantic statement and its filters: `SemanticSearchRepository.search` in `src/course_explorer/search/repository.py`.
- Name or code normalization and the string methods: `normalized_text` in `src/course_explorer/search/projection.py`, `official_display_name`, and the three methods of `CourseLookupService` in `src/course_explorer/search/lookup.py`. The browser port is `normalizeLookup`, `narrowCourses` and `narrowModules` in `web/src/shared/course/`.
- Caller input rules: `run_search_command` in `src/course_explorer/search/commands.py`.
- The query embedding request policy: the two `SEARCH_EMBEDDING_*` fields of `SearchSettings` in `src/course_explorer/config.py` and the projection `run_search_command` builds from them.
- The optional semantic composition and the effective tier order: `run_search_command` in `src/course_explorer/search/commands.py` and `UnifiedCourseSearchService.search` in `src/course_explorer/search/unified.py`.
- The native fuzzy-name scorer and the container build that produces it: `native/lookup.cpp` and `scripts/build_native.py`. [Native libraries](/docs/architecture/native-libraries.md) states the three compiled libraries and the host libraries they load.

The four methods, the tier order, and the two reads over official identity are described in [Search](/docs/backend/search-and-discovery/search.md).
