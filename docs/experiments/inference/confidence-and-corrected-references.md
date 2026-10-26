# Confidence calibration and corrected reference judgments

This report records how finding confidence was tested as a publication boundary, why the reference answers were corrected, and how the product policy ended with no confidence or flag filter.

**Evidence status:** Corrected.

The [Experiments section](/docs/experiments/README.md) gives the catalogue, the evidence labels and the hardware. The [glossary](/docs/reference/glossary.md) defines the product terms. The [reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) page states the reference corpus, the judge, the four verdicts, the rubric and the correction rules. This report states what the confidence measurements found and what the corrections did to the judgments.

The confidence measurement and the correction ran on 2026-09-26. The held-out comparison ran on the night of 2026-09-28 to 2026-09-29, and the policy was selected on 2026-09-29.

## The question

Every proposed option and every proposed equivalence group carried a confidence between `0` and `1` that the model stated as its own certainty. The prompt told the model that this value was its certainty rather than established truth. The measurement asked whether that stated certainty separated the findings a teaching-text judge would support from those it would reject, well enough to publish only findings above one cutoff.

A cutoff was attractive because of the two errors it could weigh. The judge's rubric already treated an omitted true prerequisite as the lesser error and a wrong claim as the one to refuse. If confidence marked the doubtful claims, one threshold could remove them before publication without reading every finding.

Two further questions had to be answered before any cutoff could be proposed. The verdicts it would calibrate against had to become a usable reference, and a confidence rule had to hold on targets and on a model that were not used to fit it. The policy question therefore came last, on held-out output: whether any confidence or flag rule improved the output enough to justify removing findings. A confidence boundary was measured and rejected, the reference it measured against was corrected, and a second filter failed on held-out output.

## The findings and their verdicts

The measured set was the 386 findings of the 200 CE-only reference answers, one answer per target course from DeepSeek V4.1 Flash under prompt v6. The findings covered 151 of the 200 targets. Required options were 199 in 124 requirement sets, recommended options 101 in 79 sets, and equivalence groups 86. The other 49 targets proposed no direct option and no equivalence group, and carried routing or suppression only.

Each finding received one verdict against the teaching text the answering model had seen, with the producing model, its confidence and its flags withheld. Of the 386 verdicts, 98 were reused from the [earlier packet comparison](/docs/experiments/inference/candidate-packet-selection.md), keyed by the same target, category and member set in the same frozen packet: 47 required, 27 recommended and 24 equivalence. Their reused totals reproduced the packet comparison's CE-only column exactly: 57 supported, 31 unsupported, nine partly and one unclear. The other 288 findings were shuffled with seed 20260926 and judged in six batches of 48, one read-only session per batch. One batch was refused once by a rate limit and judged after the reset. Coverage was complete, 386 of 386.

The four verdicts and the category tests are defined on the [method page](/docs/experiments/inference/reference-answers-and-judging.md). In the correction a `supported` finding was kept, an `unsupported` or `unclear` one dropped, and a `partly` one kept, demoted or dropped by its stored reason.

Two properties of a verdict matter for everything below. A `supported` verdict records what the supplied teaching text supports under the rubric. The university's own prerequisite record stayed outside the judgment. An `unsupported` verdict records that the text did not support that claim in that category. A claim in the wrong category, an over-broad AND, an irrelevant course and a course that belongs in another category all produce the same verdict. Whether the answer omitted a true prerequisite is a separate question that the verdict leaves open.

## The confidence bins

Confidence arrived in steps of 0.05 between 0.50 and 0.95, with one value at 0.78. The tables give every bin as emitted, with `partly` and `unclear` visible and never folded into `supported`. The supported rate is supported divided by the findings in the bin.

| Required options | n | Supported | Rate | Partly | Unsupported | Unclear |
|---|---:|---:|---:|---:|---:|---:|
| 0.50 | 1 | 0 | 0.00 | 1 | 0 | 0 |
| 0.55 | 3 | 2 | 0.67 | 1 | 0 | 0 |
| 0.60 | 7 | 4 | 0.57 | 2 | 0 | 1 |
| 0.65 | 3 | 1 | 0.33 | 1 | 0 | 1 |
| 0.70 | 14 | 5 | 0.36 | 3 | 5 | 1 |
| 0.75 | 6 | 3 | 0.50 | 1 | 1 | 1 |
| 0.78 | 1 | 1 | 1.00 | 0 | 0 | 0 |
| 0.80 | 64 | 25 | 0.39 | 26 | 13 | 0 |
| 0.85 | 44 | 23 | 0.52 | 13 | 7 | 1 |
| 0.90 | 52 | 29 | 0.56 | 15 | 6 | 2 |
| 0.95 | 4 | 3 | 0.75 | 1 | 0 | 0 |
| All | 199 | 96 | 0.48 | 64 | 32 | 7 |

| Recommended options | n | Supported | Rate | Partly | Unsupported | Unclear |
|---|---:|---:|---:|---:|---:|---:|
| 0.50 | 3 | 2 | 0.67 | 1 | 0 | 0 |
| 0.55 | 1 | 1 | 1.00 | 0 | 0 | 0 |
| 0.60 | 5 | 4 | 0.80 | 1 | 0 | 0 |
| 0.70 | 38 | 23 | 0.61 | 10 | 4 | 1 |
| 0.75 | 6 | 4 | 0.67 | 1 | 1 | 0 |
| 0.80 | 47 | 36 | 0.77 | 9 | 1 | 1 |
| 0.90 | 1 | 1 | 1.00 | 0 | 0 | 0 |
| All | 101 | 71 | 0.70 | 22 | 6 | 2 |

| Equivalence groups | n | Supported | Rate | Partly | Unsupported | Unclear |
|---|---:|---:|---:|---:|---:|---:|
| 0.60 | 2 | 2 | 1.00 | 0 | 0 | 0 |
| 0.70 | 5 | 3 | 0.60 | 0 | 2 | 0 |
| 0.75 | 3 | 1 | 0.33 | 0 | 2 | 0 |
| 0.80 | 12 | 9 | 0.75 | 0 | 3 | 0 |
| 0.85 | 18 | 14 | 0.78 | 1 | 3 | 0 |
| 0.90 | 30 | 23 | 0.77 | 3 | 4 | 0 |
| 0.95 | 16 | 11 | 0.69 | 2 | 3 | 0 |
| All | 86 | 63 | 0.73 | 6 | 17 | 0 |

The largest bin holds 64 findings and four bins hold one finding. The reading below rests on the large cells.

The chart plots the five confidence levels that all three categories used.

![Judged supported share by emitted confidence for required options, recommended options and equivalence groups, on the five confidence levels common to all three categories. None of the three lines rises steadily with confidence.](/docs/charts/inference-confidence-bins.svg)

A rise from left to right is the signal a cutoff needs. The required line falls from 0.57 at 0.60 to 0.36 at 0.70, rises to 0.50 at 0.75, falls to 0.39 at 0.80 and rises to 0.56 at 0.90. The recommended line is higher at every level and still not monotone. The equivalence line starts at 1.00 in its two-finding 0.60 bin, falls to 0.33 at 0.75 and then rises.

The cumulative view asks what one threshold would keep.

| Cutoff | Required n / rate | Recommended n / rate | Equivalence n / rate |
|---|---|---|---|
| 0.70 or above | 185 / 0.48 | 92 / 0.70 | 84 / 0.73 |
| 0.80 or above | 164 / 0.49 | 48 / 0.77 | 76 / 0.75 |
| 0.85 or above | 100 / 0.55 | 1 / 1.00 | 64 / 0.75 |
| 0.90 or above | 56 / 0.57 | 1 / 1.00 | 46 / 0.74 |
| 0.95 or above | 4 / 0.75 | 1 / 1.00 | 16 / 0.69 |

## What the bins showed

For required options the supported rate rose only from 0.48 at 0.70 or above to 0.57 at 0.90, by way of 0.49 at 0.80 and 0.55 at 0.85. The individual confidence bins were not monotone. The 0.80 bin, the largest with 64 findings, was the worst large cell at 0.39, below the 0.50 of the six-finding 0.75 bin. At 0.90 or above, 24 of 56 findings were not supported: 16 `partly`, six `unsupported` and two `unclear`, or 43 percent. Raising the cutoff mostly discarded findings rather than separating them. The `partly` verdict also dominated several required cells, with 26 of the 64 findings at 0.80.

Recommended options were mildly better and improving: 0.61 at 0.70, 0.67 at 0.75 and 0.77 at 0.80. Only one recommended finding was emitted above 0.80, so no cutoff above 0.80 was usable for the category.

Equivalence groups were moderately supported at 0.73 overall and roughly flat with confidence: 0.75 at 0.80 or above, 0.74 at 0.90 and 0.69 at 0.95. Unsatisfactory groups occurred at every level, including 0.95, where 11 of 16 were supported and the other five were `partly` or `unsupported`.

The interpretation is that confidence behaved as a weak, not monotone signal. Any one numeric cutoff would either admit a material share of non-supported required and equivalence findings or discard many supported ones. A confident wrong claim was common at the top of the scale, and a lower confidence did not reliably mark a worse claim.

The open question was closed on 2026-09-26 with no finding-confidence cutoff. Confidence alone could not separate good findings from bad ones. The measurement named no fallback filter. The next step was a separate corrected reference, and the tuning step would test a confidence-plus-per-finding-flag drop or demote rule on the local model's own output and on held-out targets, using the per-finding flag schema rather than the reference model's target-level flags.

One working count of required findings covered both packet variants. At confidence 0.80 it held 10 supported and 16 unsupported required options. That set was the 97 differing required findings across the CE-only and RRF packets, not the CE-only corpus. On the CE-only corpus the same bin holds 25 supported, 26 `partly` and 13 unsupported required options of 64. The two are not comparable, and the CE-only table is the one this line used.

## The target-level routing check

The reference answers also carried one routing confidence and zero or more routing flags per target. A check after the confidence run asked whether that target-level metadata, rather than per-finding confidence, marked the targets that held at least one unsupported finding. It read the same 386 verdicts and the same answers and changed neither.

In total, 161 of the 200 targets carried at least one routing flag. The 34 required findings on unflagged targets included 21 supported. The 165 required findings on flagged targets included 75 supported. Keeping required findings only at routing confidence 0.8 or above with neither `directness_ambiguity` nor `substitute_overlap_ambiguity` retained 44 findings: 29 supported, nine `partly`, four unsupported and two `unclear`. A reported count of 42 was those 44 without the two `unclear` verdicts, not the number the rule retained.

A 20-split check fitted the rule on one half of the targets and applied it to the other. Targets were sorted by identity, the halves were shuffled 100 and 100 with seed 20260926, and the rule search covered routing cutoffs of 0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9 and 0.95 and the exclusion of zero to three of the five saved flags. On each fitting half the search picked the rule with the highest supported share among rules that kept at least 15 required findings, breaking ties toward keeping more, and the other half scored it. Mean fitting share was 0.75 and held-out share 0.57, against 0.48 with no filter. An earlier 20-split calculation gave about 0.76 and 0.56 without recording its rule search and split recipe. The recomputed values support the same conclusion: a weak out-of-sample signal.

Two further observations closed this route. The reference model's evidence strings did not distinguish a correct claim from an incorrect one, so they were not turned into a text classifier. The target-level flags of the saved answers were examples, not a fixed vocabulary, and could not be carried into the per-finding flag schema that prompt tuning introduced. The target-level metadata stayed raw evidence.

## Correcting the reference

Confidence alone failed, and the tuning step needed a reference that could score a model's output better than the raw verdicts could. Two defects stood between the verdicts and that use. The `partly` verdict combined a partial AND, a wrong category and a required option missing its entry condition under one label, so it could not say whether a finding should stay in any form. And 45 of the 86 equivalence groups did not contain their target, so the judge had compared the members with the target instead of only with one another. Those verdicts did not test the group claim.

The correction called no answering model, changed no answer and read no official prerequisite label. It did not rewrite the 386 verdicts. It built a separate 200-target reference by mapping each finding to keep, demote or drop under rules fixed before the mapping.

| Category | Verdict | Findings | Keep | Demote | Drop |
|---|---|---:|---:|---:|---:|
| Required | `supported` | 96 | 96 | 0 | 0 |
| Required | `partly` | 64 | 1 | 56 | 7 |
| Required | `unsupported` | 32 | 0 | 0 | 32 |
| Required | `unclear` | 7 | 0 | 0 | 7 |
| Recommended | `supported` | 71 | 71 | 0 | 0 |
| Recommended | `partly` | 22 | 15 | 0 | 7 |
| Recommended | `unsupported` | 6 | 0 | 0 | 6 |
| Recommended | `unclear` | 2 | 0 | 0 | 2 |
| Equivalence | Target member, `supported` | 35 | 35 | 0 | 0 |
| Equivalence | Target member, `partly` | 3 | 0 | 0 | 3 |
| Equivalence | Target member, `unsupported` | 3 | 0 | 0 | 3 |
| Equivalence | Target not a member | 45 | 45 | 0 | 0 |

The mapping kept 263 findings, demoted 56 and dropped 67, leaving 319. Required options fell from 199 to 97 in 70 sets. Recommended options rose from 101 to 142 in 126 sets, the 86 kept plus the 56 demoted, with each demoted option as its own single-option set. Equivalence groups fell from 86 to 80. A demoted option kept its evidence and confidence byte for byte, and no recommended finding was promoted.

The 56 demotions are the largest movement between categories in the correction. Every one of them moved a required option into the recommended category because its stored reason described relevant background without a clear entry requirement, or because a blind fine judgment read it that way.

### The partly class

All 92 `partly` findings received an action. Of these, 83 carried a stored reason, and each reason was read by hand into a hand-authored classification rather than a keyword rule. Eight reasonless required options went to a blind fine-disposition judge, which returned one `correct as required`, six `correct only as recommended` and one `partial AND`. The one reasonless target-member equivalence group dropped by rule, without another judgment. The fine batch showed the teaching text, the claim and the model evidence, and withheld the old verdict, the producing model and the answer key.

In the required category, 50 reasoned `partly` options became recommended, and six reasoned ones dropped for overlap, duplicated content or an unsupported AND. The fine judge supplied the other six demotions and one drop.

For recommended `partly` findings the rule's default kept the recommendation unless the reason said the relation was wrong or an overlap. A reason that called the link weak, loose or tangential kept it. Under that reading seven of 22 dropped and 15 stayed. The reading was disclosed because a stricter reading of "loose" as "wrong" would have dropped the 15 kept rows. The saved classification marks those rows, so the reading could be re-applied without another judgment. This report treats the 15 as a recorded interpretation, not as a measured boundary.

### The equivalence exception

The exception took precedence over every other rule. A group that did not contain its target stayed exactly as the reference model emitted it, whatever verdict it carried. In total, 45 groups were kept this way: 28 with a `supported` verdict, 14 unsupported and three `partly`. Their verdicts are unreliable corrections, and keeping the group claim and keeping the verdict are different acts. The correction disclosed both.

The other 41 groups contained their target and were corrected on their verdicts. The 35 supported groups stayed, and the three `partly` and three unsupported groups dropped.

### What the correction changed

The corrected reference is a 200-target evaluation corpus, not a set of edits to the answers. Every emitted finding has one recorded action: keep, demote or drop. The saved verdicts stay as judged. The reference model was not called again, and no relationship was added to balance a category.

## What the corrected reference can and cannot show

The corrected reference corrects emitted findings only. It fills no gap. The reference model may have omitted true prerequisites, and no rule could recover them. The 49 targets that emitted nothing hold no finding for a support rate to count, and the reference holds nothing for them. The reference is evaluation evidence, not the university's prerequisite record.

Only generated claims were judged. Every support rate in this report divides by the findings a model chose to emit. A model that emits few, safe findings can show a higher supported share than a model that emits more, and the same model can raise its rate by proposing less. Supported shares are comparable only beside their emission counts and their category counts. The corrected reference inherits the same limit for the whole-result score, because the score reads the reference model's claims and fills no target that the measured model never addressed.

`Unsupported` counts a claim, and the taxonomy behind one verdict is wider than one error. A wrong category, an over-broad AND, an irrelevant course and a course that is an official prerequisite of another course all arrive as `unsupported`. The correction treated those cases differently and left that course invisible. A count of unsupported findings measures claims the text did not support. It leaves the count of omitted official prerequisites unmeasured.

The equivalence limitation passes through unchanged. A comparison against the corrected reference scores 45 groups whose group-wide support was never judged, and it scores them as the reference model wrote them.

The reuse of 98 verdicts carries its own limit. The two blind renderings were not byte-identical for every reused item: course order, literal HTML tags and truncation after formatting differed, while the packet itself did not change. The reuse is a limit of rendered-text reuse, not a second source.

The corrected reference was secondary evidence in this line. Its whole-result F1 compares a model's emitted options with a single-sample reference, and the reference holds more findings than any measured model emitted. The line used blind judged support as the primary quality measure and F1 as a disagreement diagnostic.

## The held-out rule fit

The next test moved from the reference model's target-level metadata to a local model's own per-finding confidence and flags. The 150 held-out targets were the complement of the 50 targets used for prompt tuning. Qwen3.8-27B IQ3_S ByteShape, with prompt v9 and schema v2, answered all 150 held-out targets with 150 valid results, and its 168 findings were judged blind. A drop or demote rule was fitted on the 100 fit targets and applied unchanged to the distinct 50 validation targets. The search covered a baseline, a confidence cutoff at 0.8, 0.85 and 0.9, a drop of any flagged finding, a demotion of required options flagged `requiredness_uncertain`, and one combined confidence and flag rule.

Neither signal separated harmful claims, where a harmful claim is a finding judged unsupported.

Confidence ran the wrong way. All 18 unsupported findings on the fit 100 sat at confidence 0.95. The 0.80, 0.85 and 0.90 bins carried no unsupported finding. Dropping findings at confidence 0.9 or below kept 76 of the 109 judged findings, still kept all 18 unsupported ones, and scored F1 0.219 against the 0.230 baseline.

Flags ran the wrong way. No-flag findings carried 16 of the 18 unsupported findings. `requiredness_uncertain` carried none, and `group_scope_uncertain` carried two. Dropping every flagged finding kept 70 findings and still kept 16 unsupported ones, at F1 0.189. Demoting `requiredness_uncertain` changed nothing, because the flag sat almost entirely on recommended options.

| Rule on the ByteShape fit 100 | Findings kept | Unsupported kept | F1 |
|---|---:|---:|---:|
| Keep every finding | 109 | 18 | 0.230 |
| Drop confidence 0.90 or below | 76 | 18 | 0.219 |
| Drop every flagged finding | 70 | 16 | 0.189 |

The chart compares the findings kept and the unsupported findings kept under the baseline and the two candidate rules.

![Findings kept and unsupported findings kept under the baseline and two candidate rules on the ByteShape fit targets. Dropping low-confidence findings keeps all 18 unsupported ones, and dropping flagged findings keeps 16 of them.](/docs/charts/inference-confidence-rule-fit.svg)

The chart shows why no rule was proposed. Both candidate filters removed supported findings and left nearly all the unsupported ones in place.

No candidate rule improved the fit 100 or the distinct validation 50, and several made F1 worse. The validation result was a failure. Target-level routing failed the same way. A target counted as harmful when it held at least one unsupported finding. Of the 107 finding-bearing targets on the held-out 150, 15 had high routing confidence, no routing flag and at least one harmful finding. Another 77 had high routing confidence, no flag and no harmful finding. The ten low-confidence flagged targets and the five low-confidence unflagged targets all had no harmful finding. Routing confidence was 0.9 on 147 of 168 findings, and routing flags were empty on 154 of 168. Routing metadata marked targets with no harmful finding rather than harmful ones.

The held-out record of Qwen3.8-27B IQ3-MIX added the same observation. Its combined 150 targets held 15 unsupported required findings, and all 11 unsupported findings from the targets added to its cohort lacked both finding and routing flags. The ByteShape rule was not transferred or re-fitted to MIX. A MIX-specific calibration is untested.

## Limits that qualify every number

- One sample per slot. The 100 paired reference answers produced 257 distinct findings, 52 in both answers and 205 in one, an overlap of about 0.34 finding F1. Most paired differences were consistent with sampling noise. No self-agreement measurement was run.
- One judge and one rubric. No agreement measurement between the judge and a human reader exists, so the judge's error rate is unknown, and the verdicts are tied to one model's reading of the rubric.
- A bounded rendering of each course, with truncated names, outcomes and content, and markup passed as literal characters. Nine findings were `unclear` because the text was too sparse.
- The equivalence judge flaw and the 45 groups kept by exception.
- The 98 reused verdicts whose renderings differed in course order, literal tags and truncation.
- Single-night held-out observations on deterministic cohorts. The 50 validation targets were a size-quantile subset of the 150, and the 100 fit targets were the rest.
- Small confidence bins. Four bins hold a single finding and several hold three or fewer, and no per-bin interval was computed. A flat line is read as no usable ordering, not as proof that two probabilities are equal.
- A filter fitted on one local model and one prompt. The MIX-specific rule was never fitted, so the absence of a working rule for MIX is untested rather than measured.

### Untested follow-up questions

1. A confidence or flag rule fitted to MIX's own held-out output. The ByteShape rule was not transferred, and no MIX rule was measured.
2. A re-judged equivalence set with the 45 target-not-member groups compared only among their members, to see whether their verdicts and the corrected reference change.
3. A human re-read of a sample of the 386 findings, which would put a number on the judge's error.

## Setup details

| Item | Value |
|---|---|
| Reference answers | 200 CE-only complete target results from DeepSeek V4.1 Flash under prompt v6 |
| Findings judged | 386 across 151 targets: 199 required, 101 recommended, 86 equivalence |
| Verdicts reused | 98: 47 required, 27 recommended, 24 equivalence |
| Verdicts judged here | 288, in six batches of 48, shuffle seed 20260926 |
| Judge | Claude Opus 5.5 at the low variant, one read-only session per batch |
| Confidence scale | Model-stated, 0 to 1, emitted in steps of 0.05 with one 0.78 value |
| Correction actions | Keep 263, demote 56, drop 67, applied to a separate 200-target reference |
| ByteShape fit cohort | 100 fit targets and a distinct 50-target validation set from the held-out 150 |
| ByteShape findings | 168 over 150 targets, with 109 judged findings on the fit 100 |
| MIX findings | 178 over 150 targets |
| Held-out model | Qwen3.8-27B IQ3_S ByteShape, prompt v9 and schema v2, thinking off, temperature 0 |
| Selected model | Qwen3.8-27B IQ3-MIX, prompt v9 and schema v2, 131,072-token MTP key first, 163,840-token no-MTP key when needed |
| Hardware | AMD Radeon RX 9070 XT (16 GB model), ROCm 7.2.1, 33.4 GB usable RAM |

## The selected policy

On 2026-09-29 the policy was selected and applied. Qwen3.8-27B IQ3-MIX runs solo at its measured 131,072-token MTP key with `q4_0` KV, and at its 163,840-token no-MTP key with `q4_0` KV only when the full packet, the configured output and headroom do not fit the first key. No packet is truncated and no measured context ceiling is exceeded. No target is rerouted because its output looks uncertain. ByteShape, Qwen3.6-35B-A3B, gpt-oss-20b and Nemotron-3-Nano-30B-A3B were not selected.

The selected quality policy keeps inferred recommended options exactly as emitted. It applies no confidence cutoff and no flag cutoff, drops no emitted finding and demotes no required finding to recommended. Per-finding confidence and flags, and target-level routing confidence and flags, are retained as raw evidence and never filter or transform published output. The [inference behaviour page](/docs/backend/inference/inference.md#proposals-and-publication) states the applied configuration: `INFERENCE_RECOMMENDATION_POLICY` is `include`, and `INFERENCE_FINDING_FILTER_POLICY` is `none`.

The measured quality stands: 15 unsupported required findings among MIX's 100 required findings on the held-out 150, with 111 of 178 findings supported overall, 54 of 100 required, 38 of 47 recommended and 19 of 31 equivalence. The course exclusion input lets an inferred course that is wrong in the graph or in a route be excluded. Inferred output stays separate from university-authored fact.

The fitted ByteShape rule was not transferred, because it had failed on distinct targets. A MIX-specific rule was neither fitted nor rejected on its own evidence. The full held-out comparison is on [the held-out model quality page](/docs/experiments/inference/held-out-model-quality.md).

Corrected-reference F1 stayed a secondary diagnostic. On the 150 held-out targets MIX scored 0.192 and ByteShape 0.236, and neither value gated the selection.

One separate rule removes output before publication. Composition absorbs an inferred option that an official option already names in full, removes members covered by an official option of the other category, and drops an equivalence group that repeats the target course and one official single-course substitute. That deduction compares the output with official structure. It is not a confidence or flag filter, and it was not part of the quality policy this line closed.

The filter question that the confidence measurements opened closed on 2026-09-29 with no confidence cutoff, no flag cutoff, no finding drop and no finding demotion. Confidence and flags are recorded evidence, and no threshold narrows the published output.
