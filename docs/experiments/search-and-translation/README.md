# Search and translation experiments

Three experiments ask whether translation preserves retrievability and whether cheaper search reads and SQL lexical matching preserve the application's results.

## The questions the category asked

The category holds two related lines of questioning. The translation experiment asked whether a machine [translation](/docs/reference/glossary.md#courses-and-the-catalogue) can stand in for official text without breaking retrieval. The semantic experiment asked whether an exact semantic read can be made cheaper without changing its set and order, and what a bounded approximate index loses. The lexical experiment asked whether SQL matching can reproduce the Python set and order, and why order depends on collation.

The lines do not share a metric. Translation scores retrieval utility through a proxy. The other two score result preservation on fixed inputs, one for a vector read and one for lexical matching. A value from one line does not apply to another.

The reports describe a catalogue of 11,086 courses, 4,543 active, and 58,962 teaching-text chunks. The [Experiments overview](/docs/experiments/README.md) states that catalogue and the hardware the reports used. The cohorts are separate. Translation has 60 generated texts, semantic retrieval four stored vectors, and lexical matching four query strings over 16 cells. The translation run took place on 13 September 2026. Both search runs took place on 21 October 2026.

| Report | Question | Result that stands |
|---|---|---|
| [Translation and retrieval](/docs/experiments/search-and-translation/translation-and-retrieval.md) | Does a translation retrieve its official counterpart within its field and target language? | 59 of 60 top-1 and a mean reciprocal rank of 0.9875 |
| [Semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md) | Can exact semantic SQL be cheaper without changing the result, and what does an approximate index lose? | Pushdown exact but slower, centred SQL faster on the sample, NumPy exact but expensive, and no HNSW setting exact on all four vectors |
| [Lexical matching and collation](/docs/experiments/search-and-translation/lexical-matching-and-collation.md) | Can SQL reproduce the Python set and order, and what decides order? | Order parity in 32 sampled cells under explicit C collation, with lower() and trigram set mismatches |

## Translation utility

The translation experiment crossed three fields with two target languages. Name, content and learning outcomes each had a Finnish-target cell and an English-target cell. The six cells held 10 cases each, and a Finnish-target cell drew from English official text while an English-target cell drew from Finnish official text. A case held official text in the source language and its official counterpart in the target language. The generated translation was the query, and the paired official text was the only correct answer among the 10 official texts of that cell.

The model was TranslateGemma 12B, instruction-tuned, in a Q5_K_M quantization, and BGE-M3 embedded the generated text and the targets. Five of the six cells ranked the paired target first on all 10 cases. The Finnish name cell ranked it first on nine and produced a mean reciprocal rank of 0.925. Across all cells the result was 59 of 60 top-1, a rate of 0.9833, and a mean reciprocal rank of 0.9875. The run cleared the floors of 0.90 overall, 0.80 in every cell and a projected duration below 604,800 seconds.

That number is a within-cell retrieval proxy, not a search-quality score. Each cell held 10 official targets, and the scorer used raw cosine over whole fields without subtracting the [embedding hub](/docs/reference/glossary.md#capture-and-data-preparation). The product searches 11,086 courses and 58,962 [chunks](/docs/reference/glossary.md#capture-and-data-preparation), ranks 1,200-character chunks with a 120-character overlap, and subtracts the embedding hub. A translation that wins among 10 official texts can rank differently in the product's full search. The proxy also cannot read the translation, so it establishes no fluency, adequacy, terminology or reader preference.

With 10 cases, one case moves a cell rate by 0.10, so the cell values are coarse. Observed: the one miss and the lowest mean paired cosine, 0.6940, fell in the same cell. The experiment does not establish a cause.

The retrieval values come from a corrected BGE-M3 launch. The earlier launch left the batch sizes unset, so it could not embed a text longer than 512 tokens whole. The corrected launch passed the configured 2,048-token value to the context and both batch sizes and embedded every text. Its peak resident memory was 2,044.0 MB and its warm query p95 was 0.074 seconds. A feasibility measurement before the correction recorded 1,117.51 MB and 0.0535 seconds. The two are separate measurements with a corrected launch and a different probe size, so the difference is not evidence that the model became slower. The corrected run is the source of the 59 of 60 top-1 and the 0.9875 mean reciprocal rank, and those values stand.

The duration for the full workload was a projection, not an observed run. The 60 cases generated in 156.008147444 seconds from 29,633 source characters. At the run, 9,916 representative cells were pending with 5,171,027 source characters. Scaling by characters gave 27,223.8 seconds, the larger of the item and character estimates, below the 604,800-second ceiling. The projection excludes model load, the health check, embedding and controller work, and it assumes the sample's rates and retry incidence hold. The full pass that followed filled every translatable gap, and its record gives no end-to-end duration, so the projection was never checked against a measured full run.

Interpreted: the result supports TranslateGemma 12B for the translation stage within the proxy's limits. It does not show that the translations are good by human standards or that 12B is the best available model.

## Exact and approximate semantic reads

Four stored descriptive chunk vectors were the queries. One came from learning outcomes and three from content, all English at chunk index 0, each from a different canonical course. The reference was the product exact semantic read at a 0.3 threshold, which returned 240, 168, 479 and 592 courses for the four vectors. Five reads competed. They were the exact product read, a representative-filter pushdown, a centred SQL read over a stored hub-subtracted column, a bounded exact NumPy read, and an approximate HNSW index at two candidate bounds and two `ef_search` values.

Pushdown preserved the exact set, order and scores on all four vectors, with a maximum score delta of 0.0. It was slower on every query, with medians from 0.6939 to 0.8105 seconds against 0.5699 to 0.6202 for the exact read. The centred SQL read matched set and order on all four and ran in 0.4898 to 0.5023 seconds, about 0.08 to 0.13 seconds faster per query than the exact read. That is a sample result, not a selected product change.

The bounded NumPy read matched set and order with score differences below 3.1e-7. Its 17.78 seconds of fixture read and 3.93 seconds of arithmetic covered 58,962 chunks in 116 batches and were shared across all four queries in one pass, so they are not a single-query latency. At this corpus size the shared read was far slower than centred SQL.

HNSW is approximate. The index build took 95.8 seconds and occupied 369.65 MB. Only candidate 512 with `ef_search` 512 reached recall 1.0000 and the same set, and only for vector-1. The other three queries at that setting returned recall 0.9940, 0.5783 and 0.5152, and none had the same set. Every setting except 512/512 returned recall between 0.1791 and 0.4226. No candidate bound or `ef_search` value returned the exact set for all four vectors, and none is a product setting.

The comparison measures exactness, recall and read cost, not semantic quality. The four vectors are query inputs, not a semantic oracle, and the exact reference ran on a fixture copy of the compatible chunk rows. The read times start after the query vector exists. They exclude the embedding request, because a test provider returned the fixed vector. A separate embedding-only measurement put warm p95 at 53.5 ms and compared it with a 0.5-second search budget, but it did not measure the full search path. The 53.5 ms and the 0.49 to 0.62 seconds are not added, and their sum is not an end-to-end search latency. The HNSW comparison reports recall and candidate counts, with no query latency.

The first pushdown call used the raw stored vector as the query instead of the hub-centred vector, so its comparison did not count. The corrected call matched the oracle. Three NumPy corrections fixed missing joins, the array input type and a score formula before that pass counted. Interpreted: on this sample, no approximate setting is exact enough to replace the exact read.

## Lexical matching in SQL

The lexical experiment asked whether SQL can reproduce the Python matching the application performs. It fixed four queries before any comparison. They were one course code, two codes in one query, a fullwidth Unicode literal and a misspelled literal. Every query ran in Finnish and English, under the all-courses and active-only scopes, so one SQL form was compared over 16 cells.

The Python baseline used a five-key order. Active courses came first, rows with a displayed name came before rows without one, and the three text keys were normalized display name, normalized code and canonical group identity. The normalized projection was built with `NFKC(value).casefold().strip()` before any SQL timing started.

The comparison separated two properties. Set equality asks whether the same canonical courses appear. Order equality asks whether every position matches. The list position decides what a reader sees first, so order equality is a separate requirement. The first measurement compared the projection exact-code form, the projection substring form, a raw `lower()` substring form and a trigram name form against their Python baselines under the fixture's default `en_US.utf8` collation.

Exact code returned the same set and order in all 16 cells. Projection substring returned the same set in all 16 and the same order in 15. The differing cell was the all-courses Finnish cell for the fullwidth query, with 61 results. Raw `lower()` matched the set in 14 cells, with two mismatches on the fullwidth query. Trigram matched the set in 13 cells, with three mismatches across the fullwidth and misspelled queries.

An ordering proof then applied explicit `COLLATE "C"` to the three text keys, kept the same normalization and five keys, and compared full ordered identity lists and key values. It covered 16 exact-code and 16 substring cells, 32 in total. All 32 matched, including the 61-result cell. The fixture database kept its default `en_US.utf8` collation, so this is not a C-collated database. It is a C collation on the ordering expressions.

The earlier 15 of 16 substring order became 16 of 16, and the result that stands is order parity in the 32 sampled cells. The proof reran neither raw `lower()` nor trigram. Their set mismatches stand as observations on these inputs.

Normalization and collation answer different questions. Normalization changes the text before matching, so a fullwidth query and a composed query can become the same string. Collation changes the order of strings that already matched. Raw `lower()` does not apply NFKC or Unicode casefolding, which is why the fullwidth query found nothing there. The trigram form measures shared three-character sequences at a 0.8 cutoff, not the Python weighted whole-string ratio plus token coverage. Interpreted: NFKC and casefolding have to happen before the comparison, and collation is a property of the ordering expression.

SQL durations cover one statement on a pre-normalized projection. They exclude the NFKC and casefold work that prepares the rows. The first comparison had no warmup pass, and the ordering proof had one warmup and three recorded passes. The four form medians, 1.6 ms, 2.3 ms, 9.0 ms and 40.7 ms, are medians over the 16 cells of the first recorded pass, not medians across all three passes. The warmed per-cell medians in the proof ran from 1.109 ms to 2.995 ms.

The projection has a storage cost. The first projection was 3.33 MB and the narrower proof projection 2.26 MB, 32 percent smaller. No SQL matcher, collation or index from the line is a selected product setting. The application performs lexical matching in Python.

## How the reports fit together

The three reports answer different questions about one pipeline. Translation sits upstream. It decides the effective text that the embedding stage reads, and the retrieval proxy scores whether that text points at the official counterpart. The semantic report then measures the vector read over stored vectors, with the exact read, a representative pushdown, a centred SQL form and an approximate index. The lexical report covers the exact-code, substring and fuzzy methods, where the application matches codes and names in Python and a SQL form would have to reproduce both set and order.

The recommended reading order is translation, semantic, lexical. Translation comes first because it explains what text search sees. Semantic comes next because it measures the vector path and its cost. Lexical comes last because it covers the other matching path and depends on the same distinction between set and order. The order is conceptual. Both search reports were measured on 21 October 2026, after the 13 September 2026 translation run, and their results do not combine into a single score.

Each report is self-contained, and the links above lead to the full setup, tables and limitations.

## Category-wide limits

None of the three is an end-to-end search benchmark. No measurement joins the query embedding request to the database read, exercises concurrent load, or measures a browser query through the merged search path. The translation projection excludes model load and embedding. The semantic read times exclude the embedding request. The lexical times exclude normalization. The three cover separate parts of the path, not its total.

The cohorts are small and fixed. Translation has 60 cases, so one case moves a cell rate by 0.10 and the split is deterministic rather than random. Semantic retrieval has four stored vectors on one snapshot. Lexical matching has four purposive query strings over 16 cells each. None is a random sample of the catalogue's field, length, language or user-input mix.

The measurements establish retrieval utility, exactness and parity on those inputs. They do not establish translation quality, semantic relevance, or that a SQL form should replace the Python matcher. Neither an approximate HNSW setting nor a SQL matcher, collation or index was selected for the product.

## Untested questions

Each question below is untested.

- Whether a human rating of fluency, terminology and adequacy agrees with the translation retrieval proxy.
- Whether these translations preserve retrieval in the product's 1,200-character, hub-centred semantic search over the full catalogue.
- Whether TranslateGemma 27B at Q4_K_M, or a fine-tune, would raise the Finnish name cell or the overall mean reciprocal rank.
- Whether a full search path that adds the 53.5 ms embedding request to the exact read meets the 0.5-second budget used in the embedding feasibility measurement. The parts were measured separately and never joined.
- Whether the centred SQL advantage holds on a larger corpus or under concurrent load, and whether an index on the centred expression preserves exactness at lower read cost.
- Whether an indexed trigram query can approach the Python fuzzy result, whether normalization can move to write time without changing order, and whether a larger Unicode set preserves order parity under explicit C collation.
