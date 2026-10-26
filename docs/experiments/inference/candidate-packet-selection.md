# Candidate packet selection

Two candidate packets for the same held-out target courses were compared through reference answers judged against the supplied teaching text.

**Evidence status:** Comparative.

The [Experiments section](/docs/experiments/README.md) gives the catalogue, the evidence labels, and the hardware the experiments ran on.

## The question

An inference call receives one target course and a bounded list of candidate courses. The model may cite only those candidates, and every stage before the call may rank candidates but may not emit a relation. The candidate packet is therefore the model's whole view of the catalogue for that target, and its contents decide what the model can possibly propose.

The packet was assembled in two steps. A multiview query retrieved a pool of 1,000 candidates per target, and a cross-encoder reranked that pool into a complete ordering. The top 50 of that ordering formed the cross-encoder-only (CE-only) packet. The measured alternative added a ranking-only small model. That model scored the cross-encoder top 200, the two orderings were fused by reciprocal rank fusion, and the fused top 50 formed the RRF packet.

The comparison asked whether the extra scoring pass changed the answers enough to justify running it on every target. Both packets had been carried forward from the ranking measurements as alternatives, with neither selected as a policy, so that one complete-target prompt could be evaluated on both before a choice. Two packets were measured on the same targets, so the difference between them carries the claim.

## The two packets

| Packet | Candidates | Construction |
|---|---|---|
| CE-only top 50 | 50 | Top 50 of the cross-encoder ranking of the 1,000-candidate pool |
| Qwen3 0.6B RRF top 50 | 50 | Top 50 by fused rank over the cross-encoder top 200 |

The cross-encoder was `bge-reranker-v2-m3` at Q8_0, served by the pinned llama.cpp runtime. It scored the content-first teaching text at 1,536 characters for the target and 1,536 characters for each candidate.

The ranking-only model was Qwen3 0.6B at Q8_0. It scored the cross-encoder top 200 in ten batches of 20 candidates, with 512 characters of candidate text per candidate. The fusion used the two ranks alone.

```text
fused(c) = 1 / (60 + rank_qwen(c)) + 1 / (60 + rank_ce(c))
```

Only ranks entered the fusion, so a wide spread of small-model scores and a narrow one carried the same weight. The offset of 60 damped the contribution of deep ranks. Both packets carried the target's teaching text and the 50 candidate descriptors in full, and the 512-character limit applied to the ranking model's input rather than to the packet the answering model saw.

For one target the two packets shared the target, the prompt, the schema, the settings and the 1,000-candidate pool. They differed in which 50 candidates they carried and in their order, and in nothing else.

## Cohort and prompt version

The paired comparison ran on the first 100 targets of a fixed set of 200 held-out target courses. The 200 are active courses with a representative version, chosen deterministically from one catalogue snapshot and spread across the catalogue. They are disjoint from the 100 development targets, and courses used in prompt examples are excluded from the set and from its candidate lists. The remaining 100 targets received a CE-only answer after the packet decision and play no part in the comparison. A pair is the CE-only answer and the RRF answer for one target.

All 300 answers used complete-target prompt version 6, and the run set `INFERENCE_PROMPT_VERSION` to `v6`. Both packets used the same prompt text and the same strict result schema.

### From v5 to v6

Prompt v5 was frozen on development targets and passed 44 of 44 development calls, covering the fixed development ten under both packets and four repeat indices per packet on a fixed set of three development targets. The held-out run then started on v5.

It stopped at 86 answers. Spot checks on held-out answers showed two general gaps. First, v5 forbade a course from appearing in several OR options of one category, which blocks a form such as `(A AND B) OR (A AND C)`. Second, only `too_basic_transitive` was defined as a suppression outcome, so sibling modules and the course a student normally takes immediately before the target were recorded as too basic. The prompt was corrected before the run continued.

Version 6 changed exactly those two rules and kept the rule that a course may not be both required and recommended. It defines five suppression outcomes: `too_basic_transitive`, `reverse_prerequisite`, `overlap`, `related` and `unrelated`. It allows a course to repeat across options or requirement sets of one category when the logic needs it, for example `(A AND B) OR (A AND C)`.

The revised prompt was proved on 20 local calls, the fixed development ten under both packets, with Qwen3.6-35B-A3B UD-IQ3_S at 192k context and q8_0 KV as the provisional runtime. Nineteen answers validated and one invented a course code. The resulting failure rate of 5 percent was recorded before the held-out run restarted. That proof ran on the GPU machine, an AMD Radeon RX 9070 XT (16 GB model), whose fit and throughput are reported in [local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md).

The 86 v5 answers were kept unused. Two further v5 answers were lost while directories were reconciled and were not used.

This history limits the comparison. Held-out answers motivated the wording of v6, so the corpus is not an untouched prompt holdout. Both changes are general rules about grouping and suppression rather than rules tuned to particular courses, and each was stated as a prompt rule that applies to every target.

The repeated-course allowance then went unexercised. It appeared in none of the 200 CE-only answers, although about 31 official multi-option prerequisites would need that form. No action followed from that observation.

## Answer generation

Each answer is one sample from DeepSeek V4.1 Flash, with thinking enabled at low reasoning effort, the JSON object response format, and no temperature value sent. Every request carried one frozen label-free packet, and no official prerequisite label, retrieval score, rank value or prior answer entered a request. The candidates were listed in packet order. Official labels were read only after an answer existed, for spot checks. An invalid answer was sent again with the identical request until it validated, and every attempt was retained.

| Run | Targets | Validated answers | Invalid attempts retried | Spend (USD) |
|---|---|---|---|---|
| Paired prefix, both packets | 100 | 200 | 12 (7 JSON or schema, 5 unknown codes) | 2.38 |
| CE-only remainder | 100 | 100 | 2 (JSON or schema) | 1.39 |
| Total | 200 | 300 | 14 | 3.77 |

The corpus holds 300 validated answers from 314 attempts. Every saved answer passed strict parsing and a check that each cited course code came from its own packet, so a finding could only name a course the packet had supplied. A 25 USD spend guard applied to the first pair's projected cost and to cumulative spend, and the run never approached it. The paid calls ran outside the provider's peak hours only.

The 100 pairs were answered first, the packet decision was taken on them, and the remaining 100 targets were then answered with the CE-only packet only.

## Reference judgments

Each answer is a model sample rather than an official record, so every finding the two answers of a pair did not share was judged on its own against the teaching text the model had been given. A Claude Opus 5.5 session at the low reasoning variant judged them blind to the packet they came from and without official labels, and [how reference answers and support verdicts were produced](/docs/experiments/inference/reference-answers-and-judging.md) states the rubric and the batching.

## Measurements

### Finding sets

A finding is one proposed option or one proposed equivalence group. The 100 pairs produced 257 distinct findings.

| Finding set | Findings |
|---|---|
| Distinct findings across the 100 pairs | 257 |
| Found by both answers of a pair | 52 |
| Found only by the CE-only answer | 98 |
| Found only by the RRF answer | 107 |

The two answers of a pair therefore differed on 205 findings, and agreed on 52. In the 100 pairs, the CE-only answers emitted 150 findings in total and the RRF answers 159, so the 52 shared findings give a finding F1 of about 0.34 between the two answers for the same target, computed as twice the shared count divided by the sum of the two totals.

### Judged support

Each differing finding scored 1 when the judge found it supported, 0.5 when partly supported and 0 when unsupported. The 52 shared findings were not judged and enter neither score.

| Category | CE-only score | CE-only findings | RRF score | RRF findings |
|---|---|---|---|---|
| All differing findings | 0.63 | 98 | 0.56 | 107 |
| Required options | 0.45 | 47 | 0.30 | 50 |
| Recommended options | 0.77 | 27 | 0.71 | not recorded |
| Equivalence groups | 0.85 | 24 | 0.91 | not recorded |

| Category | CE-only supported | CE-only unsupported | RRF supported | RRF unsupported |
|---|---|---|---|---|
| All differing findings | 57 | 31 | 52 | 39 |
| Required options | 17 | 22 | 10 | 30 |

The per-category finding counts for the recommended and equivalence rows of the RRF packet are not recorded separately. Subtracting unsupported from supported over all differing findings gives a net of +26 for the CE-only answer and +13 for the RRF answer.

The chart compares the judged support of the two packets by category.

![Judged support score for differing findings under the CE-only and RRF packets, by category, with CE-only ahead on all findings and on required options.](/docs/charts/inference-packet-support-by-category.svg)

The CE-only packet led on all findings, on required options and on recommended options. The RRF packet led on equivalence groups, where it scored 0.91 against 0.85.

### Per-target difference

Of the 100 targets, 62 had at least one finding that only one of the two answers emitted. On those 62 targets the score comparison is:

| Outcome across the 62 targets | Targets |
|---|---|
| CE-only answer scored higher | 27 |
| RRF answer scored higher | 26 |
| Equal score | 9 |

The chart splits the 62 targets by which answer scored higher.

![Counts of the 62 targets whose two answers differed, split into 27 where the CE-only answer scored higher, 26 where the RRF answer scored higher and nine with equal scores.](/docs/charts/inference-packet-per-target-outcome.svg)

The mean per-target score difference was 0.21, with a 95 percent bootstrap interval from -0.37 to 0.84. The interval spans zero, and the win counts are 27 against 26. The per-target comparison therefore does not separate the packets.

### Packet overlap

| Measure | Value |
|---|---|
| Mean candidates in common per target | 40 of 50 |
| Differing findings that involve a course in both packets | 178 of 205 |

Most of the variation between the two answers concerns courses that both packets supplied. The remaining 27 differences each involve at least one course that only one of the two packets carried.

## The decision

CE-only top 50 was selected as the packet policy. It emitted fewer unsupported required options, 22 of 47 against 30 of 50, and it needs no ranking-only scoring pass on any target. The applied pipeline carries 50 candidates selected by the cross-encoder alone, with `INFERENCE_SELECTION_FINAL_K` set to 50. [Candidate retrieval and rerank](/docs/backend/inference/inference.md#candidate-retrieval-and-rerank) states the applied pool depth and packet size. The RRF packet is historical evidence and is not a ranking stage in the product's selection path.

The selected packet does not win on the per-target measure. Its case rests on the required-option row and on the cost of the ranking stage, not on a decisive margin between the two answers.

The quality preference recorded on 2026-09-27 ranks a right course in the right category first, a right course in the wrong required-or-recommended category second, and an omission third, and treats a course that is not a prerequisite at all as the error to refuse. Under that preference an unsupported required option is the costliest error this comparison can see, which is why the required row carried more weight than the near-tie in the per-target counts.

The comparison also produced a separate observation that changed later work. About half of the differing required findings were judged unsupported under either packet, 22 of 47 and 30 of 50. The finding-confidence measurement that followed used the 200 CE-only answers.

## What the comparison supports

Observed: the CE-only packet produced a higher judged support score on all differing findings and on required options, and fewer unsupported required options. The RRF packet produced a higher score on equivalence groups.

Interpreted: most of the variation between the two answers is consistent with single-sample variation in the answering model rather than with the packet. That reading rests on the overlap count and on the interval, and it is an interpretation rather than a measured decomposition of the two sources of variation.

Not supported: a claim that either packet is decisively better on the whole answer. The interval includes zero and the per-target counts differ by one target.

## Limitations and corrections

A single sample per slot. Each answer is one DeepSeek sample, and no target was answered twice under the same packet. The size of sampling noise is therefore not measured directly. No self-agreement measurement was run, so the 0.34 finding F1 between two answers for the same target and the 178 differences that involve courses in both packets are the available evidence about that noise, and both mix sampling variation with the packet difference.

One answering model. Both packets were answered by DeepSeek V4.1 Flash at the settings listed below, so the comparison measures the two packets for that answering model only.

Verdicts are support by teaching text. The judge asked whether the supplied text supports a finding. It did not ask whether the university publishes that prerequisite, and no official label entered judging. The judge read a bounded rendering of each course, with the name and the outcomes and content text truncated, so a verdict rests on that excerpt. A true prerequisite that both packets omitted is invisible to this comparison, and the scores cannot show it.

One model judged every finding. The judge is a model applying a fixed rubric, and its equivalence verdicts are strict, which makes the equivalence score a lower bound. No agreement measurement between the judge and a human reader exists, so the judge's own error rate is unknown.

Across the 200 CE-only answers, 45 of the 86 equivalence groups did not contain their target course, and the judge compared those groups' members with the target. That defect applies to the equivalence verdicts in this comparison and was disclosed rather than repaired, so the RRF lead on equivalence groups is the least secure of the four rows.

The paired subset is the first 100 targets of the frozen order, not a random sample. The 100 unpaired targets carry only a CE-only answer, so the comparison covers half of the held-out set.

One packet size and one pool. Both packets carried 50 candidates drawn from the 1,000-candidate pool. Neither a different packet size nor a different pool depth was measured, and the comparison says nothing about either.

The prompt is not pristine. Version 6 was written after held-out answers were read, for the two general gaps described above. The comparison measures the two packets under one prompt, and the absolute support scores carry that history.

The corpus is conditioned on validity. An invalid answer was re-requested with the identical request until it validated, so each slot holds the first valid sample rather than a random one. The 14 invalid attempts are retained.

### Corrections and design changes

The planned corpus was 200 pairs, about 400 whole-target calls. The corpus was set to 100 pairs, and 100 further CE-only answers were added. The 300 validated answers are the final corpus and no further RRF calls were made. The comparison therefore rests on 100 pairs rather than 200.

The run began on prompt v5 and restarted on v6 after 86 held-out answers. The v5 answers were kept and not used, and the v6 corpus replaced them for every slot.

Both packets were carried as alternatives through the prompt evaluation, with neither selected as a policy. The selection of CE-only top 50 was made after the judged comparison, so the earlier position was that the packet choice was open, and the result that stands is the CE-only packet.

## Setup details

| Parameter | Value |
|---|---|
| Retrieval pool | 1,000 candidates per target (`INFERENCE_SELECTION_POOL_K`) |
| Packet size | 50 candidates (`INFERENCE_SELECTION_FINAL_K`) |
| Cross-encoder | `bge-reranker-v2-m3`, Q8_0, content-first layout, 1,536 characters of target text and 1,536 characters of candidate text |
| Ranking-only model | Qwen3 0.6B, Q8_0, 512 characters of candidate text, ten batches of 20 |
| Fusion offset | 60 |
| Answering model | DeepSeek V4.1 Flash, thinking enabled at low reasoning effort, JSON object response format, no temperature |
| Judging model | `anthropic-sdk/claude-opus-5-5` at the low variant |
| Finding score | supported 1, partly 0.5, unsupported 0 |
| Per-target interval | 95 percent bootstrap over per-target score differences |
| Spend guard | 25 USD |

## Untested follow-ups

Whether repeated sampling under each packet would shrink the per-target interval enough to separate them. No self-agreement measurement was made, so it is untested.

Whether a rejudged equivalence comparison, with group members compared only with one another, would preserve the RRF lead on equivalence groups. Untested.

Whether a packet of 25 or 100 candidates would change the balance between the two packets. Both packets were measured at 50 only, so it is untested.
