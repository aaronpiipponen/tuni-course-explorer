# Search

A search query matches courses through four methods, and the app merges their results into one ordered list per course.

## One query, four methods

[Unified search](/docs/reference/glossary.md#search-and-comparison) runs all four search methods for one query and merges their results into one entry per course, so a course that several methods match appears once with the list of methods that matched it. The four methods are Exact code, Substring, Fuzzy search, and Semantic.

One request carries the query, the app language, a minimum score for each scored method, and whether inactive courses take part. The request reads the represented courses once and shares that read between the four methods, so every method describes the same catalogue.

The semantic method needs a vector for the query, and it embeds the query through the same service that produced the stored vectors. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes that service and the vectors it stores.

![One query reaches the four search methods, and the embedding service supplies the query vector that the semantic method measures. The four methods' results are merged into one entry per course and ordered by the configured tier order.](/docs/diagrams/search-pipeline.svg)

## The four search methods

Each method has its own matching rule, its own cutoff where it has one, and its own order.

> [!IMPORTANT]
> The fuzzy cutoff and the semantic threshold decide how many courses those two methods return. Every course a method matches at or above its cutoff is returned, and no method applies a result-count limit. Lowering either cutoff widens the result.

### Exact code

The query is split into tokens on commas and whitespace, and each token is normalized and counted once. A course matches when its official code equals one of those tokens, so a comma-separated list of codes finds every course in the list. A token that names no course adds nothing to the result.

### Substring

A course matches when the query is contained in its official code or in the name the app shows for the app language of the request, ignoring case. The match is a containment test on official identity, so it needs no exact spelling of a whole name.

### Fuzzy search

Fuzzy search scores the displayed official name of each course against the query from 0 to 100 and keeps every course at or above the cutoff, so a name with a typo or a different word order can match as well. A course with no displayed official name takes no part in the scoring. `FUZZY_SEARCH_MIN_SCORE` in `config/search.toml` sets the cutoff, and the example sets 80.

### Semantic

The semantic method embeds the query and measures that vector against the stored vectors of the represented courses. A course's relevance is its best chunk. The read takes the completed chunks of the course's current representative version that were written under the configured embedding configuration, and a chunk of another version, a pending chunk, and a failed chunk contribute no score. A score is a cosine measured after the embedding hub is subtracted from the query vector and from the stored vector, so a score runs from -1 to 1 and an unrelated course scores close to zero. Every course whose best chunk reaches the threshold is returned. `SEMANTIC_SEARCH_MIN_SCORE` in `config/search.toml` sets the threshold, and the example sets 0.30.

## Running one search

The two keys in `config/search.toml` set the fuzzy cutoff and the semantic threshold that every request uses. A request may carry its own fuzzy cutoff from 0 to 100 or its own semantic threshold from -1 to 1, and that value replaces the configured one for that request, so one caller can read a narrower or a wider result than the configured default.

```bash
uv run python scripts/search.py "data structures" --display-language en --active-only
```

The command runs one unified search and prints one JSON report with the merged results, the effective fuzzy cutoff, the effective semantic threshold, the activity scope, the tier order, and whether semantic matching was available.

## When the query embedding request fails

The semantic method needs a query vector, and a search makes one query embedding request for it. `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` in `config/search.toml` is the timeout of that request in seconds and is greater than 0, and the example sets 5. `SEARCH_EMBEDDING_MAX_ATTEMPTS` is its attempt count including the first, at least 1, and the example sets 1. The timeout bounds the network phases of each attempt, so it is not a deadline for the whole search. The two keys are separate from the generation policy of the embedding stage, which `EMBEDDING_REQUEST_TIMEOUT_SECONDS` and `EMBEDDING_MAX_ATTEMPTS` set for its batch requests.

A transport failure, a 429 status, and a status from 500 to 599 are retried while attempts remain, up to the attempt count `SEARCH_EMBEDDING_MAX_ATTEMPTS` sets, with a wait that grows between attempts, and every other non-200 status ends the request at once. The query embedding request fails when no attempt succeeds. When it fails, the search returns the exact-code, substring, and fuzzy matches it found. The report then carries `semantic_available` false, no semantic match source, and no semantic score in any result, and it may carry no result at all. A request that reaches the service and returns no course above the threshold reports `semantic_available` true, because the method ran and found nothing. A malformed successful response, a database failure, and an invalid input are not request failures, and each one ends the search with a failure and no report.

## Scores and match sources

Each merged result carries the methods that matched it and the score of each scored method that matched. A fuzzy score is a percentage from 0 to 100 and a semantic score is a cosine from -1 to 1, and the two live in separate fields.

## Tier order

Merged results are ordered by [tier order](/docs/reference/glossary.md#search-and-comparison). `SEARCH_TIER_PRIORITY` in `config/search.toml` lists the four methods in their order of precedence, and it must name each of them exactly once. The example sets `exact_code`, `substring`, `fuzzy_name`, and `semantic` in that order.

Three rules decide the merged order, applied in turn.

1. The place of the result's first match source in the configured order. A course that matched only the semantic method therefore comes after a course that matched the substring method, whatever order the two methods returned them in.
2. Active courses before inactive courses.
3. The place of the course in the ordered results of that first match source.

Each method orders its own results before the merge. Exact code and Substring list active courses first, then courses with a displayed name before courses without one, then by displayed name, official code, and canonical identity. Fuzzy search and Semantic list active courses first and then by descending score, so the two scored methods order their own tier by relevance.

## Language and activity

The app language decides which official name the string methods read: the official name in that language when the version carries one, otherwise the other official name. A version that carries the name of the app language is matched on that name alone, so a search matches the name the app shows. An exact code match reads the official code, which is the same in Finnish and in English, and the semantic method measures the embedded teaching text, so its matches follow the meaning of the query in either language.

Whether inactive courses take part is one setting of a request, and every method honours it, so a search limited to active courses returns active courses only. The Search tab offers that setting as its Active only switch.

## Validation outcomes

The search refuses a blank query, an app language other than Finnish or English, a semantic threshold outside -1 to 1, and a fuzzy cutoff outside 0 to 100. It decides all four before it loads any settings or reads the database, and its report repeats the thresholds, the inactive-course setting, and the semantic availability it used.

## Other reads over official identity

Three reads serve the other tabs: the course lookup, the module lookup, and the id-or-code resolver. Each one matches official identity directly and returns one entry per canonical course or module, so a picker or a stored identity gets its answer from one read.

### Course lookup

The course lookup returns every represented course whose displayed official name or official code contains the query, ignoring case. It takes the app language and its own setting for inactive courses, and it refuses a blank query and an unsupported app language before it reads any settings.

### Module lookup

The module lookup returns the modules of the current academic year whose displayed official name or code contains the query, ignoring case. Degree programmes come first, then the other modules, ordered by displayed name and code. Modules carry no activity flag, so no scope applies, and every matching module is returned. A module with more than one version for the current academic year makes the lookup fail when it matches, so no version is chosen silently.

### The id-or-code resolver

The Compare, Prerequisites, Discover, and Structure of studies tabs hold courses by their canonical identity and resolve those identities here. An input is matched first as an exact canonical identity and then as an exact official code, and each input resolves to exactly one represented course. The result keeps the order of the inputs, and an input that appears twice resolves twice. A blank input, an unknown input, and an official code that matches more than one canonical course each fail instead of resolving to a guess.

## Configuration keys

| Key | Meaning |
|---|---|
| `SEARCH_TIER_PRIORITY` | The order of the four search methods that sorts merged results. The example sets `exact_code`, `substring`, `fuzzy_name`, and `semantic` in that order. |
| `SEMANTIC_SEARCH_MIN_SCORE` | The smallest semantic score that returns a course, from -1 to 1. The example sets 0.30. |
| `FUZZY_SEARCH_MIN_SCORE` | The smallest name-similarity score that returns a course, from 0 to 100. The example sets 80. |
| `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` | The timeout of the one query embedding request a search makes, in seconds and greater than 0. The example sets 5. |
| `SEARCH_EMBEDDING_MAX_ATTEMPTS` | The attempt count of that query embedding request, the first included, at least 1. The example sets 1. |

The services behind the four methods, the read that the semantic method measures against, and the merge are described in [Search queries and merge](/docs/backend/search-and-discovery/search-queries.md).
