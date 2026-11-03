# Search and translation experiments

Five experiments ask whether machine translation preserves retrievability and whether cheaper semantic and lexical reads preserve the product's search results.

## The questions the line asked

The folder covers two branches of one pipeline. The translation branch asks whether a machine [translation](/docs/reference/glossary.md#courses-and-the-catalogue) can stand in for official text without breaking retrieval. The embedding stage reads the [effective text](/docs/backend/text-and-vectors/teaching-text.md#official-text-translation-and-effective-text), so a translation that moves too far in embedding space can make search miss the course.

The search branch asks what a change to a search read costs and whether it changes the result. One report measures the exact semantic read against cheaper and approximate alternatives. Another asks which stored representation makes the exact read cheapest and what the cheapest representation costs to serve. A third asks whether SQL can reproduce the Python lexical set and order, and why order depends on collation. A fourth asks whether one normalized projection and a native fuzzy-name scorer can replace per-query normalization and Python matching.

The branches do not share a metric. Translation scores a proxy for retrieval utility. The search reports score result preservation against the product's own output on fixed inputs, with the cost of the read. The folder combines none of the values into one score.

The [Experiments section](/docs/experiments/README.md) states the catalogue snapshot and the hardware. Each report states its cohort, settings, timing boundary and evidence label.

## The reports

| Report | Question | Result that stands | Run dates |
|---|---|---|---|
| [Machine translation as retrieval-preserving transformation](/docs/experiments/search-and-translation/translation-and-retrieval.md) | Does a generated translation retrieve its official counterpart within its field and target language? | 59 of 60 top-1 and a mean reciprocal rank of 0.9875, with every cell at or above the 0.80 floor. A within-cell retrieval proxy that scores retrieval utility. | 13 September 2026 |
| [Exact and approximate semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md) | Can the exact semantic read be cheaper without changing its result, what does a bounded approximate index lose, and what does the read cost inside the served request? | The pushdown was exact and slower, the centred SQL read exact and 0.08 to 0.13 s faster per query, the bounded NumPy read exact and far slower per pass, and no approximate setting exact on all four vectors. No compared vector read was selected. The served summary-read change was kept, and the served median fell from 1,783.9 to 898.6 ms, with 858.6 ms in the final run. | 21 and 28 October 2026 |
| [Packed exact semantic search](/docs/experiments/search-and-translation/packed-exact-semantic-search.md) | Which stored representation makes the exact semantic read cheapest, and what does the cheapest cost in memory and serving work? | The packed relation is the product's semantic read, with 7.6 times fewer core-seconds than the product SQL and every measured result equal. The packed file was cheaper in core-seconds and was not adopted. | 28 to 31 October 2026 |
| [Lexical matching equivalence and collation](/docs/experiments/search-and-translation/lexical-matching-and-collation.md) | Can SQL reproduce the Python lexical set and order, and what decides order? | Order parity in all 32 sampled cells when the three text keys carry explicit C collation, with set mismatches for raw `lower()` and trigram matching. No SQL form was selected. | 21 October 2026 |
| [Lexical lookup projection and native fuzzy matching](/docs/experiments/search-and-translation/lexical-lookup-projection-and-native-fuzzy.md) | Can one normalized projection and a native fuzzy-name scorer replace per-query normalization and Python matching without changing any result? | All 16 cells matched for each of the three matchers, all 64 score comparisons found zero differences, and the fuzzy stage fell to 0.0264 to 0.0419 core-s. The projection and the native token coverage were applied. | 21, 28 and 29 October 2026 |

## The shared method

Every search comparison fixed its inputs before it measured. The semantic line used four stored chunk vectors. The lexical line used four fixed query strings, each run in Finnish and English and in the all-courses and active-only scopes, which gives 16 cells per matcher. The fuzzy score parity extended those four strings to eight queries.

Each read or matcher was compared with the product's own output on the same snapshot. Set equality asks whether the same courses appear, and order equality asks whether every position matches. The score difference and the threshold counts cover the values behind the list, and each report states which of them it compared. Cost appears as core-seconds, wall time or peak memory, and each report states the boundary of its timer, such as one SQL statement, one database read or one HTTP request.

The translation line measures a within-cell retrieval proxy instead, which [Machine translation as retrieval-preserving transformation](/docs/experiments/search-and-translation/translation-and-retrieval.md) defines.

## What was selected

| Applied to the product | Measured and not applied |
|---|---|
| The packed exact relation as the product's semantic read | The representative pushdown, the centred SQL read, the bounded NumPy read and every approximate HNSW setting |
| The lookup projection, built once by the supervisor and inherited by its workers | The SQL lexical forms, explicit C collation on the order keys and the trigram matcher |
| The native token coverage in the fuzzy-name stage | The native whole-title `WRatio` port |
| TranslateGemma 12B at Q5_K_M for the translation stage | The packed file |

Exact code and substring matching compare the lookup projection's rows in Python. The fuzzy method scores whole-name Jaro-Winkler similarity with RapidFuzz's compiled code from Python on the projection's name list, then raises the scores through the native lookup library's token coverage, so a query tokenizes no title.

The applied translation model cleared its acceptance floors and ran the full pass over every missing representative field, which filled every translatable gap. The [translation report](/docs/experiments/search-and-translation/translation-and-retrieval.md) also carries the embedding runtime measurements and the provider feasibility figures.

## Category-wide limits

- No measurement is an end-to-end search benchmark. None joins the query embedding request, the database read and browser rendering into one budget, and no served measurement reports the cost of each stage of its request.
- Every cohort is small and fixed. The folder has 60 translation cases, four stored query vectors, four query strings over 16 cells and eight fuzzy parity queries, and none is a random sample of the catalogue's input, field, length or language mix. Only Finnish and English have a measured result.
- Preservation is not quality. No measurement rates the relevance of a semantic result set, no human rating covers translation fluency, terminology or adequacy, and the exactness on four stored vectors is empirical.

## Untested questions

Each question below is untested.

- Whether these translations preserve retrieval in the product's chunked, hub-centred search over the full catalogue.
- Whether a served search that joins the query embedding request, the read and browser rendering under concurrent load meets a stated budget.
- Whether the exactness and parity results hold on a wider sample of queries, Unicode names and codes, and languages, or on another catalogue snapshot.
- Whether human judgement agrees with the two proxies, a translation rating against the retrieval proxy and a relevance rating of a semantic result set.
- Whether the packed relation's update path for another embedding generation costs less than a full rebuild at this catalogue size.
- Whether the projection's total size with its per-language token tables stays near the 167.8 MB the run measured.
