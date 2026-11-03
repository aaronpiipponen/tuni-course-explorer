# Recommendation scoring calibration

This report records the choice of a 0.80 relatedness floor and the retention of a 0.30 overlap penalty as starting values for whole-basis recommendations.

**Evidence status:** Exploratory. **Run date:** 10 October 2026.

## The question

[Recommendations](/docs/backend/search-and-discovery/recommendations.md) sit beside the next-course list. They should lead from the completed [basis](/docs/reference/glossary.md#prerequisites-and-routes) to courses that deepen or connect its topics, and they should not offer a course that repeats teaching the basis already contains. A whole-basis recommendation draws its candidates and its overlap from the completed set as a whole, not from one course in it. Two policy values control that balance:

- the relatedness floor, below which a candidate is not recommended
- the overlap penalty weight, which lowers a candidate's score by a share of how much of its text the basis already covers

A third value, the near-duplicate share, removes a candidate outright when its overlap with the basis reaches a set share.

The experiment fixed the request, the embedding model and the rest of the policy, then checked the floor at three values, with the 0.80 and 0.85 counts recorded for all three fixed baskets and the 0.55 count for the one-course basket alone. The expanded basket ran at the selected floor only. It asked whether the chosen values produced sensible starting behavior, not whether they were optimal. A relatedness floor is a similarity cut. It does not measure whether a course is a sensible next step for a student, and no such measure was collected.

## The request and the baskets

Every request used the completed courses as the basis, the `at_least_one` prerequisite mode, English display, no inferred prerequisites and active courses only. The product offers both prerequisite modes, All and Partially covered. The prerequisite mode decides which next courses the recommendation step removes before similarity, so another mode changes the candidate pool.

The next-course step ran first, and the recommendation step removed the basis and every next course from its candidate pool. The similarity results are therefore an addition to the next-course list, not the whole recommended list.

In this report, a basket is a fixed set of completed courses used as the basis. Four baskets were used: a single programming course, a three-course computing set, a three-course math-heavy set, and an expanded computing basket of 49 courses. The measurement ran against one build of the recommendation command, called the measured build. [Recommendation latency diagnosis and remediation](/docs/experiments/recommendations/latency-diagnosis-and-remediation.md) states how each basket was built and the time its command took.

## How a candidate was scored

The scoring ran in a fixed sequence:

1. For each basis chunk, the nearest-chunk read asked the stored approximate index for at most `RECOMMENDATION_CHUNK_TOP_K` = 40 chunks in the same language and in the content or learning-outcomes field. It excluded the basis and the next courses.
2. The greatest raw cosine of each course became its relatedness, mapped to 0 to 100. A hit from a version other than the representative version was dropped. Courses below the floor were removed, the rest were sorted by relatedness, and the measured build shortlisted at most 100 of them for measurement.
3. Each shortlisted candidate was measured over all of its content and learning-outcomes chunks. A candidate without a descriptive chunk was skipped.
4. Overlap was measured against the whole basis. For each common language, every candidate chunk took its greatest cosine against any basis chunk, and content could match learning outcomes. A chunk counted as covered when that cosine reached the strong-match floor of 0.79. Covered characters divided by the candidate's characters gave the share, and the shares of the common languages were averaged equally.
5. A candidate whose overlap reached the near-duplicate share of 75 percent was dropped.
6. The score subtracted 0.30 times the overlap from the relatedness. Results were ordered by score, then relatedness, then name and code, and the measured build kept the first 30.

```text
relatedness = 100 * greatest raw cosine between one candidate chunk and one basis chunk
overlap     = 100 * covered candidate characters / candidate characters, averaged over common languages
covered     = a candidate chunk whose best basis cosine reaches at least 0.79
score       = max(0, relatedness - 0.30 * overlap)
keep        = relatedness at least 80 and overlap below 75
order       = score descending, relatedness descending, name and code
```

The floor was applied to the candidate pool before the overlap was measured. The near-duplicate cut and the score were computed after it. The configured floor is a fraction between zero and one, so 0.80 corresponds to 80 on the relatedness percentage.

Relatedness was a greatest chunk cosine, so one closely matching chunk set the value. Overlap measured the other direction, the share of the candidate's text that the basis already covered. The penalty changed the score, and the score decided the order, while the reported relatedness was the raw value. At a weight of 0.30, 10 points of overlap lowered the score by three points. Of the two overlap settings, only the near-duplicate cut removed a course outright.

## The floor check

The floor is set by `RECOMMENDATION_MIN_RELATEDNESS` and was checked at three values on the fixed baskets, without a parameter grid and with the other policy values held at their starting settings:

| Relatedness floor | One-course results | Computing results | Math-heavy results |
|---:|---:|---:|---:|
| 0.55 | 22 | not reported | not reported |
| 0.80 | 19 | 13 | 3 |
| 0.85 | 1 | 1 | 0 |

At 0.85 the one-course and computing lists each held only Data-Intensive Programming, and the math-heavy list held nothing. At 0.55 the check recorded 22 results for the one-course basket, and the list included broad study-planning and internship suggestions. The computing and math-heavy counts at 0.55 were not reported.

At 0.80 the three fixed baskets returned 19, 13 and three results. The math-heavy list held Measure and Integration, Complex Functions and Introduction to University Mathematics. The computing list held Basic Electronics, Computer Architecture and Data-Intensive Programming among broader options. The one-course list held Programming Technique C, Basic Electronics and Guided Planning of Studies among its 19 results.

The counts show that one floor produced lists of different lengths. The math-heavy basket lost all three results between 0.80 and 0.85, while the one-course and computing baskets kept one result each. The floor did not act as a list-size control. It is a similarity cut, and the number of courses above it depends on the subject and on the candidate pool.

The value 0.80 was kept as the starting floor because 0.85 collapsed the lists and 0.55 admitted broad suggestions on the one-course basket. That is a judgment from counts and names, not a measured optimum. The check records that some broad or unexpected suggestions appeared at 0.80.

The check recorded counts and example names, not the full membership at each floor. A course that left or entered a list between two floors cannot be traced except where an example names it.

## Settings of the measured build

The floor was the only recommendation policy value checked at more than one setting. These values were left at their starting settings:

| Setting | Key | Value |
|---|---|---:|
| Near-duplicate share | `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | 75 percent |
| Whole-basis overlap weight | `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | 0.30 |
| Chunks per basis chunk | `RECOMMENDATION_CHUNK_TOP_K` | 40 |

In the measured build the near-duplicate share and `COMPARISON_HEAVY_OVERLAP_PERCENT` both held 75 percent. Neither value was separately calibrated.

Three further keys set the measured build. The product reads none of them. Its list is cut by the relatedness floor and the near-duplicate rule alone, so it has no configured length limit.

| Setting | Key | Value |
|---|---|---:|
| Candidate shortlist | `RECOMMENDATION_CANDIDATE_LIMIT` | 100 |
| Result cap | `RECOMMENDATION_MAX_RESULTS` | 30 |
| Strong-match cosine floor | `COMPARISON_STRONG_MATCH_MIN_SCORE` | 0.79 |

The measured build shortlisted at most 100 candidates and kept at most 30 results. `COMPARISON_STRONG_MATCH_MIN_SCORE` set the cosine at which a candidate chunk counted as covered by the basis.

## What bounded the counts

The shortlist of 100 bounded how many candidates reached the overlap measurement. No recorded measurement gives the shortlist size, so the returned counts cannot show how much of that bound was used.

The returned counts are also after the 30-result cap. The expanded computing basket returned 30 similarity results, equal to the cap. The count before truncation was not measured, so 30 is the recorded value at the cap, not the number of courses that qualified. The other three baskets returned 19, 13 and three results, below the cap.

The pool was drawn from an approximate nearest read, with at most 40 chunks per basis chunk. A related course whose close chunk was missed by the search, or fell outside the 40, could not enter the pool. The experiment did not measure that loss.

Checks on the returned lists confirmed that every result named a distinct canonical course, was active and was disjoint from the basis and the next courses. Every result was also at or above the floor, below the near-duplicate share when overlap was available, within the result cap, and computed by the formula. Those checks show that the policy was applied. They do not show that the near-duplicate share or the penalty weight removed the right courses. No rejected candidate or reordered result was recorded.

## The scoring scale in the product

The values in this report apply to the scoring that the measurement used. That scoring took relatedness from the single best matching chunk and measured overlap against the whole basis at once.

The product computes a candidate's relatedness as a hub-centred similarity to a trimmed basis vector, measures the near-duplicate share one basis course at a time, and calibrates its overlap percentages between a configured floor and ceiling. Its example values are a relatedness floor of 0.33, a near-duplicate share of 90 percent and a penalty weight of 0.0. The percentages and the weight in this report are therefore not comparable with those settings. The 0.80 floor, the 75 percent share and the 0.30 weight are the experiment's own starting values, not the product's policy. [Recommendations](/docs/backend/search-and-discovery/recommendations.md) states the scoring that applies.

The changes to the overlap measure and to the scorer are measured in [Centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md) and [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md).

## What the results do not establish

- The course names are not relevance labels. No student, teacher or other judge rated the suggestions, and a returned course is not evidence that it is a good next course.
- The 0.80 floor is a starting value chosen from counts and names, not a measured optimum. No parameter grid ran.
- The four baskets cover one programming course, one computing set, one math set and one expanded computing set from one captured catalogue. The expanded basket reuses the computing basket, so the four are not independent subjects. They do not represent other subjects or a whole degree.
- Relatedness came from one best chunk pair and overlap from the whole basis. Neither is a course-level judgment of whether the teaching connects.
- The candidate pool excluded the next courses and the basis, and was drawn from an approximate nearest read, with 40 chunks per basis chunk and up to 100 shortlisted candidates in the measured build. The measured build returned at most 30 results. Every count is conditional on those cuts.
- The near-duplicate share and the penalty weight were not varied, and no rejected candidate was reviewed.
- The request used one prerequisite mode, one display language, one activity scope and no inferred prerequisites. Another mode changes which courses the next-course step removes, and therefore changes the candidate pool.
- The scoring scale in the product differs from the scale measured here, so the values do not transfer as settings.

## Setup details

| Item | Value |
|---|---|
| Catalogue | 11,086 courses, each counted once through a representative version (4,543 active), and 58,962 teaching-text chunks |
| Model | `BAAI/bge-m3` |
| Pooling | CLS |
| Normalization setting (`EMBEDDING_NORMALIZATION`) | 2 |
| Context size | 2,048 |
| Chunk size | 1,200 characters |
| Chunk overlap | 120 characters |
| Embedding batch size | 32 |
| Hardware | 4-core aarch64 server, 24.1 GB of RAM |
| Database access | Read only, with no stored writes |
| Basis | Completed courses |
| Prerequisite mode | Partially covered (`at_least_one`) |
| Display language | English |
| Inferred prerequisites | Excluded |
| Activity scope | Active courses only |

The commands read stored vectors and made no embedding request. No GPU or model-provider call ran.

## Open questions

- Whether the near-duplicate share of 75 percent and the weight of 0.30 remove re-taught courses without discarding useful neighbours. No relevance judgment or rejected-candidate review was recorded. Untested.
- Whether a floor chosen on a programming, computing and math basket transfers to a humanities or social-science basis, or to a single course outside computing. Untested.
- Whether the hub-centred scoring scale in the product would rank these baskets in the same order. The two scales were not compared on the same inputs. Untested.
