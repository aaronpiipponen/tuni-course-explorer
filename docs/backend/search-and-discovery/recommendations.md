# Recommendations

Recommendations are the courses whose teaching text is similar to the basis, ranked by similarity and listed apart from the next courses.

## What a recommendation request reads

A recommendation request takes the same inputs as a next-course request: the selected course set, the completed course set, the [basis](/docs/reference/glossary.md#prerequisites-and-routes), the mode, the display language, the inference toggle, and the activity scope. Validation runs first, so a blank identity, an unknown basis, an unknown mode, or an unsupported display language fails before any read.

One command runs the next-course discovery with those inputs and then removes both the chosen basis courses and the returned next courses from the recommendation candidates, so a course the chosen mode lists as a next course is never recommended. The next-course report cache supplies a repeated canonical request without recompiling its eligibility.

An empty chosen basis returns no recommendations, as does a basis with no stored descriptive text.

The site serves the shared descriptive chunk store of the opened artifact build, so a descriptive read opens no database session and returns the content and learning-outcomes rows alone. A missing store, or a store of another embedding configuration, fails when the artifact set opens with guidance to run `serving-artifacts`. [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md#the-shared-descriptive-chunk-store) states the store, the artifact key it records and the build that writes it.

The diagram follows one request from the basis chunks to the ordered list.

![The basis chunks enter a nearest chunk search, whose hits choose the candidates after the basis courses and the next courses are left out. A centroid prefilter keeps the candidates whose stored centroid reaches the relatedness floor, and every kept candidate is then measured over all of its descriptive chunks against the trimmed basis vector. A candidate that duplicates one basis course is dropped, the whole-basis overlap reduces the score, and the list is ordered by score, then relatedness, then the displayed name and code.](/docs/diagrams/recommendation-ranking.svg)

## The candidate pool

The pool starts from the basis chunks: the content and learning-outcomes chunks of the basis courses that were stored under the embedding configuration in force. A basis course with no such chunk contributes nothing to it.

A nearest search then asks for the stored closest chunks to each basis chunk, in the same language and in the same two fields, with the basis courses and the next courses excluded. It keeps at most `RECOMMENDATION_CHUNK_TOP_K` stored rows per basis chunk. The build stores up to `SEARCH_NEIGHBOR_TABLE_ROWS_PER_CHUNK` nearest rows per query chunk, so a request whose exclusions leave fewer stored rows returns fewer. The request's activity scope and exclusions apply to the stored rows, so a basis chunk fills the limit when at least that many stored rows survive. [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md#the-nearest-read) states how the build produces the stored rows.

The search decides the candidates, and the native scorer orders them. Each hit names one candidate course, and the hits of one course are reduced to a single entry that carries no score. A hit whose stored chunk belongs to a version that is not the representative version of its course is dropped, so only a current representative becomes a candidate.

The measured text is read apart from the search. Once the pool is fixed, every compatible content and learning-outcomes chunk of each surviving candidate takes part in the measurement, so a candidate is measured over all of its descriptive text rather than the chunk that matched. The candidate chunk rows come straight from the shared serving chunk store, so that measurement opens no database read. The measured saving of that projection is recorded in [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md#narrow-read-results).

The activity scope applies to the pool. Under active only an inactive course is never proposed, and under the all-courses scope it takes part like any other candidate. An inactive basis course contributes its chunks to the basis vector.

## The centroid prefilter

Each represented course with a descriptive chunk has one stored centroid: the unit mean of its hub-centred, unit-normalized content and outcomes chunk vectors. The centroid store identifies it by the course, the representative identity and the embedding configuration.

The command applies `RECOMMENDATION_MIN_RELATEDNESS` to the candidate centroids before it reads candidate summaries and full chunk vectors, so a candidate below the floor is dropped before the summary and chunk reads. A candidate at or above the floor continues through the same summary read, chunk read, relatedness measurement, near-duplicate test and ordering as the rest of the page describes. [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md#the-centroid-prefilter) states the centroid read and the matrix product.

A centroid describes the chunk set the artifact build read, and the scorer applies the same floor to the candidate point it computes from the stored chunks, so the two agree while the build matches the served chunks. A change to the chunk set under the same representative identity and embedding configuration is not detected. [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md#the-centroid-prefilter) states the rebuild that keeps the centroid matrix, the chunk store and the hub pair aligned.

A missing store or a directory of another configuration fails when the artifact set opens with guidance to run `serving-artifacts`. The opened build supplies the hub pair, so no separate configured pair is compared. The supervisor maps the shared store in the opened set and every worker inherits it, so the worker's first dataset read builds only its centroid lookup over that mapping.

## Relatedness to the trimmed basis vector

Every vector is centred before it is measured, on the embedding hub for content and on the outcomes hub for learning outcomes, as [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes.

One basis vector stands for the whole basis, and the basis courses that agree with the whole basis steer it. This keeps the mandatory strands of a broad degree from steering the basis vector, so a candidate has to relate to the dominant subject of the basis instead of to one course in it. A basis of one course forms the basis vector on its own.

Relatedness is the cosine between the candidate's teaching text and that basis vector. The cosine is measured from 0 to 1 and then calibrated for display: the `RECOMMENDATION_MIN_RELATEDNESS` floor keeps its own percentage, `RECOMMENDATION_RELATEDNESS_CEILING` reads as 100, and the values between spread linearly onto the rest of the scale, so a close match reads high while the weakest kept candidate stays low. The calibration is monotone and changes no cut or order. The native scorer computes the candidate rows, the relatedness, the overlap, the near-duplicate test and the order. A library that is absent or mismatched raises one `ValueError` naming the build command, and [Native libraries](/docs/architecture/native-libraries.md) states that build. [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md#ranking-the-trimmed-basis-vector-and-the-near-duplicate-rule) states the scorer, its formulas and its order.

A candidate without a compatible descriptive chunk is omitted, because there is no text to measure.

## Near-duplicate rejection

A candidate whose teaching text repeats one basis course at or above a configured share is a [near-duplicate](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) and is left out.

The share is measured one basis course at a time, by the same overlap rule that the comparison meters use, and a candidate whose greatest single-basis-course share reaches `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` is left out.

Measuring one basis course at a time keeps a course that shares some content with a broad basis, while a course that duplicates one basis course reads as a near-duplicate.

## The score and the ordering

The candidate is also measured against the whole basis at once, over every basis course together, and that whole-basis overlap reduces the score by `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT`. The penalty applies to the score alone, so the relatedness that the app shows is the calibrated cosine with the basis vector. A weight of 0 leaves the score equal to the raw basis-vector cosine percentage, so the whole-basis overlap does not change the order.

The list is ordered by descending score, then by descending relatedness, then by the displayed official name and code key. The relatedness floor and the near-duplicate rule are the only cuts, so the list has no configured length limit.

## Derived text

Each result states whether derived text took part. The flag is true when any chunk of the candidate or any descriptive chunk of the basis came from a translation rather than from official text, and the app notes it beside the **Similarity** meter.

## Configuration keys

`config/search.toml` holds the recommendation policy, which the settings owner validates.

| Key | Meaning | Example |
|---|---|---|
| `RECOMMENDATION_CHUNK_TOP_K` | The number of closest chunks one basis chunk asks for | 40 |
| `SEARCH_HNSW_ITERATIVE_SCAN` | The iterative-scan mode of the serving artifact build's nearest query: `relaxed_order` or `strict_order` | `relaxed_order` |
| `SEARCH_HNSW_MAX_SCAN_TUPLES` | The greatest number of HNSW candidates one nearest-neighbour scan of the serving artifact build reads | 20000 |
| `SEARCH_NEIGHBOR_TABLE_ROWS_PER_CHUNK` | The nearest-neighbour rows the serving artifact build stores per query chunk | 128 |
| `RECOMMENDATION_MIN_RELATEDNESS` | The relatedness floor, from 0 to 1, at or above which a candidate is kept | 0.33 |
| `RECOMMENDATION_RELATEDNESS_CEILING` | The raw relatedness, from 0 to 1, that reads as 100 in the displayed Similarity meter | 0.65 |
| `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | The single-basis-course overlap at or above which a candidate is left out | 90 |
| `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | How strongly the whole-basis overlap reduces the score, from 0 to 1 | 0.0 |

`RECOMMENDATION_CHUNK_TOP_K`, `SEARCH_HNSW_MAX_SCAN_TUPLES` and `SEARCH_NEIGHBOR_TABLE_ROWS_PER_CHUNK` are greater than 0, and the two relatedness keys take 0 to 1 with the floor below the ceiling.

The overlap calibration of the near-duplicate share and of the whole-basis overlap uses `COMPARISON_OVERLAP_FLOOR` and `COMPARISON_OVERLAP_CEILING`, which the comparison meters share. [Comparison](/docs/backend/search-and-discovery/comparison.md#overlap-calibration-and-the-verdict) lists those two keys and their example values.

## Availability on a site

A recommendation reads stored vectors, so a site serves it while `WEB_EMBEDDINGS_ENABLED` is true in that site's `config/web.toml`. A site with the switch off refuses the recommendation request with status 403 and the detail `Feature disabled` before the command runs, and its browser offers no Recommended list and requests the next courses alone.

The route also applies `WEB_INFERENCE_ENABLED` to the request's inference toggle, so a site that serves the embedding features but not the inference features builds the next-course step from official prerequisites alone. That step decides which courses the recommendation excludes, so the inference switch changes the candidate set. The command, its inputs, its ranking and the script adapter are the same on both kinds of site.

The nearest read, the pool aggregation, the basis-vector computation, and the tests that cover them are described in [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md).
