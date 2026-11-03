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

![Effective text feeds a candidate pool, a rerank, and a packet. A local language model generates a result, validation accepts it, a proposal deduplicates it against the official prerequisites, and publication writes the inferred sets and equivalence groups. The accent outline marks the label-safe model inputs, which exclude official prerequisite structure from candidate selection and every model input.](/docs/diagrams/inference-pipeline.svg)

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

[Candidate retrieval, multiview fusion and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md#which-selection-the-product-uses) gives the measurements that set the pool depth and the text bounds, and [Candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) gives the comparison that selected the cross-encoder-only packet at a fixed size of 50.

## Generation and validation

Each generation attempt asks the local language model for one complete result for its target course. The result states a required option set, a recommended option set, equivalence groups, and target-level routing metadata. Each option names its member course codes, its evidence, its confidence, and zero or more finding flags, and the configured finding policy retains every flag. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md#failures-retries-and-isolation) describes retries after a failed attempt.

Model output is untrusted input. A result is accepted only when it parses as strict JSON and validates against the result contract, schema `v2`. The contract refuses a contradictory answer, an option or group repeated in a logically identical form, a course that is both required and recommended, a suppressed candidate that is also a direct option, and the target course as its own direct or suppressed source. It also refuses a code that names no curriculum course and a code that names two canonical courses, and a confidence outside 0 to 1. An equivalence group may contain the target course.

An accepted result states one complete answer for its target course, so a partial or contradictory answer is refused rather than repaired. [Inference pipeline](/docs/backend/inference/inference-pipeline.md) lists the exact contract rules, the finding-flag vocabulary, and the emitted schema.

The finding-flag experiments are in [Prompt and flag schema tuning](/docs/experiments/inference/prompt-and-flag-schema-tuning.md), and the prompt selection measurements are in [Prompt sweeps and the v9 selection](/docs/experiments/inference/prompt-sweeps-and-v9-selection.md).

### Direct prerequisites and suppression

The model classifies each candidate and records every non-direct candidate with its raw outcome. A candidate whose outcome is `too_basic_transitive` is a broad or transitive foundation below the target's entry level, and it is not drawn as a direct prerequisite. A course recorded as a suppressed non-direct candidate cannot also appear as a direct option, and the direct prerequisite outcome is refused for such a candidate. Suppression evidence is retained with the result, so a broad foundation is reported rather than silently dropped.

## Proposals and publication

An accepted result becomes a proposal, composed from that one result. Composition applies the only deduction against official data: an inferred option that an official option already names in full is absorbed, an official option of the other category removes its members from the inferred option, and an equivalence group that repeats the target course plus one official single-course substitute is dropped. Every other option and group is kept with its own finding flags. The configuration selects the retained-recommendation and no-cutoff policies through `INFERENCE_RECOMMENDATION_POLICY` (`include`) and `INFERENCE_FINDING_FILTER_POLICY` (`none`), so no confidence threshold, drop, or demotion rule narrows the output. [Inference pipeline](/docs/backend/inference/inference-pipeline.md) states the exact rule.

[Confidence and flag calibration](/docs/experiments/inference/confidence-and-flag-calibration.md) records the confidence bins, the target-level routing check and the filter's fit and validation. [Reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) states the corrected-reference method.

Publication writes the accepted proposals into the inferred sets and the equivalence groups of the catalogue. An accepted result is written as the whole stored result of its target course, and each stored set and group is written in one step. Publication reads only the courses that an accepted result names. It reruns no selection, no rerank, and no model work.

[Inference coverage](/docs/reference/glossary.md#inference) reports the state of the inferred sets with the counts of eligible, processed, and accepted sources. A target course with no accepted result and no operator decision has no inferred set and is counted as uncovered, so it contributes no inferred prerequisite. An operator **done** decision completes a target course with no inferred output even when no result was ever accepted, so it is counted as complete coverage rather than uncovered, and publication removes its inference-produced inferred set and equivalence groups. A target course whose accepted result names no option has a complete inferred set with no option, and it contributes no inferred prerequisite either. [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) shows how the graph draws official and inferred requirements, and [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md) states the two decisions and their outcomes.

## The local model and rerank runtimes

Inference is a remote stage, and both language models run on the worker. Each is a local model served over a loopback address.

Each artifact is pinned by a revision and a SHA-256 digest. `INFERENCE_RUNTIME_REVISION` in `config/inference.toml` pins the serving runtime, `INFERENCE_PRIMARY_MODEL_REVISION` and `INFERENCE_PRIMARY_ARTIFACT_REVISION` pin the source model and the quantized artifact, and `INFERENCE_PRIMARY_ARTIFACT_SHA256` pins the artifact bytes. The cross-encoder is pinned the same way through `INFERENCE_RERANK_MODEL_REVISION`, `INFERENCE_RERANK_ARTIFACT_REVISION`, and `INFERENCE_RERANK_ARTIFACT_SHA256`, and it shares the pinned runtime revision with the language model.

`INFERENCE_HOST` and `INFERENCE_RERANK_HOST` accept only a loopback address, so the worker serves the models to itself. `INFERENCE_LOCAL_VARIANTS` names two ordered keys for the language model, ordered by increasing context. A key that is loaded counts the tokens of a request, and the run loads the first key when no key is loaded. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md#the-fit-rule) lists the two keys and their configured context sizes. The measured fit and throughput of those keys are in [Local model hardware and throughput](/docs/experiments/inference/local-model-hardware-and-throughput.md).

The execution identity is built from the pinned model and runtime identities, the prompt version, the result schema version, the pipeline version and the route. Each target adds its canonical identity, its activity context and the digest of its rendered input, so work produced under different values has a distinct identity. The stored output records the identity that produced it.

### The generation artifact and runtime keys

The language model is served from one quantized artifact, and every key in this table is required in `config/inference.toml`. The source model and the artifact carry their own repository and revision, and the artifact's digest is checked against the downloaded bytes.

| Key | Meaning | Example |
|---|---|---|
| `INFERENCE_PRIMARY_MODEL_REPOSITORY` | The source model's repository in `owner/repository` form | `Qwen/Qwen3.8-27B-FP8` |
| `INFERENCE_PRIMARY_MODEL_REVISION` | The source model's pinned commit | a 40-character commit |
| `INFERENCE_PRIMARY_ARTIFACT_REPOSITORY` | The repository that holds the quantized artifact, in `owner/repository` form | `vmarcelo/Qwen3.8-27B-MIX_GGUF` |
| `INFERENCE_PRIMARY_ARTIFACT_REVISION` | The artifact's pinned commit | a 40-character commit |
| `INFERENCE_PRIMARY_ARTIFACT_FILE` | The artifact's GGUF file name, with no directory | `Qwen3.8-27B-IQ3-MIX.gguf` |
| `INFERENCE_PRIMARY_ARTIFACT_PATH` | The repository-relative path of the artifact, whose basename must equal the file name | `models/qwen3.8-27b-iq3-mix-f922f9d9/Qwen3.8-27B-IQ3-MIX.gguf` |
| `INFERENCE_PRIMARY_ARTIFACT_QUANT` | The artifact's quantization, one literal | `IQ3_MIX` |
| `INFERENCE_PRIMARY_ARTIFACT_SHA256` | The SHA-256 digest the downloaded bytes must match | a 64-character digest |
| `INFERENCE_PARALLEL` | The parallel sequence slots the runtime serves, as a positive integer | 1 |
| `INFERENCE_GPU_LAYERS` | The model layers offloaded to the GPU, either `all` or a nonnegative integer | `all` |
| `INFERENCE_FLASH_ATTENTION` | The flash-attention mode, whose only valid value is `on` | `on` |
| `INFERENCE_REQUEST_TIMEOUT_SECONDS` | The bound of one generation request in seconds, above zero and at most 600 | 600 |
| `INFERENCE_TEMPERATURE` | The temperature of the first attempt of one calculation, whose only valid value is zero | 0.0 |
| `INFERENCE_RETRY_TEMPERATURE` | The temperature of every attempt after the first, above zero and at most 2 | 0.3 |
| `INFERENCE_SEED` | The base seed, a nonnegative integer advanced by the durable lifetime attempt ordinal | 0 |
| `INFERENCE_CHAT_TEMPLATE_KWARGS` | The chat-template flags, required to be exactly `{ enable_thinking = false }` | `{ enable_thinking = false }` |
| `INFERENCE_PROMPT_VERSION` | The prompt version, which pairs with schema version `v2` | `v9` |
| `INFERENCE_SCHEMA_VERSION` | The result schema version, one literal | `v2` |
| `INFERENCE_PIPELINE_VERSION` | The pipeline version, one literal | `v1` |
| `INFERENCE_PROPOSAL_VERSION` | The proposal composition version, one literal | `v1` |
| `INFERENCE_ROUTING_POLICY` | The routing policy, one literal | `solo_fit_only` |
| `INFERENCE_RECOMMENDATION_POLICY` | The retained-recommendation policy, one literal | `include` |
| `INFERENCE_FINDING_FILTER_POLICY` | The finding filter policy, one literal | `none` |
| `INFERENCE_CONTROLLER_HEALTH_ATTEMPTS` | The runtime health reads one start makes, one configured interval apart, from 1 to 600 | 120 |

Each entry of `INFERENCE_LOCAL_VARIANTS` states its own alias, port, context size, KV cache type, batch and micro-batch sizes, speculation type, MTP draft count and achieved maximum context. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md#the-fit-rule) states the fit rule with its output cap `INFERENCE_MAX_TOKENS` and fit margin `INFERENCE_FIT_HEADROOM_TOKENS`, and [Failures, retries, and isolation](/docs/backend/inference/inference-scheduling.md#failures-retries-and-isolation) states the preparation attempt bound `INFERENCE_MAX_ATTEMPTS` and the retry waits `INFERENCE_RETRY_BACKOFF_SECONDS`, `INFERENCE_RETRY_MAX_BACKOFF_SECONDS` and `INFERENCE_RETRY_POLL_SECONDS`.

### The rerank artifact and serving keys

The cross-encoder is a separate pinned artifact served by the same runtime revision at its own loopback address and port.

| Key | Meaning | Example |
|---|---|---|
| `INFERENCE_RERANK_PORT` | The loopback port the cross-encoder serves | 18083 |
| `INFERENCE_RERANK_MODEL_ALIAS` | The short ASCII alias a rerank request names | `bge-reranker-v2-m3-q8` |
| `INFERENCE_RERANK_MODEL_REPOSITORY` | The cross-encoder's source repository in `owner/repository` form | `BAAI/bge-reranker-v2-m3` |
| `INFERENCE_RERANK_MODEL_REVISION` | The source model's pinned commit | a 40-character commit |
| `INFERENCE_RERANK_ARTIFACT_REPOSITORY` | The repository that holds the quantized cross-encoder | `gpustack/bge-reranker-v2-m3-GGUF` |
| `INFERENCE_RERANK_ARTIFACT_REVISION` | The artifact's pinned commit | a 40-character commit |
| `INFERENCE_RERANK_ARTIFACT_FILE` | The artifact's GGUF file name, with no directory | `bge-reranker-v2-m3-Q8_0.gguf` |
| `INFERENCE_RERANK_ARTIFACT_PATH` | The repository-relative path of the artifact, whose basename must equal the file name | `models/bge-reranker-v2-m3-3093af03/bge-reranker-v2-m3-Q8_0.gguf` |
| `INFERENCE_RERANK_ARTIFACT_QUANT` | The artifact's quantization, one literal | `Q8_0` |
| `INFERENCE_RERANK_ARTIFACT_SHA256` | The SHA-256 digest the downloaded bytes must match | a 64-character digest |
| `INFERENCE_RERANK_CONTEXT_SIZE` | The serving context in tokens, from 1 to 8192 | 8192 |
| `INFERENCE_RERANK_BATCH_SIZE` | The physical batch and micro-batch, from 1 to 8192 and no greater than the context | 2048 |
| `INFERENCE_RERANK_REQUEST_TIMEOUT_SECONDS` | The bound of one cross-encoder request in seconds, above zero and at most 60 | 60 |
| `INFERENCE_RERANK_TEXT_LAYOUT` | The order of the teaching-text fields in one pair, one literal | `content-first` |

`INFERENCE_RERANK_REQUEST_TIMEOUT_SECONDS` belongs to the rerank runtime identity, so a changed value selects a different rerank input identity.

The module layout, the identities, and the stored tables behind the behavior on this page are described in [Inference pipeline](/docs/backend/inference/inference-pipeline.md).
