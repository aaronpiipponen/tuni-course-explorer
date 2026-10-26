# Candidate retrieval, multiview fusion and reranking

This report measures how candidate courses reach the prerequisite model, from exact embedding retrieval through multiview fusion and cross-encoder reranking.

**Evidence status:** Comparative.

The [Experiments section](/docs/experiments/README.md) gives the catalogue, the evidence labels and the hardware.

## The question

Inference proposes prerequisites for one target course from a bounded list of candidate courses. The model can name only courses that the list carries, so a course missing from the list is invisible to every later stage, and no model quality can recover it. Retrieval and ranking therefore decide part of the achievable result before the model runs.

That separates two questions that one end-to-end score would mix. Candidate recall asks whether the official prerequisite courses reach the candidate list. Inference quality asks whether the model, given the list, proposes supported prerequisites in the right category. This report covers candidate recall and the selection stages that answer it. [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) covers the second question, and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) covers the packet comparison that chose the final 50.

Label safety fixes the order of the measurement. A target's official prerequisite structure is absent from its candidate query, packet, prompt and model input, so recall can be measured only after the candidate list is fixed. Every recall value here comes from reading official course labels after the selection stage that it measures. [Label safety](/docs/reference/glossary.md#inference) is the governing rule.

Three values bound the answer: the depth of the candidate pool, the number of candidates the model receives, and the cost of scoring pairs on one GPU. The runs below set each of them by measurement rather than by preference.

## The runs in this line

Recall counts the official labels a stage retrieved, over the labels its cohort has. Micro recall pools every label, and macro recall averages the per-target share over the labelled targets.

| Stage | Inputs | Measured | Result |
|---|---|---|---|
| Development baseline | 100 targets, all-field cosine, top 100 | Recall of 156 labels at 10, 20, 50 and 100 | 23.08, 34.62, 46.79 and 58.33 percent |
| Threshold sizing | Same 100 targets, four thresholds and four caps | 16 cells of candidate count, packet bytes and recall | Every top-50 cap 46.79 percent, uncapped 0.65 median 3,569 candidates |
| Multiview pool | Same 100 targets, four views, pools of 1,000 and 1,500 | Recall at each pool depth | 150/156 and 152/156 |
| Pool replay | 100 saved pools of 1,000 | Packet identity, count, bytes and time | 100 packets, 1,000 candidates each, about 77 seconds |
| Runtime qualification | One synthetic request | Endpoint, fit and memory | HTTP 200, 36 ms, 25/25 layers offloaded |
| Scored-input pilot | 10 pairs on 2 targets | Token fit and per-pair latency | 512 batch failed at 747 tokens, 2,048 passed at 0.103728 s/pair |
| Representative trial | 3 targets, 3,000 pairs | Scores, latency and top-50 recall | 3,000 scores, 0.02193 s/pair, 4/7 at 50 |
| Text bound comparison | Same 3 targets at 3,072 characters | Recall and latency | 4/7 unchanged, 0.04389 s/pair |
| Ten-target text grid | 12 variants over 10 targets, one failed fit | Reachable labels at 50, 100 and 200 | Best nine of 12 at 50, content-first 1,536 selected |
| 200-target comparison | 200 targets, 200,000 pairs | Full ranking and post-output labels | 37/66 at 50, 57/66 at 200 |
| Ranking-only Qwen | Labelled ten and the saved 200 | Top-50 recall after fusion | 89/143 for 0.6B d512 against 90/143 for CE-only |

The cohort changes matter. The first four rows measure the 100-target development set. The runtime qualification uses a synthetic request, and the pilot, the trial and the text comparison use sampled or three-target inputs. The ten-target and 200-target rows are separate cohorts with separate denominators, and a value from one is not comparable with a value from another.

No run in this report measures inference quality. The recall values measure retrieval and ordering against official labels. The one quality judgement mentioned here is the blind comparison that chose the final packet, and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) reports it.

## Cohorts and label eligibility

Every cohort holds active canonical courses with a representative version and compatible teaching chunks. Candidate sources are all represented courses, including inactive ones, except the target itself. The pool is the ranked candidate list that a target's query retains before any reranking, and its depth is the number of candidates kept.

| Cohort | Targets | How it was selected | Labelled targets | Prerequisite labels | In the 1,000 pool |
|---|---|---|---|---|---|
| Development 100 | 100 | Deterministic, label-blind declaration filtered to the COMP, MATH and DATA prefixes, prompt-example targets excluded | 64 | 156, none unmeasurable | 156 |
| Tuning ten | 10 | Fixed indices 0, 11, 22, 33, 44, 55, 66, 77, 88 and 99 of the saved pool order | 5 | 12 reachable, one further label outside the pool | 12 |
| Labelled ten | 10 | Fixed, evenly spaced selection from the officially labelled targets of the development 100 | 10 | 23 | 21 |
| Disjoint 200 | 200 | Deterministic, snapshot-bound selection from the whole active represented catalogue, disjoint from the development 100, spanning undotted codes and codes outside the three prefixes | 31 | 66 | 62 |

The development 100 declaration binds the catalogue identity, the embedding configuration, the split seed and the nine prompt-example target identities. A declaration that differs from the current deterministic selection stops before any candidate query runs.

Labels chose the target group of the labelled ten, and they never entered an input. Every other cohort was declared without reading labels, and no scoring input in any cohort carries one.

The disjoint 200 excludes every prompt-example target and every course that appears as a candidate in a prompt example. The exclusion covers both the cohort and its candidate lists, so an example cannot disclose a cohort target's answer or name a cohort course. Its selection spans the catalogue rather than one subject prefix, which is why its label density differs from the development set.

A label is one distinct canonical course identity named by the target's representative version in its official prerequisite options, counted once per target across all options. Only course members count. A module requirement is not converted into courses, so a target whose prerequisite is a module contributes no label for that requirement. The label set therefore measures the course-level part of the official structure.

The combined label set adds the course members of the target's own official substitute options, deduplicated by canonical identity against the prerequisite set. A substitute applies in one direction and to one target, so the member may replace that target without making the two courses interchangeable elsewhere. The combined set is a separate, versioned label set and it never overwrites the prerequisite-only counts. It covers 255 labels on 74 targets of the development 100, 29 labels on the labelled ten, and 143 labels on 61 targets of the disjoint 200.

Official course prerequisites are a partial retrieval proxy. They record the university's formal course-level requirement, not every course that supplies useful entry knowledge or a plausible alternative. A module requirement is dropped, so a target whose only requirement is a module contributes no label, and a target with a module and a course requirement contributes only the course. Recall against this proxy is evidence that the pool misses required courses. It is not evidence that a packet is useful to the model, and a high value does not show that every useful candidate was retrieved.

## Retrieval baseline and threshold sizing

The first measurement used one exact query over the stored teaching vectors. For one target, the query compared every compatible chunk of the target with every compatible chunk of each represented course, kept the best-scoring chunk pair per course, excluded the target itself, and ordered the complete measurable candidate set by cosine score descending, then by canonical course identity. It used only stored vectors. It did not embed text, did not consult the search path, and put no cap on the SQL result. The caller retained the top K candidates with the retrieval score and the matched chunk pair.

Candidates without a completed vector under the current embedding configuration were omitted rather than given a fabricated score. Inactive courses stayed eligible as candidate sources. The packet carried the effective teaching text, the activity, representative, source and embedding identities, the retrieval score and the matched chunk provenance. All packets for a target were assembled before that target's official labels were read.

| Depth | Retrieved labels | Micro recall |
|---|---|---|
| 10 | 36/156 | 23.08% |
| 20 | 54/156 | 34.62% |
| 50 | 73/156 | 46.79% |
| 100 | 91/156 | 58.33% |

The retrieved counts follow from the recorded micro recall over 156 labels. The baseline result is recorded as micro recall only.

A cosine threshold was then sized against the same labels. The sizing pass covered 16 cells: thresholds 0.50, 0.55, 0.60 and 0.65, each uncapped and capped at 50, 100 and 200.

| Cell | Value |
|---|---|
| Thresholds measured | 0.50, 0.55, 0.60, 0.65 |
| Caps measured | uncapped, 50, 100, 200 |
| Cells | 16 |
| Micro recall at every top-50 cap | 46.79% |
| Median candidates, 0.65 uncapped | 3,569 |
| Median packet bytes, 0.65 uncapped | 17.2 MB |

Every top-50 cap returned the same micro recall as the uncapped baseline at 50. Interpreted, the cap did the bounding while the threshold up to 0.65 removed nothing the top 50 would have retrieved. The uncapped 0.65 cell still held a median of 3,569 candidates, far beyond the 50-candidate packet later selected. A score threshold alone therefore could not both keep the measured recall and bound the candidate list.

Those cells were development measurements and no threshold was applied. The selected depth is a rank depth of 1,000 over a fused ordering, described next.

## Multiview fusion and the pool ceiling

The pool query adds field views to the all-field ranking. The target's side of the query can be restricted to one teaching field, name, content or outcomes, while candidate chunks stay unrestricted. One all-field comparison is combined with one comparison per field, and the views are fused by reciprocal rank:

```text
score(c) = sum over views v that surfaced c of 1 / (60 + rank_v(c))
```

The offset is `INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET`, set to 60. The fused score is not a cosine value. Ties are broken by canonical course identity alone, and no label, official structure or prior recall value enters the fusion. A field view that surfaces nothing contributes no synthetic rank, so a target without a compatible chunk in one field still gets a pool from the remaining views. Every nonempty view covers the same candidate universe, so a candidate missing from one view is an absence rather than a differently bounded list.

| Depth | Retrieved labels | Micro recall | Macro recall |
|---|---|---|---|
| 1,000 | 150/156 | 96.15% | 97.01% |
| 1,500 | 152/156 | 97.44% | 97.79% |

The macro column averages over the 64 labelled targets.

The 100-target pool measurement took 34 minutes 43 seconds, against 10 minutes 49 seconds for the all-field baseline measurement.

Six labels were outside the 1,000 pool. Their fused ranks were 1,150, 1,497, 1,659, 2,378, 2,417 and 2,506, so no reranker reading the pool could recover any of them. The two at 1,150 and 1,497 are inside the 1,500 measurement, which is why the deeper pool recovers two more labels.

On the combined label set the same pool recovered 248 of 255 labels. That set is wider than the prerequisite-only set and covers 74 targets, so the two recall values are not interchangeable.

The selected retrieval depth is 1,000 candidates per target, recorded in `INFERENCE_SELECTION_POOL_K`. The selection includes the six out-of-pool labels. It is a ceiling on candidate retrieval for later development and for bulk selection, not a packet policy and not a claim that recall is complete.

No measurement in this line reports the all-field ranking's recall at 1,000. The 58.33 percent at depth 100 and the 96.15 percent at depth 1,000 differ in both depth and fusion, so the share of the gain that comes from each is unmeasured. That separation is listed as an untested follow-up.

## Replay of the saved pool

The saved pool was replayed through one digest-bound loader so that later stages could score the same candidates without querying vectors again. The loader checks the saved pool's raw digest, the baseline digest, the exact development target set, the current catalogue and effective teaching text, the embedding identities, the ordered targets, the configured field views, the fusion offset and a measured pool depth before it yields a packet.

A replay yields one strict target packet per target from the configured prefix of the saved fused order and the current effective text. Each candidate's current representative identity is checked. The replay does not query vectors, call a model or read post-selection labels, ranks or recall. Its audit records the input identities, the selected depth, and each target's candidate count, canonical packet digest and UTF-8 byte size. It writes no packet text and no candidate identities.

The measured replay produced 100 packets of 1,000 candidates each in about 77 seconds for the development set. It is an identity check on the pool, not a recall measurement.

The development replay is the sole source of candidate packets for the development scoring runs in this report. The 200-target run follows the same pattern from its own saved pool. The pool is measured once, saved and rendered into packets, so no scoring run queries the vectors again.

Saved development rankings are not a shortcut for bulk selection. Bulk selection checks the current catalogue and embedding identities, and a replay against changed identities fails rather than reusing stale candidates.

## Reranker runtime and input fit

The reranker is `bge-reranker-v2-m3` at Q8_0, served by the same pinned llama.cpp revision as the language model on its own loopback port. It was qualified with one synthetic, label-free request before any course text was scored.

| Measure | Value |
|---|---|
| Serving context | 8,192 tokens |
| Physical batch and micro-batch | 2,048 and 2,048 |
| GPU layers offloaded | 25/25 |
| Artifact quantization | Q8_0 |
| Request result | HTTP 200, both indices scored, calculus above literature |
| Elapsed time | 36 ms |
| Committed GPU memory, prelaunch to loaded to request | 0.0 MB, 503.8 MB, 521.0 MB |
| Free system RAM, before to after load | 19.92 GB to 18.94 GB |
| Listener after stop | absent |

The per-adapter split between dedicated and shared GPU memory was unavailable for this measurement and was not inferred. The committed value covers every allocation on the GPU, so it is an upper bound for the reranker.

The scored-input pilot then sent ten pairs built from the saved pool: two targets and five saved-pool positions. Each pair carried the course code and the effective teaching name, outcomes and content, capped at 1,536 characters per side. The first attempt ran with a physical batch and micro-batch of 512. An input of 747 tokens failed with an HTTP 500 unsplittable-task response and produced no score. That is a fit failure of the serving geometry, not a model failure.

The correction set one validated batch value of 2,048 for both `--batch-size` and `--ubatch-size`, kept the 8,192 context and the same text bounds, and changed nothing else. The retest scored a warmup and ten single-document requests with finite, indexed and untruncated scores, including the input that had failed. The mean was 0.103728 seconds per pair, which projects to about 10,372.75 seconds for 100,000 pairs. The projection was recorded as provisional. The failed input and its evidence stayed separate from the retest.

The pilot's mean per-pair latency is about 4.7 times the mean of the later 3,000-pair trial over three complete 1,000-candidate pools, 0.02193 seconds. Both values are recorded, and the recorded evidence does not explain the difference. The pilot's ten requests are a small sample, so its projection is not used here as a throughput estimate.

## Representative rerank trial

The next trial scored three complete 1,000-candidate pools. The three targets were chosen deterministically from the saved pool order: the lexical first, the lower middle, and the largest packet outside those two. They were scored with the same artifact, context and 2,048 batch.

| Measure | Value |
|---|---|
| Pairs scored | 3,000 of 3,000 |
| Maximum observed tokens | 963 |
| Per-target seconds | 27.303, 11.617, 26.871 |
| Mean seconds per pair | 0.02193 |
| Projection for 100,000 pairs | about 2,193 seconds |
| Reachable labels recovered at top 50 | 4 of 7 |
| Micro recall at top 50 | 0.5714 |
| Macro recall at top 50 | 0.5833 |

One of the three targets had no official course labels and contributed no recall. The three reachable labels outside the top 50 sat at rerank ranks 89, 178 and 64. Every score was finite and no truncation was reported. The listener was absent after the run.

The trial established token fit, complete scoring and throughput. It could not select a depth, a text bound or a packet policy, because seven labels on three targets cannot separate candidates. Interpreted, four of seven at 50 was too weak a signal to justify the planned 100-target evaluation, which is why the longer-text comparison followed.

## Text bound comparison

The same three targets were then scored again at 3,072 characters per side. The pool, model, runtime, context, batch and offload were unchanged. Only the two character bounds differed, and the original inputs and scores stayed byte-identical.

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
| Projection for 100,000 pairs | about 2,193 seconds | about 4,389 seconds |
| Committed GPU memory, loaded to request | not reported | 576.7 MB to 2,562.7 MB |
| Free system RAM, before to after request | not reported | 16.82 GB to 16.29 GB |

The longer bound changed which labels were retrieved without changing how many. One target kept two of three reachable labels and its lone miss moved from rerank rank 89 to 160. Another kept two of four and swapped which two: a label at pool rank 49 that had been retrieved moved to rerank rank 113, a label at pool rank 231 that had been missed moved to rank 64, and a label at pool rank 305 stayed missed while moving from rank 178 to 135.

Doubling the text raised the mean pair time from 0.02193 to 0.04389 seconds and the p95 from 0.02981 to 0.07266 seconds, and bought no measured top-50 recall on these three targets. Three targets still cannot choose a bound, so the comparison did not settle one. The proposed next step was a ten-target cross-encoder tuning pass followed by a 100-target evaluation. The tuning ran, the 100-target evaluation stopped at one score, and the 200-target measurement replaced it.

## Ten-target text selection

The cross-encoder ordering was tuned on the tuning ten with only two dimensions free: the teaching-text layout and the character bounds of the target and candidate text. Twelve variants were built. Eleven were scored once each at 10,000 pairs, and the twelfth failed fit before scoring. The pool, reranker, runtime, context and batch did not change.

| Variant (layout, target/candidate) | Reachable at 50 | At 100 | At 200 | Mean seconds per pair | Selected packet bytes, min/max |
|---|---|---|---|---|---|
| content-first 1,536/1,536 | 9/12 | 10 | 11 | 0.02493 | 125,159 / 282,832 |
| content-first 2,048/2,048 | 8/12 | 10 | 11 | 0.03106 | 120,422 / 260,227 |
| content-first 1,024/1,024 | 8/12 | 8 | 10 | 0.01888 | 128,432 / 284,065 |
| content-first 1,024/1,536 | 8/12 | 10 | 10 | 0.02229 | 126,975 / 298,436 |
| content-first 1,536/1,024 | 7/12 | 8 | 10 | 0.02322 | 129,529 / 283,928 |
| content-first 3,072/3,072 | failed fit at a 2,162-token document against a 2,048 batch | not scored | not scored | not scored | not scored |
| outcomes-first 1,536/1,536 | 6/12 | 8 | 10 | 0.02396 | 114,492 / 276,792 |
| outcomes-first 2,048/2,048 | 8/12 | 9 | 9 | 0.03008 | 122,746 / 276,819 |
| outcomes-first 3,072/3,072 | 6/12 | 10 | 11 | 0.04112 | 124,001 / 247,238 |
| balanced 1,536/1,536 | 6/12 | 7 | 10 | 0.02436 | 145,102 / 249,901 |
| balanced 2,048/2,048 | 6/12 | 6 | 11 | 0.03064 | 113,650 / 251,671 |
| balanced 3,072/3,072 | 8/12 | 10 | 11 | 0.04001 | 124,001 / 236,547 |

The denominator of 12 is the reachable labels in this ten-target group. One further label lay outside the 1,000 pool and no rerank could retrieve it.

The selected setting is content-first at 1,536 characters for the target and 1,536 for each candidate. It recovered the most reachable labels at top 50, matched the highest count at the 100 and 200 diagnostic depths, and stayed well below the symmetric 2,048 and 3,072 variants in mean pair time. The 3,072 content-first variant failed fit because a 2,162-token document exceeded the 2,048 physical batch. The settings were applied to the tracked input keys: `INFERENCE_RERANK_TEXT_LAYOUT` is `content-first`, and `INFERENCE_RERANK_QUERY_MAX_CHARACTERS` and `INFERENCE_RERANK_DOCUMENT_MAX_CHARACTERS` are both 1,536.

The 50, 100 and 200 columns show where the remaining reachable labels sit. Several variants move one or two labels between 50 and 100 or 200, which places the loss at the 50-candidate cut rather than at the 1,000 pool. The columns are diagnostics only and do not change the hard maximum of 50.

## The 200-target comparison

The comparison ran on the disjoint 200. Each target's pool was measured once, checkpointed per target, and published as one pool record. The saved pool was then rendered to 200 inputs at content-first 1,536/1,536 and scored one target per bounded invocation. Every invocation started its own listener, verified the artifact, loopback binding, offload, context and batch, ran one synthetic warmup, scored the 1,000 pairs, and stopped the listener. All 200 targets and 200,000 pairs produced finite scores and deterministic ranks, and the complete evidence was audited before any official label was read. The scoring took 4,938.9 seconds in total, a mean of 0.0247 seconds and a 95th percentile of 0.0313 seconds per pair.

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

The depth axis of the chart is logarithmic. The reranked ordering leads the pool at every depth below the ceiling. At the shallow depths that matter for a 50-candidate packet the difference is large: the reranked top 50 recovers 37 labels, against 26 for the pool at the same depth, and it still leads the pool's 33 labels at 100 by four. At 200 the pool recovers 42 and the reranked ordering 57.

Among the 62 labels inside the pool, reranker recall is 37 of 62 at top 50, 49 of 62 at top 100 and 57 of 62 at top 200. The missing 29 labels at top 50 divide into the four that are outside the pool and 25 that are inside it but ranked below 50. At top 200 the five reachable misses are all inside the pool.

The run also produced a combined label measurement. The cross-encoder top 200 holds 121 of the 143 combined labels and 121 of the 130 combined labels that are inside the pool, so the combined label set loses nine reachable labels between the pool and the cross-encoder top 200.

The 200 are a comparison cohort, not an untouched ranking-policy holdout. Their labels were read after the run for this retrieval measurement, and the same labels were then available to the ranking comparison. No configuration was tuned on them, but no stage in this line is a blind test of ranking policy against them.

### The 100-target evaluation that stopped

The 100-target rerank evaluation that had been planned next was built and started, then produced exactly one score. The scoring loop read its input manifest on standard input, and the memory sampler that ran after the first score inherited the same descriptor. The sampler consumed the remaining manifest lines, the loop ended after one target, and the run stopped without any model error.

The defect was reproduced with a synthetic three-entry loop before it was corrected. The sampler runs with its standard input redirected from the null device before its output redirect, and the 200-target procedure scores one target per invocation and proves the same loop on three synthetic entries before any course score. The single score and its run evidence remain recorded. The run was not repeated, and the 200-target comparison is the result that stands.

## Ranking-only Qwen comparison

The last comparison asked whether a small ranking-only model adds enough ordering information to justify scoring every target. Both candidates are Qwen3 Q8_0 artifacts, 0.6B and 1.7B, served by the same pinned llama.cpp runtime on loopback with thinking off, temperature 0 and seed 0. The model scored exactly the saved cross-encoder top 200 as ten batches of 20 candidates. Each batch request returned one score row per candidate, and only the resulting ranks entered the fusion:

```text
fused(c) = 1 / (60 + rank_qwen(c)) + 1 / (60 + rank_ce(c))
```

The offset is 60. The CE term uses the candidate's position in the cross-encoder top 200, which is the same list the model saw. Only ranks enter, so a wide score spread and a narrow one carry the same weight. The base geometry was 16,384 context, 1,024 batch and 1,024 output tokens. Measured variants also changed context between 8,192 and 32,768, output between the measured 512 and 1,024 budgets, candidate document width between 192 and 1,024 characters, three layouts, and prompt wordings v7 to v12. Every variant was scores-only and every input was teaching-only and label-free.

The first round on one target was read as a plateau. That reading was wrong: the 384-character document width had not been tested, and testing it produced a better three-target result. The work then ran five adaptive rounds and 118 distinct variants.

| Variant | Combined labels on the three-target group |
|---|---|
| Qwen3 0.6B, 384 characters, RRF | 10/12 |
| Qwen3 0.6B, 384 characters, pure scores, 8,192 context | 10/12 |
| Qwen3 0.6B, 512 characters, RRF | 9/12 |
| Qwen3 0.6B, 256 characters | 9/12 |
| Qwen3 0.6B, 192 characters | 9/12 |
| Qwen3 1.7B, best variant, 512 characters, pure scores | 8/12 |

The 1.7B model has three-target evidence only. The losing lane was not run on ten targets or on the 200, so its 8/12 is not comparable with the 0.6B full results below.

Two 0.6B RRF variants were carried into the full measurements, one at 384 and one at 512 characters. Both scored all ten targets of the labelled ten and all 200 saved targets.

| Cohort | Labels | CE-only top 50 | Qwen3 0.6B RRF, 384 | Qwen3 0.6B RRF, 512 |
|---|---|---|---|---|
| Labelled ten, combined | 29 | 16/29 | 17/29 | 17/29 |
| Labelled ten, prerequisite only | 23 | 11/23 | 12/23 | 12/23 |
| Disjoint 200, combined | 143 | 90/143 | 86/143 | 89/143 |
| Disjoint 200, prerequisite only | 66 | 37/66 | 36/66 | 34/66 |

On the 200, the 512 RRF variant recovered 89 of the 121 combined labels inside its cross-encoder input and the 384 variant 86 of 121. The CE-only top 50 recovered 90 of 143 overall. The input ceiling matters for all three: the cross-encoder top 200 holds 121 of the 143 combined labels, so no ordering built on that top 200 can exceed 121. For the prerequisite-only set the input holds 57 of the 66 labels, so the ceiling is 57. On the labelled ten the same input holds 25 of the 29 combined labels and 19 of the 23 prerequisite labels.

The fused ordering won one combined label on the labelled ten and lost between one and four combined labels on the 200. No variant beat the CE-only ordering on the larger cohort. Those leads sit on different denominators and are one to four labels wide, so the ranking comparison does not establish a quality advantage for either ordering.

Measured mean times were 26.66 seconds per target for the 512 variant and 23.30 for the 384 variant on the labelled ten, and 31.70 and 29.54 seconds per target on the 200. The ten-target means projected 200-target runs of 1.48 hours and 1.29 hours, which is why both ran as one complete pass.

Three corrections belong to this comparison. First, the premature plateau reading was replaced by five rounds and 118 variants after the untested 384 width proved better. Second, the best 1.7B three-target figure was reported as 7/12 and corrected to 8/12, which left the 0.6B lead intact. Third, the prerequisite-only cross-encoder comparator at top 50 was reported as 57/66 and corrected to 37/66, since 57/66 is the top-200 value. The corrected 37/66 is the value in the tables above.

The measurement closed the ranking comparison, and no final packet policy was selected with it. The 384 evidence was kept but retired from later comparison. The 512 variant was carried forward as the ranking-only alternative to the cross-encoder packet.

## Corrections and reversals

| Earlier result or position | Correction or reversal | Result that stands |
|---|---|---|
| A cosine threshold between 0.50 and 0.65 could bound the candidate list | Every top-50 cap kept the 46.79 percent recall while the uncapped 0.65 cell held a median 3,569 candidates | A rank depth of 1,000 over the fused pool was selected, and no threshold was applied |
| The next step was a ten-target tuning pass, then a 100-target rerank evaluation | The 100-target run stopped after one score when the memory sampler drained the manifest | The 200-target comparison stands, and the 100-target run was not repeated |
| A 1,536-character bound was provisional and 3,072 was worth testing | Recall was unchanged at 4/7 while mean pair time rose from 0.02193 to 0.04389 seconds | The ten-target grid selected content-first 1,536/1,536, and those values are applied |
| A 512 physical batch was the serving geometry | A 747-token input failed with HTTP 500 | One batch and micro-batch value of 2,048 is applied |
| One adaptive round showed a plateau | The untested 384-character width produced a better three-target result | Five rounds and 118 variants, with the 384 and 512 variants retained |
| The best 1.7B three-target result was 7/12 | Corrected to 8/12 | The 0.6B lane still leads at 10/12 |
| The prerequisite-only CE top-50 comparator was 57/66 | Corrected to 37/66, since 57/66 is the top-200 value | CE-only top 50 is 37/66 on the 200 |
| Both 384 and 512 RRF variants were candidates for later work | The 384 evidence was kept and retired from later comparison | The 512 variant was carried forward, and CE-only top 50 was selected after the blind judged comparison |

## Which selection the product uses

The applied pipeline retrieves a fused multiview pool of 1,000 candidates per target. One all-field view is combined with the field views name, content and outcomes, and the views fuse by reciprocal rank at offset 60. It reranks that pool with `bge-reranker-v2-m3` at Q8_0 over content-first text bounded at 1,536 characters for the target and 1,536 for each candidate. The strongest 50 of the reranked order form the packet. The ranking-only small model does not run in the operating path.

The diagram shows one target through the four views, the fusion, the pool, the rerank and the packet, with the applied values labelled.

![The target course feeds an all-field view and the name, content and outcomes views, which fuse at rank offset 60 into 1,000 candidates per target. The cross-encoder scores content-first text bounded at 1,536 characters per side, and the strongest 50 candidates form the packet.](/docs/diagrams/inference-candidate-selection.svg)

The pool depth, the fusion offset and the two character bounds are configured settings, and the selection stages read them from configuration. The measurements above selected 1,000 for the depth and 1,536 for each bound. `INFERENCE_SELECTION_POOL_K` holds 1,000, `INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET` holds 60, and `INFERENCE_RERANK_QUERY_MAX_CHARACTERS` and `INFERENCE_RERANK_DOCUMENT_MAX_CHARACTERS` hold 1,536 each. The packet size of 50 is a hard maximum enforced by the selection code as `FINAL_CANDIDATE_MAX`, and a configured `INFERENCE_SELECTION_FINAL_K` other than that value fails instead of selecting another policy.

The final packet was chosen by a blind comparison of judged support on the 100 paired answers, not by official-label recall. [Candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) reports that comparison. On the 200 the CE-only top 50 also led the stronger ranking-only variant by one combined label, but the recall measurement was diagnostic and did not make the choice.

[Inference](/docs/backend/inference/inference.md#candidate-retrieval-and-rerank) states the operating retrieval and rerank settings, and the [inference pipeline](/docs/backend/inference/inference-pipeline.md) states the code that fuses the views and scores the pairs.

## Interpretation

Observed: the all-field baseline recovered 91 of 156 labels at depth 100. The fused pool recovered 150 at 1,000 on the same labels. On the disjoint 200 the reranker raised recall from 26 to 37 labels at a depth of 50 and from 42 to 57 at 200, and both orderings met at 62 at 1,000. The ten-target grid placed the best variant at nine of 12 reachable labels at 50 and 11 at 200. The ranking-only variants sat within one to four labels of the cross-encoder ordering on both full cohorts.

Interpreted: as stages are added, the binding limit moves. The pool ceiling removes six labels on the development set and four on the 200, which is a small share. The 50-candidate cut removes far more: 25 reachable labels on the 200 at top 50, against five at top 200. A deeper pool would not recover those labels, because they are already inside the pool and below the cut. A better ordering is the lever, and the cross-encoder is the ordering that was measured.

Interpreted: more text is not more recall. The 3,072 comparison doubled the scoring cost and changed which labels were retrieved without changing the count, and the ten-target grid preferred 1,536 over both longer and shorter bounds for the selected layout.

Failed hypotheses:

- A score threshold could bound the packet at unchanged recall.
- 3,072 characters would improve top-50 recall.
- A ranking-only 0.6B stage would clearly beat the cross-encoder ordering.
- Three targets with seven labels could settle the text bound.
- One adaptive round had exhausted the ranking-only space.

Untested: whether the fused pool's recall at 1,000 comes from depth or from fusion, whether a deeper selected pool would raise recall at 50, and whether a different cross-encoder would order the same pool better.

## Limitations

The label proxy is partial. Module requirements contribute no labels, official substitutes are counted only in the separate combined set, and a target with no course prerequisite contributes nothing. The 200-target recall describes 66 labels on 31 of 200 targets, so it says nothing about the 169 unlabelled targets.

The labelled share is small in every cohort. The development set has 64 labelled targets, the 200 has 31, the labelled ten has all ten labelled, and the tuning ten has five. A per-target or per-label difference of one or two labels moves the percentages materially, which is why the report keeps the counts beside every percentage.

The 200 are not a blind holdout. Their labels were read post-output for the retrieval measurement and remained available for the ranking comparison. No ranking parameter was tuned on them, but a genuinely untouched cohort would be needed to test a policy against them.

The small groups cannot settle a bound. The representative trial and the text bound comparison each used three targets, and the text bound comparison had seven reachable labels. The ten-target grid has 12 reachable labels. Those groups selected a setting inside a measured space, and the 200 then measured the selected setting, but neither group supports a claim about other layouts or bounds beyond the values tested.

The development 100 has no reranked recall of its own. The 100-target evaluation stopped after one score, so the reranked values on that cohort come from the three-target trial, the tuning ten and the labelled ten, each with its own denominator.

One snapshot, one embedding model and one reranker. Every value comes from one catalogue snapshot, BGE-M3 teaching vectors, and one `bge-reranker-v2-m3` Q8_0 artifact on one runtime. Other embedding models, other rerankers and other catalogue states are unmeasured.

Characters are not tokens. The text bounds are character counts, and the observed token counts differ by document. The 2,162-token document at 3,072 characters shows that a character bound does not guarantee a token fit against a fixed physical batch.

Timing is single-run. Each trial scored each input once, and a repeated score would produce different wall seconds. The display state, other GPU use and per-request overhead are not separated. The pilot's 0.103728 seconds per pair and the trial's 0.02193 are both recorded, and the difference is unexplained.

The ranking-only comparison is asymmetric. The 1.7B model has three-target evidence only, and the 0.6B model received the full ten-target and 200-target runs. The 200 comparison also reused labels that were already known, and only one sample per input was scored.

Macro recall was not recorded for the development baseline, so the baseline table shows micro recall only.

The reranker's memory attribution is incomplete. The committed GPU memory was recorded, but the split between dedicated and shared memory was unavailable and is not inferred.

## Setup details

| Parameter | Value |
|---|---|
| Embedding model | BGE-M3 chunks under the captured embedding configuration |
| Candidate query | Exact best-chunk cosine over stored vectors, no ANN and no SQL cap |
| Development targets | 100, deterministic and label-blind, COMP, MATH and DATA prefixes |
| Disjoint targets | 200, deterministic, snapshot-bound and disjoint from the development 100 |
| Pool depth | 1,000 (`INFERENCE_SELECTION_POOL_K`) |
| Field views | name, content, outcomes (`INFERENCE_MULTIVIEW_EVALUATION_FIELDS`) |
| Fusion | `1 / (60 + rank)` summed over the views that surfaced the candidate |
| Fusion offset | 60 (`INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET`) |
| Reranker | `bge-reranker-v2-m3`, Q8_0, pinned llama.cpp revision |
| Rerank context | 8,192 tokens |
| Rerank batch and micro-batch | 2,048 and 2,048 |
| Rerank text | content-first, 1,536 characters for the target and 1,536 for the candidate |
| Packet maximum | 50 (`INFERENCE_SELECTION_FINAL_K`) |
| Ranking-only models | Qwen3 0.6B and Qwen3 1.7B, Q8_0 |
| Ranking input | cross-encoder top 200, ten batches of 20 |
| Ranking base geometry | 16,384 context, 1,024 batch, 1,024 output tokens |
| Ranking generation | thinking off, temperature 0, seed 0 |
| Ranking fusion | `1 / (60 + rank_qwen) + 1 / (60 + rank_ce)` |
| Hardware | AMD Radeon RX 9070 XT (16 GB model), ROCm 7.2.1, 33.4 GB usable RAM |

A label is reachable when its fused rank is at most the pool depth under measurement.

## Untested follow-ups

Whether an all-field ranking at depth 1,000 recovers as many labels as the fused pool. That measurement would separate the effect of depth from the effect of fusion, and it is absent from this line.

Whether a deeper pool lifts the reranked top 50. The 1,500 measurement raised pool recall by two labels on the development set, but no rerank was run over the deeper pool, so the effect on the 50-candidate packet is untested.

Whether another cross-encoder changes the ordering at 50 on the same saved pools. Only one reranker artifact was qualified, and its ordering is the basis of every reranked value here.
