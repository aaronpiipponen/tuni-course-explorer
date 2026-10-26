# Reference answers and judging

This page states how the inference comparisons produced their reference answers and their blind support verdicts, and what those verdicts can show.

The corpus and the corrected reference date from 2026-09-26.

## Why the category shares one reference

The inference experiments ask whether a candidate packet, a prompt version or a local model produces better inferred prerequisites. A difference between two variants can come from the model, the prompt, the candidate list or the sample. The category fixes the answer inputs and the judge so that a comparison measures the variant it names.

The reference answers are 300 saved complete target results from one external model on 200 fixed targets. A comparison reads the reference built from the saved answers instead of asking the model again. One unit of an answer is a [finding](/docs/backend/inference/inference.md#what-inference-produces), either one required option, one recommended option or one equivalence group. The judge is a separate language model that sees one finding and the teaching text it refers to and returns one of four support verdicts. It never sees which model produced the finding.

The corpus is evaluation evidence, not [the university's prerequisite record](/docs/reference/glossary.md#prerequisites-and-routes). The corrected reference derived from it is also evaluation evidence. The sections below state how both were produced, how one judge flaw and the `partly` cases were handled, and which limits every support number inherits.

## The reference model and its settings

The reference model is DeepSeek V4.1 Flash, requested from the DeepSeek chat-completions API. It is not one of the local models that the inference experiments measure. Every request enabled thinking at low reasoning effort and asked for a JSON object as the response. The request carried no temperature and no output token limit, so the provider defaults applied.

Calls ran only in the provider's off-peak window. The corpus ran over a weekend. A $25 spend guard ran on the first pair's projected cost and on cumulative spend, and it was never approached.

| Setting | Value |
|---|---|
| Model | DeepSeek V4.1 Flash |
| Endpoint | DeepSeek chat-completions API |
| Thinking | Enabled, `reasoning_effort=low` |
| Response format | `json_object` |
| Temperature | Not sent |
| Output token limit | Not sent |
| Prompt version | v6 |
| Candidates per packet | 50 |
| Answer validation | Strict complete-target result schema and supplied-code check |
| Retry | The identical request, with every attempt retained |
| Spend guard | $25, on the first-pair projection and on cumulative spend |
| Off-peak prices | Cache hit $0.003, cache miss $0.15, output $0.60 per million tokens |
| Corpus spend | $3.77 |

## What the prompt asked for

The prompt is one system message and one user message per call. The user message carries the target descriptor and the ordered candidate descriptors of one packet. The system prompt fixes the output contract and the reasoning rules. Its version is v6.

- One complete result. The keys `required`, `recommended`, `equivalence` and `routing` are always present. An empty category is a complete answer, not a missing key.
- Grouping. Required and recommended are each an AND of requirement sets. Each set is an OR of options. Each option is an AND of course codes. A course may repeat across options of one category when the logic needs it, for example `(A AND B) OR (A AND C)`, but not across required and recommended.
- Copied codes. Every emitted course code must be copied from the candidate list. The target's own code may appear only in an equivalence group. The validator rejects an unknown or forbidden code.
- Directness. A candidate is a required prerequisite only when the target expects its knowledge immediately on entry. A chain does not justify a direct edge. A broad or transitive foundation is recorded as a suppressed candidate, not as an option.
- Categories. Required means the knowledge is expected before the course starts. Recommended means directly relevant background that is not an entry condition.
- Equivalence. A group asserts course-wide interchangeability. Similarity and target-local substitution do not qualify.
- Evidence and confidence. Every option and group carries a short evidence string and a confidence between 0 and 1. The prompt states that confidence is the model's certainty, not established truth.
- Routing. `routing` carries a confidence, zero or more of five flags and at most five suppressed candidates. The flags are `directness_ambiguity`, `alternative_path_ambiguity`, `breadth_ambiguity`, `substitute_overlap_ambiguity` and `insufficient_course_information`. The suppression outcomes are `too_basic_transitive`, `reverse_prerequisite`, `overlap`, `related` and `unrelated`.
- Hidden target labels. The model is told that the target's official prerequisite structure is withheld. No worked example shows the target's own answer.

The prompt also carries worked examples of a direct prerequisite, an AND option, an OR alternative, a suppression, a course-wide equivalence and an insufficient-information case. Each example is a curated reading of teaching text, not a university-authored prerequisite fact.

Prompt v5 stopped after 86 held-out answers. Spot checks found two general gaps. The prompt forbade one course from appearing in several OR options of one category, and it defined one suppression outcome only, for a broad or transitive foundation. Version v6 changed only those two rules and defined the five outcomes above. The held-out answers shaped the wording, so the v6 corpus overlaps prompt development. A 20-call local check of v6 validated 19 answers and failed one on an invented course code, and an invalid rate of 5 percent was accepted for the run. The 86 v5 answers are retained but unused, and two further v5 answers were lost.

## The cohort and the paired packets

The cohort is 200 active represented target courses, fixed before any answer was generated. It is disjoint from the fixed 100-target development set, which contains the 10 development targets used for prompt checks. A packet carries the candidates' identity fields and teaching text in packet order, with no retrieval score, rank value or official prerequisite label. Every target has a CE-only packet of 50 candidates. The first 100 targets in the fixed target order also have a 50-candidate RRF packet. Both packets for one target share the prompt, schema, settings and target and differ only in the ordered candidate descriptors.

The CE-only packet is the top 50 of a cross-encoder ranking over the saved 1,000-candidate multiview pool. The RRF packet is the top 50 by reciprocal rank fusion of the cross-encoder ranking and a ranking by Qwen3 0.6B at Q8_0, which scored 512 characters of candidate text. The corpus was first sized at 400 answers, 200 pairs. After the first 100 pairs it was reduced to 300 validated answers, because 100 pairs were judged enough for the packet comparison. The remaining 100 targets therefore carry one packet each.

In the corpus run, official prerequisite labels were read only after an answer existed, for spot checks, and never entered a packet, prompt or request. A separate retrieval measurement had already read the cohort's official labels, so the 200 are not an untouched holdout for ranking policy.

| Targets | Packets per target | Validated answers | Invalid attempts | All attempts | Spend |
|---|---|---|---|---|---|
| First 100 | CE-only top 50 and RRF top 50 | 200 | 12 | 212 | $2.38 |
| Remaining 100 | CE-only top 50 | 100 | 2 | 102 | $1.39 |
| All 200 | 300 answer slots | 300 | 14 | 314 | $3.77 |

## The answers, retries and cost

An answer was accepted only when it parsed against the strict complete-target result schema and every emitted course code appeared in the supplied packet. An invalid answer was re-sent with the identical request until it validated. There was no per-slot retry ceiling, and the $25 total guard bounded the run. Every attempt is retained, and a validated answer is written once and never overwritten.

The paired calls produced 200 validated answers from 212 attempts. The 12 invalid attempts were seven JSON or schema failures and five unknown or forbidden codes. The CE-only calls produced 100 validated answers from 102 attempts, with two JSON or schema failures. The corpus holds 300 validated answers from 314 attempts and cost $3.77.

## The blind judge

The judge is a language model that applies a fixed rubric to one finding at a time. It served the packet comparison, the reference corpus, the eight ambiguous required options and the local-model comparisons, and every one of those stages used Claude Opus 5.5 with the low variant. The judge is not the reference model and produced none of the corpus answers.

A verdict saved for one target, category and member set was reused for the same claim instead of judging it again. The packet comparison and the reference corpus judged each distinct finding once.

A separate session judged each batch. The session read only its batch file, ran no commands and did not search the repository. It returned one JSON array with one object per item in input order.

### What the judge saw

| Field | Content |
|---|---|
| `id` | A batch-local identifier |
| `claim` | One fixed phrase, either a required option with all listed courses taken together, a recommended option with all listed courses taken together, or a course-wide equivalence group |
| `target` | The target course code, name, learning outcomes and content |
| `courses` | The named courses with code, name, outcomes and content. For an equivalence group, the members other than the target |
| `target_is_member` | Whether the target belongs to the equivalence group |
| `model_evidence` | The producing model's own justification for the claim |

The rubric told the judge that the text may be Finnish or English and may be sparse, and that `model_evidence` may be wrong. The judge had to decide from the teaching text, not from the justification.

### What the judge did not see

The item carried no model identity, no confidence, no finding flag and no routing metadata. It did not show which packet, trial or model produced the finding. The batch carried no official prerequisite or label, no stored verdict and no corrected reference. The key that linked an item to its stored record stayed in a separate file, and the judge read only the batch.

### Verdicts and the rubric

The judge returned one of four verdicts for each item.

- `supported`: the teaching text clearly supports the claim as stated.
- `partly`: part of the claim holds, for example one member of an AND option or most of an equivalence group, or the category is wrong.
- `unsupported`: the text does not support the claim or contradicts it.
- `unclear`: the text is too sparse to judge.

The rubric gives each category its own test.

- Required prerequisite. Supported only when the listed courses teach knowledge the target expects the student to hold immediately on entry. A broad or distant foundation, a sibling course taken alongside the target, a course that builds on the target, and related topic material are not required prerequisites.
- Recommended prerequisite. Supported when the listed courses are directly relevant background the target builds on, even if they are not an entry condition. Topic similarity alone is not enough.
- Equivalence group. Supported only when the members are interchangeable course-wide, so completing one could replace another everywhere. The same name with near-identical outcomes supports it. The same name with no text is unclear. Numbered series parts that are separate repeatable credits are not equivalent unless the text says they are interchangeable.

The rubric told the judge to be strict and consistent. Leaving out a true prerequisite is better than accepting a wrong one, so topic resemblance never earns `supported`. Every reason is 25 words or fewer.

The judge's verdicts over the 386 findings of the 200 CE-only answers are below. The share of findings with a `supported` verdict is the judged support of that set. `partly` and `unclear` carry their own counts and are never folded into `supported`.

| Category | Findings | Supported | Partly | Unsupported | Unclear |
|---|---|---|---|---|---|
| Required options | 199 | 96 | 64 | 32 | 7 |
| Recommended options | 101 | 71 | 22 | 6 | 2 |
| Equivalence groups | 86 | 63 | 6 | 17 | 0 |
| All findings | 386 | 230 | 92 | 55 | 9 |

### Sessions and batching

The 288 findings that needed judgment were shuffled with seed 20260926 and split into batches of 48. The key stayed in a separate file. One separate session judged each batch, serially, and each returned array was saved unchanged. The join covered all 386 findings, with one verdict for each.

Six batches judged the 288 findings that were not reused. One batch was refused once by a rate limit and judged normally after the reset, and no other judgment failed.

### Fine-disposition mode

The reference also needed a narrower reading for eight findings. These were required options whose stored `partly` verdict carried no reason. A second, explicitly requested mode returned one of four dispositions instead of the four verdicts.

- `correct as required`
- `correct only as recommended`
- `partial AND`
- `wrong`

The batch showed the teaching text, the claim and `model_evidence`, and withheld the old `partly` verdict, the producing trial, the model identity, official labels and the answer key. One session judged the eight items and returned all eight dispositions. The mapping was `correct as required` to keep, `correct only as recommended` to demote, and `partial AND` or `wrong` to drop. The eight items produced one keep, six demotions and one drop.

## Correcting the reference

The 386 verdicts were not rewritten. The correction produced a separate 200-target reference by mapping every finding to a keep, demote or drop action. It made no call to the reference model, changed no prompt and read no official label. All saved answers, verdicts and judge batches were read only.

### Reused verdicts and their limit

Of the 386 findings, 98 were not judged again. The packet comparison had judged the 205 findings that appeared in only one of the two answers of a pair. Its 98 CE-only verdicts were reused here, keyed by the same target, category and member set in the same frozen packet. The split was 47 required options, 27 recommended options and 24 equivalence groups. Their reused CE-only totals were 57 supported, 31 unsupported, nine partly and one unclear. The other 288 findings were judged in six batches.

The two blind renderings were not byte-identical for every reused item. Course order, literal HTML tags and truncation after formatting account for the differences, and the packet itself did not change. The reuse is a limit of rendered-text reuse, not a second source and not a second model answer. The reused verdicts remain in the reference unchanged.

### The equivalence judge flaw

45 of the 86 emitted equivalence groups do not contain their target. The item for such a group put the members in `courses` and the target in `target`, and set `target_is_member` to false. The judge compared the members with the target instead of only with one another, so its verdict did not test the group's claim. Those verdicts are unreliable.

The correction did not re-judge those groups. One fixed rule gives the exception precedence. Every target-not-member group stays exactly as emitted, whatever its verdict. Their saved verdicts are 28 supported, 14 unsupported and three partly. The corrected reference therefore carries 45 equivalence groups whose group-wide support was never properly judged, and every comparison that reads the reference inherits that limit.

### The correction rules

All 92 `partly` findings received an action. The hand classification read all 83 stored reasons and is a hand-authored map, not a keyword classifier. Eight reasonless required options were judged in fine mode, and one reasonless target-member equivalence group was resolved by rule. The rules were fixed in advance.

1. A `supported` finding stays.
2. An `unsupported` or `unclear` finding drops.
3. A `partly` required option that is relevant background without a clear entry requirement becomes recommended.
4. A `partly` finding whose reason identifies overlap, duplicated content, a more apt equivalence or an unsupported AND drops as a whole.
5. A `partly` recommended finding stays unless its reason says the relation is wrong or an overlap.
6. A target-not-member equivalence group stays exactly as emitted, whatever its verdict.
7. A target-member equivalence `partly` without full-group support drops.
8. A reasonless `partly` finding goes to fine mode when it is a required option, and drops by rule when it is a target-member equivalence group without full-group support.

A demoted option becomes its own single-option recommended set named `recommended_demoted_<n>`. It keeps its stored evidence and confidence byte for byte. No new OR grouping is invented, no recommended finding is promoted, and a requirement set left with no options drops.

The rule for a `partly` recommended finding has one recorded reading. For recommended findings the rule's default keeps the recommendation unless the reason says wrong or overlap. A reason that only calls the link weak, loose or tangential keeps it. Seven of the 22 recommended `partly` findings dropped under that reading and 15 stayed. The saved rows record the reading, so it could be re-applied without another judgment.

### The corrected reference

The corrected reference holds 97 required options in 70 sets, 142 recommended options in 126 sets and 80 equivalence groups. It retains 319 findings and drops 67. Of the 386 findings, 263 take a keep action, 56 a demotion and 67 a drop.

| Category | Emitted | Kept in category | Demoted to recommended | Dropped | Corrected |
|---|---|---|---|---|---|
| Required options | 199 | 97 | 56 | 46 | 97 |
| Recommended options | 101 | 86 | 0 | 15 | 142 |
| Equivalence groups | 86 | 80 | 0 | 6 | 80 |
| All findings | 386 | 263 | 56 | 67 | 319 |

The chart plots the same counts by category and action. Demotion to recommended applies to required options only, and 45 of the 80 kept equivalence groups are kept by exception.

![The 386 emitted findings appear by category and correction action. Required options were kept, demoted or dropped, while recommended options and equivalence groups were mostly kept.](/docs/charts/inference-reference-correction.svg)

## Where the method is used

The packet comparison and the local-model comparisons state their own variants, cohorts and numbers and link here for the corpus and the judge. The [Experiments section](/docs/experiments/README.md#inference) places this method page beside those reports. The confidence measurements and the full correction findings belong to separate reports.

## Limits of judged support

The corpus and the judge support comparisons between variants. They do not establish that a prerequisite is true.

### Judged support is not exhaustive ground truth

`supported` means that the supplied teaching text supports the claim under the rubric. It does not mean that the university requires the course. The judge read only the claim, the model's evidence, the target and the named courses, and it read their text truncated. No agreement measurement between the judge and a human reader is recorded, so the judge's own error rate is unknown.

`partly` combines a partial AND with a wrong category, and only the eight ambiguous required options were judged at the finer grain. Nine findings were `unclear` because the text was too sparse. The equivalence rubric is strict, and its equivalence verdicts were treated as a lower bound rather than an exact measure (interpretation).

### Only emitted claims were judged

The 386 findings cover 151 of the 200 targets. The other 49 targets produced no direct option or equivalence group, only routing or suppression, so no judged support includes them. The judge cannot penalise a true prerequisite that a model omitted, and it never saw a target with no finding.

A model that emits few, safe findings can therefore show higher judged support than a model that emits more. Judged support has different denominators across models, prompts and packets, and it is comparable only beside its emission counts. The corrected reference inherits every omission, because it corrects emitted findings and fills no gap. The project treats agreement with the corrected reference as a secondary diagnostic, not an accuracy score.

### One sample per slot

Each target and packet has one reference answer. The sample limit is visible in the pairs. The 100 paired answers produced 257 distinct findings, 52 in both answers and 205 in one. The overlap corresponds to about 0.34 finding F1. The packets shared a mean of 40 of 50 candidates, so most of the differences are consistent with sampling noise rather than the packet.

The request carried no temperature field, so the provider default applied. No self-agreement measurement was run, so sampling variability was not measured.

### Truncated and sparse text

The judge saw a bounded rendering. A course name was cut at 135 characters. Outcomes and content were each cut at 700 characters for the target and 450 characters for each named course. The stored text was passed with its markup as literal characters. A course with no outcomes or content contributes a name only, and some `partly` reasons say exactly that. The judge could not consult the rest of the catalogue or the official prerequisite record.

### One judge and one rubric

The judge model was the same at every stage. The verdicts are tied to that model's reading of the rubric. No sampling settings for the judge are recorded beyond the model and its low variant. No repeat judgment of the same item was measured, so judge stability is unknown.

The rubric was held unchanged across the prompt versions and local models so that their support numbers stay comparable. Its strictness, especially on equivalence, is a property of the measure, not of the models.

## Untested follow-up questions

Three questions remain untested.

1. A human re-read of a sample of the 386 findings would put a number on the judge's error. No such measurement exists.
2. A second DeepSeek answer per slot would separate sampling noise from packet or prompt effects. The 100 pairs show that one sample disagrees with another, but a self-agreement measurement was declined and remains untested.
3. Judged support over emitted findings cannot reward a prerequisite that no model emitted. Measuring recall needs a reference independent of the generated claims, and none exists.
