# Comparison

Comparison measures two courses against each other through their stored teaching-text vectors and reports five percentages and one verdict.

## What is compared

Each stored chunk holds one piece of the effective text of a representative version as a vector, and a comparison reads the chunks the embedding stage stored for the two courses. Every number comes from arithmetic over those vectors, so no language model runs for a comparison request and no text is generated for it.

Each input is a canonical identity or an exact official code, resolved to exactly one represented course.

A comparison reads the completed chunks that were written under the embedding configuration in force, so vectors written under other embedding settings take no part in it.

> [!IMPORTANT]
> Every meter and the verdict are calculated analysis of the stored teaching-text vectors. They estimate how close two courses are and are not an official statement that one course is equivalent to another. The app shows the note **Course information analysis, not official equivalence.** beside the verdict.

## The five meters

The comparison reports five [comparison meters](/docs/reference/glossary.md#search-and-comparison). Every meter is a percentage from 0 to 100, or it has no value.

| Meter | What it measures |
|---|---|
| Overall relatedness | The whole teaching text of the two courses, the name, the content, and the learning outcomes together, instead of one passage of it. |
| Content similarity | The content text of the two courses. |
| Learning-outcome similarity | The learning outcomes of the two courses. |
| Overlap: A in B | The share of the first course's teaching text that has a close match in the second course. |
| Overlap: B in A | The share of the second course's teaching text that has a close match in the first course. |

The two overlap meters are directional, and the app names each of them with the two course codes and the direction it measures, so the direction of each share is clear.

The diagram shows the two courses entering the comparison through their stored chunk vectors, the centring of those vectors on the hub of their field, the five meters that follow, and the verdict that the strongest overlap and the overall relatedness decide.

![Two courses enter the comparison with their stored chunk vectors, which are centred on the embedding hub and, for learning outcomes, the outcomes hub. The five meters report overall relatedness, content similarity, learning-outcome similarity, and overlap in each direction. The verdict follows from the strongest directional overlap and otherwise from the overall relatedness.](/docs/diagrams/comparison-meters.svg)

## Languages and fields

Every meter is computed one language at a time. Finnish text is measured against Finnish text and English text against English text, so a meter that has no language in common between the two courses has no value.

Content similarity measures content against content, and Learning-outcome similarity measures learning outcomes against learning outcomes, so a similarity meter reads one field on both sides. Overall relatedness combines the name, the content, and the learning outcomes of the two courses with configured weights, and it counts a field of one language only when both courses carry that field, so the weights are shared by the fields the pair has in common.

The two overlap meters read the content and the learning outcomes of both courses together. A content chunk may find its close match in a learning-outcomes chunk, because the overlap asks whether the teaching text of one course appears in the other course, and a chunk of either descriptive field answers that question. A title takes no part in an overlap meter, because a similar name does not show similar teaching.

The weights are `COMPARISON_NAME_WEIGHT`, `COMPARISON_CONTENT_WEIGHT`, and `COMPARISON_OUTCOMES_WEIGHT` in `config/search.toml`, and the example sets 0.10, 0.45, and 0.45.

## Hubs

Every vector is centred before it is measured. The [embedding hub](/docs/reference/glossary.md#capture-and-data-preparation) is subtracted from a name or content chunk, and the outcomes hub is subtracted from a learning-outcomes chunk. Stored chunk vectors share a common direction, so their raw similarity is high for any course pair, and centring is what makes two unrelated courses score close to zero.

## Overlap calibration and the verdict

An overlap meter reports how much of one course's teaching text appears in the other. A configured floor maps to 0 and a configured ceiling maps to 100, so a partial match reads as a partial percentage instead of collapsing to 0 or 100.

The verdict is one label, chosen in a fixed order.

1. The strongest of the two overlap values, when one exists, decides the two overlap labels. At or above the heavy threshold the verdict is Heavily overlapping, and at or above the partial threshold it is Partly overlapping.
2. Otherwise Overall relatedness decides. At or above the same-area threshold the verdict is Same area, different content, and at or above the loose threshold it is Loosely related. Below the loose threshold the verdict is Unrelated.
3. A comparison with no overlap value and no Overall relatedness value has no verdict.

| Key | Meaning | Example |
|---|---|---|
| `COMPARISON_OVERLAP_FLOOR` | The mean match that maps to 0 percent in both overlap meters | 0.20 |
| `COMPARISON_OVERLAP_CEILING` | The mean match that maps to 100 percent in both overlap meters | 0.90 |
| `COMPARISON_HEAVY_OVERLAP_PERCENT` | The strongest overlap at or above which the verdict is Heavily overlapping | 70 |
| `COMPARISON_PARTIAL_OVERLAP_PERCENT` | The strongest overlap at or above which the verdict is Partly overlapping | 30 |
| `COMPARISON_SAME_AREA_PERCENT` | Overall relatedness at or above which the verdict is Same area, different content | 35 |
| `COMPARISON_LOOSE_RELATED_PERCENT` | Overall relatedness at or above which the verdict is Loosely related | 20 |

The settings refuse a floor at or above the ceiling, a partial threshold at or above the heavy threshold, and a loose threshold at or above the same-area threshold, so the order of the thresholds always holds.

## Not available

A meter has no value when the two courses share no language, or when one side has no text in the field the meter reads.

| Condition | Meters without a value |
|---|---|
| The two courses share no language | All five, and no verdict |
| No shared language carries content on both sides | Content similarity |
| No shared language carries learning outcomes on both sides | Learning-outcome similarity |
| No shared language carries a content or learning-outcomes chunk on both sides | Both overlap meters |
| A side has no stored chunk under the embedding configuration in force | All five, and no verdict |

A name-only course has no value in Content similarity, Learning-outcome similarity, or either overlap meter, while Overall relatedness has one.

A computed value of 0 is a result, not a missing comparison. A meter without the inputs it needs is shown as Not available. The app uses the same label when the comparison has no verdict.

## Self-comparison, inactive courses, and derived text

A comparison of a course with itself resolves both sides to the same course, and its meters come from that course's own stored chunks. A course that carries content text therefore reads 100 on Content similarity and on both overlap meters.

An explicitly chosen inactive course takes part in a comparison like any other course, because the two inputs resolve by canonical identity or exact official code.

The report states whether either side used derived text. A stored chunk is derived when the effective text it holds came from a translation, and the app adds the note **Includes derived text.** to a comparison whose chunks on either side include one. The stored chunk records that origin, which [Data model](/docs/backend/catalogue/data-model.md) describes.

The arithmetic behind every meter, the exact form of each score, the read that supplies the chunks, and the tests that cover them are described in [Comparison arithmetic](/docs/backend/search-and-discovery/comparison-arithmetic.md).
