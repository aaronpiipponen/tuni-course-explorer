# Inference experiments

The inference experiments asked whether one local language model could propose direct prerequisites and equivalence groups for every active course from teaching text alone.

## The question the line asked

The [inference stage](/docs/backend/inference/inference.md) reads the teaching text of a target course and a bounded list of candidate courses, then proposes inferred prerequisites and equivalence groups. The product stores the result apart from the official prerequisite record and draws it in the same [prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) while the **Inferred** toggle is on. A course reached only through an inferred occurrence carries the inferred label. One unit of an answer is a finding, either one required option, one recommended option or one equivalence group.

The scale set the constraint. The catalogue snapshot holds 11,086 courses, of which 4,543 are active, and 58,962 teaching-text chunks. Every active canonical course is a target, and an inactive course is eligible as a candidate source. On one AMD Radeon RX 9070 XT (16 GB model), in a machine that also served other work outside the dedicated measurement windows, the run had to finish inside a month from its start.

The question separated into parts that one end-to-end score would mix. A candidate missing from the packet is invisible to every later stage, so retrieval and ordering decide part of the achievable result before the model runs. A model that emits few findings can show high judged support, the share of its findings that a judge marks supported, so quality is measured over the claims a model chose to emit. A result is usable only when the pipeline can publish it, resume after a stop and recover a failed target. The eight reports cover those parts in turn, and one of them states the reference and the judge they share. The [Experiments overview](/docs/experiments/README.md) states the catalogue, the evidence labels and the hardware.

## The order of the line

The reports are presented in the order the line is read, with the shared method first. That is not the order in which every measurement was taken. Fit and throughput work began before the prompt tuning and continued through the full run.

[Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) states the method every comparison reads. It records the reference model and its settings, the 300 answers, the blind judge and its four verdicts, the correction of the reference and the limits every support number inherits. It is placed first because the later reports link to it instead of restating the rubric.

[Local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md) covers fit, memory and speed. It measured five artifacts against one card, the context each key held, the VRAM accounting and the rate per complete target, and it selected the Qwen3.8-27B IQ3-MIX artifact (MIX below) and its two context keys. The hardware report records a first runtime proof and a prompt-readiness check, and the same measurements continued through the full run.

Candidate retrieval then fixed what the model can see, because the packet bounds what every later stage can propose. [Candidate retrieval, multiview fusion and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md) measured recall of official course prerequisites from an all-field cosine baseline through a fused multiview pool and a cross-encoder. It set the pool depth and the rerank text bound, and its 50-candidate cut became the hard maximum. It also carried a ranking-only small model as an alternative ordering.

The packet itself was then decided on answer quality rather than recall. [Candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) compared two 50-candidate packets on 100 held-out targets. Its answers became part of the corpus for the rest of the line. The comparison used prompt version 6, which corrected two rules after spot checks of 86 answers under version 5.

[Confidence calibration and corrected reference judgments](/docs/experiments/inference/confidence-and-corrected-references.md) asked whether the confidence a model states can gate publication. It placed the 386 findings in confidence bins, tested a target-level routing rule out of sample, corrected the reference and fitted a confidence and flag rule on one local model's held-out output. It ended with no filter.

[Prompt and structured-output tuning](/docs/experiments/inference/prompt-and-structured-output-tuning.md) covers the prompt versions and the per-finding flag schema. It moved from the version 6 baseline to a frozen checkpoint, ran a re-tuning round over 13 variants and selected version 9 with schema version 2. The flag vocabulary and its multi-flag contract were defined and tested there.

[Held-out local model quality](/docs/experiments/inference/held-out-model-quality.md) compares ByteShape and MIX on 150 targets, with Qwen3.6 and gpt-oss on the shared 50, and reports the model and policy that were selected on 2026-09-29 and applied to the full-catalogue run. [Full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md) covers execution. It records the acceptance runs and the defects they exposed, the rehearsal, the retry rules, the mid-run stop and the completed cycle over every active target. It measures coverage and recovery, not quality.

## Headline results

| Report | Question | Result that stands |
|---|---|---|
| Reference answers and judging | What reference and judge do the comparisons share? | 300 validated answers from 314 attempts, 386 findings judged blind, a corrected reference of 319 findings |
| Local model hardware and throughput | Which model, quantization and context fit the card, and how fast? | MIX at 60.5 seconds per complete target, 4,520 of 4,543 targets local, 23 oversize |
| Candidate retrieval, multiview fusion and reranking | Which candidates reach the model? | A 1,000-candidate fused pool, a cross-encoder top 50, 37 of 66 labels at depth 50 on the 200 |
| Candidate packet selection | Does a ranking-only pass improve the answer? | CE-only top 50 selected, 0.63 against 0.56 judged support score, 22 unsupported required against 30 |
| Confidence calibration and corrected reference judgments | Can confidence or flags gate publication? | No confidence cutoff, no flag cutoff, no finding drop and no demotion |
| Prompt and structured-output tuning | Which prompt and schema, and did flags separate harmful claims? | Version 9 with schema version 2, 150 valid of 150, 88 of 168 findings supported |
| Held-out local model quality | Which local model produced the best supported findings? | MIX 111 of 178 supported with 15 unsupported required, selected with no filter |
| Full-catalogue inference run | Can one cycle finish over every active course? | 4,543 published, 2,348 with an expression, 2,195 empty, none failed |

The reference work produced the measure every later comparison reads. The corpus is 300 validated answers from DeepSeek V4.1 Flash under prompt version 6, and the judge was Claude Opus 5.5 at the low variant. It was first sized at 400 answers and reduced to 300 after the first 100 pairs, which were judged enough for the packet decision. Of the 386 findings, 230 were supported, 92 partly, 55 unsupported and nine unclear. The correction retained 319 findings and dropped 67, and 56 required options were demoted to recommended. It also kept 45 equivalence groups that did not contain their target as emitted, so the group-wide support of those 45 was never judged. Every comparison that reads the reference inherits that limit.

The fused pool held 150 of 156 official labels on the development set, and on the disjoint 200 the cross-encoder top 50 held 37 of 66 against 26 for the pool at the same depth. Six labels on the development set sat outside the 1,000 pool, while on the 200, 25 reachable labels sat inside it and below the cut. The reading of those counts places the binding limit at the 50-candidate cut. A deeper pool would not recover the 25, because they sit inside the pool below the cut, so the lever is the ordering.

The per-target comparison did not separate the two packets. The CE-only packet led on required options, where an unsupported required claim is the costliest error the comparison can see, and it needs no ranking-only pass. The comparison used 100 pairs, or 200 answers. Another 100 answers completed the 300-answer corpus after the packet decision. Finding F1 between paired answers was about 0.34. Most of the difference is therefore consistent with single-sample variation.

Observed across the prompt line, the format target was met early and every 50-target run returned zero invalid output. The corrected-reference score across the nine full-50 variants stayed between 0.218 and 0.258. Eight of the nine scored over 49 valid targets, and the v8 control over 47, where the reference held 72 findings rather than 80. The prompt report interprets the remaining gap as a different view of which courses belong, not only a wrong required-or-recommended label. It also reads the flags as describing the model's required-or-recommended boundary rather than weak teaching-text support. Confidence ran the wrong way on held-out output, where all 18 unsupported findings of the fit 100 sat at 0.95, and no candidate filter improved either cohort.

The model choice rested on judged support, not speed. MIX led on all findings and on required findings, and ByteShape led on equivalence groups. Qwen3.6-35B-A3B took 30.2 seconds per complete target, about half the MIX wall clock, and supported 25 of 109 findings. gpt-oss-20b produced no valid answer at all. The corrected-reference score reversed the order of the two strongest models and stayed a diagnostic. The full run then published every eligible target, and the empty share is the largest fact it adds. Of the 4,543 published sets, 2,195 name no option, and the coverage counts cannot separate a correct empty answer from a model omission.

## Corrections and reversals

| Earlier result or position | Correction | Result that stands |
|---|---|---|
| A cosine threshold between 0.50 and 0.65 could bound the candidate list | Every top-50 cap kept the 46.79 percent recall while the uncapped 0.65 cell held a median 3,569 candidates | A rank depth of 1,000 over the fused pool, with no threshold |
| A 3,072-character rerank bound was worth testing | Recall was unchanged at 4/7 while mean pair time rose from 0.02193 to 0.04389 seconds | Content-first 1,536 characters for the target and each candidate |
| A 512 physical batch was the serving geometry | A 747-token input failed with HTTP 500 | One batch and micro-batch value of 2,048 |
| The best 1.7B three-target result was 7/12 | Corrected to 8/12 | The 0.6B lane leads at 10/12 |
| The prerequisite-only cross-encoder top-50 comparator was 57/66 | Corrected to 37/66, since 57/66 is the top-200 value | 37 of 66 at top 50 on the 200 |
| The next step was a 100-target rerank evaluation | The run stopped after one score when a memory sampler drained its input manifest | The 200-target comparison stands, and the 100-target run was not repeated |
| The frozen version 7 checkpoint was the endpoint of the prompt tuning | The tuning budget was unspent and the agreement was not convincing | Tuning continued, and version 9 was selected |
| A confidence cutoff could publish only supported findings | The rate was flat and not monotone, and dropping low-confidence findings kept every unsupported fit-100 finding | No cutoff, no flag cutoff, no drop and no demotion |
| A 196,608-token gpt-oss key provided that context | A request reported a training context of 131,072 and capped the slot | The native 131,072-token key, with 0 valid answers of 50 |
| The catalogue's largest estimated prompt needed a 393,216-token local key | The figure was arithmetic over character counts, above both measured keys | The configuration kept 131,072 and 163,840 tokens |
| The first 20-target acceptance ended at 12 proposals and 0 published sets | Eight complete-empty results re-read as schema version 1 and composition refused them, and the stored read was then bound to the run's schema | The completion published 20 sets, three groups and 17 members |
| The fit check unloaded the local model for every oversize packet | It counted tokens through the loaded key and stayed loaded across the oversize call | One rerank load and one generation load per window |
| The MIX comparison cohort was the shared 50 targets | The other 100 were run later the same night as a distinct trial | MIX covers 150 targets, 150 valid, 178 findings |
| The measurement night named MIX the leading candidate and left the policy open | The model and policy were selected on 2026-09-29 | MIX solo on version 9 and schema version 2, with no filter |

## The configuration the line ended on

| Element | Applied value |
|---|---|
| Local model | Qwen3.8-27B IQ3-MIX, 12.6 GB |
| Prompt, schema and pipeline | Version 9, schema version 2, pipeline version 1 |
| First context key | 131,072 tokens, MTP, `q4_0` KV cache |
| Second context key | 163,840 tokens, no MTP, `q4_0` KV cache |
| Fit rule | Prompt tokens plus 8,192 output tokens and 1,024 headroom inside the key |
| Retrieval pool | 1,000 candidates, field views name, content and outcomes, fusion offset 60 |
| Rerank | `bge-reranker-v2-m3` at Q8_0, content-first 1,536 characters per side |
| Packet | 50 candidates |
| Quality policy | No confidence or flag cutoff, recommendations kept, `INFERENCE_RECOMMENDATION_POLICY` `include` and `INFERENCE_FINDING_FILTER_POLICY` `none` |
| Routing | MIX solo. A packet that fits neither key fails as one capacity failure with the reason `context_exceeded` |
| Oversize route | The run's explicit route sent the whole target to DeepSeek V4.1 Flash, 23 of 4,543 targets, with no truncation |

The full run applied this configuration with no filter and no reroute for uncertain output. In the product a packet that fits neither key fails as one capacity failure with the reason `context_exceeded`, no generation request is made for it, and the product configuration has no fallback route. The full run supplied an explicit oversize route that sent such targets whole to DeepSeek V4.1 Flash, which the 23 oversize targets took. The generation settings measured on the held-out cohort were thinking off, temperature 0, seed 0 and an output cap of 8,192 tokens. [The fit rule](/docs/backend/inference/inference-scheduling.md#the-fit-rule) pairs that cap and the headroom with each key.

## The shared reference and its limits

The category fixes the answer inputs and the judge so that a comparison measures the variant it names. The reference answers are 300 saved complete target results from one external model on 200 fixed targets, and a comparison reads the saved answers instead of asking the model again. The judge sees one finding and the teaching text it refers to, and returns one of four support verdicts. The share of findings a judge marks supported is the judged support of that set, and it is a statement about the supplied text rather than the university's record. The [reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) page states the models, prompts, batching and correction rules.

### Judged support is not exhaustive ground truth

A supported verdict records that the supplied teaching text supports the claim under the rubric. It does not record that the university requires the course. The judge read a bounded rendering with truncated names, outcomes and content, and it never saw the official prerequisite record. No agreement measurement between the judge and a human reader exists, so the judge's own error rate is unknown.

### Only generated claims were judged

Judged support is measured over the findings a model chose to emit. A true prerequisite that a model omitted is invisible, and the reference fills no gap. A model that emits few, safe findings can show higher judged support than a model that emits more, so judged support is comparable only beside its emission counts and category counts. Of the 200 reference targets, 49 emitted no direct option or equivalence group and enter no judged support.

### Official prerequisites are a partial retrieval proxy

Recall counts the official course labels a stage retrieved. A module requirement contributes no label, a target whose only requirement is a module contributes nothing, and official substitutes appear only in the separate combined label set. A high value shows that the pool missed few required courses. It does not show that a packet was useful to the model or that every useful candidate was retrieved.

### One sample per slot

Each target and packet holds one reference answer, with no repeated sample under the same packet. The 100 target pairs produced 257 distinct findings, with 52 in both and 205 in one, which is a finding F1 of about 0.34. That overlap is context for how far two answers can differ. It is not a measurement of sampling noise, because a self-agreement measurement was not run.

## Untested questions

Each question below is untested. None of them has a measurement in this line.

- A second sample per target and per model, which would separate sampling noise from a model, prompt or packet effect. Every saved answer is one sample.
- A human re-read of a sample of the judged findings, which would put a number on the judge's error. No agreement measurement exists.
- A MIX-specific confidence and flag calibration, fitted on one cohort and validated on a distinct one. The rule fitted on ByteShape failed on its own validation and was not transferred.
- A 393,216-token local key. No key above 163,840 tokens was measured for the selected model, and the figure came from arithmetic rather than a tokenizer measurement.
- An all-field ranking at depth 1,000 on the same labels, which would separate the effect of depth from the effect of fusion. A rerank over the 1,500-candidate pool and a second cross-encoder over the same saved pools are also unmeasured.
- A tokenizer-measured distribution of catalogue packet sizes, in place of the conservative character bound. The full run is the only full-catalogue fit sample.
- An unchanged rerun on the finished catalogue and a changed-source recalculation. The finished catalogue has no measured rerun or invalidation behavior.
- A per-target split of prefill, decode, model load and transfer across the full run. The recorded result gives counts and routes, not a time split.
- A re-judged equivalence set, with the 45 target-not-member groups compared only among their members.
