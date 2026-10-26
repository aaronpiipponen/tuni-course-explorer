# Lexical matching equivalence and collation

This report tests whether SQL lexical matching can reproduce the application's Python matching, and why result order depends on collation.

**Evidence status:** Corrected. **Run date:** 21 October 2026.

The [Experiments section](/docs/experiments/README.md) gives the catalogue and the hardware this line used.

## The question

The application matches course codes and names in Python. An [exact code match](/docs/reference/glossary.md#search-and-comparison) compares normalized query tokens with normalized official codes. A substring match looks for the normalized query inside a code or displayed name. A fuzzy match scores a displayed name against the query. A SQL version could move that work into PostgreSQL, but it is acceptable only if it returns the same courses and lists them in the same order.

Those are two separate properties. Set equality asks whether the same canonical courses appear. Order equality asks whether every position in the list is the same. A set match with a different order changes what a reader sees first, so this line measured both.

The line also asks what the SQL representation costs. A normalized projection has to be built and stored, and a query over it has a duration. The durations here cover the SQL statement only, not the Python normalization that prepares the rows.

No SQL matcher, collation or index from this line is a selected product setting. The application performs lexical matching in Python over its normalized lookup projection. The [four search methods](/docs/backend/search-and-discovery/search.md#the-four-search-methods) describe how the application matches codes and names. The SQL forms are measured alternatives.

## Fixed inputs and setup

The catalogue snapshot holds 11,086 represented courses, of which 4,543 are active, and 58,962 teaching-text chunks. This line reads only course identities, official codes and official display names. It uses no embedding, translation or inference model.

Four query strings were fixed before any comparison. They exercise one code, two codes in one query, a fullwidth Unicode literal and a misspelled literal.

| Case | Query | Source |
|---|---|---|
| case-1 | `XYKSJV20-M001` | First active canonical course code |
| case-2 | `XYKSJV20-M001 MARIH.319` | First two distinct active canonical course codes |
| case-3 | `ＯＨＪＥＬＭＯＩＮＴＩ` | Fixed fullwidth literal |
| case-4 | `tietokanta suunnittlu` | Fixed fuzzy literal |

Every query ran under both display languages, Finnish and English, and both activity scopes, all courses and active courses only. One cell is one query in one language and one scope. The first measurement compared 16 cells for each SQL form. The ordering proof compared 16 cells for each of two matchers.

| Item | Value |
|---|---|
| Represented courses | 11,086 |
| Active courses | 4,543 |
| Display languages | Finnish, English |
| Activity scopes | All, active only |
| PostgreSQL | 18.6 on aarch64 |
| Python | 3.14.3 |
| Trigram extension | `pg_trgm` 1.6 |
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Available memory at proof start | 10.22 GB |
| Fixture database collation | `en_US.utf8`, locale provider `c` |
| Fixture memory and swap | 805.3 MB, no swap |
| Client address space | 1.074 GB |
| Parallel query workers | 0 |
| Models | None |

The fixture is a disposable PostgreSQL container with no network and no published port. The catalogue snapshot was read through a read-only connection with a 30 s statement timeout. The network isolation bounds the fixture, and the read-only connection and the statement timeout bound the snapshot read.

### Normalization and the projection

The product normalization is one function:

```text
normalized_text(value) = NFKC(value).casefold().strip()
```

NFKC turns compatibility forms into their composed equivalents. Casefolding maps characters to a case-insensitive form. Outer trimming removes leading and trailing whitespace. The normalization does not strip punctuation inside the string, collapse runs of spaces or apply a locale.

The normalized lookup projection has one row per represented course. It holds the canonical group identity, the activity flag, the normalized code and one normalized displayed name for each language. A requested official name is used first. When that language has no name, the other official name is used as a fallback. A name in the other language is never matched when the requested name exists. Across the catalogue, 793 Finnish rows and 373 English rows used the fallback, and no row lacked a display name in both languages.

### The five order keys

Python orders exact-code and substring matches by a five-part key. The [normalization and ordering](/docs/backend/search-and-discovery/search-queries.md#normalization-and-ordering) page defines it. The first part puts active courses first, the second puts rows with a displayed name before rows without one, and the remaining three are the normalized displayed name, the normalized code and the canonical group identity. The fuzzy matcher sorts by a six-part key: the activity flag, the descending score, and then the four parts from the display-name flag onward.

```text
(not is_active, display_name is None, normalized display name, normalized code, group_id)
```

The SQL comparison used the same five keys. The first two are booleans, and PostgreSQL orders false before true. The three text keys carry ordering under the selected collation. The block below is the later ordering-proof form, which specifies C collation. The first comparison left those text keys under the database's default collation.

```sql
ORDER BY (NOT is_active),
         (NOT has_display),
         ndisplay COLLATE "C",
         ncode COLLATE "C",
         group_id COLLATE "C"
```

Python compares strings by Unicode code point. A database collation can order the same strings by language rules, which may weight case, accents and punctuation differently. C collation compares UTF-8 bytes, and for valid UTF-8 that byte order equals code-point order. This distinction is the subject of the ordering correction below.

## The matchers compared

Two SQL forms ran over the pre-normalized projection. Two diagnostic forms ran to show what happens when SQL supplies its own normalization or similarity.

| Form | Python baseline | Match rule | Normalization in SQL |
|---|---|---|---|
| `projection_exact_code` | Exact code | Equality between a normalized query token and the normalized code, any token | None, the projection is pre-normalized |
| `projection_substring` | Substring | Containment of the full normalized query in the normalized code or displayed name | None, the projection is pre-normalized |
| `sql_lower_substring` | Substring | `lower()` on raw code and raw names, then containment | `lower()` only |
| `trigram_name` | Fuzzy name | `pg_trgm` similarity at or above 0.8 on the displayed name | Query normalized in Python, title pre-normalized |

The exact matcher splits the query on commas and whitespace, normalizes each token, drops empty tokens and compares the resulting set with the codes. A match on any token is enough. The SQL form passes the sorted token set to `ncode = ANY(...)`, which has the same OR semantics.

The substring matcher uses the whole normalized query, not its tokens. It checks the normalized code and the displayed name. The SQL form builds a `LIKE` pattern and escapes `%`, `_` and the backslash itself, so those characters match literally as they do in Python.

The fuzzy matcher scores the whole normalized displayed name with RapidFuzz `WRatio`. It then adds query-token coverage. A candidate whose weighted ratio is at or below the token weight times 100, 95 in the example, can be raised by the mean of the best `fuzz.ratio` between each query token and a title token, multiplied by the configured token weight. The cutoff is 80 on a 0 to 100 scale, set by `FUZZY_SEARCH_MIN_SCORE`, and the token weight is `FUZZY_TOKEN_MATCH_WEIGHT`, 0.95. The fuzzy matcher reads display names only, not codes.

The trigram form uses the `pg_trgm` `similarity` function, which compares sets of three-character sequences and returns a fraction from 0 to 1. The SQL cutoff is 0.8, the configured fuzzy cutoff divided by 100. That fraction and the RapidFuzz score are different scales, and the trigram form has no token-coverage step. It also scores the displayed name only.

## Results under the default collation

The first measurement compared each SQL form with its Python baseline over 16 cells. The fixture database used its default `en_US.utf8` collation, and the SQL order clauses had no explicit collation.

| Form | Python baseline | Same set | Same order | Mismatched inputs | Median SQL time per input, first recorded pass |
|---|---|---|---|---|---|
| Projection exact code | Exact code | All 16 | All 16 | 0 | 1.6 ms |
| Projection substring | Substring | All 16 | 15 of 16 | 0 | 2.3 ms |
| Raw `lower()` substring | Substring | 14 of 16 | Not all | 2 | 9.0 ms |
| Trigram name | Fuzzy name | 13 of 16 | Not all | 3 | 40.7 ms |

The exact form returned the same set and the same order in every cell. The projection substring form returned the same set in every cell but a different order in one cell, the all-courses Finnish case-3 cell with 61 results. That cell is the measured collation counterexample: the set was equal, but the position-by-position list was not. The exact form's order equality is an observation on these cells. The order comes from the five keys, not from the order of the query tokens.

### Set equality and order equality

Set equality compares the canonical group identities without regard to position. Order equality compares the complete lists position by position. The first measurement reported both for every cell. The ordering proof below compares complete ordered identity lists and the five key values for each identity.

A set match is not enough for this matcher. The application shows a list, and the five keys decide which active course, which displayed name and which code come first. A list with the same courses in a different order is a different result.

### Where raw `lower()` fails

The raw `lower()` form had two set mismatches, both on the fullwidth query.

| Scope | Language | Case | Python results | SQL results | Missing | Added |
|---|---|---|---|---|---|---|
| All | Finnish | case-3 | 61 | 0 | 61 | 0 |
| Active | Finnish | case-3 | 5 | 0 | 5 | 0 |

The query `ＯＨＪＥＬＭＯＩＮＴＩ` normalizes to `ohjelmointi` under NFKC. The projection stores that normalized form, and the Python matcher finds names and codes containing it. `lower()` does not apply NFKC, so the fullwidth characters remain fullwidth and no raw value contains them. SQL `lower()` also does not equal Unicode casefolding. It maps case under the database locale, while casefolding applies the wider Unicode mapping.

The two mismatching cells are the all-courses and active-only Finnish cells. The English cells return nothing.

### Where trigram similarity fails

The trigram form had three set mismatches.

| Scope | Language | Case | Python results | SQL results | Missing | Added |
|---|---|---|---|---|---|---|
| Active | Finnish | case-3 | 7 | 0 | 7 | 0 |
| All | Finnish | case-3 | 75 | 7 | 68 | 0 |
| All | Finnish | case-4 | 7 | 0 | 7 | 0 |

For the fullwidth query, the Python fuzzy matcher returns 75 Finnish names in the all-courses scope and seven in the active scope. Trigram similarity returns seven rows in the all-courses scope and none in the active scope. All seven returned rows are also in the Python result, so the trigram form is a subset here, not an addition.

For `tietokanta suunnittlu`, the Python matcher returns seven Finnish names in the all-courses scope, with scores from 81.4 to 87.0. The trigram form returns none at its 0.8 cutoff. The two methods measure different things. RapidFuzz compares the whole strings with an edit-aware weighted ratio and can raise a score through token coverage. Trigram similarity counts shared three-character sequences and compares that fraction with a fixed cutoff.

## Ordered parity under explicit C collation

The ordering proof isolated the order rule. It copied only the normalized projection columns into a fresh fixture. The fixture database kept its default `en_US.utf8` collation with locale provider `c`, so this is not a C-collated database. The three text keys in each `ORDER BY` carried an explicit `COLLATE "C"` expression. The first two keys stayed boolean.

The proof ran one warmup pass and three recorded passes. Each pass issued 16 exact-code queries and 16 substring queries, 32 in total, covering four cases, two languages and two scopes. All four passes produced identical compared output.

For every cell the proof saved the full ordered Python identity list and the full ordered SQL identity list. The saved Python result holds ordered identities but no key values. The proof therefore read the five key values from the same projection for the Python identities, read them from the SQL rows, and compared the two sequences. It also checked that each sequence was already in Python code-point order. A Python identity absent from the projection would have stopped the run as an input mismatch.

The full ordered identity lists match in all 16 exact-code cells and all 16 substring cells. The key sequences match in all 32 cells and are sorted in Python code-point order. The 61-result substring cell that differed under `en_US.utf8` matches in full under the explicit C collation. Every empty cell is empty on both sides, and no cell has a first difference.

### Exact code, 16 cells

| Scope | Language | Case | Results | Median SQL time (ms) | Full order equal | Key sequences equal |
|---|---|---|---:|---:|---|---|
| All | Finnish | case-1 | 1 | 1.278 | Yes | Yes |
| All | Finnish | case-2 | 2 | 1.465 | Yes | Yes |
| All | Finnish | case-3 | 0 | 1.357 | Yes | Yes |
| All | Finnish | case-4 | 0 | 1.427 | Yes | Yes |
| All | English | case-1 | 1 | 1.293 | Yes | Yes |
| All | English | case-2 | 2 | 1.497 | Yes | Yes |
| All | English | case-3 | 0 | 1.309 | Yes | Yes |
| All | English | case-4 | 0 | 1.445 | Yes | Yes |
| Active | Finnish | case-1 | 1 | 1.155 | Yes | Yes |
| Active | Finnish | case-2 | 2 | 1.168 | Yes | Yes |
| Active | Finnish | case-3 | 0 | 1.109 | Yes | Yes |
| Active | Finnish | case-4 | 0 | 1.217 | Yes | Yes |
| Active | English | case-1 | 1 | 1.157 | Yes | Yes |
| Active | English | case-2 | 2 | 1.184 | Yes | Yes |
| Active | English | case-3 | 0 | 1.128 | Yes | Yes |
| Active | English | case-4 | 0 | 1.213 | Yes | Yes |

### Substring, 16 cells

| Scope | Language | Case | Results | Median SQL time (ms) | Full order equal | Key sequences equal |
|---|---|---|---:|---:|---|---|
| All | Finnish | case-1 | 1 | 2.281 | Yes | Yes |
| All | Finnish | case-2 | 0 | 2.222 | Yes | Yes |
| All | Finnish | case-3 | 61 | 2.860 | Yes | Yes |
| All | Finnish | case-4 | 0 | 2.995 | Yes | Yes |
| All | English | case-1 | 1 | 2.349 | Yes | Yes |
| All | English | case-2 | 0 | 2.305 | Yes | Yes |
| All | English | case-3 | 0 | 2.762 | Yes | Yes |
| All | English | case-4 | 0 | 2.898 | Yes | Yes |
| Active | Finnish | case-1 | 1 | 1.646 | Yes | Yes |
| Active | Finnish | case-2 | 0 | 1.602 | Yes | Yes |
| Active | Finnish | case-3 | 5 | 1.821 | Yes | Yes |
| Active | Finnish | case-4 | 0 | 1.935 | Yes | Yes |
| Active | English | case-1 | 1 | 1.665 | Yes | Yes |
| Active | English | case-2 | 0 | 1.679 | Yes | Yes |
| Active | English | case-3 | 0 | 1.866 | Yes | Yes |
| Active | English | case-4 | 0 | 1.951 | Yes | Yes |

The per-cell figures run from 1.109 ms to 2.995 ms and are the medians of the three recorded passes. The three whole-pass medians were 55.82 ms, 56.07 ms and 56.16 ms, and the warmup pass took 59.94 ms. A pass issues 32 statements, so the pass median is not a per-query latency. The complete measured invocation, including fixture cleanup and the post-cleanup checks, took 5.093 s.

Exact code case-2 returns its two courses in one fixed order that the query codes do not set. The first query code, `XYKSJV20-M001`, belongs to the second result. The five keys decide the order, and the proof confirms that the key values already lie in Python code-point order.

## Representation and cost

The projection is not free. The first comparison table held normalized code, normalized display names, the raw code and the raw Finnish and English names, so that the raw `lower()` form could read the raw columns. The ordering proof held only the normalized code, one normalized display name per language, the activity flag and the display-present flags. The narrower table is 32 percent smaller.

| Representation | Rows | Size | Contents |
|---|---:|---:|---|
| SQL projection, first comparison | 11,086 | 3.33 MB | Normalized keys, raw code and names, and flags |
| SQL projection, ordering proof | 11,086 | 2.26 MB | Normalized code, one display name per language and flags |

The Python leg built its normalized rows in memory for every matcher call and did not record a separate projection size. Its process peak was 168.6 MB. The SQL comparison client peaked at 168.7 MB and the ordering proof client at 162.4 MB. The SQL client peaks include the fixture copy. All three are process-wide peaks, so they are not the memory of one query or one process.

| Measurement | Value |
|---|---|
| Python lexical leg, elapsed | 4.885 s |
| Python lexical leg, process peak | 168.6 MB |
| SQL lexical leg, process peak | 168.7 MB |
| SQL ordering proof, process peak | 162.4 MB |
| SQL lexical fixture, cgroup current | 77.08 MB |
| SQL lexical fixture, cgroup peak | 86.41 MB |

The Python leg's 4.885 s is not a per-query latency. It covers three recorded passes, each with two scopes, two languages and four cases, and each cell ran three matchers. It also rebuilt the normalized rows on each matcher call. The SQL medians cover one statement per form over a projection that was normalized and copied before timing.

The chart shows the first-pass median SQL time for the four forms.

![First-pass median SQL time for the four lexical forms. Exact code is the cheapest and trigram matching the slowest.](/docs/charts/lexical-matching-form-medians.svg)

The four form medians from the first recorded pass span a factor of about 25. Exact code equality is the cheapest at 1.6 ms, projection containment is 2.3 ms, raw `lower()` containment is 9.0 ms and trigram similarity is 40.7 ms. Each value is the median over that pass's 16 cells, not over all three passes. The trigram form scans the projection and computes a similarity for each row, and no trigram index was built. The first measurement had no warmup pass, so these four medians are not directly comparable with the warmed per-cell medians in the ordering proof.

The projection is prepared by the Python normalization rule before any SQL timing starts. The SQL numbers therefore contain no NFKC or casefold normalization cost. The 3.33 MB and 2.26 MB sizes are the copied relations, not the size of the catalogue snapshot they were copied from.

## Corrections and the result that stands

The first measurement reported that projection containment matched the Python substring set but not its order under the fixture's default `en_US.utf8` collation. The differing cell was the all-courses Finnish case-3 cell with 61 results. Exact code matching matched set and order in all its cells.

The ordering proof corrected that result for order. It kept the same normalization and the same five keys, added explicit C collation to the three text keys, and compared full ordered identities and key values. All 32 sampled cells matched, including the 61-result cell.

The result that stands is order parity for exact code and substring matching on the four fixed queries, two display languages and two activity scopes, under explicit C collation on the pre-normalized projection. Under the default `en_US.utf8` collation, the substring order differed in one of the 16 cells. The proof does not apply to a C-collated database.

The correction does not extend to raw `lower()` or trigram matching. Those forms produced different sets under the default collation, and the ordering proof reran neither. Their mismatches stand as observations on these inputs. The proof also does not measure NFKC or casefold normalization cost or explain every possible Unicode ordering.

An earlier SQL attempt stopped before it produced a comparison because PostgreSQL 18 does not expose the `lc_collate` setting. The comparison read the database collation from `pg_database.datcollate` instead. No measured result comes from the stopped attempt.

The first measurement ran no warmup pass for either lexical leg. The ordering proof ran one warmup pass and three recorded passes, and all four produced identical compared output.

## What the results establish

Observed: over the pre-normalized projection, SQL equality reproduced the Python exact-code set and order in all 16 cells of the first comparison and in all 16 cells of the ordering proof. SQL containment reproduced the Python substring set in all 16 cells of each comparison, the order in 15 cells under the default collation, and all 16 under explicit C collation.

Observed: raw `lower()` did not reproduce the Python substring results on the fullwidth query. Trigram similarity did not reproduce the Python fuzzy results on the fullwidth query or the misspelled query. The failures are set differences, not only order differences.

Interpreted: NFKC and casefolding have to happen before the comparison. A projection built with the product normalization carries the needed equivalence, while `lower()` on raw columns does not. A trigram fraction is not a substitute for the weighted whole-string ratio plus token coverage.

Interpreted: collation is a property of the ordering expression. The same projection and the same keys produced Python order when the text keys carried explicit C collation, even though the database default stayed `en_US.utf8`.

Not established: that every Unicode input orders identically. The four queries are a purposive sample chosen to exercise exact codes, multi-token OR, a compatibility form and a misspelling. They are not a random sample of names, codes or user input.

Not established: normalization cost, index behavior, concurrency, HTTP latency or whole-search latency. The timings cover single SQL statements on a fixture with no competing load and no trigram index.

## Limitations

- The comparison covers four fixed query strings, two display languages and two activity scopes. It does not cover every possible Unicode or lexical input.
- The projection is built by the Python normalization rule before the SQL read. The comparison isolates matching and ordering, not NFKC or casefold normalization cost.
- The ordering proof uses explicit C collation on three text keys. The fixture database keeps its default `en_US.utf8` collation, so the result does not describe a C-collated database.
- C collation orders UTF-8 bytes, which equal code-point order for valid UTF-8 text. The proof compares sampled strings, not the whole Unicode range.
- The saved Python result stores ordered identities, not key values. The key values on the Python side are read from the same projection for those identities.
- The first lexical measurement ran no warmup and three recorded passes. The ordering proof ran one warmup and three recorded passes.
- Database and CPU cache warmth is uncontrolled.
- The process peak memory figures are process-wide and include the fixture copy. They are not query working memory or per-process memory.
- No SQL form was selected for the product, and no result here supports a claim about serving latency at another corpus size or under concurrent load.

## Setup details

| Item | Value |
|---|---|
| Catalogue snapshot | 11,086 represented courses, 4,543 active |
| Display fallback rows, Finnish and English | 793 and 373 |
| Rows with no display name in either language | 0 |
| Query strings | Four, fixed before comparison |
| Display languages | Finnish, English |
| Activity scopes | All, active only |
| Python | 3.14.3 |
| PostgreSQL | 18.6, Debian 18.6-1.pgdg13+2 on aarch64 |
| Trigram extension | `pg_trgm` 1.6 |
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Available memory at proof start | 10.22 GB |
| Fixture database collation | `en_US.utf8`, locale provider `c` |
| Fixture memory and swap | 805.3 MB, no swap |
| Client address space | 1.074 GB |
| Parallel query workers | 0 |
| Fixture setup, first lexical leg | 0.24 s |
| Fixture setup, ordering proof | 0.157 s |
| First lexical passes | No warmup, three recorded |
| Ordering proof passes | One warmup, three recorded |
| Statement timeout | 30 s per statement |
| Proof pass timer | 60 s per pass |
| Models | None |

The catalogue snapshot was read once per leg through a read-only connection. The fixture copy, setup and cleanup ran inside the owned container. The proof created no vector, trigram or semantic object.

## Follow-up questions

These are untested.

- Whether an indexed trigram query can approach the Python fuzzy result at this corpus size, and what index size and build time it would add.
- Whether normalization can move to write time without changing the order of any input, and what that would cost per course.
- Whether a much larger set of Unicode names and codes preserves order parity under explicit C collation.
