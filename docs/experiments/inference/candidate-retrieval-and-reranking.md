# Candidate retrieval, multiview fusion and reranking

This report measures how candidate courses reach the prerequisite model, from exact embedding retrieval through multiview fusion and cross-encoder reranking.

**Evidence status:** Comparative. **Run dates:** 17 to 25 September 2026.

The [Experiments section](/docs/experiments/README.md) gives the catalogue, the evidence labels and the hardware.

## The question

Inference proposes prerequisites for one target course from a bounded list of candidate courses. The model can name only courses that the list carries, so a course missing from the list is invisible to every downstream stage, and no model quality can recover it. Retrieval and ranking therefore decide part of the achievable result before the model runs.

That separates two questions that one end-to-end score would mix. Candidate recall asks whether the official prerequisite courses reach the candidate list. Inference quality asks whether the model, given the list, proposes supported prerequisites in the right category. This report covers candidate recall and the selection stages that answer it. [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) covers the second question, and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) covers the packet comparison that chose the final 50.

Label safety fixes the order of the measurement. A target's official prerequisite structure is absent from its candidate query, packet, prompt and model input, so recall can be measured only after the candidate list is fixed. Every recall value here comes from reading official course labels after the selection stage that it measures. [Label safety](/docs/reference/glossary.md#inference) is the governing rule.

Three values bound the answer: the depth of the candidate pool, the number of candidates the model receives, and the cost of scoring pairs on one GPU. The runs below set each of them by measurement rather than by preference.

The line measured an all-field cosine baseline, a fused multiview pool, a cross-encoder rerank and a ranking-only small model. The cohorts changed between stages, and a value from one cohort is not comparable with a value from another.

## Method

### Cohorts and labels

Every cohort holds active canonical courses with a representative version and compatible teaching chunks. Candidate sources are all represented courses, including inactive ones, except the target itself. The pool is the ranked candidate list that a target's query retains before any reranking, and its depth is the number of candidates kept.

| Cohort | Targets | How it was selected | Labelled targets | Prerequisite labels | In the 1,000 pool |
|---|---|---|---|---|---|
| Development 100 | 100 | Deterministic, label-blind declaration filtered to the COMP, MATH and DATA prefixes, prompt-example targets excluded | 64 | 156, all measurable | 150 |
| Tuning ten | 10 | Fixed indices 0, 11, 22, 33, 44, 55, 66, 77, 88 and 99 of the saved pool order | 5 | 13, of which 12 are reachable | 12 |
| Labelled ten | 10 | Fixed, evenly spaced selection from the officially labelled targets of the development 100 | 10 | 23 | 21 |
| Disjoint 200 | 200 | Deterministic, snapshot-bound selection from the whole active represented catalogue, disjoint from the development 100, spanning undotted codes and codes outside the three prefixes | 31 | 66 | 62 |

The label set measures the course-level part of the official structure. [The inference overview](/docs/experiments/inference/README.md#official-prerequisites-are-a-partial-retrieval-proxy) states what this proxy does not cover.

The combined label set adds the course members of the target's own official substitute options, deduplicated by canonical identity against the prerequisite set. A substitute applies in one direction and to one target, so the member may replace that target without making the two courses interchangeable elsewhere. The combined set is a separate, versioned label set and it never overwrites the prerequisite-only counts. It covers 255 labels on 74 targets of the development 100, 29 labels on the labelled ten, and 143 labels on 61 targets of the disjoint 200.

The development 100 declaration binds the catalogue identity, the embedding configuration, the split seed and the nine prompt-example target identities. A declaration that differs from the current deterministic selection stops before any candidate query runs.

Labels chose the target group of the labelled ten, and they never entered an input. Every other cohort was declared without reading labels, and no scoring input in any cohort carries one.

The disjoint 200 excludes every prompt-example target and every course that appears as a candidate in a prompt example. The exclusion covers both the cohort and its candidate lists, so an example cannot disclose a cohort target's answer or name a cohort course. Its selection spans the catalogue rather than one subject prefix, which is why its label density differs from the development set.

No run in this report measures inference quality. The recall values measure retrieval and ordering against official labels. The one quality judgement mentioned here is the blind comparison that chose the final packet, and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) reports it.

### Pool construction and fusion

The retrieval query uses one exact comparison over the stored teaching vectors. For one target, the query compares every compatible chunk of the target with every compatible chunk of each represented course, retains the best-scoring chunk pair per course, excludes the target itself, and orders the complete measurable candidate set by cosine score descending, then by canonical course identity. It uses only stored vectors. It does not embed text, does not consult the search path, and puts no cap on the SQL result.

Candidates without a completed vector under the current embedding configuration are omitted rather than given a fabricated score. Inactive courses stay eligible as candidate sources. The packet carries the effective teaching text, the activity, representative, source and embedding identities, the retrieval score and the matched chunk provenance.

The pool query adds field views to the all-field ranking. The target's side of the query can be restricted to one teaching field, name, content or outcomes, while candidate chunks stay unrestricted. One all-field comparison is combined with one comparison per field, and the views are fused by reciprocal rank:

```text
score(c) = sum over views v that surfaced c of 1 / (60 + rank_v(c))
```

The offset is `INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET`, set to 60. The fused score is not a cosine value. Ties are broken by canonical course identity alone, and no label, official structure or measured recall value enters the fusion. A field view that surfaces nothing contributes no synthetic rank, so a target without a compatible chunk in one field gets a pool from the remaining views. Every nonempty view covers the same candidate universe, so a candidate missing from one view is an absence rather than a differently bounded list.

The selected retrieval depth is 1,000 candidates per target, recorded in `INFERENCE_SELECTION_POOL_K`. The pool is measured once, saved and rendered into packets, so no scoring run queries the vectors again. The depth is a ceiling on candidate retrieval for development and for bulk selection, not a packet policy and not a claim that recall is complete.

### Rerank depth and text bounds

The rerank scores every one of the 1,000 pool candidates for a target and retains the strongest 50. Each pair carries the course code and the effective teaching name, outcomes and content, rendered content-first and bounded at 1,536 characters for the target and 1,536 characters for the candidate. The applied keys are `INFERENCE_RERANK_TEXT_LAYOUT` at `content-first`, and `INFERENCE_RERANK_QUERY_MAX_CHARACTERS` and `INFERENCE_RERANK_DOCUMENT_MAX_CHARACTERS` at 1,536 each.

The character bound does not guarantee a token fit. The ten-target grid below records a 3,072-character variant that failed fit at a 2,162-token document.

### Setup

| Parameter | Value |
|---|---|
| Embedding model | BGE-M3 teaching chunks under the captured embedding configuration |
| Candidate query | Exact best-chunk cosine over stored vectors, no approximate index and no SQL cap |
| Development targets | 100, deterministic and label-blind, COMP, MATH and DATA prefixes |
| Disjoint targets | 200, deterministic, snapshot-bound and disjoint from the development 100 |
| Field views | name, content, outcomes (`INFERENCE_MULTIVIEW_EVALUATION_FIELDS`) |
| Fusion | `1 / (60 + rank)` summed over the views that surfaced the candidate |
| Fusion offset | 60 (`INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET`) |
| Pool depth | 1,000 (`INFERENCE_SELECTION_POOL_K`) |
| Reranker | `bge-reranker-v2-m3`, Q8_0 |
| Rerank runtime | llama.cpp, a pinned build |
| Rerank context | 8,192 tokens |
| Rerank batch and micro-batch | 2,048 and 2,048 |
| Rerank text | content-first, 1,536 characters for the target and 1,536 for the candidate |
| Packet maximum | 50 (`INFERENCE_SELECTION_FINAL_K`, hard maximum `FINAL_CANDIDATE_MAX`) |
| Ranking-only models | Qwen3 0.6B and Qwen3 1.7B, Q8_0 |
| Ranking input | cross-encoder top 200, ten batches of 20 |
| Ranking base geometry | 16,384 context, 1,024 batch, 1,024 output tokens |
| Ranking generation | thinking off, temperature 0, seed 0 |
| Ranking fusion | `1 / (60 + rank_qwen) + 1 / (60 + rank_ce)` |
| Hardware | AMD Radeon RX 9070 XT (16 GB model), ROCm 7.2.1, 33.4 GB usable RAM |

## Retrieval baseline

The baseline measurement used the exact query above. The caller retained the top K candidates with the retrieval score and the matched chunk pair. All packets for a target were assembled before that target's official labels were read.

| Depth | Retrieved labels | Micro recall |
|---|---|---|
| 10 | 36/156 | 23.08% |
| 20 | 54/156 | 34.62% |
| 50 | 73/156 | 46.79% |
| 100 | 91/156 | 58.33% |

The baseline result is recorded as micro recall only, and macro recall was not recorded for it.

## Threshold sizing

A cosine threshold was sized against the same labels. The sizing pass covered 16 cells: thresholds 0.50, 0.55, 0.60 and 0.65, each uncapped and capped at 50, 100 and 200.

| Cell | Value |
|---|---|
| Thresholds measured | 0.50, 0.55, 0.60, 0.65 |
| Caps measured | uncapped, 50, 100, 200 |
| Cells | 16 |
| Micro recall at every top-50 cap | 46.79% |
| Median candidates, 0.65 uncapped | 3,569 |
| Median packet bytes, 0.65 uncapped | 17.2 MB |

Every top-50 cap returned the same micro recall as the uncapped baseline at 50. The cap provided the bound, while the threshold up to 0.65 discarded nothing the top 50 would have retrieved. The uncapped 0.65 cell held a median of 3,569 candidates, far beyond the selected 50-candidate packet. A score threshold alone therefore could not both retain the measured recall and bound the candidate list, and the hypothesis failed on that combination.

The cells were development measurements and no threshold was applied. The selected depth is a rank depth over a fused ordering, described next.

## Multiview pool and its ceiling

The fused pool recovered 150 labels of 156 at depth 1,000 and 152 at depth 1,500.

| Depth | Retrieved labels | Micro recall | Macro recall |
|---|---|---|---|
| 1,000 | 150/156 | 96.15% | 97.01% |
| 1,500 | 152/156 | 97.44% | 97.79% |

The macro column averages over the 64 labelled targets. The 100-target pool measurement took 34 minutes 43 seconds, against 10 minutes 49 seconds for the all-field baseline measurement.

Six labels were outside the 1,000 pool. Their fused ranks were 1,150, 1,497, 1,659, 2,378, 2,417 and 2,506. No reranker reading the selected pool can recover them. The two at 1,150 and 1,497 are inside the 1,500 measurement, which is why the deeper pool recovers two more labels.

On the combined label set the same pool recovered 248 of 255 labels. That set is wider than the prerequisite-only set and covers 74 targets, so the two recall values are not interchangeable.

No measurement in this line reports the all-field ranking's recall at 1,000. The 58.33 percent at depth 100 and the 96.15 percent at depth 1,000 differ in both depth and fusion, so the share of the gain that comes from each is unmeasured. That separation is listed as an untested follow-up.

## Reranker runtime and input fit

The reranker is `bge-reranker-v2-m3` at Q8_0, served on its own loopback port by the llama.cpp runtime. It was qualified with one synthetic, label-free request before any course text was scored.

| Measure | Value |
|---|---|
| Serving context | 8,192 tokens |
| Physical batch and micro-batch | 2,048 and 2,048 |
| GPU layers offloaded | 25/25 |
| Artifact quantization | Q8_0 |
| Request result | HTTP 200, both indices scored, calculus above literature |
| Elapsed time | 36 ms |
| Committed GPU memory, prelaunch to loaded to request | 0.0 MB, 503.8 MB, 521.0 MB |
| Free system RAM, before to after load | 19.93 GB to 18.94 GB |

The split between dedicated and shared GPU memory was unavailable for this measurement and was not inferred. The committed value covers every allocation of that process, so it is an upper bound for the reranker.

A serving geometry with a physical batch of 512 could not score a 747-token input, which is a fit failure of the serving geometry rather than a model failure. One batch and micro-batch value of 2,048 was applied, with the 8,192 context and the same text bounds.

## Representative rerank trial

The trial scored three complete 1,000-candidate pools. The three targets were chosen deterministically from the saved pool order: the lexical first, the lower middle, and the largest packet outside those two. They were scored with the same artifact, context and 2,048 batch.

| Measure | Value |
|---|---|
| Pairs scored | 3,000 of 3,000 |
| Maximum observed tokens | 963 |
| Per-target seconds | 27.303, 11.617, 26.871 |
| Mean seconds per pair | 0.02193 |
| Reachable labels recovered at top 50 | 4 of 7 |
| Micro recall at top 50 | 0.5714 |
| Macro recall at top 50 | 0.5833 |

One of the three targets had no official course labels and contributed no recall. The three reachable labels outside the top 50 sat at rerank ranks 89, 178 and 64. Every score was finite and no truncation was reported.

The trial established token fit, complete scoring and throughput. It could not select a depth, a text bound or a packet policy, because seven labels on three targets cannot separate candidates.

## Text bound comparison

The same three targets were scored again at 3,072 characters per side. The pool, model, runtime, context, batch and offload did not change. Only the two character bounds differed. The 1,536-character inputs and scores stayed byte-identical.

| Measure | 1,536 characters | 3,072 characters |
|---|---|---|
| Finite scores | 3,000 | 3,000 |
| Reachable labels at top 50 | 4/7 | 4/7 |
| Micro recall at top 50 | 0.5714 | 0.5714 |
| Macro recall at top 50 | 0.5833 | 0.5833 |
| Maximum observed tokens | 963 | 1,850 |
| Truncation warnings | none | none |
| Mean seconds per pair | 0.02193 | 0.04389 |
| p95 seconds per pair | 0.02981 | 0.07266 |
| Committed GPU memory, loaded to request | not reported | 576.7 MB to 2,562.7 MB |
| Free system RAM, before to after request | not reported | 16.82 GB to 16.29 GB |

The longer bound changed which labels were retrieved without changing how many. One target kept two of three reachable labels and its lone miss moved from rerank rank 89 to 160. Another kept two of four and swapped which two: a label at pool rank 49 that had been retrieved moved to rerank rank 113, a label at pool rank 231 that had been missed moved to rank 64, and a label at pool rank 305 stayed missed while moving from rank 178 to 135.

Doubling the text raised the mean pair time from 0.02193 to 0.04389 seconds and the p95 from 0.02981 to 0.07266 seconds, and bought no measured top-50 recall on these three targets. Three targets cannot choose a bound, so the comparison did not settle one. The hypothesis that a longer text would improve top-50 recall failed, and the ten-target grid measured the bound directly.

## Ten-target text selection

The cross-encoder ordering was tuned on the tuning ten with only two dimensions free: the teaching-text layout and the character bounds of the target and candidate text. Twelve variants were built. Eleven were scored once each at 10,000 pairs, and the twelfth failed fit before scoring. The pool, reranker, runtime, context and batch did not change.

| Variant (layout, target/candidate) | Reachable at 50 | At 100 | At 200 | Mean seconds per pair |
|---|---|---|---|---|
| content-first 1,536/1,536 | 9/12 | 10/12 | 11/12 | 0.02493 |
| content-first 2,048/2,048 | 8/12 | 10/12 | 11/12 | 0.03106 |
| content-first 1,024/1,024 | 8/12 | 8/12 | 10/12 | 0.01888 |
| content-first 1,024/1,536 | 8/12 | 10/12 | 10/12 | 0.02229 |
| outcomes-first 2,048/2,048 | 8/12 | 9/12 | 9/12 | 0.03008 |
| balanced 3,072/3,072 | 8/12 | 10/12 | 11/12 | 0.04001 |
| content-first 1,536/1,024 | 7/12 | 8/12 | 10/12 | 0.02322 |
| outcomes-first 1,536/1,536 | 6/12 | 8/12 | 10/12 | 0.02396 |
| balanced 1,536/1,536 | 6/12 | 7/12 | 10/12 | 0.02436 |
| balanced 2,048/2,048 | 6/12 | 6/12 | 11/12 | 0.03064 |
| outcomes-first 3,072/3,072 | 6/12 | 10/12 | 11/12 | 0.04112 |
| content-first 3,072/3,072 | failed fit | not scored | not scored | not scored |

The denominator of 12 is the reachable labels in this ten-target group. One further label lay outside the 1,000 pool and no rerank could retrieve it.

The selected setting is content-first at 1,536 characters for the target and 1,536 for each candidate. It recovered the most reachable labels at top 50, matched the highest count at the 100 and 200 diagnostic depths, and its mean pair time was below the symmetric 2,048 and 3,072 variants. The 3,072 content-first variant failed fit because a 2,162-token document exceeded the 2,048 physical batch. The settings were applied to the tracked input keys: `INFERENCE_RERANK_TEXT_LAYOUT` is `content-first`, and `INFERENCE_RERANK_QUERY_MAX_CHARACTERS` and `INFERENCE_RERANK_DOCUMENT_MAX_CHARACTERS` are both 1,536.

The 50, 100 and 200 columns show where the remaining reachable labels sit. Several variants move one or two labels between 50 and 100 or 200, which places the loss at the 50-candidate cut rather than at the 1,000 pool. The columns are diagnostics only and do not change the hard maximum of 50.

## The 200-target comparison

The comparison ran on the disjoint 200. Each target's pool was measured once, checkpointed per target, and published as one pool record. The saved pool was then rendered to 200 inputs at content-first 1,536/1,536 and scored one target per bounded process. Each target was scored in its own process, which loaded the model and ran one synthetic warmup before the 1,000 pairs. All 200 targets and 200,000 pairs produced finite scores and deterministic ranks, and the official labels were read only after scoring. The scoring took 4,938.9 seconds in total, a mean of 0.0247 seconds and a 95th percentile of 0.0313 seconds per pair. The total is the sum of the per-target scoring times.

The label measurement was made afterwards. Of the 200 targets, 31 carry official course prerequisites, with 66 distinct per-target label occurrences. Sixty-two of the 66 are inside the saved 1,000 pool. Four are not, so no reranker reading the pool can recover them.

| Depth | Multiview pool | Cross-encoder rerank |
|---|---|---|
| 10 | 14/66 (21.2%) | 17/66 (25.8%) |
| 20 | 19/66 (28.8%) | 22/66 (33.3%) |
| 50 | 26/66 (39.4%) | 37/66 (56.1%) |
| 100 | 33/66 (50.0%) | 49/66 (74.2%) |
| 200 | 42/66 (63.6%) | 57/66 (86.4%) |
| 500 | 55/66 (83.3%) | 62/66 (93.9%) |
| 1,000 | 62/66 (93.9%) | 62/66 (93.9%) |

The chart compares the two orderings at every measured depth.

![Recall of the official prerequisite labels against candidate depth on a logarithmic scale for the 200-target cohort, for the fused multiview pool and the cross-encoder reranking. The reranked ordering leads at every depth below 1,000, and both recover 62 of 66 labels at 1,000.](/docs/charts/inference-rerank-depth-recall.svg)

The depth axis of the chart is logarithmic. The reranked ordering leads the pool at every depth below 1,000, and the gap is large at the shallow depths that matter for a 50-candidate packet.

Among the 62 labels inside the pool, reranker recall is 37 of 62 at top 50, 49 of 62 at top 100 and 57 of 62 at top 200. The missing 29 labels at top 50 divide into the four that are outside the pool and 25 that are inside it but ranked below 50. At top 200 the five reachable misses are all inside the pool.

The run also produced a combined label measurement. The cross-encoder top 200 holds 121 of the 143 combined labels. Of the 130 combined labels inside the pool, it holds 121, so nine reachable labels are lost between the pool and the cross-encoder top 200.

The 200 are a comparison cohort, not an untouched ranking-policy holdout, and their labels were read after the run.

## Ranking-only Qwen comparison

The last comparison asked whether a small ranking-only model adds enough ordering information to justify scoring every target. Both candidates are Qwen3 Q8_0 artifacts, 0.6B and 1.7B, served by the same llama.cpp runtime on loopback with thinking off, temperature 0 and seed 0. The model scored exactly the saved cross-encoder top 200 as ten batches of 20 candidates. The cross-encoder-only packet is CE-only, and the fused packet is RRF, for reciprocal rank fusion. Each batch request returned one score row per candidate, and only the resulting ranks entered the fusion:

```text
fused(c) = 1 / (60 + rank_qwen(c)) + 1 / (60 + rank_ce(c))
```

The offset is 60. The cross-encoder term uses the candidate's position in the cross-encoder top 200, which is the same list the model saw. Only ranks enter, so a wide score spread and a narrow one carry the same weight. The base geometry was 16,384 context, 1,024 batch and 1,024 output tokens. Measured variants also changed context between 8,192 and 32,768, output between the measured 512 and 1,024 budgets, candidate document width between 192 and 1,024 characters, three layouts, and prompt wordings v7 to v12. Every variant was scores-only and every input was teaching-only and label-free.

| Variant | Combined labels on the three-target group |
|---|---|
| Qwen3 0.6B, 384 characters, RRF | 10/12 |
| Qwen3 0.6B, 384 characters, pure scores, 8,192 context | 10/12 |
| Qwen3 0.6B, 512 characters, RRF | 9/12 |
| Qwen3 0.6B, 256 characters | 9/12 |
| Qwen3 0.6B, 192 characters | 9/12 |
| Qwen3 1.7B, best variant, 512 characters, pure scores | 8/12 |

The 1.7B model has three-target evidence only. Its lane was not run on ten targets or on the 200, so its three-target count is not comparable with the 0.6B full results below.

A search read a plateau on one target and stopped before testing the 384-character document width. Measuring that width raised the best 0.6B three-target result from 9/12 to 10/12, so the plateau was a failed hypothesis: a plateau on a narrow sample had not exhausted the search space.

Two 0.6B RRF variants were carried into the full measurements, one at 384 and one at 512 characters. Both scored all ten targets of the labelled ten and all 200 saved targets.

| Cohort | Labels | CE-only top 50 | Qwen3 0.6B RRF, 384 | Qwen3 0.6B RRF, 512 |
|---|---|---|---|---|
| Labelled ten, combined | 29 | 16/29 | 17/29 | 17/29 |
| Labelled ten, prerequisite only | 23 | 11/23 | 12/23 | 12/23 |
| Disjoint 200, combined | 143 | 90/143 | 86/143 | 89/143 |
| Disjoint 200, prerequisite only | 66 | 37/66 | 36/66 | 34/66 |

On the 200, the 512 RRF variant recovered 89 of the 121 combined labels inside its cross-encoder input and the 384 variant 86 of 121. The input ceiling matters for every ordering: the cross-encoder top 200 holds 121 of the 143 combined labels, so no ordering built on that top 200 can exceed 121. For the prerequisite-only set the input holds 57 of the 66 labels, so the ceiling is 57. On the labelled ten the same input holds 25 of the 29 combined labels and 19 of the 23 prerequisite labels.

The fused ordering won one combined label on the labelled ten and lost between one and four combined labels on the 200. No variant beat the CE-only ordering on the larger cohort. Those leads sit on different denominators and are narrow, so the ranking comparison does not establish a quality advantage for either ordering. The extra stage also cost a ranking run per target, with measured means of 26.66 seconds per target for the 512 variant and 23.30 for the 384 variant on the labelled ten, and 31.70 and 29.54 seconds per target on the 200. The hypothesis that a ranking-only 0.6B stage would clearly beat the cross-encoder ordering failed, and the ranking-only stage did not enter the operating path.

## Which selection the product uses

The applied pipeline retrieves a fused multiview pool of 1,000 candidates per target. One all-field view is combined with the field views name, content and outcomes, and the views fuse by reciprocal rank at offset 60. It reranks that pool with `bge-reranker-v2-m3` at Q8_0 over content-first text bounded at 1,536 characters for the target and 1,536 for each candidate. The strongest 50 of the reranked order form the packet. The ranking-only small model does not run in the operating path.

The diagram shows one target through the four views, the fusion, the pool, the rerank and the packet, with the applied values labelled.

![The target course feeds an all-field view and the name, content and outcomes views, which fuse at rank offset 60 into 1,000 candidates per target. The cross-encoder scores content-first text bounded at 1,536 characters per side, and the strongest 50 candidates form the packet.](/docs/diagrams/inference-candidate-selection.svg)

The pool depth, the fusion offset and the two character bounds are configured settings, and the selection stages read them from configuration. The measurements above selected 1,000 for the depth and 1,536 for each bound. `INFERENCE_SELECTION_POOL_K` holds 1,000, `INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET` holds 60, and `INFERENCE_RERANK_QUERY_MAX_CHARACTERS` and `INFERENCE_RERANK_DOCUMENT_MAX_CHARACTERS` hold 1,536 each. The packet size of 50 is a hard maximum enforced by the selection code as `FINAL_CANDIDATE_MAX`, and a configured `INFERENCE_SELECTION_FINAL_K` other than that value fails instead of selecting another policy.

The final packet was chosen by a blind comparison of judged support on the 100 paired answers, not by official-label recall. [Candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) reports that comparison. On the 200 the CE-only top 50 also led the 512-character ranking-only variant by one combined label, but the recall measurement was diagnostic and did not make the choice.

[Inference](/docs/backend/inference/inference.md#candidate-retrieval-and-rerank) states the operating retrieval and rerank settings, and the [inference pipeline](/docs/backend/inference/inference-pipeline.md) states the code that fuses the views and scores the pairs.

## Interpretation

Interpreted: as stages are added, the binding limit moves. The pool depth costs a small share of labels, while the 50-candidate cut removes far more reachable labels that the pool already holds. A deeper pool would not recover those labels, because they sit below the cut. A better ordering is the lever, and the cross-encoder is the ordering that was measured.

Interpreted: more text is not more recall. The 3,072 comparison doubled the scoring cost and changed which labels were retrieved without changing the count, and the ten-target grid preferred 1,536 over both longer and shorter bounds for the selected layout.

Interpreted: a ranking-only stage over the cross-encoder top 200 adds no ordering advantage that the measurement can establish. Its recall sits below the cross-encoder's on the 200, and the input ceiling bounds any ordering built on that top 200.

Failed hypotheses: a score threshold could bound the packet at the same recall, 3,072 characters would improve top-50 recall, a ranking-only 0.6B stage would beat the cross-encoder ordering, and a short search had exhausted the ranking-only space. Each was tested and each failed.

## Limitations

The label proxy is partial. The 200-target recall describes 66 labels on 31 of 200 targets, so it says nothing about the 169 unlabelled targets. [The inference overview](/docs/experiments/inference/README.md#official-prerequisites-are-a-partial-retrieval-proxy) states the proxy's limits.

The labelled share is small in every cohort. The development set has 64 labelled targets, the 200 has 31, the labelled ten has all ten labelled, and the tuning ten has five. A per-target or per-label difference of one or two labels moves the percentages materially, which is why the report states the counts beside every percentage.

The 200 are not a blind holdout. Their labels were read post-output for the retrieval measurement and the same labels were available to the ranking comparison. No ranking parameter was tuned on them, but a genuinely untouched cohort would be needed to test a policy against them.

The small groups cannot settle a bound. The representative trial and the text bound comparison each used three targets, and the text bound comparison had seven reachable labels. The ten-target grid has 12 reachable labels. Those groups selected a setting inside a measured space, and the 200 measured the selected setting, but neither group supports a claim about other layouts or bounds beyond the values tested.

The development 100 has no reranked recall of its own. The reranked values on that cohort come from the three-target trial, the tuning ten and the labelled ten, each with its own denominator.

One snapshot, one embedding model and one reranker. Every value comes from one catalogue snapshot, BGE-M3 teaching vectors, and one `bge-reranker-v2-m3` Q8_0 artifact on one runtime. Other embedding models, other rerankers and other catalogue states are unmeasured.

Characters are not tokens. The text bounds are character counts, and the observed token counts differ by document. The 2,162-token document at 3,072 characters shows that a character bound does not guarantee a token fit against a fixed physical batch.

Timing is single-run. Each trial scored each input once, and a repeated score would produce different wall seconds. The display state, other GPU use and per-request overhead are not separated. The ten-pair pilot measured 0.103728 seconds per pair against 0.02193 in the 3,000-pair trial, and the recorded evidence does not explain the difference. The pilot's ten requests are too few to serve as a throughput estimate.

The ranking-only comparison is asymmetric. The 1.7B model has three-target evidence only, and the 0.6B model received the full ten-target and 200-target runs. Only one sample per input was scored.

The reranker's memory attribution is incomplete. The committed GPU memory was recorded, but the split between dedicated and shared memory was unavailable and is not inferred.

## Untested follow-ups

Whether an all-field ranking at depth 1,000 recovers as many labels as the fused pool. That measurement would separate the effect of depth from the effect of fusion, and it is absent from this line.

Whether a deeper pool lifts the reranked top 50. The 1,500 measurement raised pool recall by two labels on the development set, but no rerank was run over the deeper pool, so the effect on the 50-candidate packet is untested.

Whether another cross-encoder changes the ordering at 50 on the same saved pools. Only one reranker artifact was qualified, and its ordering is the basis of every reranked value here.

Whether a tokenizer-measured text bound would retain the same top-50 recall at a lower token cost. The bounds are character counts, and the token count of a document varies.
