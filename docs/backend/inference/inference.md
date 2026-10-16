# Inference

Inference reads the effective text of a target course and proposes inferred prerequisites and equivalence groups, stored apart from the official catalogue.

## What inference produces

Inference proposes [inferred prerequisites](/docs/reference/glossary.md#prerequisites-and-routes) from the teaching text of one [target course](/docs/reference/glossary.md#inference) and records courses that the text treats as interchangeable as equivalence groups. Every inferred prerequisite belongs to a required or a recommended category, and an equivalence group holds two or more courses.

Inferred output is written to its own tables, beside the official catalogue. Writing inference output never modifies an official prerequisite, an official substitution, a course, or a module. The interface identifies inferred relationships separately, and the graph includes them only when the **Inferred** toggle is on. The stores and the separation are described in [Data model](/docs/backend/catalogue/data-model.md).

A successful target course receives one complete result, written as a whole. The result carries its direct prerequisites as required and recommended options, its equivalence groups, and its [finding flags](/docs/reference/glossary.md#inference). Each option and each equivalence group carries its own flag list, and a list may be empty.

## The target course and its teaching text

One run judges a target course from that course's own teaching text together with a bounded list of candidate courses. The request carries a packet that holds the target course and its ordered candidates, and each course arrives with its identity, its course code, its activity state, and its effective text. [Inference pipeline](/docs/backend/inference/inference-pipeline.md) lists the exact fields of the packet.

Only effective text enters the packet. The packet carries the identity, the code, the activity context, the effective text, and the provenance of each course. The packet and the prompt hold only those fields, so an official prerequisite option or an official substitution option never reaches the model through them.

The whole packet is sent or the target course fails. A request whose packet fits no configured local key is reported as one capacity failure for that target course, with the reason `context_exceeded`, and the run continues with the other target courses. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md) states the fit rule.

The diagram follows one target course from its effective text through candidate selection, generation, and validation to the stored inferred set. The accent outline marks the label-safe model inputs, which exclude official prerequisite structure from candidate selection and the model input. The official prerequisite structure enters only at the proposal, which deduplicates the accepted result.

![Effective text feeds a candidate pool, a rerank, and a packet. A local language model generates a result, validation accepts it, a proposal deduplicates it against the official prerequisites, and publication writes the inferred set. The accent outline marks the label-safe model inputs, which exclude official prerequisite structure from candidate selection and every model input.](/docs/diagrams/inference-pipeline.svg)

## Label safety

[Label safety](/docs/reference/glossary.md#inference) separates the evidence used to propose a prerequisite from the official answer. Candidate selection ranks courses from their embedded teaching text, the packet holds effective text and identities, and the prompt and the model input are assembled from that evidence.

> [!IMPORTANT]
> Official prerequisite structure is excluded from candidate selection and every model input. The composer reads the official prerequisite and substitution options only after a result exists, so the model that proposes a prerequisite never sees the official answer.

## Candidate retrieval and rerank

Candidate courses come from the [embedded teaching text](/docs/backend/text-and-vectors/embeddings.md) of the catalogue. A target course is first compared with every represented course, and the closest candidates form a pool of `INFERENCE_SELECTION_POOL_K` courses. The pool combines one comparison over every field with one comparison per configured field, and the combined order is deterministic. A second step, the rerank, scores each target and candidate pair with a cross-encoder and retains the strongest `INFERENCE_SELECTION_FINAL_K` candidates for the language model.

| Key | Meaning | Example |
|---|---|---|
| `INFERENCE_SELECTION_POOL_K` | The number of closest courses the pool retains before the rerank | 1000 |
| `INFERENCE_SELECTION_FINAL_K` | The number of candidates the rerank retains for the language model | 50 |
| `INFERENCE_MULTIVIEW_EVALUATION_FIELDS` | The teaching-text fields the pool compares in their own view | name, content, outcomes |
| `INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET` | The offset that fuses the field views into one pool order | 60 |
| `INFERENCE_RERANK_QUERY_MAX_CHARACTERS` | The character bound of the target text one rerank request sends | 1536 |
| `INFERENCE_RERANK_DOCUMENT_MAX_CHARACTERS` | The character bound of one candidate text a rerank request sends | 1536 |

Every key is in `config/inference.toml`. The candidate pool holds both active and inactive courses, because an inactive course is a valid prerequisite source.

Each rerank request carries one target text and one candidate text, rendered from the course code and the effective teaching cells only. The scored order selects the candidates of the packet, so the packet holds the strongest candidates in one deterministic order.

## Generation and validation

Each generation attempt asks the local language model for one complete result for its target course. The result states a required option set, a recommended option set, equivalence groups, and target-level routing metadata. Each option names its member course codes, its evidence, its confidence, and zero or more finding flags, and the configured finding policy retains every flag. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md#failures-retries-and-isolation) describes retries after a failed attempt.

Model output is untrusted input. A result is accepted only when it parses as strict JSON and validates against the result contract, schema `v2`. The contract refuses a contradictory answer, an option or group repeated in a logically identical form, a course that is both required and recommended, a suppressed candidate that is also a direct option, and the target course as its own direct or suppressed source. It also refuses a code that names no curriculum course and a code that names two canonical courses, and a confidence outside 0 to 1. An equivalence group may contain the target course.

An accepted result states one complete answer for its target course, so a partial or contradictory answer is refused rather than repaired. [Inference pipeline](/docs/backend/inference/inference-pipeline.md) lists the exact contract rules, the finding-flag vocabulary, and the emitted schema.

### Direct prerequisites and suppression

The model classifies each candidate and records every non-direct candidate with its raw outcome. A candidate whose outcome is `too_basic_transitive` is a broad or transitive foundation below the target's entry level, and it is not drawn as a direct prerequisite. A course recorded as a suppressed non-direct candidate cannot also appear as a direct option, and the direct prerequisite outcome is refused for such a candidate. Suppression evidence is retained with the result, so a broad foundation is reported rather than silently dropped.

## Proposals and publication

An accepted result becomes a proposal, composed from that one result. Composition applies the only deduction against official data: an inferred option that an official option already names in full is absorbed, an official option of the other category removes its members from the inferred option, and an equivalence group that repeats the target course plus one official single-course substitute is dropped. Every other option and group is kept with its own finding flags. The configuration selects the retained-recommendation and no-cutoff policies through `INFERENCE_RECOMMENDATION_POLICY` (`include`) and `INFERENCE_FINDING_FILTER_POLICY` (`none`), so no confidence threshold, drop, or demotion rule narrows the output. [Inference pipeline](/docs/backend/inference/inference-pipeline.md) states the exact rule.

Publication writes the accepted proposals into the inferred sets and the equivalence groups of the catalogue. An accepted result is written as the whole stored result of its target course, and each stored set and group is written in one step. Publication reads only the courses that an accepted result names. It reruns no selection, no rerank, and no model work.

[Inference coverage](/docs/reference/glossary.md#inference) reports the state of the inferred sets with the counts of eligible, processed, and accepted sources. A target course with no accepted result and no operator decision has no inferred set and is counted as uncovered, so it contributes no inferred prerequisite. An operator **done** decision completes a target course with no inferred output even when no result was ever accepted, so it is counted as complete coverage rather than uncovered, and publication removes its inference-produced inferred set and equivalence groups. A target course whose accepted result names no option has a complete inferred set with no option, and it contributes no inferred prerequisite either. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) shows how the graph draws official and inferred requirements, and [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md) states the two decisions and their outcomes.

## The local model and rerank runtimes

Inference is a remote stage, and both language models run on the worker. Each is a local model served over a loopback address.

Each artifact is pinned by a revision and a SHA-256 digest. `INFERENCE_RUNTIME_REVISION` in `config/inference.toml` pins the serving runtime, `INFERENCE_PRIMARY_MODEL_REVISION` and `INFERENCE_PRIMARY_ARTIFACT_REVISION` pin the source model and the quantized artifact, and `INFERENCE_PRIMARY_ARTIFACT_SHA256` pins the artifact bytes. The cross-encoder is pinned the same way through `INFERENCE_RERANK_MODEL_REVISION`, `INFERENCE_RERANK_ARTIFACT_REVISION`, and `INFERENCE_RERANK_ARTIFACT_SHA256`, and it shares the pinned runtime revision with the language model.

`INFERENCE_HOST` and `INFERENCE_RERANK_HOST` accept only a loopback address, so the worker serves the models to itself. `INFERENCE_LOCAL_VARIANTS` names two ordered keys for the language model, ordered by increasing context. A key that is loaded counts the tokens of a request, and the run loads the first key when no key is loaded. The example sets the two keys to 131072 and 163840 tokens.

A pinned revision or digest, the prompt, the result schema, and the recorded runtime values all take part in the execution identity, so work produced under different values has a distinct identity. The stored output records the identity that produced it.

The module layout, the identities, and the stored tables behind the behavior on this page are described in [Inference pipeline](/docs/backend/inference/inference-pipeline.md).
