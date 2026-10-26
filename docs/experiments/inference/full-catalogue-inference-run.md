# Full-catalogue inference run

This report covers the operational acceptance, readiness, recovery and full-catalogue execution of the inference stage over every active target course.

**Evidence status:** Observational. **Run dates:** 30 September to 25 October 2026.

The [Experiments overview](/docs/experiments/README.md) states the catalogue, the evidence labels and the hardware specifications. The [Inference experiments](/docs/experiments/inference/README.md) overview places this report in the category. This report covers the execution line of the inference category: whether one result could be published at all, whether a worker night could stop and resume, whether the full catalogue could be prepared for a bulk run, how failures recovered, and what the full run published. The quality of the selected configuration is reported in [Held-out model quality](/docs/experiments/inference/held-out-model-quality.md), and its fit and speed in [Local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md).

The measurements are read-only observations of the rehearsals that preceded the run and of the completed run, with no variant measured against another.

## The question

Inference proposes prerequisites for one target course from its teaching text and a bounded candidate list. Every active canonical course is a target, an inactive course is a valid candidate source, and one cycle visits every target. The operational question was whether that cycle could complete over the whole active catalogue on a part-time worker without losing a target.

The scale sets the constraint. The catalogue holds 4,543 active targets among 11,086 courses. Each target needs a candidate pool, a rerank and one generation call, and the run had to finish inside a month from its start on an AMD Radeon RX 9070 XT (16 GB model), in a machine that also served other work outside the dedicated measurement windows. A defect in one target can go unseen at small scale, so the line tested publication, then a night window, then the full catalogue's preparation, before the whole catalogue ran.

The quality question is separate and is not re-measured here. The configuration had been judged on 150 held-out packets, and the run applied it. This report measures execution, [inference coverage](/docs/reference/glossary.md#inference) and recovery, not whether a proposed prerequisite is right.

## Setup

### The pipeline a run executes

One processing cycle advances through multiview, rerank, inference and publication and reaches complete when every target checkpoint is terminal and no target is failed. The three compute stages record a durable checkpoint per target, so a stopped run resumes at the first unfinished unit, and publication runs once over the retained cohort. [Inference processing](/docs/backend/inference/README.md) states the cycle and its checkpoints.

The fit rule decides the route. A target goes to the local model when the rendered prompt, an output cap of `INFERENCE_MAX_TOKENS` and a headroom of `INFERENCE_FIT_HEADROOM_TOKENS` fit one local key. A packet that fits no key is never shortened. The product reports it as one capacity failure for that target with the reason `context_exceeded`, and this run supplied an explicit oversize route that sent each such target whole to DeepSeek V4.1 Flash. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md) states the local fit rule and the retries.

A run ends through the stage lifecycle. Pause unloads the local model at a checkpoint and keeps the session. Stop finalizes on the worker, returns the worker's dataset copy and makes the verified copy the selected dataset. [Stage lifecycle](/docs/operations/stage-lifecycle.md) and [Worker sessions](/docs/operations/worker-sessions.md) describe the states and the return.

### The configuration the run applied

| Route | Model | Quantization and context keys | Output contract |
|---|---|---|---|
| Local generation | Qwen3.8-27B | IQ3_MIX, 12.6 GB, 131,072 tokens with MTP and 163,840 without, `q4_0` KV | Prompt v9, schema v2, pipeline v1 |
| Rerank | BAAI/bge-reranker-v2-m3 | Q8_0, top 50 of a 1,000-course pool | Pair scores only |
| Oversize generation, the route this run supplied | DeepSeek V4.1 Flash | Thinking enabled at low reasoning effort, 40,000-token output cap, no temperature or seed sent | Prompt v9, schema v2, pipeline v1 |

The pipeline version was `v1`. No quality filter ran inside the run: recommendations were kept, and every confidence and finding flag was retained as raw evidence. The full-catalogue run used the model, prompt and result schema whose quality the [held-out benchmark](/docs/experiments/inference/held-out-model-quality.md) judged before the run started.

The local model and the rerank ran on an AMD Radeon RX 9070 XT (16 GB model) on ROCm 7.2.1, in a machine with 33.4 GB of usable RAM. The earlier fit measurements ran under a 4.295 GB memory limit and 8.590 GB of swap. The readiness rehearsals on 2026-10-06 ran under the 4.295 GB memory limit, and no memory-cap record covers the full run.

### The cohort

The run read the fixed catalogue snapshot: 11,086 courses, of which 4,543 are active, and 58,962 teaching-text chunks. Every active canonical course is an eligible target and every course is a candidate source. The rerank kept 50 candidates per target, so the run's expected packet-candidate count was 50 for each of the 4,543 targets, or 227,150 in total.

### What was and was not measured

The post-run read counted coverage, routes, published sets, groups and warnings on the selected dataset. It did not measure a per-target split of prefill, decode, load and transfer time. It did not reconstruct prompt-token counts for the oversize route, which the product does not retain. Three checks of the finished catalogue were also not run: a representative command acceptance over published results, an unchanged-rerun proof and a changed-source recalculation proof.

## Result acceptance on 20 targets

On 2026-09-30 the cohort was fixed before generation: the first 20 target groups in sorted order from a 200-target list, taken only when active at preflight. All 200 listed targets were active with a selected representative, so no exclusion applied. Twenty targets at 50 candidates each gave 1,000 packet candidates, equal to the expected count.

Every target completed locally in one validated attempt. Selection and generation together took 137 to 216 s per target, and generation alone 35 to 98 s. All 20 took the local route and none took the oversize route.

Two targets, MEDALATEPA and TEA.821, lost the connection during the rerank request, before any work row existed. Each was retried once and both retries succeeded. The rerank process ran for 55 minutes and served about 37,000 requests without an error line, so the drop was recorded as a transport failure and the failed attempts were retained beside their retries. A memory reading under load was attempted and failed, so memory under load is recorded as unavailable rather than estimated.

The run's diagnostics before publication are below.

| Measure | First acceptance run |
|---|---|
| Eligible, selected and processed targets | 20, 20, 20 |
| Local route, oversize route | 20, 0 |
| Composed proposals | 12 |
| Published inferred sets | 0 |
| Equivalence groups proposed | 3 |
| Failed targets | 0 |
| Packet candidates observed and expected | 1,000, 1,000 |

The read-only review passed its structural invariants. No suppressed candidate reached a proposal, every expression and group carried its own proposal evidence, each of the 12 composed targets had complete coverage with 50 processed sources, and each of the three global groups had its supporters and at least two members present in the catalogue. Disagreement with the frozen reference answer was recorded as a diagnostic, not as a gate. Several targets differed in their required, recommended and equivalence sets, and some matched structurally, including DPES.505, MEDATYTEPA, KIE.AV.345 and DPENS.566.

### The defect that stopped publication

Eight of the 20 valid results were complete empty results. They named no required, recommended or equivalence finding, and their routing confidence was 0.3 with the routing flag `insufficient_course_information`. Each was validated and stored as a schema-version-2 result. Proposal composition rejected all eight with a message that composition requires a validated schema-version-2 result.

The cause was in the stored read, not in generation or publication. A complete empty version-2 document carries no per-finding flag anywhere, because its option and group lists are empty, and that makes it structurally identical to a version-1 document. The stored result was re-read through a left-to-right union that tries version 1 first, so exactly this shape came back as a version-1 result and composition refused it. The composition path had been exercised only with the in-memory attempt, never with a re-read of the stored document, so the shape was not covered.

The fix bound the stored-result read to the schema recorded on the run, so a stored document is validated against the schema that produced it. The publication writer did not depend on the concrete result type, and it handled a target with no expression correctly once a proposal existed.

The impact was a partial publication that would have looked complete. Publication would have written the 12 non-empty targets and reported the eight empty ones as having no accepted result. The run halted before the publication writer was called, and the final stores held 0 inferred sets, 0 groups and 0 members. All works, attempts and 12 proposals were retained. That halt is the result of that run, and the completion below is the result that stands.

[Inference](/docs/backend/inference/inference.md#proposals-and-publication) states what a publication run writes from an accepted result.

## Completing the acceptance from stored evidence

The completion ran on 2026-09-30 from the same 20 stored works, with no GPU, model, rerank, embedding or external call. It was an accepted exception for unchanged inputs, not a reusable operational shortcut. Recurring work selects fresh inputs, and the exception covered acceptance only.

The read-only inspection matched every recorded identity before any write. The run's recorded identities held the same 20 targets. The run's recorded hashes, the model, rerank and runtime identities, the pool and final candidate counts, the prompt, schema, pipeline and proposal versions, the prompt-tree and system-prompt hashes, the catalogue and embedding-configuration identities, and every work and run identity all matched. All 20 chains held one completed work and one validated attempt that re-read as a concrete version-2 result. The final stores held 0 inferred sets, 0 groups and 0 members.

The eight stored complete empty results were composed through the product's proposal command. Each returned no prerequisites and no equivalence group, and the retained proposal rows went from 12 to 20. The 12 original proposal identities did not change.

Prepare then reported eligible, selected, processed and accepted at 20, with 20 local and 0 oversize targets, three groups and 0 warnings. Every target payload was complete with 50 processed sources, and the eight empty payloads had no expression and 0 accepted sources. Publication wrote the cohort once: 20 published sets and 0 failed targets. A read-back through the inferred-set reader returned all 20 as current and complete, the equivalence reader resolved the three groups from each of their members, and the final stores held 20 inferred sets, three groups and 17 group members.

A product command on EDU.050 returned complete coverage with 50 eligible, 50 processed and 0 accepted sources, no requirement nodes and no route courses. That proved a complete empty result through the stored read path. The populated payloads were proven by their prepared expressions and the final readers.

The completion did not recompute embedding rows or rerank scores. Their unchanged state was the same-day premise, and the selection, input and policy hashes were the evidence recorded that day. Disagreement with the frozen reference was retained as a diagnostic: five of the eight empty results matched it exactly, MEDALILE and EDU.050 each named one required option the model did not emit, and VIM.VI.280 named one equivalence group.

## Worker resume and checkpoint readiness

The night-run acceptance on 2026-10-06 exercised the five stage actions on a disposable dataset with three active targets and 1,000 inactive sources, one packet built to be oversized, on the worker and the GPU. It made one external call.

### The routing defect

The fit check counted prompt tokens through the first ordered key and unloaded the local model before an oversize route. Every packet that fitted neither key therefore unloaded the 27B model, and the next local target reloaded it. A target that needed the larger key reloaded twice. In a first pass over 10 active targets, five leaked oversized text into their packets, each took the oversize route, and the model cycled with a load of about 28 s and about 3 s alive.

The fixture was corrected first, so the oversized text sat in a cell that the rerank document truncates before it and only the intended target carried an oversized packet. The router was then fixed at its owner. It counts tokens through the loaded key, loads the first ordered key only on first use, switches to the larger key only when only that key fits, and leaves the loaded runtime loaded across an oversize call. The third window measures the result.

### The three windows

| Window | Coverage read | What it showed |
|---|---|---|
| First, partial stop | Eligible 3, retained 2, published 2, uncovered 1, failed 0 | Two local targets at about 25,400 prompt tokens and one validated attempt each. A pause with the model loaded unloaded it, left the worker idle and stopped the database service. Resume continued the same session. |
| Second, completed | Eligible 3, retained 3, published 3, uncovered 0, failed 0 | The two local targets kept an attempt count of 1, so their completed work was reused. The third took the DeepSeek route with 181,131 prompt tokens and one validated attempt. |
| Third | Eligible 3, retained 3, published 3 | One rerank load and one generation load served two local targets and one oversize target, and the generation runtime was loaded across the oversize call. |

The oversize target's 181,131 prompt tokens exceed what the larger key can hold, because that key reserves the 8,192-token output cap and the 1,024-token headroom inside 163,840 tokens:

```text
163840 - 8192 - 1024 = 154624
```

The target therefore had no local route, and the acceptance supplied an explicit oversize route that sent it whole to DeepSeek V4.1 Flash.

### The checkpoint restart

One restart was observed. The worker paused with a restart due at 60.37 s of loaded model time and kept the same session. After the restart the worker's own boot identifier had changed, and the same session continued with only pending work. The repeated restart cadence was not observed while it happened, and automated tests cover it. Translation lifecycle was outside this line.

## Bulk-run preparation

### What readiness covered

Before the run, the selected dataset was enrolled and accepted by the code at hand: 11,086 courses, 4,543 active, 58,962 completed embeddings, no cycle, and no pending schema migration. All four stage tools reported idle. The worker ran the prepared code and its read-only preflight reported every resource ready, with no missing component. The selected dataset and the backups were read only, and the database write counters before and after were equal.

Worker preparation is separate from the recurring start. One attempt on 2026-10-01 stopped before the worker was changed: a stale translation session pointer was held in the session record, and the worker's tree held an uncommitted tracked configuration file. Both were resolved reversibly, the pointer moved aside and the file stashed, and the pull then moved the worker to the target branch. The check that followed reported the locked dependencies missing for the target revision, and a full setup supplied them.

Two later preparation records on 2026-10-04 reported every resource ready, one with 56 s of setup and 20 s of preflight, and a foreground re-run with 39 s and 15 s. The re-run superseded the earlier record, which came from an interrupted backgrounded run.

### The first rehearsal and its two defects

The first rehearsal on 2026-10-06 failed at full scale, in two places.

The disposable copy could not be restored. PostgreSQL's parallel index build could not allocate a 64 MB shared-memory segment because the database container kept Docker's default shared-memory size. The setting was raised to 1 GB. The restore then succeeded and produced a dataset verification identical to the reference receipt.

The worker session then failed after about 143 s with a database driver error, and the cause was not memory. Two readiness reads built one statement over the whole catalogue. One held 294,810 bind parameters from 58,962 chunk identities, above the driver's ceiling of 65,535 parameters. The other held 11,086 course pairs and exceeded PostgreSQL's statement-complexity limit. Both reads were changed to bounded batches of 1,000 identities or pairs. The embedding-state digest builds the same record list, sorts it by the same key and hashes it with the same function, so its bytes, the work identities and the reuse did not change.

### The memory measurement

| Measurement | Python peak (MB) | Database peak (MB) |
|---|---:|---:|
| Preparation before the query fix | 496 | 2,062 |
| Preparation after the query fix | 475 | 2,052 |
| First multiview unit after the fix | 575 | 1,997 |
| Restore under a 4.295 GB memory limit | not applicable | 1,686 |

The first multiview unit held 575 MB resident and reached a high-water mark of 621 MB. The Python peak rose step by step: 86 MB at baseline, 275 MB with the catalogue loaded, 352 MB with the chunks, 426 MB after the readiness read, 449 MB after the embedding-state read and 475 MB with the first multiview pool. The restore ran under a 4.295 GB memory limit, a 12.885 GB memory-plus-swap limit, of which 8.590 GB was swap, and 1.074 GB of shared memory. It succeeded in 99 s, peaked at 1,686 MB and recorded no out-of-memory kill.

The conclusion was that the 4.295 GB worker budget was not the constraint. The worker process peaked at 575 MB and the database at 2,062 MB against that budget. PostgreSQL memory tuning and per-target lazy course text were therefore not applied, because the measurements did not show that either was needed.

### The second rehearsal

| Step | Result |
|---|---|
| Worker code update and preflight | Prepared revision, `resources.ready=true`, no missing component |
| Create, restore and verify the disposable copy | 138 s |
| `inference start` | Exit 0, returns in about 0.5 s, detached |
| Status at 203 s | Running, multiview unit 2 |
| Status at 278 s | Running, multiview unit 15, 0 failed |
| Pause at 303 s | Paused at multiview unit 19, worker idle, database service stopped |
| Resume at 320 s | Running, and multiview unit 20 at 368 s with pending work only |
| Stop | 192 s, idle at 571 s |
| Coverage after the stop | 4,543 eligible, 0 failed, 24 multiview units completed, a non-null cycle |

Worker memory peaked at 2,597 MB of the 4,104 MB available to it, the database container used 1,890 MB, 1,506 MB remained available, and no out-of-memory stop occurred. Multiview advanced from unit two to unit 15 in 75 s, about 10.4 units per minute, which projects a full-catalogue multiview time of about 7.3 hours. The window including preparation ran about 601 s, at the 10-minute budget rather than comfortably below it. The first rehearsal had used about five minutes before it failed.

Readiness did not prove the rerank, generation and publication stages at full scale. Their per-target reads were below the driver's parameter ceiling, and the night-run acceptance had exercised them at small scale. The full run is what exercised them over the catalogue.

## Failure recovery during the run

### The retry rules the run used

Preparation, multiview and rerank retry one target up to three times. After those attempts the stage is failed for that target, its downstream stages are blocked, and a following run retries it. Whole-target generation retries locally without a fixed attempt cap until one result is accepted or the run is stopped, and the wait grows from 1 s toward 10 s in 1 s steps, so a stop is answered between steps. The first attempt of one calculation is greedy and each retry samples at a configured temperature from a durable lifetime counter, so a consumed seed is never drawn again. A failure is isolated to its target, which keeps its pool, its shortlist and its work identity for the next entry. Each failed generation attempt is recorded once with its stage, fixed reason, error type and attempt count, and every recorded failure samples the restart clock, so repeated failures cannot postpone a restart.

The oversize route is bounded differently. It allows ten generation requests per whole-target pass, including the first, and a fresh pass renews that budget without renewing the local greedy status or the lifetime seeds.

### The mid-run stop and the end state

By the stop on 2026-10-12 the selected dataset held 727 published inferred sets and 145 recorded target failure rows, against 4,543 eligible targets. The run finished with 4,543 published sets, 0 failed targets, 0 uncovered and 0 pending targets, and no operator disposition.

| Measure | Mid-run stop, 2026-10-12 | Post-run read, 2026-10-25 |
|---|---:|---:|
| Published inferred sets | 727 | 4,543 |
| Recorded target failure rows | 145 | 0 |

The chart compares the two reads.

![Published inferred sets and recorded target failure rows at the two reads. Published sets rise from 727 to 4,543 while recorded failure rows fall from 145 to 0.](/docs/charts/inference-run-recovery-checkpoints.svg)

No failure survived the run. A target whose stage had failed would have blocked its downstream stages, and the run reported one complete cycle with no failed target, so every target that recorded a failure ended with an accepted result. That is an interpretation from the end state. The post-run read reports the failure rows as one count, so this report cannot say which targets failed or how often, and the retry history of the run is not reconstructed.

The run also spanned a code change. On 2026-10-12, while the run was stopped, the selected dataset was backed up with its embeddings and migrated through two additive schema revisions, and the retry and disposition code was deployed. The migration preserved the retained counts, a model-free readiness pass succeeded, and an ordinary start continued the run. The retained cycle and its checkpoints were not lost.

## The full-catalogue run

The run finished as one processing cycle at the complete stage. Its coverage and output counts are below.

| Measure | Value |
|---|---:|
| Eligible active targets | 4,543 |
| Multiview, rerank and inference completed | 4,543, 4,543, 4,543 |
| Skipped targets | 0 |
| Retained complete and published | 4,543, 4,543 |
| Uncovered, failed and pending targets | 0, 0, 0 |
| Local route | 4,520 |
| DeepSeek route | 23 |
| Packet candidates observed and expected | 227,150, 227,150 |
| Published sets with an expression | 2,348 |
| Published complete empty sets | 2,195 |
| Equivalence groups | 345 |
| Strict-ancestor warnings | 669 |
| Operator dispositions | 0 done, 0 failed |

The chart shows the target counts at each completed stage and the content of the published sets.

![Targets at each stage of the full-catalogue run. Every stage holds all 4,543 eligible targets, and the 4,543 published sets split into 2,348 with an expression and 2,195 complete empty results, with no uncovered or failed target.](/docs/charts/inference-run-stage-outcome.svg)

Every eligible target was retained and published. Of the 4,543 published sets, 2,348 carry an expression and 2,195 are complete empty results. An empty set is a complete result that names no option, so it contributes no inferred prerequisite and is not counted as uncovered. The run also wrote 345 equivalence groups.

The 23 oversize targets are the measured gap between the full-catalogue packets and the two local keys. Each packet fitted neither 131,072 nor 163,840 tokens with the output cap and headroom, and the run's oversize route sent each as one whole target to DeepSeek V4.1 Flash with no truncation. The 4,520 local targets were served by Qwen3.8-27B under prompt v9 and schema v2.

The fit rule tests each prepared packet against the local keys in configuration order. The prompt count from the prepared request, the 8,192-token output cap and the 1,024-token margin are added, and the total must fit the key. The first key holds 131,072 tokens and enables MTP speculation with two draft tokens. The larger key holds 163,840 tokens and runs without MTP. A packet that fits the first key is generated on that key, and a packet that fits only the larger key is generated on the larger key.

When neither key fits, the packet has no local route. When no oversize route is supplied, the product records one capacity failure for the target with the reason `context_exceeded`, makes no generation request and writes no work or proposal for it, and blocks its downstream stages. The routing step does not shorten the packet.

The diagram shows the two fit tests, the product boundary and the route the run supplied outside the fit rule.

![A prepared packet is counted with the 8,192-token output cap and the 1,024-token margin, then tested against the 131,072-token MTP key and the 163,840-token no-MTP key. A packet that fits neither ends at the context_exceeded capacity failure on the product path when no oversize route is supplied, while the dashed route supplied by the run sends the whole packet to DeepSeek V4.1 Flash for 23 targets.](/docs/diagrams/inference-run-capacity-routing.svg)

This run supplied the route explicitly, so its 23 neither-fit targets took the dashed branch and none ended at `context_exceeded`. The route sends the packet whole and without truncation to DeepSeek V4.1 Flash.

Both routes call the same whole-target writer, which validates the result and records the attempt for the same target and cycle. The route opens only after a completed prompt count finds no fitting key, so a tokenizer failure, a refused admission or a local generation failure does not reach it.

All 11,086 catalogue processing markers are processed. That covers the 4,543 active targets and 6,543 inactive courses that served as candidate sources without target attempts of their own. The local policies were the configured ones: `INFERENCE_ROUTING_POLICY` `solo_fit_only`, `INFERENCE_RECOMMENDATION_POLICY` `include` and `INFERENCE_FINDING_FILTER_POLICY` `none`. The routing policy is strict fit-only and supplies no fallback route, so the run added its oversize route explicitly. No operator decision narrowed the cohort and no target was skipped.

The model attempts ran from 2026-10-09 06:19 UTC to 2026-10-21 08:07 UTC. That is an elapsed span across part-time windows, pauses, restarts and dataset transfers, not a generation rate. The held-out measurement of 60.5 s per complete target is the generation figure, reported with its cohort in [Local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md).

The 669 strict-ancestor warnings were recorded as review evidence only. They scheduled no model work and triggered no rerun.

## Interpretation

The operational path completed. Every eligible target reached retained complete and published, the uncovered, failed and pending counts are zero, the two route counts sum to the cohort, and the packet-candidate count equals 50 for each target. On the counts it reports, the run has no silent gap.

The pre-scale checks caught blocking defects. The acceptance run exposed a proposal composition path that would have kept eight valid results out of publication, the night-run acceptance exposed a router that unloaded the model for every oversize packet, and the bulk rehearsal exposed the shared-memory and query limits. None of those defects reached the full run, and the corrected behavior is what the run measured.

The empty share is the largest fact the run adds. 2,195 of the 4,543 published sets name no option. This report cannot separate a correct "no prerequisite" answer from a model omission, because the coverage counts measure stored results, not correctness. The judged-support method measures emitted findings only, so it inherits the same limit, as [reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) states.

Readiness changed the preparation and two read paths, and it stopped there. The two full-scale defects were fixed at their owners, and the memory measurements showed the 4.295 GB cap was not the constraint, so no PostgreSQL memory tuning and no per-target text change was applied. The second rehearsal then reproduced the run's start, pause, pending-only resume and stop on a full copy.

The line does not support quality, per-target speed, rerun behavior or invalidation behavior. The coverage counts and the route split are the evidence, and the quality evidence is on the held-out report.

## Limitations and corrections

Five corrections changed an earlier result or a planned step, and each result that stands is stated with it.

1. The first 20-target acceptance halted on the complete empty composition defect. The result that stands is the completed acceptance: 20 published sets, including eight complete empty results, with three groups and 17 members.
2. The fit-only router unloaded the local model before every oversize route. The result that stands is one rerank load and one generation load per window across local and oversize targets.
3. The first bulk rehearsal failed on shared memory and on unbounded query parameters. The result that stands is the second rehearsal, which passed with bounded reads and a 1 GB shared-memory setting.
4. The memory question was answered by measurement, so the proposed PostgreSQL tuning and per-target lazy text were not applied.
5. The first worker preparation record came from an interrupted backgrounded run and was superseded by a foreground re-run at the next revision.

The remaining limits are these.

- The post-run check was narrowed to whether the inferred results exist. The representative command acceptance, the unchanged-rerun proof and the changed-source recalculation proof were not run, so the finished catalogue has no measured rerun behavior and no measured invalidation behavior.
- Prompt-token counts for the 23 oversize targets are not retained by the product and were not reconstructed, so the oversize route has no token distribution.
- Target failure rows are counted, not classified. The run's retry history is known only from the two reads.
- The 20-target acceptance was completed from stored evidence under a same-day unchanged-input exception. Embedding rows and rerank scores were not recomputed, so the completion is not evidence of fresh operational selection.
- The 669 strict-ancestor warnings were not adjudicated, and they triggered no rerun.
- The 345 groups consolidate exact member sets. This report does not test them against official substitutions.
- Memory under load is unavailable for the first acceptance run.
- The elapsed span of the run says nothing about throughput.

## Setup details

The cohort is every active canonical course in the fixed snapshot, 4,543 of 11,086, with 58,962 teaching-text chunks. The candidate pool holds 1,000 courses, the rerank keeps 50, and the packet carries those 50 candidates.

The fit rule reserves the output cap and the headroom inside the local key:

```text
fits = prompt_tokens + 8192 + 1024 <= key_context
```

The local keys are 131,072 tokens with MTP and 163,840 tokens without, both with `q4_0` KV, and the first key that fits receives the request. The product reports a packet that fits neither as one capacity failure with the reason `context_exceeded`, and this run supplied an explicit oversize route that sent each such packet whole to DeepSeek V4.1 Flash.

The cycle identity is built from the catalogue identity, the current embedding state and the selection, context and rerank settings. A run that finds an unfinished cycle with the same identity and target set resumes it, and a resumed run dispatches the current stage and the stages after it only. A target is visited when its own teaching-text marker is false or when the marker of a course in its selection is false.

A checkpoint is a committed unit of work. Inference records one per target, publication runs once over the retained cohort, and a completed cycle marks every catalogue course processed. The restart clock counts only the time a local model is loaded, samples at a completed unit and at every recorded failed generation attempt, and uses `WORKER_GPU_REBOOT_INTERVAL_MINUTES`, which the example sets to 120 minutes. The night-run rerun set it to 600 minutes for the whole rerun, and no further restart occurred.

A stop finalizes on the worker, imports the retained output into the worker's copy, exports a snapshot, verifies it against the snapshot taken at the start, restores it, selects it and rotates older datasets. A verified receipt is required before the worker copy is dropped.

Measured memory figures are decimal MB and GB, converted from the binary units the measurements recorded. Configured limits are stated as configured. Memory under load is reported as unavailable where the reading failed.

## Untested follow-ups

1. An unchanged rerun on the finished catalogue would show that matching work is reused and no target is regenerated. It was not run.
2. A changed-source recalculation would show that only the affected targets re-enter, and that unchanged courses which become candidates are picked up. It was not run.
3. A per-target time and token split, including the 23 oversize packets, would separate prefill, decode, load and transfer from the elapsed span. The product does not retain the oversize counts, so the split needs additional instrumentation.
