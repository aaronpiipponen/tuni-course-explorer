# Prompt and structured-output tuning

This report records how prompt revisions and per-finding uncertainty flags changed one local model's inferred prerequisites, and why no confidence or flag cutoff survived the held-out check.

**Evidence status:** Corrected. **Run dates:** 27 to 29 September 2026.

The trials ran on 27 September 2026, and the re-tuning continued through the following night. The held-out check ran on the night of 28 to 29 September, and the policy was selected on 29 September 2026. The line corrected an earlier checkpoint result, and a cutoff rule fitted on later held-out targets failed validation.

The [Experiments section](/docs/experiments/README.md#inference) gives the catalogue, the evidence labels and the hardware specifications, and the [Inference experiments](/docs/experiments/inference/README.md) overview places this report in the category. This report covers one line of that work: the prompt versions, the per-finding flags and the structured-output contract that one local model used for complete-target inference. The [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) report fixes the candidates the prompt sees, and [local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md) gives the fit and speed of the model.

## The question

A complete-target inference call has a fixed packet, a fixed target and a fixed schema. The prompt decides what the model treats as a direct prerequisite, how it groups options, when it proposes an equivalence group and how it reports doubt. Prompt tuning was therefore the part of the quality question that could move without changing the candidates or the model.

Three questions ran together through the trials.

- Can a local model produce valid grouped results on long packets without truncating the input?
- Does prompt wording improve whole-result agreement with a separately corrected reference?
- Can per-finding uncertainty flags or target confidence support a drop or demote rule that removes harmful findings without removing good ones?

The third question matters because a wrong required claim is the costliest error in this report's ranking. A right course in the right category ranks first, a right course in the wrong required-or-recommended category ranks second, and an omission ranks third. A course that is not a prerequisite at all is the error that matters. A filter that removed unsupported findings would be valuable only if its signal marked those findings rather than the model's general uncertainty.

The corrected reference is evaluation evidence, not the university's prerequisite record. It comes from one DeepSeek V4.1 Flash answer per target, corrected for the precision of the findings that answer emitted, and it cannot recover prerequisites that answer omitted. The [reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) page states the corpus, the blind judge and the four-verdict rubric. Every F1 here is a disagreement diagnostic against that reference, and every support count comes from the same blind judge.

## Setup and fixed cohorts

### Model and request

The model was ByteShape Qwen3.8-27B IQ3_S, a 27B-class artifact at 3.23 bits per weight. Its 11.0 GB file holds 64 layers, a hybrid attention and state-space design, and an embedded multi-token-prediction head. It ran on an AMD Radeon RX 9070 XT (16 GB model) on ROCm 7.2.1, in a machine with 33.4 GB of usable RAM. The model runtime had a 4.295 GB memory limit and 8.590 GB of swap.

| Item | Value |
|---|---|
| Model | ByteShape Qwen3.8-27B IQ3_S, 3.23 bits per weight |
| Artifact | 11.0 GB |
| Architecture | 64 layers, hybrid attention with a state-space component, embedded MTP head |
| Card | AMD Radeon RX 9070 XT (16 GB model), ROCm 7.2.1 |
| System RAM | 33.4 GB usable |
| Model runtime limits | 4.295 GB of memory and 8.590 GB of swap |
| First local key | 118,784 tokens with MTP and a `q8_0` KV cache |
| Second local key | 147,456 tokens without MTP and a `q8_0` KV cache |
| Generation | Thinking off, temperature 0, seed 0, 8,192 output tokens |
| Request timeout | 300 seconds in the re-tuning runs |
| Prefix cache | Shared system and examples prefix of about 13,000 tokens, reused at 800 to 880 prompt tokens per second |

The 118,784-token key was the one every tuning trial used. The largest tuning packet was 160,087 ByteShape prompt tokens, so it exceeded both ByteShape keys and was always a reported context skip. It was never truncated. Every other tuning packet fitted the first key.

The request carried the target descriptor and the 50 candidate descriptors in packet order. No retrieval score, rank value or official prerequisite label entered a request. The corrected reference was read only by the scorer after a trial's outputs were saved.

### Prompt versions and the flag schema

The prompt is one system message and one user message per call. The user message carries the target and the ordered candidates. The system message fixes the output contract, the directness rule, the grouping rule, the category definitions, the equivalence rule and the code-copying rule. It never contains the target's official answer.

| Version | Main change from the previous version | Schema | Role in this line |
|---|---|---|---|
| v6 | Complete-target prompt with nine curated examples, one grouping rule per category and five suppression outcomes | v1 | Baseline for the first trials |
| v7 | Per-finding `finding_flags`, flag guidance and a firmer flag instruction | v2 | First research checkpoint |
| v8 | v7 system plus the measured flag-contract paragraphs, with v7 example bytes | v2 | Research checkpoint before re-tuning |
| v9 | v8 bytes plus a multi-flag section with worked doubt combinations | v2 | Prompt selected for the held-out check and applied with the selected model |

Schema version 2 makes `finding_flags` a required, possibly empty array on every option and every equivalence group. An option carries zero or more of `requiredness_uncertain`, `member_uncertain` and `directness_uncertain`. An equivalence group carries zero or more of `member_uncertain` and `group_scope_uncertain`. A finding may carry several distinct flags but never the same flag twice. The product's generation and validation read the same field, as [Inference](/docs/backend/inference/inference.md#generation-and-validation) states. Schema version 1 carried no such field and rejected it.

One saved c4 result shows the nesting. This is the `required` requirement set for `RAK.RS.610`, printed from the model output and not taken from any official requirement record.

```json
{
  "requirement_id": "required_1",
  "options": [
    {
      "course_codes": [
        "RAK.RS.600"
      ],
      "evidence": "RAK.RS.600 teaches the basics of CLT-structure design, timber member stability, and structural stiffening, which are the direct entry-level prerequisites for the advanced topics in multi-storey timber buildings and CLT structures covered in the target course.",
      "confidence": 0.95,
      "finding_flags": []
    },
    {
      "course_codes": [
        "53161"
      ],
      "evidence": "53161 is titled 'Timber Structures' and is a course-wide equivalent to RAK.RS.600, providing the same foundational knowledge in timber design and stability required for the target course.",
      "confidence": 0.9,
      "finding_flags": [
        "member_uncertain"
      ]
    },
    {
      "course_codes": [
        "RTEK-3410"
      ],
      "evidence": "RTEK-3410 covers timber structure design principles, stability, and material properties, serving as an alternative foundational course for the timber design knowledge assumed by the target.",
      "confidence": 0.85,
      "finding_flags": [
        "directness_uncertain"
      ]
    }
  ]
}
```

The `options` array is the OR level, and each option's `course_codes` array is the AND level. This saved set holds three alternatives of one code each. The complete result also holds a recommended set, one equivalence group and routing metadata. An accepted result holds zero or one requirement set in each of `required` and `recommended`, while an equivalence array holds groups.

The first flag vocabulary and the v2 parser were built during the tuning. The field was named `finding_flags`, not `flags`, and the prompt told the model that a finding may carry more than one flag. None of the three flag-audit trials carried more than one flag on a finding. The 50-target v8 control run did: one recommended option, `EE.ELE.520` for `EE.ELE.512`, carried both `requiredness_uncertain` and `directness_uncertain`. That single finding is the only multi-flag finding among the runs whose flags this report counts, and the crafted example and the parser test cover the rest.

### The 50 tuning targets and the 150 held-out targets

The cohort is 200 active represented target courses with a cross-encoder-only (CE-only) packet of 50 candidates each. It was fixed before any ByteShape output. The 50 tuning targets were selected without labels from the 200 by sorting on the rendered user-prompt character length and the target identity, then taking the integer-floor indices `(i*199)//49` for `i` from 0 to 49. The rule includes the smallest and largest packet. The tuning sizes span 37,065 to 534,313 characters. The other 150 targets formed the complement and were not used for tuning.

A 15-target format-check subset was drawn from the 50 with the same floor rule, `(i*49)//14`. Every format trial ran that subset. The 15 are listed below with their rendered packet size.

| Course | Rendered packet characters |
|---|---:|
| XLI-KKTLA01.012 | 37,065 |
| EDU.050 | 61,486 |
| EDU.030 | 75,498 |
| YKT.YKE.504 | 80,385 |
| LANG.RUO.007 | 87,683 |
| HAL.JOIK.314 | 94,370 |
| EDU.TRI.002 | 100,976 |
| LAAL.615 | 105,335 |
| VIM.VI.280 | 113,809 |
| TEA.311 | 124,185 |
| MEDAHTHEPA | 129,161 |
| MUS.010 | 133,966 |
| BBT.012 | 140,646 |
| EE.ELE.512 | 151,749 |
| MEDAYLKKOE | 534,313 |

The 15 are inside the 50. The one 534,313-character packet is the only tuning target above both ByteShape context keys. Its 160,087 prompt tokens exceed the 118,784-token first key and the 147,456-token second key, so every 50-target trial reports one context skip. The valid count is 49 except for the v8 control, which saved 47 valid results. Its two transport errors are `LAAL.615` and `AUT.250`, each attempted four times.

The later held-out check used the other 150 targets. Within those 150, a deterministic size-quantile subset of 50 served as the shared comparison cohort and the distinct validation set, and the other 100 were the fit set for the cutoff rule. The 50 and the 100 are disjoint. No tuning result counts toward the 150.

### Scoring, the reference and the judge

A finding is one option, with all of its courses taken together, or one equivalence group. A true positive requires the same member set and, in the primary score, the same category. A category-agnostic true positive requires only the same member set, so a right course in the wrong category counts. A near-match is a right member set with required and recommended swapped. Exact whole-result agreement requires every category and every member set to match.

The scores pool findings over the valid targets in the stated cohort. F1 is the harmonic mean of precision and recall against the corrected reference. The reference for the 49 valid targets of the first tuning sequence holds 80 findings. The re-tuning candidates that returned 49 valid results use the same 49 target identities, the same per-target reference counts and the same 80 findings. The v8 control returned 47 valid results and is treated with its own denominator below. Of the 49 valid targets, 16 have an empty reference, and the skipped `MEDAYLKKOE` is the seventeenth empty reference among all 50. The reference has more findings than the model emits, so recall and F1 are low by construction. The reference is a single sample and cannot recover an omission, which is why the whole-result score is secondary to blind judged support.

The blind judge is the one described in [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md). It sees a claim, the target and the named courses, and the producing model's evidence, but no model identity, confidence, finding flag, routing metadata, packet identity or reference verdict. It returns one of four verdicts: `supported`, `partly`, `unsupported` or `unclear`. The first flag audit used it on 89 unique claims from three saved trials, carried by 153 finding occurrences. The claims were deduplicated by target, category and unordered member set, each unique claim was judged once, and the verdict was reused for every occurrence. The re-tuning night then ran a separate judge pass over the six full-50 candidates and judged every emitted claim: 59, 64, 58, 49, 44 and 50 claims, 324 in total. Those 324 are claim occurrences, not deduplicated unique claims, and the two audits share no total.

## The first prompt sequence

The first sequence moved from the v6 baseline through four candidate prompts to a frozen v7. All of the format trials used the same 15 targets and the same ByteShape key. Every trial except the temperature trial used deterministic settings at temperature 0 and seed 0. The invalid count was zero on every fitting target. Transient transport drops were retried.

| Trial | Prompt and schema | Valid | Exact | Precision | Recall | F1 | Observation |
|---|---|---:|---:|---:|---:|---:|---|
| Baseline | v6, schema v1 | 14 | 4 | 0.133 | 0.080 | 0.100 | Mostly empty output |
| Candidate 1 | v6 wording plus flags and an emit-direct instruction, schema v2 | 14 | 4 | 0.182 | 0.080 | 0.111 | Every flag array empty |
| Candidate 2 | Adds equivalence target inclusion, an emit-recall instruction and a three-entry suppression cap | 14 | 3 | 0.235 | 0.160 | 0.190 | Equivalence groups include the target |
| Candidate 3 | Adds flag-bearing worked examples and flag-use guidance | 14 | 4 | 0.222 | 0.160 | 0.186 | Flags empty |
| Candidate 4 | Renames the field `finding_flags` and adds a firmer instruction | 14 | 4 | 0.278 | 0.200 | 0.233 | First emitted flags and the highest first-sequence F1 |
| Temperature 0.3 | v7 at temperature 0.3 and seed 1 | 14 | 3 | 0.214 | 0.120 | 0.154 | Lower emission and lower agreement |

Candidate 3 emitted no flag from either change, a worked example with flags and explicit flag-use guidance. Candidate 4 emitted flags, only after the field name changed from `flags` to `finding_flags` and the instruction became firmer. The earlier guidance did not produce a flag, and the rename with the firmer instruction did.

The temperature trial moved away from the target. At temperature 0 and seed 0 the model is deterministic, so repeated prompts differ only through prompt bytes. The 15-target subset itself swings by about plus or minus 0.03. The frozen v7 measured 0.205 on the subset beside candidate 4 at 0.233 on identical settings. A difference of that size on 14 targets is not a prompt ranking.

### Candidate 4 on the full tuning set

Candidate 4 was the measured tuning candidate. On all 50 targets it attempted 50, returned 49 valid results and reported one context skip. Invalid complete-target output was zero. It matched 16 of 49 whole results exactly and reached precision 0.273, recall 0.225 and F1 0.247. The reference held 80 findings on the 49 fitting targets, and the model emitted 66.

| Category | True positive | False positive | False negative | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| Required | 9 | 26 | 15 | 0.26 | 0.38 |
| Recommended | 0 | 14 | 35 | 0.00 | 0.00 |
| Equivalence | 9 | 8 | 12 | 0.53 | 0.43 |

Candidate 4 never emitted a recommended finding that coincided with the corrected reference's recommended set, so the recommended row carries no true positive. Several cases show the right course under the wrong category. `ACC.140` emitted `ACC.010` as required where the reference keeps it recommended, and `KIR.234` emitted only `KIR.140` where the reference requires `KIR.110` and `KIR.140`.

A post-output diagnostic separated membership from category. Of the 66 emitted findings, only 22 had a member set present anywhere in the reference, and 18 were exactly right. Relabelling every finding into its best category therefore caps F1 at 0.301. Most of the gap is a different member set, not a wrong required-or-recommended label. The reference's recommended set is mostly DeepSeek required options that the judge demoted as relevant background. A recommended true positive therefore requires the model to emit the same course, not only to choose the recommended label.

### The v7 checkpoint and the frozen-bytes correction

The frozen v7 bytes made two contract changes to the candidate 4 prompt. It restored the suppression cap to five entries, because a three-entry cap contradicted a worked example with four suppressions. It also added a multi-flag example, because no example showed more than one flag on a finding. The instruction text otherwise matched candidate 4.

Because the exact bytes then differed from the measured candidate, the frozen v7 bytes were run again on the same 50. The re-run returned 49 valid results, the same one context skip and zero invalid output. It matched 14 of 49 whole results and reached precision 0.267, recall 0.200 and F1 0.229.

| Category | True positive | False positive | False negative | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| Required | 8 | 21 | 16 | 0.28 | 0.33 |
| Recommended | 0 | 13 | 35 | 0.00 | 0.00 |
| Equivalence | 8 | 10 | 13 | 0.44 | 0.38 |

The re-run sits within tuning noise of candidate 4. Candidate 4 is the measured tuning candidate, and frozen v7 is the exact-bytes checkpoint. Both values are reported. Neither is treated as a separate estimate of a prompt's quality.

The v7 checkpoint was first described as the endpoint of the tuning. That reading was corrected. The working budget was not spent and the agreement was not convincing, so the same 50 targets were tuned further. The v7 prompt, schema and evidence were kept as a historical checkpoint, and the next versions were measured on the same fixed cohort.

The flag audit also corrected a claim. The first text said the tuning model used only `requiredness_uncertain`. A re-read of the saved outputs found `requiredness_uncertain` on 14 findings, `directness_uncertain` on two required options and `group_scope_uncertain` on one equivalence group in candidate 4. The frozen v7 bytes carried the same kinds at 13, two and one. Neither run carried more than one flag on a finding. The 50-target v8 control, described above, is the measured exception.

## The broader prompt sweep

The next sweep tested whether a completeness prompt or a stronger flag contract could lift agreement above candidate 4. The v8b variant asked for complete coverage and produced more findings. It emitted 76 findings against the reference's 80, against 60 for frozen v7. It also produced the first recommended true positive. The extra emission became more false positives than true positives.

| Run | Required F1 | Recommended F1 | Equivalence F1 | Category-agnostic F1 |
|---|---:|---:|---:|---:|
| Frozen v7 | 0.302 | 0.000 | 0.410 | 0.271 |
| v8b | 0.300 | 0.036 | 0.341 | 0.256 |
| c4 flags, later v9 | 0.340 | 0.000 | 0.390 | not recorded |

On the 49 fitting targets, v8b reached precision 0.224, recall 0.212 and F1 0.218. Frozen v7 reached 0.229. Whole-result exact matches were 14 of 49 for both. The completeness prompt therefore did not improve agreement, and its category-agnostic score was slightly lower, 0.256 against 0.271. It was rejected as the next prompt.

The v8 format screen covered three prompts on the same 15 targets.

| Trial | Prompt | Valid | Exact | Precision | Recall | F1 | Observation |
|---|---|---:|---:|---:|---:|---:|---|
| v8a | v8a emit variant | 14 | 4 | 0.250 | 0.200 | 0.222 | No gain over candidate 4 |
| v8d | v8 flag-contract wording | 14 | 4 | 0.263 | 0.200 | 0.227 | Best of the frozen-style format prompts |
| Exact v8 bytes | v8 with two version labels changed | 14 | 4 | 0.353 | 0.240 | 0.286 | Highest format result |

The v8d variant kept the v7 system and added the measured flag-contract paragraphs. It screened at F1 0.227 on the format subset, with a category-agnostic F1 of 0.318, seven of 19 findings flagged and four equivalence flags. It became prompt version 8 for the research run, with the v7 example bytes.

The exact v8 bytes then differed from v8d only in two version labels, the title and the flag-section heading. The exact bytes were screened again on the format subset and reached F1 0.286, with category-agnostic precision 0.471, recall 0.320 and F1 0.381, four exact results and eight of 17 findings flagged, including five equivalence groups. That is the highest format-subset F1 in the line.

The label-only result is a warning, not a quality claim. Two version strings shifted a deterministic 14-target result from 0.227 to 0.286 with no semantic prompt change. The range across the format prompts is wide, 0.154 to 0.286, and the subset has 14 valid targets. Within the first sweep the exact v8 bytes were not run on the full 50, so that sweep left their full-50 agreement unmeasured. The re-tuning night ran them as the v8 control, with 47 valid results of 50 and F1 0.244.

## Blind support and the flag audit

### Support by trial

The saved findings of frozen v7, v8b and the exact v8 bytes were judged blind in the first flag audit, which is separate from the re-tuning judge pass over 324 claims. The 89 unique claims came from 86 in v7 or v8b plus three that the exact v8 bytes added. The occurrences were 60, 76 and 17. Every claim was judged once, and the verdict was reused for the same claim in every trial that carried it.

| Trial | Findings | Required supported | Recommended supported | Equivalence supported | All supported |
|---|---:|---|---|---|---|
| Frozen v7 | 60 | 15/29 (0.52) | 8/13 (0.62) | 13/18 (0.72) | 36/60 (0.60) |
| v8b | 76 | 16/36 (0.44) | 15/20 (0.75) | 17/20 (0.85) | 48/76 (0.63) |
| Exact v8 bytes, 14-target screen | 17 | 5/8 (0.62) | 2/3 (0.67) | 5/6 (0.83) | 12/17 (0.71) |

The verdict counts were 36 supported, 13 partly, nine unsupported and two unclear for v7, 48 supported, 13 partly, 13 unsupported and two unclear for v8b, and 12 supported, three partly, two unsupported and no unclear for the exact v8 bytes. The unique-claim totals were 53 supported, 19 partly, 14 unsupported and three unclear out of 89, or 0.60 supported.

The exact v8 figure has a 14-target denominator and is not a 50-target result. It is also the smallest sample. That row is the 14-target format screen. The 50-target v8 control, with 59 findings over 47 valid targets, belongs to the re-tuning table and not to this 89-claim audit. The v7 and v8b figures share the same 49 targets and the same judge pass.

On those same 49 targets, the reference model's own CE-only answers were also judged. The matched comparison removes the different target mix that a comparison against all 200 reference answers would carry.

| Source, same 49 targets | Required | Recommended | Equivalence | Findings |
|---|---|---|---|---|
| DeepSeek V4.1 Flash, v6 CE-only | 24/46 (0.52) | 14/21 (0.67) | 15/23 (0.65) | 90 |
| ByteShape frozen v7 | 15/29 (0.52) | 8/13 (0.62) | 13/18 (0.72) | 60 |
| ByteShape v8b | 16/36 (0.44) | 15/20 (0.75) | 17/20 (0.85) | 76 |

The local judged support is close to the reference model's on the same targets. It is better on equivalence, comparable on recommended and similar to worse on required. ByteShape emitted fewer claims than the reference model on those targets, yet produced more outright unsupported required claims, six for v7 and 10 for v8b against four for the reference. The reference model's equivalence row is the less reliable one because 45 of its 86 groups were judged against the target instead of only among group members. Each ByteShape equivalence group was judged against its own member set.

This is a precision measure over emitted claims. It cannot reward a prerequisite that the model omitted, and it is not a recall measure. The support rates and the corrected-reference F1 therefore answer different questions, and the gap between them is expected.

### Flags and routing metadata

The flag behaviour of the saved runs is below. A flag occurrence is counted independently, so a finding with two flags appears under both flags and once under the any-flag total. The three judged trials of this audit are frozen v7, v8b and the exact v8 bytes on the 14-target format screen. The other rows are listed for their flag counts.

| Run | Findings | Flagged | Multi-flag | `requiredness_uncertain` | `directness_uncertain` | `member_uncertain` | `group_scope_uncertain` |
|---|---:|---:|---:|---:|---:|---:|---:|
| Candidate 4 | 66 | 17 | 0 | 14 | 2 | 0 | 1 |
| Frozen v7 | 60 | 16 | 0 | 13 | 2 | 0 | 1 |
| v8b | 76 | 33 | 0 | 21 | 2 | 0 | 10 |
| Exact v8 bytes, 14-target format screen | 17 | 8 | 0 | 3 | 0 | 0 | 5 |
| v8d, 14-target format screen | 19 | 7 | 0 | 3 | 0 | 0 | 4 |
| v8 control, 50 targets (47 valid) | 59 | 29 | 1 | 14 | 4 | 0 | 12 |
| c4 flags, later v9 | 58 | 25 | 0 | 10 | 1 | 1 | 13 |

Across the three judged trials the flags were 37 `requiredness_uncertain`, 16 `group_scope_uncertain` and four `directness_uncertain`, with no `member_uncertain`. `requiredness_uncertain` dominated and sat almost entirely on recommended options. Every recommended occurrence in those three trials was flagged `requiredness_uncertain`, 36 of 36. The 50-target v8 control sits outside those three trials: its 30 flag occurrences fall on 29 findings, 14 `requiredness_uncertain`, 12 `group_scope_uncertain` and four `directness_uncertain`, with no `member_uncertain`.

| Group | Findings | Supported | Partly | Unsupported | Unclear |
|---|---:|---:|---:|---:|---:|
| Any flag | 57 | 40 (0.70) | 7 | 7 | 3 |
| No flag | 96 | 56 (0.58) | 22 | 17 | 1 |

The mild difference runs the wrong way for a precision signal. It is a category confound, not separation. Recommended is better supported than required, and every recommended finding is flagged. By contrast, the required options flagged `requiredness_uncertain` are not the unsupported required options. The flags mark the model's required-or-recommended boundary uncertainty, not weak teaching-text support.

Target routing metadata behaved the same way. Routing confidence was 0.9 on almost every target and routing flags were nearly absent. The table counts only the targets that emitted at least one finding. The routing-flag counts in the paragraph below cover every valid target.

| Trial | Targets with findings | Targets with any routing flag | Routing confidence values |
|---|---:|---:|---|
| Frozen v7 | 32 | 0 | 0.9 on 31, 0.85 on 1 |
| v8b | 31 | 1 (`directness_ambiguity`) | 0.9 on 30, 0.8 on 1 |
| Exact v8 bytes, 14-target screen | 9 | 0 | 0.9 on 9 |

The one flagged target in v8b had one finding, judged supported. The v7 target at 0.85 had two findings, both judged partly. These are single-target observations, not a signal. Across all valid targets, routing flags were almost always `insufficient_course_information`, 11 for v7, 11 for v8b and two for the exact v8 bytes, plus the one `directness_ambiguity`. Most of those targets emitted no finding to judge.

Neither per-finding flags nor routing metadata separated support on the tuning set. No cutoff or demote rule was fitted from those results.

## Retuning on the same 50

### The funnel and the variants

The re-tuning asked whether broad prompt changes could reduce outright unsupported findings, especially false required claims, while keeping useful coverage and improving category correctness. It used the same 50 targets and the same deterministic five-target batches, in size order. Batch 10 carries the oversize packet.

A variant first ran a 10-target screen, the union of batches 1 and 7. A promising variant then ran a fixed 20-target set, batches 1, 4, 7 and 10, identical for every variant. Only a variant that completed the fixed 20 could run the full 50. Thirteen variants ran. Six were drafted before the night with the targeted amendments below. Seven more followed, identified by direction: entry test, deliver test, pressure removal, strict required, flags discipline, flags with pressure removal, and an older-or-overlapping-code rule. The tier column names the furthest of the three: the 10-target screen, the fixed 20, or the full 50.

| Variant | Targeted amendment | Tier reached | Targets saved | Outcome |
|---|---|---|---:|---|
| v8 control | Exact v8 bytes | 50 | 50 | 47 valid, 1 context overflow, 2 transport errors |
| c1 overlap | Near-identical, older or other-code course becomes overlap or equivalence, never a prerequisite | 10 | 10 | 10 valid |
| c2 target teaches | Material the target itself delivers is not required entry knowledge | 10 | 10 | 10 valid |
| c3 entry discipline | Strict required boundary, omission preferred to a wrong required claim | 50 | 50 | 49 valid, 1 context overflow |
| c4 flags | Deliberate multi-flag use with worked doubt combinations | 50 | 50 | 49 valid, 1 context overflow |
| c5 combined | c1, c2, c3 and c4 combined | 20 | 20 | 19 valid, 1 context overflow |
| c6 | Earlier, parallel or renamed equivalents of the target are never required entry knowledge: use a recommended option for background the target does not deliver, a course-wide equivalence group when interchangeable, or overlap suppression otherwise | 20 | 20 | 19 valid, 1 context overflow, 50 listed but unfinished |
| c7 entry test | Entry test | 10 | 10 | 10 valid |
| c8 deliver test | Deliver test | 10 | 10 | 10 valid |
| c9 no pressure | Pressure removal | 50 | 50 | 49 valid, 1 context overflow |
| c10 strict required | Strict required | 50 | 50 | 49 valid, 1 context overflow |
| c11 flags discipline | Flags discipline | 10 | 10 | 10 valid, 20 listed but 10 saved |
| c12 flags and no pressure | Flags with pressure removal | 50 | 50 | 49 valid, 1 context overflow |

The c6 trial listed all 50 targets but saved 20, and the c11 trial listed 20 but saved 10. Both stopped before completing the listed set. They are unfinished attempts, not 50-target results. The c6 direction is recorded in its saved system prompt, which names earlier versions, parallel implementations and renamed equivalents of the target and excludes them from required entry knowledge. The variants that stopped below the full 50, c5, c6 and c11, were not blind-judged. They carry corrected-reference diagnostics but no support verdicts.

The six full-50 candidates were judged once each, in two judging sessions of three, with the same rubric and no re-judging. Their reports hold 59, 64, 58, 49, 44 and 50 claims, 324 in total. Those are emitted claim occurrences, and they are separate from the 89 unique claims of the earlier flag audit. The v8 control ran on the same night, which matters because the historical v8b audit had 10 unsupported required findings out of 36, while the same-night control had three out of 30. Cohort and judge-pass differences dominate that gap. Only the same-night control is used for the selection.

### Blind judgment of six candidates

| Candidate | Claims | Supported | Partly | Unsupported | Unclear | Unsupported required |
|---|---:|---|---:|---:|---:|---|
| v8 control | 59 | 32 (0.542) | 21 | 4 (0.068) | 2 | 3/30 (0.100) |
| c3 entry discipline | 64 | 35 (0.547) | 18 | 8 (0.125) | 3 | 8/33 (0.242) |
| c4 flags | 58 | 35 (0.603) | 20 | 1 (0.017) | 2 | 1/29 (0.034) |
| c12 flags and no pressure | 49 | 36 (0.735) | 10 | 3 (0.061) | 0 | 3/26 (0.115) |
| c9 no pressure | 44 | 22 (0.500) | 18 | 4 (0.091) | 0 | 3/25 (0.120) |
| c10 strict required | 50 | 33 (0.660) | 13 | 4 (0.080) | 0 | 3/26 (0.115) |

The per-category counts show where the support sits. Each cell is findings, supported, partly, unsupported and unclear.

| Candidate | Required | Recommended | Equivalence |
|---|---|---|---|
| v8 control | 30 / 13 / 13 / 3 / 1 | 12 / 7 / 3 / 1 / 1 | 17 / 12 / 5 / 0 / 0 |
| c3 entry discipline | 33 / 14 / 9 / 8 / 2 | 13 / 9 / 3 / 0 / 1 | 18 / 12 / 6 / 0 / 0 |
| c4 flags | 29 / 17 / 10 / 1 / 1 | 9 / 4 / 4 / 0 / 1 | 20 / 14 / 6 / 0 / 0 |
| c12 flags and no pressure | 26 / 17 / 6 / 3 / 0 | 8 / 6 / 2 / 0 / 0 | 15 / 13 / 2 / 0 / 0 |
| c9 no pressure | 25 / 9 / 13 / 3 / 0 | 6 / 1 / 4 / 1 / 0 | 13 / 12 / 1 / 0 / 0 |
| c10 strict required | 26 / 13 / 10 / 3 / 0 | 9 / 8 / 0 / 1 / 0 | 15 / 12 / 3 / 0 / 0 |

c4 flags is the unique minimum on outright unsupported findings, one, and on unsupported required findings, one of 29. The v8 control had four and three of 30. c3 moved the other way, with eight and eight of 33. The entry-discipline direction did not reduce unsupported findings on this cohort. c12, c9 and c10 each had three unsupported required findings, and none beat c4 on either measure.

The chart plots the unsupported counts from the table above. c4 sits alone at the minimum.

![Outright unsupported findings for six prompt candidates on the 50 tuning targets. c4 flags holds one, and the other five hold between three and eight.](/docs/charts/inference-prompt-unsupported-by-candidate.svg)

The secondary corrected-reference scores did not rank the candidates the same way. c9 had the highest overall F1, 0.258, but four unsupported findings. c4 had 0.246 and one. The reference over c4's 49 valid re-tuning targets holds 80 findings against c4's 58, the same 80-finding reference as the first sequence, so recall is low by construction and does not track the judge.

An earlier summary of the re-tuning put that reference at 78 findings. The saved score records 80 findings over the same 49 valid targets and the same per-target reference counts as the first sequence. The 78 was a summary error, not a different cohort, and 80 is the value that stands.

| Candidate | Valid | Overall F1 | Required / recommended / equivalence F1 | Swapped-category near matches | Right-course F1 |
|---|---:|---:|---|---:|---:|
| v8 control | 47 | 0.244 | 0.346 / 0.000 / 0.412 | 4 | 0.268 |
| c3 entry discipline | 49 | 0.236 | 0.316 / 0.000 / 0.410 | 3 | 0.229 |
| c4 flags | 49 | 0.246 | 0.340 / 0.000 / 0.390 | 3 | 0.247 |
| c12 flags and no pressure | 49 | 0.248 | 0.320 / 0.000 / 0.444 | 3 | 0.237 |
| c9 no pressure | 49 | 0.258 | 0.327 / 0.000 / 0.471 | 4 | 0.267 |
| c10 strict required | 49 | 0.231 | 0.280 / 0.000 / 0.444 | 5 | 0.255 |

The chart below plots the F1 values of the nine variants that ran on the 50: candidate 4, frozen v7, v8b and the six re-tuning candidates. The values lie between 0.218 and 0.258. Eight variants scored over 49 valid targets and the same 80-finding reference. The v8 control scored over its 47 valid targets, where the reference holds 72 findings, because its two transport errors removed `LAAL.615`, with seven reference findings, and `AUT.250`, with one, and its context overflow removed none. Its 0.244 is not directly comparable with the other eight, and the range mixes the two denominators. The prompt changes moved format behaviour and support counts more than they moved this secondary agreement score.

![Corrected-reference F1 for nine prompt variants on the 50 tuning targets. Eight scored over 49 valid targets and the v8 control over 47, where the reference holds 72 findings. The nine values span 0.218 to 0.258, and c9 no pressure holds the highest at 0.258.](/docs/charts/inference-prompt-f1-by-variant.svg)

| Variant | Valid | Reference findings | Exact whole result | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Candidate 4 | 49 | 80 | 16 | 0.273 | 0.225 | 0.247 |
| Frozen v7 | 49 | 80 | 14 | 0.267 | 0.200 | 0.229 |
| v8b | 49 | 80 | 14 | 0.224 | 0.212 | 0.218 |
| v8 control | 47 | 72 | not recorded | not recorded | not recorded | 0.244 |
| c3 entry discipline | 49 | 80 | not recorded | not recorded | not recorded | 0.236 |
| c4 flags, later v9 | 49 | 80 | not recorded | not recorded | not recorded | 0.246 |
| c9 no pressure | 49 | 80 | not recorded | not recorded | not recorded | 0.258 |
| c10 strict required | 49 | 80 | not recorded | not recorded | not recorded | 0.231 |
| c12 flags and no pressure | 49 | 80 | not recorded | not recorded | not recorded | 0.248 |

### The selected v9 prompt

The c4 flags variant became prompt version 9 with schema version 2. The frozen system prompt equals the judged c4 system prompt except for three heading-level labels, the top heading and the flag-section heading changed from v8 to v9, and the appended section heading dropped its draft label. No instruction text changed. The examples parse identically to the examples c4 inherited from v8.

The selection is a small-sample directional result, not a proven quality gain. It rests on one judge pass over 58 claims, where c4 had one unsupported finding against four in the same-night control. The flags did not clearly isolate the errors. The single unsupported claim was unflagged, and the two unclear claims carried `requiredness_uncertain` and `member_uncertain`. The judged c4 cohort carries no multi-flag finding even though the selected instruction added multi-flag guidance. The same-night v8 control, whose prompt lacks that section, carries one two-flag finding.

## The held-out check and the cutoff rule

### Held-out validity and support

Prompt version 9 was then run on the 150 held-out targets. It returned 150 valid results from 150 attempts, with no invalid output, no context overflow and no skip. The largest attempted prompt was 92,815 tokens, so every packet fitted the 118,784-token first key. Mean wall clock was 60.5 seconds per complete target, median 59.0, range 18 to 143. Median prompt rate was 775 tokens per second and median decode rate 43.2.

The blind support over the 150 was lower than the tuning cohort's support. The tuning c4 support was 35 of 58, 0.603, while v9 on the held-out 150 supported 88 of 168, 0.52. The two figures come from different cohorts and separate judge passes, so the difference is not a direct prompt effect. The 150 is the better estimate because those targets were not used for tuning.

| Category | Supported / findings | Rate | Outright unsupported |
|---|---|---:|---:|
| Required | 41/97 | 0.42 | 22 |
| Recommended | 15/24 | 0.62 | 2 |
| Equivalence | 32/47 | 0.68 | 2 |
| All | 88/168 | 0.52 | 26 |

The full verdict counts were 88 supported, 52 partly, 26 unsupported and two unclear. Required is the weak category, with 22 outright unsupported findings. Recommended and equivalence were stronger, with two unsupported findings each.

| Cohort | Precision | Recall | F1 | Structurally equal |
|---|---:|---:|---:|---:|
| 150 held-out | 0.286 | 0.201 | 0.236 | 47/150 |
| 100 fit targets | not recorded | not recorded | 0.230 | not recorded |
| 50 validation targets | not recorded | not recorded | 0.247 | not recorded |

The reference holds 239 findings over the 150, against 168 emitted. The whole-result score is again a disagreement diagnostic, not an accuracy score. The held-out result confirmed that the prompt produces valid structured output at scale, while agreement remained low.

### The fitted cutoff rule and its rejection

The held-out work also tested whether confidence and per-finding flags could support a drop or demote rule. No cutoff had been fitted from the 50 tuning results, because flags and routing did not separate support there. Candidate rules were fitted on the 100 held-out fit targets instead, a confidence threshold at 0.90 with an optional demotion of required options flagged `requiredness_uncertain`, and applied unchanged to the distinct 50 validation targets. Confidence ran the wrong way, flags marked supported findings more often than unsupported ones, and no rule improved either set. The policy selected afterwards applies no confidence cutoff, no flag cutoff, no finding drop and no demotion, and keeps confidence and flags as raw evidence. The product applies the same no-cutoff policy at publication, as [Inference](/docs/backend/inference/inference.md#proposals-and-publication) states. [Confidence calibration and corrected reference judgments](/docs/experiments/inference/confidence-and-corrected-references.md) reports the rule fit and its validation in full.

The selected policy pairs the v9 prompt and schema version 2 with Qwen3.8-27B IQ3-MIX. It keeps every emitted recommended option and retains confidence and flags as raw evidence. The held-out comparison of the models and the quality of the selected model are reported on [held-out model quality](/docs/experiments/inference/held-out-model-quality.md), and the full-catalogue execution of that policy is reported on [full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md). The ByteShape v9 result is the prompt's quality measurement on targets outside the tuning cohort, and ByteShape is not the selected model.

## What the numbers support

### Observed

Prompt tuning moved ByteShape from the v6 baseline F1 of 0.100 to a plateau. Candidate 4 reached 0.247, frozen v7 0.229, v8b 0.218 and v9 0.246 on the 50. Across the nine full-50 variants the range is 0.218 to 0.258. The format target was met early. Across the six first-sequence trials, 84 target results were valid and none returned invalid complete-target output, and every 50-target ByteShape run had zero invalid output. The only non-valid outcome on a fitting packet was a transport drop, never a malformed result.

Blind support was 0.60 for v7, 0.63 for v8b and 0.71 for the exact v8 bytes on 14 targets. On the same 49 targets it was close to the reference model's 0.60, with better equivalence, comparable recommended and similar-to-worse required support. The held-out v9 run supported 0.52 of 168 findings and returned 150 of 150 valid results.

### Interpreted

The prompt solved the format and grouping contract but did not solve membership. Candidate 4's 66 findings contained only 22 member sets present anywhere in the reference, and a perfect relabelling would cap F1 at 0.301. The remaining gap is a different view of which courses belong, not only a wrong required-or-recommended label.

The flags describe the model's own decision boundary. `requiredness_uncertain` marks recommended options and the required-or-recommended judgement, not weak teaching-text support. The near-constant routing confidence has the same character. A filter built on either signal would remove supported claims and keep most harmful ones.

The 15-target format subset is a screen for validity and flag behaviour, not a quality estimate. The label-only v8 shift from 0.227 to 0.286 shows that a deterministic model can be sensitive to prompt bytes, and the subset's own swing is about plus or minus 0.03. The 50-target runs and the 150-target held-out run carry the quality claims.

### Failed hypotheses

- A worked example with flags plus flag-use guidance would make the model emit flags. Candidate 3 emitted none.
- A completeness prompt would improve whole-result agreement. v8b added findings and false positives without improving F1.
- A strict required boundary would reduce false required claims. c3 increased unsupported required findings to eight of 33.
- A higher temperature would improve agreement. The 0.3 trial fell to F1 0.154.
- Confidence or flags would separate harmful findings. The held-out fit found the opposite direction, and no rule survived validation.
- A label-only prompt edit would leave a deterministic format score unchanged. Two version strings moved it from 0.227 to 0.286.

## Limitations

The corrected reference is a single DeepSeek sample corrected for emitted-finding precision. It cannot recover a missing prerequisite, and 16 of the 49 valid tuning targets have an empty reference. The skipped `MEDAYLKKOE` is the seventeenth empty reference in the 50. The reference has more findings than any model emits, 80 against 66 for candidate 4 and 80 against 58 for c4 on the same 49 valid targets, so recall and F1 are low by construction. The reference also inherits the equivalence judge flaw described in [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md), where 45 of 86 groups were compared with the target rather than only among members.

The judged support is precision over emitted claims. It cannot reward an omitted prerequisite, and a model that emits fewer, safer claims can show a higher supported share. The support rates are comparable only beside their emission counts and their cohort. The judge is one model applying one rubric, no human agreement measurement exists, and the judge saw truncated teaching text.

The samples are small. The format subset has 15 targets, 14 valid, and the full tuning cohort has 50 targets, 49 valid. The exact v8 support figure rests on 17 findings from 14 targets. The re-tuning judged six candidates once each, with no repeat judgment. The held-out support rests on one run of 150 targets. The first flag audit's 89 unique claims came from three trials and were not independently resampled. The re-tuning judge pass covered 324 claims from six candidates, each judged once.

The tuning cohort was used repeatedly across prompt versions. That is the nature of tuning, but it makes the 50 a poor estimate of an unseen prompt's quality. The 150 held-out targets are the better check, and even they were used to fit and validate the cutoff rule and to compare models. The held-out v9 support of 0.52 is the better estimate than the tuning c4 value of 0.603.

Some variants are incomplete. c6 listed 50 targets but saved 20, and c11 listed 20 but saved 10. The c5, c6, c11 and four screen variants were not blind-judged. Their corrected-reference diagnostics are recorded but do not carry support verdicts. The exact v8 bytes ran on the 50 only as the same-night control of the re-tuning.

The run had operational failures. A detached launch left two racing runners on one trial. Both were stopped and the trial restarted. Transient transport drops were retried. The re-tuning night lost time to model context-allocation failures, worker reboots and one duplicate model process. The night ran about 11.2 hours of wall clock, with about 35 minutes of reboots and roughly two hours of recovery, leaving about 8.5 to 9 hours of target processing against a roughly 10-hour minimum. The work stopped at the budget, not at a quality bar.

One judge batch first returned verdicts outside the four-value vocabulary, six `plausible` and three `insufficient_evidence`. The output was saved unchanged, and the same session re-emitted the 48 judgments with the four values and the same input. No label was converted or invented. The final output covers all 48 items.

The model, runtime and hardware are one configuration. A different quantization, KV cache type, runtime revision or prompt byte sequence could change both validity and quality. The speed figures are generation wall clock and exclude model loads and reboots.

## Setup details

| Parameter | Value |
|---|---|
| Tuning cohort | 50 targets, size quantiles of 200 CE-only packets, integer-floor indices `(i*199)//49` |
| Format subset | 15 targets, integer-floor indices `(i*49)//14` over the tuning size order |
| Held-out cohort | 150 targets, the complement of the tuning 50 |
| Fit and validation split | 100 fit targets and 50 distinct validation targets within the 150 |
| Packet | CE-only top 50, fixed before any model output |
| Model | ByteShape Qwen3.8-27B IQ3_S, 3.23 bits per weight, 11.0 GB artifact |
| Context and cache | 118,784 tokens with MTP and `q8_0` KV. The 150 fitted the first key and did not load the 147,456-token no-MTP key |
| Generation | Thinking off, temperature 0, seed 0, 8,192 output tokens, 300-second timeout |
| Prompt versions | v6 baseline, v7 checkpoint, v8 checkpoint, v9 selected |
| Schema | v1 for the baseline, v2 with required `finding_flags` for v7 to v9 |
| Flags | Option flags `requiredness_uncertain`, `member_uncertain` and `directness_uncertain`. Equivalence flags `member_uncertain` and `group_scope_uncertain` |
| Finding score | Category-aware member-set match, micro over valid targets, against the corrected reference |
| Whole-result score | Exact match of every category and member set. Category-agnostic and right-course variants are also recorded |
| Judge | Blind four-verdict support. The first flag audit judged 89 unique claims from three trials. The re-tuning pass judged 324 claims from six candidates, once each |
| Cutoff fit | Candidate drop and demote rules fitted on 100 fit targets and applied unchanged to 50 validation targets |
| Selected policy | Prompt v9 and schema v2 with Qwen3.8-27B IQ3-MIX. No confidence or flag cutoff, no drop or demotion and no uncertainty-triggered reroute |

## Untested follow-ups

1. A human re-read of the judged claims would put a number on the judge's error and on the support rates. The first flag audit holds 89 unique claims and the re-tuning pass holds 324 claims. No such measurement exists.
2. A second sample per target would separate prompt effects from sampling noise. Every saved ByteShape result here is one sample per target.
3. A trial with more two-flag findings would test whether the flag vocabulary can carry two independent doubts at a useful rate. The counted runs hold one two-flag finding, in the v8 control.
