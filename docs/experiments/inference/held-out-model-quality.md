# Held-out local model quality

This report measures how well the local language models proposed prerequisites on held-out courses and which model configuration the project selected.

**Evidence status:** Comparative. **Run dates:** 28 and 29 September 2026.

The [Experiments section](/docs/experiments/README.md#inference) states the catalogue, the hardware specifications and the evidence labels. This report covers one line of the inference work: the quality of the local models' answers on target courses they had not been tuned on, and the model and policy chosen from that comparison. The [local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md) report covers fit, memory and speed. The [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) page covers the reference answers, the judge and the verdict rubric. Candidate retrieval and packet selection are separate reports.

Three models produced judged findings on the held-out cohort, and the difference between their judged support carries the main claim. The [Inference experiments](/docs/experiments/inference/README.md) overview places this report in the category.

## The question

[Inference](/docs/backend/inference/inference.md#what-inference-produces) asks one local model to propose the prerequisites of one target course from 50 candidate courses. The packet bounds what the model can name, and the prompt and schema bound the form of the answer. One unit of an answer is a finding: one required option, one recommended option or one equivalence group. The remaining question is whether the answer is right: whether a named course is knowledge the target expects on entry, whether the required or recommended category is right, and whether an equivalence group is course-wide.

This line measured that question on courses the model had not been tuned on. It asked four things. Which local model produced the strongest supported findings? Was its answer valid often enough to run? Could its own confidence and finding flags remove harmful claims without removing supported ones? And which model and routing policy should produce the catalogue?

The quality ranking this report uses places a right course in the right category first, a right course in the wrong required or recommended category second, and an omission third. A course that is not a prerequisite at all is the error that matters. That ordering is why an unsupported required finding carried more weight than an omitted finding, and why unsupported counts stand beside every support rate in this report.

Quality here is not candidate recall. A course missing from the 50-candidate packet is invisible to every model, and no model quality can recover it. [Candidate retrieval and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md) and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) measure that side. Speed is also separate. The model with the fastest decode in the earlier fixed-prompt measurements produced no valid answer at all, and the fastest per complete target did not produce the strongest support.

## The held-out packets and the comparison

The comparison used 200 active target courses with a representative version, fixed before any answer was generated. They are disjoint from the fixed 100-target development set that the prompt checks used, and courses used in prompt examples are excluded from the set and from its candidate lists. Each target has a CE-only packet, meaning 50 candidates selected by the cross-encoder alone from a 1,000-candidate pool. The packet carries the target and the candidate descriptors with their teaching text. It carries no retrieval score, rank value or official prerequisite label.

The four local artifacts are Qwen3.8-27B IQ3_S ByteShape, Qwen3.8-27B IQ3-MIX (MIX below), Qwen3.6-35B-A3B UD-IQ3_S and gpt-oss-20b MXFP4.

The 200 split into two groups fixed before any output. The 50 tuning targets were used to tune ByteShape's prompt and were not part of the comparison. The other 150 were the held-out complement, never used to tune ByteShape. Before any output existed, the 150 were ordered by rendered CE user-prompt character length and target identity. The 50 comparison targets are the size quantiles at the integer-floor indices `(i * 149) // 49` for `i = 0` to `49`, so the smallest and largest packets are included. Their rendered user-prompt sizes span 38,967 to 270,860 characters. The 50 is the shared comparison cohort and the distinct-target validation set for any ByteShape drop or demote rule. The other 100 are the rule-fit set.

The ByteShape trial ran all 150. The three comparison models ran the shared 50. Later the same night, MIX ran the other 100 as a distinct trial, so MIX also covers 150. The original 50 MIX results and the ByteShape 150 were not rerun or overwritten. The 123 findings from the other 100 were judged once, in their own batches, and the original 50 findings were not re-judged.

Official prerequisite labels were absent from every packet, prompt, request and judge item. The cohort's labels had been read in an earlier retrieval measurement, so the 200 are not an untouched holdout for ranking policy. That does not affect the answer quality comparison, because no label entered an input and the judge read only teaching text.

## Models and settings

| Model | Artifact | Context used | KV cache | Targets | Valid | Findings |
|---|---|---|---:|---:|---:|---:|
| Qwen3.8-27B IQ3_S ByteShape | 11.0 GB, 3.23 bits per weight | 118,784 tokens, MTP | `q8_0` | 150 | 150 | 168 |
| Qwen3.8-27B IQ3-MIX | 12.6 GB | 131,072 tokens, MTP | `q4_0` | 150 | 150 | 178 |
| Qwen3.6-35B-A3B UD-IQ3_S | 13.7 GB | 212,992 tokens | `q4_0` | 50 | 48 | 109 judged |
| gpt-oss-20b MXFP4 | 12.1 GB | 131,072 tokens, native | `q8_0` | 50 | 0 | 0 |

The artifact sizes are decimal GB. MTP is the artifact's multi-token prediction mode. KV is the key-value cache, and the quantization shown is the one the trial used. The MIX artifact also has a 163,840-token no-MTP key with `q4_0` KV. It was available, and no target in the 150 needed it. ByteShape's 147,456-token no-MTP key was likewise unused. Nemotron-3-Nano-30B-A3B, an 18.1 GB weights artifact, was dropped before this comparison and does not appear in the table. Its two-packet probe returned one valid result, took 261 seconds on the smallest packet, and took 1,654 seconds on the largest, which was truncated at 8,192 completion tokens and returned invalid JSON. That fit and speed measurement is on the [hardware report](/docs/experiments/inference/local-model-hardware-and-throughput.md).

The largest ByteShape packet used 92,815 prompt tokens and fitted its 118,784-token key. No ByteShape target was skipped or truncated. MIX fitted every target at its first key, with no skip, truncation or context overflow. Qwen3.6 had no context overflow and two invalid answers. gpt-oss had no context overflow and no valid answer.

## Prompt and request settings

The held-out run used the frozen v9 prompt and schema version 2, rendered by the product request renderer. Every model saw the same packet bytes, prompt text, schema and generation settings for a target. The 150 were never used to tune ByteShape, so the comparison is held out from that tuning.

The prompt was frozen on the 50 tuning targets before the 150 run. The run preparation had fixed the cohort with a v8 prompt and found the hardware gate unmet, because the discrete GPU still drove the displays. No model started on that night. Before the first held-out attempt the prompt version was changed to v9, and v8 was never run on the 150. The run preparation recorded v8 as its prompt, so that entry is a preparation label rather than a record of the run prompt. Every held-out trial used v9 and schema version 2. The wording of the prompt and its tuning history belong to a separate line of prompt work.

| Setting | Value |
|---|---|
| Prompt version | v9 |
| Result schema | Version 2 |
| Prompt renderer | The product request renderer |
| Thinking | Off |
| Temperature | 0 |
| Seed | 0 |
| Output token cap | 8,192 |
| Request timeout | 300 seconds |
| Samples per target | One |
| Invalid response handling | Retained as invalid, not requested again |
| Transport failures | Retried, with the attempt count recorded |
| Resume | One raw record per target, completed targets skipped |

### What validity covers

Validity here means the response parsed against the strict result schema. The local runner did not also check that every named course appeared in the supplied packet. One Qwen3.6 finding named `HIS.HIA.100`, a course its packet did not carry. The judge had no supplied teaching text for that course, so the finding was recorded as unjudgeable and is excluded from the judged totals. The other findings were judged normally. This is a model failure and a limit of this comparison's validity check. The reference corpus used a stricter check that also required every named code to appear in its packet.

## Answer validity and generated volume

| Model | Targets | Valid | Invalid | Findings judged | Observation |
|---|---:|---:|---:|---:|---|
| ByteShape | 150 | 150 | 0 | 168 | All targets at the 118,784-token key, no skip |
| MIX | 150 | 150 | 0 | 178 | 55 findings on the first 50, 123 on the other 100 |
| Qwen3.6-35B-A3B | 50 | 48 | 2 | 109 | Two invalid answers retained, one further finding unjudgeable |
| gpt-oss-20b | 50 | 0 | 50 | 0 | Empty content on every attempt |

Generated volume matters to every rate below. The 168 ByteShape findings come from 107 of its 150 targets. The other 43 targets returned a complete result with no option and no equivalence group, which is a complete empty result and not a missing target. The support rate is therefore a rate over findings, not over targets, and it says nothing about the 43 targets that emitted none.

The gpt-oss failure is a model and runtime interaction, not a slow answer. All 50 attempts returned HTTP 200 with `finish_reason=length`, 8,192 completion tokens and empty content, because the harmony analysis channel consumed the whole output cap.

The cap and the request shape were tested on the identical 50 packets. Raising the cap to 32,768 produced 32,768 tokens of reasoning and no content. Server-side reasoning off and low, server-default payloads, request-level `enable_thinking`, request-level `reasoning_effort`, `--reasoning-budget 0` and `--reasoning-format none` all failed. One request shape returned HTTP 500 with a `peg-native` format error. Another moved the harmony control tokens into the content and produced no valid JSON. A second full 50-target run was not launched, because no probe produced valid output.

The JSON grammar forced an object while the model tried to emit channel tokens, and the output degenerated into repetition. The two older runtime revisions available predate the reasoning flag and fail to start for this model, so the pinned revision was the only compatible runtime. No valid gpt-oss result exists, and no substitute was used for it.

Qwen3.6 returned 48 valid answers from 50 targets. The two invalid responses were retained as invalid and were not repaired. Its 109 judged findings carry the support rates below, and the one unjudgeable finding is outside them. The two invalid answers are a quality result in their own right: an invalid answer cannot become a proposal.

## Judged support

Every finding that could be judged was judged blind against the teaching text the model had been given, by the same judge model and rubric as the reference corpus, which [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) describes. The batch was shuffled with seed 20260928 and split into batches of 48. One fresh read-only session judged each batch, serially. No batch was re-judged and no substitute judge was used.

The verdicts are `supported`, `partly`, `unsupported` and `unclear`. A `supported` verdict means the supplied teaching text supports the claim under the rubric. A `partly` verdict can mean a partial AND option or a wrong category, and the local `partly` findings were not re-judged at a finer grain. `partly` and `unclear` are never folded into `supported`. The rubric and the limits it imposes are on [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md#limits-of-judged-support).

| Model | Findings | Supported | Partly | Unsupported | Unclear | All rate | Required rate | Recommended rate | Equivalence rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ByteShape | 168 | 88 | 52 | 26 | 2 | 0.52 | 0.42 | 0.62 | 0.68 |
| MIX | 178 | 111 | 51 | 15 | 1 | 0.62 | 0.54 | 0.81 | 0.61 |
| Qwen3.6-35B-A3B | 109 | 25 | 39 | 38 | 7 | 0.23 | 0.14 | 0.31 | 0.29 |

| Model | Required supported | Required unsupported | Recommended supported | Recommended unsupported | Equivalence supported | Equivalence unsupported |
|---|---|---|---|---|---|---|
| ByteShape | 41/97 | 22 | 15/24 | 2 | 32/47 | 2 |
| MIX | 54/100 | 15 | 38/47 | 0 | 19/31 | 0 |
| Qwen3.6-35B-A3B | 7/49 | 20 | 12/39 | 12 | 6/21 | 6 |

MIX supported 37 of 55 findings on the first 50, a rate of 0.67, and 74 of 123 on the other 100, a rate of 0.60. Its required support was 22/32 on the first 50, 0.69, and 32/68 on the other 100, 0.47. Its equivalence support was 4/10, 0.40, on the first 50 and 15/21, 0.71, on the other 100. The combined 150 rows are the ones in the table above.

| MIX cohort | Findings | Supported | All rate | Required rate | Recommended rate | Equivalence rate |
|---|---:|---:|---:|---:|---:|---:|
| First 50 | 55 | 37 | 0.67 | 0.69 | 0.85 | 0.40 |
| Other 100 | 123 | 74 | 0.60 | 0.47 | 0.79 | 0.71 |
| Combined 150 | 178 | 111 | 0.62 | 0.54 | 0.81 | 0.61 |

ByteShape's result on the shared 50 was 28 supported findings of 59, a rate of 0.47, and its required support there was 0.44. The full 150 result is stronger on the all-findings rate, 0.52. Both values come from the same single sample per target, so the difference is a cohort observation rather than a change in the model.

The chart compares the three models' supported shares for all findings and for each category.

![Judged support for the three local models that produced valid answers, by category. MIX leads on all findings and on required findings, ByteShape leads on equivalence groups, and Qwen3.6 is lowest in every category.](/docs/charts/inference-heldout-support.svg)

Observed: MIX has the highest support on all findings and on required options, 0.62 and 0.54. ByteShape has the highest equivalence support, 0.68 against 0.61. Qwen3.6 is lowest in every category. All three models support recommended findings more often than required findings.

The 0.10 gap between MIX and ByteShape on all findings is 23 findings, from 111 of 178 against 88 of 168. It is a lead on one night of single samples, not a decisive separation. ByteShape's equivalence lead is also a difference of a few findings on different denominators, 32 of 47 against 19 of 31, and the equivalence rubric is strict enough that its verdicts were treated as a lower bound. The Qwen3.6 result is far below both, at 0.23 over 109 findings, with 20 unsupported required findings out of 49.

## Secondary corrected-reference comparison

The second measure compares each complete answer with the corrected reference, canonically and independently of option order. Precision and recall count exact option or equivalence findings. Structural equality requires the whole result to match. This measure is secondary. The reference is built from one answer per slot, it is incomplete, and it carries more findings than any local model emits. On the ByteShape 150 the reference holds 239 findings against 168 emitted, so a low F1 is expected by construction and is not an accuracy score.

| Model | Cohort | Precision | Recall | F1 | Structural equal |
|---|---|---:|---:|---:|---:|
| ByteShape | 150 | 0.286 | 0.201 | 0.236 | 47/150 |
| MIX | First 50 | 0.200 | 0.126 | 0.155 | 15/50 |
| MIX | Other 100 | 0.236 | 0.191 | 0.211 | 30/100 |
| MIX | Combined 150 | 0.225 | 0.167 | 0.192 | 45/150 |
| Qwen3.6-35B-A3B | 48 valid | 0.109 | 0.141 | 0.123 | 3/48 |

ByteShape's F1 was 0.230 on its 100 fit targets and 0.247 on the validation 50. MIX's combined 0.192 sits below ByteShape's 0.236, so this measure reverses the order of the two strongest models. That reversal is why the secondary measure did not decide the model. It is a disagreement diagnostic, and the primary measure is the blind judged support.

The whole-result counts show a similar picture without judging either side. Over ByteShape's 150 targets, 47 results were structurally equal. The mean was 1.3 missing and 0.8 extra option findings per target, with 191 missing and 120 extra option findings in total. One target, TUTA.332, emitted no option while the reference held 15. Another, NAM.030, was structurally equal with no missing and no extra finding. A count difference is not a judgment that each reference item is correct or that each extra item is harmful. The ordered rows were read to look for an error breakpoint, and no numeric breakpoint was selected. The selected policy keeps the measured quality as a whole.

## Confidence and flags as a filter

A rule built from ByteShape's own confidence and finding flags was fitted on the 100 fit targets and applied unchanged to the distinct 50. It failed on both. Every unsupported fit-100 finding sat at confidence 0.95, 16 of the 18 carried no finding flag, and no candidate rule improved F1 on either cohort. Target-level routing confidence and routing flags marked targets with no unsupported finding rather than harmful ones, so they could not calibrate a reroute rule either. [Confidence calibration and corrected reference judgments](/docs/experiments/inference/confidence-and-corrected-references.md) gives the rule fit, the routing groups and their counts.

MIX adds no separation signal. All 11 outright unsupported findings among its added 100 lacked both a finding flag and a routing flag. The ByteShape rule was not transferred to MIX and was not fitted to MIX, so a MIX-specific filter would need its own calibration. The selected policy applies no confidence cutoff, no finding drop, no demotion and no uncertainty-triggered reroute. Confidence and both flag sets are kept as raw evidence.

## Required versus recommended

Required is the weak category for every model. ByteShape supported 41 of 97 required findings and left 22 unsupported. MIX supported 54 of 100 and left 15 unsupported. Qwen3.6 supported seven of 49 and left 20 unsupported. Recommended findings were supported at 0.62, 0.81 and 0.31, and MIX had no unsupported recommended finding at all.

The category difference is observed, not a decomposition of why. A `partly` verdict can mean a wrong category, and the local `partly` findings were not split into wrong-category and partial-AND cases. Whether a specific finding belongs in required or recommended is therefore measured only through the four verdicts, not separately. A recommendation-skip option was available: publish the recommended set empty as a complete result and keep the raw candidates. The selected policy keeps recommendations as emitted. MIX's recommended findings were supported at 0.81 and none was outright unsupported. No skip applied.

## The option-pool shape check

The selected product composition treats each category as one [option pool](/docs/reference/glossary.md#prerequisites-and-routes) of complete options. The saved MIX results were read to see whether their top-level shape matches that composition. The check read the 150 saved MIX results and computed no quality measure.

| Category | Results with no set | Results with one set | Results with two or more sets |
|---|---:|---:|---:|
| Required | 77 | 73 | 0 |
| Recommended | 115 | 35 | 0 |

No parsed MIX result had two or more requirement sets in either category. The v9 prompt says that multiple top-level sets are an AND. The observation therefore does not justify flattening a future multi-set result into the selected per-category OR pool. A multi-set result is refused at acceptance, and its raw answer is retained. The case did not occur in these 150 results, so the rejection path has not been exercised on stored output.

## The selected configuration

The model and policy below were selected on 2026-09-29 and applied to the full-catalogue inference run. The held-out comparison itself did not select a model. On the night of the measurement it reported MIX as the leading candidate, with every policy choice open. The selection came the next day and is the result that stands.

| Element | Selected value |
|---|---|
| Model | Qwen3.8-27B IQ3-MIX |
| Prompt and schema | v9 and version 2 |
| First key | 131,072 tokens, MTP, `q4_0` KV |
| Second key | 163,840 tokens, no MTP, `q4_0` KV, loaded only when needed |
| Fit rule | Use the first key that fits the packet, the 8,192-token output cap and 1,024 tokens of headroom |
| Routing | MIX runs solo. The product policy has no fallback route: a packet that fits neither local key fails as one capacity failure with the reason `context_exceeded`, and no generation request is made for it |
| Quality filter | None. No confidence cutoff, no finding drop, no demotion and no quality-triggered reroute |
| Recommended findings | Kept exactly as emitted |
| Measured quality | 111 of 178 findings supported, 54 of 100 required findings supported |
| Known limit | 15 unsupported required findings treated as uncertainty, not as fact |
| Not selected | ByteShape, Qwen3.6-35B-A3B, gpt-oss-20b and Nemotron-3-Nano-30B-A3B |

The 15 unsupported required findings are the part of the result a reader can act on in the product. A reader who finds an inferred course wrong can mark it [Excluded](/docs/guides/prerequisites.md#exclude-a-course-or-a-requirement), and the route then does not pass through it. That remedy does not make the remaining inferred output official data. The 15 findings are findings whose supplied text did not support the claim, not proof that the courses are not prerequisites.

The full-catalogue run used this configuration: MIX on v9 and schema version 2, the 131,072-token key first, the 163,840-token key only when needed, no quality filter and no quality-triggered reroute. A packet that fits neither key is never truncated. The product reports it as one capacity failure for that target with the reason `context_exceeded` and makes no generation request for it. The product configuration has no fallback route. The full run supplied an explicit capacity route that sent each such packet whole to DeepSeek V4.1 Flash, and 23 of the 4,543 targets took it. That route belonged to the run's configuration, not to the product routing policy. ByteShape, Qwen3.6, gpt-oss and Nemotron are not selected.

## Corrections and reversals

| Earlier result or position | Correction or reversal | Result that stands |
|---|---|---|
| The run preparation fixed the cohort with a v8 prompt and recorded that the hardware gate was not met | The discrete GPU drove the displays, so no model ran that night. The prompt version was changed to v9 before the first held-out attempt | v8 was never run on the 150. Every held-out trial used v9 and schema version 2, and the run preparation recorded v8 as its prompt, so that record is a preparation label |
| The MIX comparison cohort was the shared 50 | The other 100 were run with MIX later the same night as a distinct trial, after the first 50 had been judged | MIX covers 150 targets, 150 of 150 valid, with 55 findings on the first 50 and 123 on the other 100 |
| The measurement night named MIX the leading candidate and left the policy open | The model and routing policy were selected on 2026-09-29 | MIX solo on v9 and schema version 2, no quality filter, recommendations kept. Product routing has no fallback. The full run supplied an explicit capacity route to DeepSeek V4.1 Flash for the 23 packets that fitted neither local key |
| Nemotron-3-Nano-30B-A3B was a comparison candidate | Its two-packet probe returned one valid result, took 261 seconds on the smallest packet and 1,654 seconds on an invalid largest packet | It was dropped before the comparison and does not appear in any quality number |
| gpt-oss-20b had the highest decode rates in the fixed-prompt throughput table | All 50 held-out attempts returned empty content, and every probe of the cap and request shape failed | gpt-oss produced 0 of 50 valid answers. It is a recorded failure, not a fallback |
| A confidence and finding-flag rule might permit a defensible drop or demote | The candidate rules removed supported findings while unsupported findings remained, and no candidate rule improved either cohort | No cutoff, no drop and no demotion. Confidence and flags are kept as raw evidence |
| Routing confidence and routing flags might mark harmful targets | No low-confidence target was harmful, and flags marked targets with no unsupported finding | No uncertainty-triggered reroute |
| ByteShape's fitted rule might carry to another model | The rule failed its own distinct-target validation and was not fitted to MIX | No filter applies, and a MIX-specific rule would need its own calibration |
| The per-category option pool was expected to receive one requirement set per category | The shape check found at most one set per category in every saved result, but the v9 prompt allows multiple sets | A multi-set result is refused at acceptance with its raw answer retained, not flattened |

## What the numbers support

### Observed

- MIX supported 111 of 178 findings, 0.62 overall, with 54 of 100 required, 38 of 47 recommended and 19 of 31 equivalence findings supported. It left 15 required findings unsupported and none in the other two categories.
- ByteShape supported 88 of 168 findings, 0.52 overall, with 41 of 97 required, 15 of 24 recommended and 32 of 47 equivalence findings supported. It left 26 findings unsupported in total.
- Qwen3.6-35B-A3B supported 25 of 109 findings, 0.23 overall, with seven of 49 required and 20 unsupported required findings.
- gpt-oss produced no valid answer. Nemotron was dropped before the comparison.
- On the secondary corrected-reference measure ByteShape scored 0.236 and MIX 0.192, the reverse of the primary order. Qwen3.6 scored 0.123.
- No confidence or flag rule improved either ByteShape cohort, and no low-confidence target was harmful.
- Every saved MIX result had at most one requirement set per category.

### Interpreted

MIX is the strongest of the measured models on the primary measure, on all findings and on required findings. The lead is 0.10 on all findings, about 23 findings, on one night of single samples, so it is a lead rather than a decisive separation. ByteShape's equivalence lead and secondary F1 lead do not make it the stronger overall model, because the secondary measure is a disagreement diagnostic and not truth.

Required is the weak category for every model. The selected policy keeps the measured output despite that weakness, rather than adding a filter that the ByteShape fit shows does not separate harmful claims. The support rates are conditioned on emission. They cannot reward a true prerequisite that a model omitted, and a model that emits fewer safe findings can show a higher rate. Qwen3.6 emitted the fewest findings and scored lowest, so emission volume alone does not explain the ranking, but the rates measure findings rather than recall.

### Failed hypotheses

- A confidence threshold could remove harmful claims.
- A finding-flag filter could remove harmful claims.
- A target-level routing confidence or flag could route harmful targets away from the model.
- gpt-oss-20b could produce a valid complete answer on this runtime.
- Nemotron-3-Nano-30B-A3B could run at a usable speed and validity.

### Not supported

- An `unsupported` verdict does not mean the course is not a prerequisite. It means the supplied text did not support the claim under the rubric, and the judge may be wrong.
- A `supported` verdict does not mean the university publishes that prerequisite. It means the supplied text supports the claim.
- The support rates are not exhaustive ground truth and they are not a recall measure. They cover the findings a model emitted, and 43 of ByteShape's 150 targets emitted none.
- The 0.10 gap between MIX and ByteShape is not a guarantee. It is a single-night, single-sample observation on the fixed cohorts.
- ByteShape's equivalence lead is not an exact measure, because the equivalence rubric is strict and its verdicts were treated as a lower bound.
- The Qwen3.6 result is not evidence about its behaviour beyond the 48 valid answers and the 50 packets it saw.

## Limitations

One sample per target. No model was asked the same target twice, and no judge batch was judged twice. The size of sampling noise is therefore not measured for these models. The reference's paired answers, which differed in packet as well as in sample, overlapped at about 0.34 finding F1. That value is context for how much two answers can differ, not a measurement of local-model variance.

The denominators are small. MIX's required rate rests on 100 findings, its recommended rate on 47 and its equivalence rate on 31. ByteShape's rates rest on 97, 24 and 47. Qwen3.6's rates rest on 49, 39 and 21. A difference of a few findings moves a rate by several points, and no confidence interval is recorded for any support rate.

The cohorts are not random. The 50 comparison targets are deterministic size quantiles of the 150, chosen to span packet size, not a random sample. MIX's own two cohorts differ, 0.67 on the first 50 and 0.60 on the other 100, which is consistent with the cohort mix moving the rate. Qwen3.6 and gpt-oss were measured on the 50 only, so their results are not a 150-target result. ByteShape and MIX were measured on 150.

The judge is one model with one rubric. No human re-read exists, so the judge's own error rate is unknown. The judge read a bounded rendering of the teaching text, with the name, outcomes and content truncated, and it could not consult the rest of the catalogue or an official record. A `partly` verdict is coarse, and the local `partly` findings were not judged again at a finer grain. The equivalence rubric is strict, and its verdicts were treated as a lower bound.

The reference is single-sample and incomplete. It holds more findings than any local model emits, so precision and recall against it are structurally low. It cannot supply a true prerequisite that the reference answers omitted. Its 45 target-not-member equivalence groups were judged against the target rather than only among the members, which affects the secondary comparison of those groups. ByteShape's equivalence figures were judged against their own member sets. No such check was made for MIX or Qwen3.6, so their equivalence rates carry that uncertainty. Corrected-reference F1 is a diagnostic, not an acceptance gate.

The validity check is schema-only. One Qwen3.6 finding named a course absent from its packet and could not be judged. A schema-valid answer can therefore cite a course the packet did not supply, and this comparison did not enforce packet membership on local answers. The 48 valid Qwen3.6 answers and the 150 valid answers of each of ByteShape and MIX are schema-valid, not necessarily packet-membership-valid.

The artifacts are quantized and the runtime is one revision. The measured quality belongs to the exact ByteShape, MIX, Qwen3.6 and gpt-oss artifacts on one AMD Radeon RX 9070 XT (16 GB model) and ROCm 7.2.1, not to the model families in general. The gpt-oss failure is specific to the pinned runtime and the request shapes tried. No other runtime is covered.

The prompt is one frozen version. The 150 were never used to tune ByteShape, but the prompt family is not pristine: the v6 rules that v9 inherited came from held-out answers on the same 200-target packet set. A different prompt could change every rate here, and no second prompt was measured on the 150.

The MIX extension began after the first 50 had been judged. The 100 targets had not been run and the original trials were not overwritten, but the MIX trial on all 150 was not fixed before the measurement started. The 150-target MIX result is therefore a combination of one cohort fixed in advance and one added cohort, each judged once.

## Setup details

| Parameter | Value |
|---|---|
| CE-only packet set | 200 packets, 50 candidates each from a 1,000-candidate pool |
| Tuning targets | 50, used to tune ByteShape's prompt, excluded from the comparison |
| Held-out complement | 150 targets, never used to tune ByteShape |
| Shared comparison cohort | 50 size quantiles of the 150, also the rule-validation set |
| Rule-fit targets | The other 100 of the 150 |
| Rendered packet size range | 38,967 to 270,860 user-prompt characters on the shared 50 |
| Prompt and schema | v9 and version 2 |
| Generation | Thinking off, temperature 0, seed 0, output cap 8,192 tokens, timeout 300 seconds |
| Sampling | One sample per target, invalid answers retained, transport retries recorded |
| ByteShape key | 118,784 tokens, MTP, `q8_0` KV |
| MIX keys | 131,072 tokens, MTP, `q4_0` KV first. 163,840 tokens, no MTP, `q4_0` KV second, unused on these 150 |
| Qwen3.6 key | 212,992 tokens, `q4_0` KV |
| gpt-oss key | 131,072 tokens, native, `q8_0` KV |
| Judge | Claude Opus 5.5 at the low variant, blind to model, confidence, flags and labels |
| Judge batching | Shuffle seed 20260928, batches of 48, one fresh session per batch, no re-judging |
| Verdicts | `supported`, `partly`, `unsupported`, `unclear`, with `partly` and `unclear` never folded into `supported` |
| Secondary score | Canonical option and equivalence findings, precision, recall, F1 and structural equality |
| Rule fit | Fitted on the 100 fit targets, applied unchanged to the distinct 50 |
| Shape check | The 150 saved MIX results, set counts per category |
| Hardware | AMD Radeon RX 9070 XT (16 GB model), ROCm 7.2.1 |

## Untested follow-up questions

1. A second sample per target and model would separate sampling noise from a model difference. No such repeat was run, so no interval or self-agreement value exists for the local models.
2. A MIX-specific confidence and flag calibration, fitted on one cohort and validated on a distinct one, would test whether any filter helps MIX. None was run, and the selected policy applies no filter.
3. A human re-read of a sample of the local findings would put a number on the judge's error. No such measurement exists.
