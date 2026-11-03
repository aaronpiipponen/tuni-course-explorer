# Search

A search query matches courses through the lexical and semantic methods a site serves, and the app merges their results into one ordered list per course.

## One query, four methods

[Unified search](/docs/reference/glossary.md#search-and-comparison) runs every method a site serves for one query and merges their results into one entry per course, so a course that several methods match appears once with the list of methods that matched it. The methods are Exact code, Substring, Fuzzy search, and Semantic, and a site that serves embedding features runs all four.

One request carries the query, the app language, a minimum score for each scored method, and whether inactive courses take part. A serving process takes the normalized rows for the requested activity scope from its dataset lookup projection, and each lexical method reads the part it needs of the projection's rows, per-language name lists and fuzzy-name token tables, so every method describes the same catalogue. The semantic method pairs its hits with the projection's represented index for the request's activity scope, which the same lookup service returns without a database read.

The semantic method needs a vector for the query, and it embeds the query through the same service that produced the stored vectors. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes that service and the vectors it stores.

The diagram follows one query through the methods and the merge into the ordered results.

![On a site that serves semantic matching, one query reaches the four search methods, and the embedding service supplies the query vector that the semantic method measures. The four methods' results are merged into one entry per course and ordered by the configured tier order.](/docs/diagrams/search-pipeline.svg)

## The four search methods

Each method has its own matching rule, its own cutoff where it has one, and its own order.

> [!IMPORTANT]
> The fuzzy cutoff, the token-coverage weight, and the semantic threshold decide how many courses the fuzzy and semantic methods return. The fuzzy score tie-break weight decides only their order. Every course a method matches at or above its cutoff is returned, and no method applies a result-count limit. Lowering the cutoff widens the result, and raising the token-coverage weight lets a course that matches the query token by token score higher.

### Exact code

The query is split into tokens on commas and whitespace, and each token is normalized and counted once. A course matches when its official code equals one of those tokens, so a comma-separated list of codes finds every course in the list. A token that names no course adds nothing to the result.

### Substring

A course matches when the query is contained in its official code or in the name the app shows for the app language of the request, ignoring case. The match is a containment test on official identity, so it needs no exact spelling of a whole name.

### Fuzzy search

Fuzzy search scores the displayed official name of each course against the query from 0 to 100 and keeps every course at or above the cutoff, so a name with a typo or a different word order can match as well. A course with no displayed official name takes no part in the scoring.

The score starts from the stronger of two 0 to 100 values. The first is the whole-name similarity, which is symmetric and rewards a shared prefix, so a long query cannot raise a short unrelated name. The second is the coverage of the query tokens, which compares each query token with the tokens of the name. The weaker of the two values then closes part of the gap to 100, so two names that both cover the query order by their whole-name similarity. The stronger value alone decides whether a course reaches the cutoff, so the tie-break never removes a match.

The whole-name similarity runs over the projection's name list for the request's app language and activity scope, and the token comparison runs against the token table the serving dataset retains, so a query tokenizes no title. A query that holds no token is scored by whole-name similarity alone, and a cutoff above the weight times 100 leaves only whole-name similarity able to qualify a course. [Search queries and merge](/docs/backend/search-and-discovery/search-queries.md#normalization-and-ordering) states the whole-name similarity, the token comparison and their formulas.

`FUZZY_SEARCH_MIN_SCORE` in `config/search.toml` sets the cutoff. `FUZZY_TOKEN_MATCH_WEIGHT` sets the weight of token coverage, greater than 0 and at most one. A lower weight favors whole-name similarity. `FUZZY_SCORE_TIE_BREAK_WEIGHT` sets the share of the gap to 100 that the weaker value closes, from 0 to 1. Token coverage reaches the weight times 100 at most, so with a weight below one a whole-name match that scores 100 outranks every token-only score.

### Semantic

The semantic method embeds the query and measures that vector against the stored vectors of the represented courses. A course's relevance is its best chunk. The read takes the completed chunks of the course's current representative version that were written under the configured embedding configuration, and a chunk of another version, a pending chunk, and a failed chunk contribute no score. A score is a cosine measured after the embedding hub is subtracted from the query vector and from the stored vector, so a score runs from -1 to 1 and an unrelated course scores close to zero. Every course whose best chunk reaches the threshold is returned. `SEMANTIC_SEARCH_MIN_SCORE` in `config/search.toml` sets the threshold. [Exact and approximate semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md) records the measurements of the exact read and the approximate alternatives.

## The packed exact read

On a site that serves the embedding features, the semantic method reads the dataset's [packed search relation](/docs/reference/glossary.md#serving-data) in one exact scan. Each represented course's best score is returned, the threshold is applied to it, and the results are ordered by canonical group and version. The artifact set reads the meta row and the neighbour presence once when it opens. A missing packed search meta row is refused at open only when the catalogue hub is nonempty, and an empty hub opens a zero retained group count. A missing hub file, a missing embedding directory, a malformed hub, and a dataset that holds embedded chunks with no stored neighbour row each fail at open with one `ValueError` naming `scripts/admin.py serving-artifacts`. A database without the packed scan extension fails the semantic read when the scan statement runs. [Search queries and merge](/docs/backend/search-and-discovery/search-queries.md#the-semantic-read-and-the-service) describes the packed relation, the scan call and its joins.

## Running one search

`config/search.toml` sets the fuzzy cutoff, the fuzzy token-coverage weight, the fuzzy score tie-break weight, and the semantic threshold that every request uses. A request may carry its own fuzzy cutoff from 0 to 100 or its own semantic threshold from -1 to 1, and that value replaces the configured one for that request, so one caller can read a narrower or a wider result than the configured default. The two fuzzy weights have no request override.

```bash
uv run python scripts/search.py "data structures" --display-language en --active-only
```

The command runs one unified search and prints one JSON report with the merged results, the effective fuzzy cutoff, the effective semantic threshold, the activity scope, the tier order, and whether semantic matching was available.

## When the query embedding request fails

The semantic method needs a query vector, and a search makes one query embedding request for it. `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` in `config/search.toml` is the timeout of that request in seconds and is greater than 0. `SEARCH_EMBEDDING_MAX_ATTEMPTS` is its attempt count including the first, at least 1. The timeout bounds the network phases of each attempt, so it is not a deadline for the whole search. The two keys are separate from the generation policy of the embedding stage, which `EMBEDDING_REQUEST_TIMEOUT_SECONDS` and `EMBEDDING_MAX_ATTEMPTS` set for its batch requests.

A transport failure, a 429 status, and a status from 500 to 599 are retried while attempts remain, up to the attempt count `SEARCH_EMBEDDING_MAX_ATTEMPTS` sets, with a wait that grows between attempts, and every other non-200 status ends the request at once. The query embedding request fails when no attempt succeeds. When it fails, the search returns the exact-code, substring, and fuzzy matches it found. The report then carries `semantic_available` false, no semantic match source, and no semantic score in any result, and it may carry no result at all. A request that reaches the service and returns no course above the threshold reports `semantic_available` true, because the method ran and found nothing. A malformed successful response, a database failure, and an invalid input are not request failures, and each one ends the search with a failure and no report.

## A site without semantic matching

The web read composes the semantic method only when `WEB_EMBEDDINGS_ENABLED` is true in the site's `config/web.toml`, and it passes that decision to the command as its `include_semantic` argument, whose default is `true`. A site with the switch off serves the exact-code, substring, and fuzzy methods alone.

On such a site the command loads no embedding settings, builds no embedding provider, constructs no semantic repository, and reads no stored vector. Its report carries `semantic_available` false and a tier order that omits `semantic`, and every result carries no semantic score. An exact-code query on a site without embedding features therefore returns the same lexical matches it returns on a site with them.

That false availability is not the provider outage of the section above, and the Search tab distinguishes the two: it shows the unavailable notice only on a site that serves semantic matching, and it draws the returned lexical matches, the empty state and the ordinary request errors in both cases.

`scripts/search.py` takes its semantic availability from the artifact set it opens. It runs the semantic method when that set holds the embedding reads and the three lexical methods alone on a site with the embedding features off, so a bare command uses every method the set allows. It builds one lookup projection for that command lifetime, and when the build holds them it passes the catalogue hub and the packed group count explicitly. The command owns no projection cache and reads no artifact identity per request. The administrative and web callers use the same artifact opener.

## Scores and match sources

Each merged result carries the methods that matched it and the score of each scored method that matched. A fuzzy score is a percentage from 0 to 100 and a semantic score is a cosine from -1 to 1, and the two live in separate fields.

## Tier order

Merged results are ordered by [tier order](/docs/reference/glossary.md#search-and-comparison). `SEARCH_TIER_PRIORITY` in `config/search.toml` lists the four methods in their order of precedence, and it must name each of them exactly once. The tier order a report returns omits `semantic` when the search ran without the semantic method, so an effective order names only the methods that ran.

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

Two reads serve the other tabs: the minimal official catalogue and the id-or-code resolver.

### The minimal official catalogue

The catalogue read returns every represented course's canonical identity, code, FI and EN names, credits and activity flag, and every canonical module's eligible version candidates for the current academic year with their exact version identity, kind, code, FI and EN names, validity bounds and curriculum-period memberships. It carries no official URL, course representative source identity, teaching text, description or prerequisite, and it applies no activity filter to the module candidates. A module with no eligible candidate is absent.

The browser's narrowing boxes filter that one list locally. The matching is the substring rule above: a course matches when its displayed official name or code contains the normalized query, and a module candidate matches when its displayed name or code does. Two orders apply to module rows. The matching candidates of one group are compared by displayed name and code and then by exact version identity, so that order picks the candidate whose code and name the row displays. Result groups are compared with degree programmes before other modules, then by the row's displayed name and code, then by canonical group identity. Neither order selects a version for the structure. A canonical group appears as one row when any of its eligible candidates matches, the row shows the displayed candidate's code and name, and it carries the group's full eligible candidate list. The version picker of the group offers a candidate the query does not match.

### The id-or-code resolver

The Compare, Prerequisites, Discover, and Structure of studies tabs hold courses by their canonical identity and resolve those identities here. An input is matched first as an exact canonical identity and then as an exact official code, and each input resolves to exactly one represented course. The result keeps the order of the inputs, and an input that appears twice resolves twice. A blank input, an unknown input, and an official code that matches more than one canonical course each fail instead of resolving to a guess.

## Configuration keys

| Key | Meaning |
|---|---|
| `SEARCH_TIER_PRIORITY` | The order of the four search methods that sorts merged results. The example sets `exact_code`, `substring`, `fuzzy_name`, and `semantic` in that order. |
| `SEMANTIC_SEARCH_MIN_SCORE` | The smallest semantic score that returns a course, from -1 to 1. The example sets 0.30. |
| `FUZZY_SEARCH_MIN_SCORE` | The smallest name-similarity score that returns a course, from 0 to 100. The example sets 80. |
| `FUZZY_TOKEN_MATCH_WEIGHT` | The weight of query-token coverage in the fuzzy score, greater than 0 and at most 1. The example sets 0.95. |
| `FUZZY_SCORE_TIE_BREAK_WEIGHT` | The share of the gap to 100 that the weaker whole-name or token-coverage value closes, from 0 to 1. It orders fuzzy matches without changing which ones qualify. The example sets 0.1. |
| `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` | The timeout of the one query embedding request a search makes, in seconds and greater than 0. The example sets 5. |
| `SEARCH_EMBEDDING_MAX_ATTEMPTS` | The attempt count of that query embedding request, the first included, at least 1. The example sets 1. |
| `WEB_EMBEDDINGS_ENABLED` | Whether this site composes semantic matching, its provider and its stored-vector read, in `config/web.toml`. The example sets `true`. |

The services behind the four methods, the read that the semantic method measures against, and the merge are described in [Search queries and merge](/docs/backend/search-and-discovery/search-queries.md).
