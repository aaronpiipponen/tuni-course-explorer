# Recommendations

Recommendations are the courses whose teaching text is similar to the basis, ranked by similarity and listed apart from the next courses.

## What a recommendation request reads

A recommendation request takes the same inputs as a next-course request: the selected course set, the completed course set, the [basis](/docs/reference/glossary.md#prerequisites-and-routes), the mode, the display language, the inference toggle, and the activity scope. Validation runs first, so a blank identity, an unknown basis, an unknown mode, or an unsupported display language fails before any read.

One command runs the next-course discovery with those inputs and then removes both the chosen basis courses and the returned next courses from the recommendation candidates, so a course the chosen mode lists as a next course is never recommended.

An empty chosen basis returns no recommendations, as does a basis with no stored descriptive text.

A serving site retains the descriptive chunk tuples of the dataset under the `(group_id, sisu_course_unit_id, representative_source_hash)` triple. A repeated request reads only the triples it does not hold, and the measured read selects the content and learning-outcomes rows alone.

The diagram follows one request from the basis chunks to the ordered list.

![The basis chunks enter a nearest chunk search, whose hits choose the candidates and order the pool after the basis courses and the next courses are left out. Every candidate is then measured over all of its descriptive chunks against the trimmed basis profile, a candidate that duplicates one basis course is dropped, the whole-basis overlap reduces the score, and the list is ordered by score, then relatedness.](/docs/diagrams/recommendation-ranking.svg)

## The candidate pool

The pool starts from the basis chunks: the content and learning-outcomes chunks of the basis courses that were stored under the embedding configuration in force. A basis course with no such chunk contributes nothing to it.

A nearest search then asks for the closest chunks to each basis chunk, in the same language and in the same two fields, with the basis courses and the next courses excluded. It takes at most `RECOMMENDATION_CHUNK_TOP_K` chunks per basis chunk, and the example sets 40, so the search can return fewer chunks than it asks for.

The search decides the candidates, and the greatest raw cosine of each course, mapped to a percentage from 0 to 100, orders the pool. Each hit names one candidate course, the hits of one course are reduced to a single entry that keeps the greatest raw cosine, and that percentage never reaches a result. A hit whose stored chunk belongs to a version that is not the representative version of its course is dropped, so only a current representative becomes a candidate.

The measured text is read apart from the search. Once the pool is fixed, every compatible content and learning-outcomes chunk of each surviving candidate takes part in the measurement, so a candidate is measured over all of its descriptive text rather than the chunk that matched. The measured read selects the content and learning-outcomes rows alone. The measured saving of that projection is recorded in [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md#narrow-read-results).

The activity scope applies to the pool. Under active only an inactive course is never proposed, and under the all-courses scope it takes part like any other candidate. An inactive basis course contributes its chunks to the profile.

## Relatedness to the trimmed basis profile

Every vector is centred before it is measured, on the embedding hub for content and on the outcomes hub for learning outcomes, as [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes.

One profile stands for the whole basis, and the basis courses that agree with the whole basis steer it. This keeps the mandatory strands of a broad degree from steering the profile, so a candidate has to relate to the dominant subject of the basis instead of to one course in it. A basis of one course forms the profile on its own.

Relatedness is the cosine between the candidate's teaching text and that profile, reported as a percentage from 0 to 100. A candidate below the `RECOMMENDATION_MIN_RELATEDNESS` floor is left out, and the example sets 0.33, so a candidate below 33 percent is not recommended.

A candidate without a compatible descriptive chunk is omitted, because there is no text to measure.

## Near-duplicate rejection

A candidate whose teaching text repeats one basis course at or above a configured share is a [near-duplicate](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) and is left out.

The share is measured one basis course at a time, by the same overlap rule that the comparison meters use, and a candidate whose greatest single-basis-course share reaches `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` is left out. The example sets 90.

Measuring one basis course at a time keeps a course that shares some content with a broad basis, while a course that duplicates one basis course reads as a near-duplicate.

## The score and the ordering

The candidate is also measured against the whole basis at once, over every basis course together, and that whole-basis overlap reduces the score by `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT`. The penalty applies to the score alone, so the relatedness that the app shows is the profile cosine. The example sets the weight to 0.0, so the score equals the relatedness and the whole-basis overlap does not change the order.

The list is ordered by descending score, then by descending relatedness, then by the displayed official name and code key. The relatedness floor and the near-duplicate rule are the only cuts, so the list has no configured length limit.

## Derived text

Each result states whether derived text took part. The flag is true when any chunk of the candidate or any descriptive chunk of the basis came from a translation rather than from official text, and the app notes it beside the **Similarity** meter.

## Configuration keys

`config/search.toml` holds the recommendation policy, which the settings owner validates.

| Key | Meaning | Example |
|---|---|---|
| `RECOMMENDATION_CHUNK_TOP_K` | The greatest number of closest chunks one basis chunk asks for | 40 |
| `RECOMMENDATION_MIN_RELATEDNESS` | The relatedness floor, from 0 to 1, at or above which a candidate is kept | 0.33 |
| `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | The single-basis-course overlap at or above which a candidate is left out | 90 |
| `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | How strongly the whole-basis overlap reduces the score, from 0 to 1 | 0.0 |

The overlap calibration of the near-duplicate share and of the whole-basis overlap uses `COMPARISON_OVERLAP_FLOOR` and `COMPARISON_OVERLAP_CEILING`, which the comparison meters share, and the example sets 0.20 and 0.90.

## Availability on a site

A recommendation reads stored vectors, so a site serves it while `WEB_EMBEDDINGS_ENABLED` is true in that site's `config/web.toml`. A site with the switch off refuses the recommendation request with status 403 and the detail `Feature disabled` before the command runs, and its browser offers no Recommended list and requests the next courses alone.

The route also applies `WEB_INFERENCE_ENABLED` to the request's inference toggle, so a site that serves the embedding features but not the inference features builds the next-course step from official prerequisites alone. That step decides which courses the recommendation excludes, so the inference switch changes the candidate set. The command, its inputs, its ranking and the script adapter are the same on both kinds of site.

The nearest read, the pool aggregation, the profile computation, and the tests that cover them are described in [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md).
