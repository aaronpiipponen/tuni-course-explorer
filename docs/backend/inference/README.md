# Inference processing

Inference processing reads effective text with local language models and publishes inferred prerequisites apart from the official catalogue.

## Label safety

A target packet carries the target course, its ranked candidates, and the effective text of each. Official prerequisite structure is excluded from candidate selection and every model input, and the rendered request carries no label, no rank, and no target-shaped example. The fit rule assigns each target to one local model key, and [Inference](/docs/backend/inference/inference.md) describes what the stage reads and writes.

## The pipeline and its checkpoints

One processing cycle advances through the stages multiview, rerank, inference, and publication, and reaches complete when every target checkpoint is terminal and no target is failed. The three compute stages record a durable checkpoint per cycle and target, so a stopped run resumes at the first unfinished unit of work. Publication runs over the retained cohort as one stage and writes no per-target checkpoint. The rerank and inference stages run only for the targets the membership filter selects.

## Scheduling and publication

A processing marker per canonical course holds the hash of its teaching text, whether it was processed, a pointer to its accepted proposal, and the operator disposition. An operator marks one target done or failed, and a marker carries no disposition when the stage schedules that target automatically. A change to the effective text resets the marker. Publication writes a stored inferred set as one whole accepted result, so a target has one set at a time. A target with no accepted result and no operator decision is uncovered, and an operator-done target completes with no inferred output. [Inference coverage](/docs/reference/glossary.md#inference) reports the counts behind those states, and [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md) states the fit rule and the disposition outcomes.

[Inference experiments](/docs/experiments/inference/README.md) reports the fit, retrieval, prompt, held-out quality, and full-catalogue measurements behind the selected model, the two context keys, and the policy that applies no filter to the output.

The module layout, the stored identities, and the checkpoint contract behind this behavior are described in [Inference pipeline](/docs/backend/inference/inference-pipeline.md).
