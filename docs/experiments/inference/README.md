# Inference experiments

The inference experiments ask whether one local language model can propose direct prerequisites and equivalence groups for every active course from teaching text alone.

## The question

The [inference stage](/docs/backend/inference/inference.md) reads the teaching text of a target course and a bounded list of candidate courses and proposes inferred prerequisites and equivalence groups. The product stores the result apart from the official prerequisite record and draws it in the same [prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) while the **Inferred** toggle is on. One unit of an answer is a [finding](/docs/reference/glossary.md#inference), either one required option, one recommended option or one equivalence group.

The scale set the constraint. Every active canonical course is a target, and an inactive course is eligible as a candidate source. The [catalogue](/docs/experiments/README.md#the-catalogue-the-experiments-read) states the snapshot and its counts, and the [hardware](/docs/experiments/README.md#the-hardware) section states the machine. The run had to finish inside a month from its start.

The question separated into parts that one end-to-end score would mix. A candidate missing from the packet is invisible to every downstream stage, so retrieval and ordering decide part of the achievable result before the model runs. A model that emits few findings can show a high supported share, so quality is measured over the claims a model chose to emit. A result is usable only when the pipeline can publish it, resume after a stop and recover a failed target. The [Experiments section](/docs/experiments/README.md#inference) places the category.

## Shared method and cohorts

The category fixes its answer inputs and its judge so that a comparison measures the variant it names. The reference is 300 validated complete-target answers from DeepSeek V4.1 Flash under prompt version 6 on 200 fixed active targets. One blind judge, Claude Opus 5.5 at the low variant, returns one of four support verdicts for each finding, and a corrected reference of 319 findings is derived from those verdicts. [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) owns the corpus, the rubric, the correction rules and the limits every support number inherits.

Two quality numbers recur and are not interchangeable. The packet comparison reports a judged support score over the findings that only one of the two packets emitted, weighting each judged finding as 1 for supported, 0.5 for partly and 0 for unsupported. Unclear verdicts are excluded from that score's denominator. The prompt and model comparisons report a supported share, the number of supported findings divided by the findings a model emitted. A score and a share answer different questions, and neither is exhaustive ground truth.

The quality comparisons share a fixed set of 200 active targets and 50-candidate packets. The configuration the line selected holds a 1,000-candidate fused multiview pool at rank offset 60, reranks content-first text bounded at 1,536 characters per side, and forms the packet from the strongest 50. The 200 split before any output into 50 tuning targets and a 150-target held-out complement. Within the complement, the shared comparison cohort of 50 size quantiles is also the validation set for a confidence rule, and the other 100 are the rule-fit set. [Candidate retrieval and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md) and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) own the pool and packet construction, and [held-out local model quality](/docs/experiments/inference/held-out-model-quality.md) owns the cohort split.

The reports are not combined into one score, because their cohorts, denominators and metrics differ.

## Reading order

The order follows the dependency between the questions, not the order they were measured in. [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) states the corpus, judge and corrected reference every comparison reads. [Local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md) states which artifact and context fitted the card and the rate per complete target. [Candidate retrieval and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md) follows candidates from the exact vector query through the fused pool and the cross-encoder to the 50-candidate packet, and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) compares the two packets on answer quality. [Prompt and flag schema tuning](/docs/experiments/inference/prompt-and-flag-schema-tuning.md) states the prompt contract and the flag schema, [prompt sweeps and the v9 selection](/docs/experiments/inference/prompt-sweeps-and-v9-selection.md) reports the sweep that selected version 9, and [confidence and flag calibration](/docs/experiments/inference/confidence-and-flag-calibration.md) tests whether confidence or flags could gate publication. [Held-out local model quality](/docs/experiments/inference/held-out-model-quality.md) compares the local models and states the selected model and policy, and [full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md) closes the line with the cycle over every active target.

## Headline results

| Report | Question | Standing result | Run dates |
|---|---|---|---|
| [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) | What reference and judge do the comparisons share? | 300 validated answers, 386 findings judged blind, a corrected reference of 319 findings | 26 September 2026 |
| [Local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md) | Which artifact and context fit the card, and how fast? | MIX fitted all 150 held-out packets at its first key and ran at about 60.5 seconds per complete target | 19, 28 and 29 September and 14 October 2026 |
| [Candidate retrieval and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md) | Which candidates reach the model? | A 1,000-candidate fused pool and a cross-encoder top 50, with 37 of 66 official labels at depth 50 on the 200 | 17 to 25 September 2026 |
| [Candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) | Does a ranking-only pass improve the answer? | CE-only top 50 selected on its required-option row, with a judged support score of 0.63 against 0.56 | 26 to 27 September 2026 |
| [Prompt and flag schema tuning](/docs/experiments/inference/prompt-and-flag-schema-tuning.md) | Which prompt contract and flag schema did the model follow? | Every 50-target run returned zero invalid output, and the flags marked the required-or-recommended boundary | 27 September 2026 |
| [Prompt sweeps and the v9 selection](/docs/experiments/inference/prompt-sweeps-and-v9-selection.md) | Which prompt won the sweep? | Prompt version 9 selected, with 35 of 58 findings supported and one unsupported finding | 27 and 28 September 2026 |
| [Confidence and flag calibration](/docs/experiments/inference/confidence-and-flag-calibration.md) | Can confidence or flags gate publication? | No confidence cutoff, no flag cutoff, no finding drop and no demotion | 26, 28 and 29 September 2026 |
| [Held-out local model quality](/docs/experiments/inference/held-out-model-quality.md) | Which local model produced the best supported findings? | MIX supported 111 of 178 findings (supported share 0.62), with 15 unsupported required findings, and was selected with no filter | 28 and 29 September 2026 |
| [Full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md) | Can one cycle finish over every active course? | 4,543 published, 2,348 with a prerequisite expression, 2,195 complete empty, none failed | 30 September to 25 October 2026 |

## What the reports show together

### The candidate cut, not the pool, bounds recall

Retrieval reaches almost every official course label, and the 50-candidate cut loses more than the pool does. On the 200-target cohort the fused pool held 62 of 66 labels at depth 1,000 and the cross-encoder top 50 held 37. Twenty-five of the 29 labels missing at top 50 sat inside the pool below the cut and four sat outside it, so a deeper pool would not recover the 25. The packet size is where the loss concentrates, and the cross-encoder ordering is the lever that was measured.

### The packet choice rested on the costliest error

The two packets did not separate on the per-target score. Of the 62 targets whose two answers differed, 27 scored the CE-only answer higher, 26 the RRF answer and nine equal, and the 95 percent interval spanned zero. The CE-only packet was selected because an unsupported required option is the costliest error the comparison can see. It left fewer of them, 22 of 47 against 30 of 50, and it needs no ranking-only scoring pass. The selection therefore rests on the required-option row and the cost of the extra stage, not on a margin between the whole answers.

### The empty share is unresolved

The full run published 2,195 complete empty sets beside 2,348 sets with an expression, and the empty share is the largest fact it adds. The coverage counts measure stored results, so they cannot separate a correct no-prerequisite answer from a model omission, and no check of those sets against the official record or a human reading exists.

## Limitations

These limits apply to every judged support number and every official-label recall value in the folder. Each report states its own cohort limits.

- One sample per target and model. No model answered the same target twice, so sampling noise is unmeasured. The paired reference answers overlapped at about 0.34 finding F1, which is context for how far two answers can differ rather than a variance estimate.
- Only emitted findings were judged. Every support number is computed over the findings a model emitted, so a true prerequisite that a model omitted is invisible and a model that emits fewer safe findings can show a higher share. The 49 reference targets that emitted nothing enter no judged support, and 43 of ByteShape's 150 held-out targets emitted none.
- One judge and one rubric. Claude Opus 5.5 at the low variant judged every stage, and no human re-read or repeat judgment exists, so the judge's error rate and stability are unknown.
- Truncated text and no official record. The judge saw a bounded rendering, with each course name cut at 135 characters and outcomes and content each cut at 700 characters for the target and 450 for each named course, and it could not consult the rest of the catalogue or the official prerequisite record. A supported verdict therefore records what the supplied text supports, not that the university requires the course.
- An incomplete reference. The corrected reference holds 319 findings from one answer per slot, and it carries more findings than any measured model emitted, so corrected-reference F1 is a diagnostic rather than an accuracy score. It also keeps 45 equivalence groups whose group-wide support was never judged, because their members were compared with the target instead of with one another.
- One artifact and one runtime per measurement. Every quality and rate value belongs to the exact quantized artifact, settings and runtime build on one AMD Radeon RX 9070 XT with ROCm 7.2.1. A different quantization, KV-cache type, runtime revision, packet mix or prompt can change validity, quality and rates, and no result describes a model family in general.

### Official prerequisites are a partial retrieval proxy

Recall in the folder is measured against official course labels. A label is one distinct canonical course identity named by a target's representative version in its official prerequisite options, counted once per target. Only course members count, so a module requirement is not converted into courses and a target whose prerequisite is a module contributes no label for that requirement. Official substitutes are counted only in a separate combined label set and never in the prerequisite-only counts, and a target with no course prerequisite contributes nothing.

A recall value therefore describes the course-level part of the official structure. It says nothing about a module-only requirement, and it says nothing about the targets that carry no course label.

## Open questions

Each question below is untested. None has a measurement in this line, and the reports carry further untested questions of their own.

- A second sample per target and model would separate sampling noise from a model, prompt or packet effect. Every saved answer is one sample.
- A human re-read of a sample of the judged findings would put a number on the judge's error. No agreement measurement exists.
- A MIX-specific confidence and flag calibration, fitted on one cohort and validated on a distinct one, would test whether any filter helps the selected model. The ByteShape rule failed on its own validation and was not transferred.
- A prompt comparison on targets used neither for tuning nor for the cutoff fit would test whether the version 9 advantage holds outside the 50.
- A validity check that requires every named course to appear in the supplied packet, applied to local answers, would measure how often a schema-valid answer cites an unsupplied course. One Qwen3.6 finding did.
- A re-judged equivalence set, with the 45 target-not-member groups compared only among their members, would show whether their verdicts and the corrected reference change.
- An all-field ranking at depth 1,000 on the same labels, and a rerank over the 1,500-candidate pool, would separate the effect of depth from the effect of fusion and test whether a deeper pool lifts the top 50.
- A tokenizer-measured distribution of catalogue packet sizes, in place of the conservative character bound, would show how many packets fit each local key. The full run is the only full-catalogue fit sample.
- A 393,216-token local key is untested. No key above 163,840 tokens was measured for the selected model, and the estimate came from arithmetic rather than a tokenizer measurement.
- An unchanged rerun and a changed-source recalculation on the finished catalogue would show that matching work is reused and that only affected targets re-enter.
- A check of the 2,195 complete empty sets against the official record or a human reading would separate a correct no-prerequisite answer from a model omission.
