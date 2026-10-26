# Inference scheduling and disposition

Scheduling decides which target courses a processing cycle visits, how a failure is retried, and how an operator decision changes one target course.

## Which target courses a cycle visits

Every active canonical course is eligible for inference. An inactive course is never a target course, and it is a valid candidate source.

A target course is visited when its own teaching-text processing marker is false, or when the marker of any course in its selection is false. The marker records the exact effective text the course was last processed from, whether the course was active, and the accepted proposal pointer. The rerank stage and the inference stage read the same membership predicate, so a target course is reprocessed when its own text changed and when the text of a course in its selection changed.

A marker is scheduling state, so the catalogue can hold a processed course with no accepted result. [Inference coverage](/docs/reference/glossary.md#inference) is counted and read separately from the markers.

## What resets a target course

The marker is set false when the effective text of the course changes, and once when an inactive course becomes active without an accepted result. The hash behind the marker covers teaching text alone, so a change of generation model, prompt, configuration, or curriculum period does not reset a marker, and output accepted under one generation holds across all four.

A run reconciles every marker at entry and then visits the courses the markers and the membership predicate select. A visited target course reuses matching completed work. Pending work and failed attempts follow the retry policy.

## Cycles and stages

Work runs in one serial processing cycle with five stages: multiview, rerank, inference, publication, and complete. At the multiview stage the cycle visits every target course and stores each course's candidate pool. At the rerank stage it reduces each pool to that target course's shortlist. At the inference stage it runs or reuses each whole-target generation. At the publication stage it writes the retained results once. A completed cycle marks every catalogue course processed.

A target course that the membership predicate leaves out has its rerank and inference stages recorded as skipped, so it runs no rerank and no generation. A cycle that reaches publication with a failed target course is left incomplete, and the publication stage writes the accepted results that are available.

The cycle identity is built from the catalogue identity, the current embedding state, and the selection, context, and rerank settings. A run that finds an unfinished cycle with the identical identity and the identical target set resumes it. A changed identity or a completed cycle starts a fresh cycle across every active target course. A resumed run dispatches the cycle's current stage and the stages after it only, so a completed stage is never repeated.

## Failures, retries, and isolation

A failure is isolated to the target course that failed, and the run continues with the other target courses.

Multiview selection, rerank, and request preparation retry the same target course up to `INFERENCE_MAX_ATTEMPTS` times, which the example sets to three. When those attempts are used up, the stage is failed for that target course, its downstream stages are blocked, and a following run retries it.

A whole-target generation retries without a fixed attempt cap until one result is accepted or the run is stopped. The wait between attempts grows from `INFERENCE_RETRY_BACKOFF_SECONDS` toward `INFERENCE_RETRY_MAX_BACKOFF_SECONDS`, which the example sets to one second and 10 seconds, and it is waited in steps of `INFERENCE_RETRY_POLL_SECONDS`, so a stop or a restart is answered between steps. The first attempt of one calculation is greedy, and each following attempt samples at the configured retry temperature with a seed taken from the durable lifetime attempt counter, so a consumed seed is never drawn again.

Each failed generation attempt is recorded once with its stage, its fixed reason, its error type, and an attempt count. A target course whose generation failed retains its pool, its shortlist, and the work identity it was running, so the next entry resumes it at the failed stage instead of rebuilding it.

[Full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md#the-retry-rules-the-run-used) records these retry rules in a run over the whole catalogue.

## The fit rule

A generation request starts only when its rendered prompt tokens plus `INFERENCE_MAX_TOKENS` and `INFERENCE_FIT_HEADROOM_TOKENS` fit inside one configured local key. `INFERENCE_LOCAL_VARIANTS` names two ordered keys for the local language model, ordered by increasing context, and the first key that fits receives the request.

| Key | Meaning | Example |
|---|---|---|
| `INFERENCE_MAX_TOKENS` | The output cap reserved inside the context of a local key | 8192 |
| `INFERENCE_FIT_HEADROOM_TOKENS` | The template and JSON-mode margin reserved beside the output cap | 1024 |
| `INFERENCE_LOCAL_VARIANTS` | The two ordered local keys, by increasing context | 131072 and 163840 tokens |

Every key is in `config/inference.toml`. A packet that fits neither key is never shortened. It fails as one capacity failure for that target course, with the reason `context_exceeded`, and no generation request is made for it. The rest of the run continues normally, and a following run retries the target course.

The measured context each key holds is recorded with the sizing corrections in [Local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md#sizing-corrections).

## The periodic reboot

The worker restarts after a configured amount of model run time. A [periodic reboot](/docs/reference/glossary.md#administration) is taken at a safe point: the clock counts only the time a local model is loaded, and it samples at a completed target unit and at every recorded failed generation attempt, so repeated local failures cannot postpone the restart.

`WORKER_GPU_REBOOT_INTERVAL_MINUTES` in `config/worker.toml` sets the interval, and the example sets 120. After the restart the run continues with the same cycle and the pending work, and a completed stage is not repeated.

## Operator disposition

An operator can record one [disposition](/docs/reference/glossary.md#inference) for a target course: **done**, **failed**, or **automatic**, where automatic means that no decision stands. The decision is durable and belongs to the course marker, so it holds across a stop, a restart, another cycle, and a change of teaching text.

| Decision | What it does to scheduling | What it does to coverage and published results |
|---|---|---|
| Automatic | Ordinary scheduling. The target course is visited when its own marker or a member's marker is false. | The inferred set and equivalence groups of its accepted proposal are retained and published. |
| Done | The target course is never generated while the decision stands, and no inferred output is expected from it. | Counted as complete coverage with no inferred output, and publication removes its inference-produced inferred set and equivalence groups. |
| Failed | The target course is terminal. It is skipped in every pass, visited after the ordinary target courses, and the cycle is left incomplete while the decision stands. | A result the catalogue already holds for it is published and counted. The decision grants no result and no coverage of its own, so a target course with no accepted result is uncovered. |

> [!WARNING]
> A **done** decision completes the target course without an inferred result. It removes the inference-produced inferred set and equivalence groups of that target course and counts as complete coverage, rather than storing a generated empty result.

A **failed** target retains the last accepted result the catalogue holds for it, and that result is published and counted while the decision stands. The decision itself grants no result and no coverage, so a failed target course with no accepted result is uncovered. The cycle cannot complete while a failed target course stands, and recording the decision on a cycle that was complete reopens it at the inference stage.

Clearing a decision returns the target course to automatic scheduling. The marker becomes unprocessed, the inference stage reopens, and a completed upstream stage is preserved when a retained pool or shortlist can support it. Only the stages that genuinely cannot be recovered reopen, so clearing one target course does not repeat the work of the others.

The decision is recorded on the selected dataset while the stages are idle. [Operator menu](/docs/operations/operator-menu.md) describes the entry that sets it.

The diagram shows the three decisions of one target course, Automatic, Done, and Failed, and every transition an operator records between them. An operator sets done or sets failed from any decision, and clearing returns the target course to Automatic. A repeated decision is a no-op.

![Three decisions for one target course, Automatic, Done, and Failed, with a labelled transition for setting done, for setting failed, and for clearing. Automatic holds ordinary scheduling, Done means the target course completes without inferred output, and Failed means it is skipped with the cycle left incomplete. Every transition between the three decisions is drawn, including Done to Failed and Failed to Done, and clearing returns the target course to Automatic.](/docs/diagrams/inference-disposition.svg)

The stages, their stored checkpoints, and the transitions between them are described in [Inference pipeline](/docs/backend/inference/inference-pipeline.md). The fit rule and the local models are described in [Inference](/docs/backend/inference/inference.md).
