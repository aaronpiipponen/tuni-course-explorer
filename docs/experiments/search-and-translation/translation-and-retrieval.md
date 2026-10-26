# Machine translation as retrieval-preserving transformation

The TranslateGemma 12B evaluation asked whether machine translations keep their official counterparts retrievable by embedding similarity.

**Evidence status:** Corrected. **Run date:** 13 September 2026.

This is a translation-utility experiment, not a translation-quality rating. It measures whether a translated [teaching text](/docs/reference/glossary.md#capture-and-data-preparation) field points at the official text in the other language strongly enough for an embedding to retrieve it. It does not measure fluency, adequacy, terminology or reader preference. The retrieval values come from a corrected scoring runtime, and they stand.

The [translation stage](/docs/backend/text-and-vectors/translation.md) fills a missing name, content or learning-outcomes field from the same field in the other language. The [embedding service](/docs/backend/text-and-vectors/embeddings.md) then embeds the [effective text](/docs/backend/text-and-vectors/teaching-text.md#official-text-translation-and-effective-text), which is the official text when it exists and a current translation otherwise. If a translation moves too far in embedding space, [semantic search](/docs/backend/search-and-discovery/search.md) can miss the course even when a reader would accept the translation.

## The question

The evaluation asks whether a generated translation is close enough to its official counterpart that the counterpart ranks first among the official texts of the same field and target language. The generated text is the query. The official text in the other language is the only correct answer. The other nine official texts in the cell are distractors.

That construction is a retrieval proxy. A retrieval proxy is a stand-in task that scores a translation by whether retrieval finds the right official text, rather than by human judgement. Here the proxy is within-cell retrieval: 10 official targets compete, and the paired target is the correct one.

An embedding is a vector of numbers that represents the meaning of a text. Cosine similarity measures the angle between two vectors and ranges from -1 to 1. BGE-M3 returns 1,024-component vectors, and the product's semantic search measures cosine similarity. Comparison and recommendations subtract the hub of the field, the outcomes hub for learning outcomes, while semantic search subtracts the embedding hub, a mean of catalogue unit vectors. The proxy uses raw cosine and subtracts neither hub.

The proxy cannot read the translation. A fluent translation can use different vocabulary and rank below a distractor. A poor translation can stay close to the official text and rank first. The result is evidence about retrieval utility only.

## The evaluation setup

The run took place on 13 September 2026. It used one translation model and one retrieval scorer, with no second translation candidate.

### The six cells

The evaluation crossed three fields with two target languages. A cell is one field and one target language. Each cell held 10 cases. For a Finnish target the source was English, and for an English target the source was Finnish. The source and target had to be official text in the same field of the same representative version.

| Field | Target language | Source language | Cases |
|---|---|---|---:|
| Name | Finnish | English | 10 |
| Name | English | Finnish | 10 |
| Content | Finnish | English | 10 |
| Content | English | Finnish | 10 |
| Learning outcomes | Finnish | English | 10 |
| Learning outcomes | English | Finnish | 10 |

### Cohort and selection

The catalogue snapshot held 11,086 courses and 58,962 teaching-text chunks. Of the courses, 4,543 were active. The cohort covered every canonical course, active and inactive, once through its [representative version](/docs/backend/catalogue/representative-versions.md). A case entered a cell only when the representative version held official text in the source language and official text in the target language for the same field. A field with official text in one language only could not supply a label and was not a case.

Within each cell, candidates were ordered by an evaluation ID. The ID is a one-way hash of the split seed, the course unit id, the field and the target language, so it is stable and carries no readable identity. The first candidate for a target text hash was kept, and further exact duplicates of the same target text were dropped, so no cell held the same official target twice. The first 10 remaining candidates became the cases. The split is deterministic, not a random sample.

The result was 60 cases, 10 per cell. At the run, the translation selection held 9,916 pending representative cells with a same-field source, covering 5,171,027 source characters. That is the full workload the duration projection scales to.

### Leakage isolation

Leakage isolation means keeping the official target text and every identity field out of the input the translation model sees. The generated text is the model's answer. The official target text is the label. The two were kept apart.

| Item | What it held |
|---|---|
| Translation input | Evaluation ID, field, source and target language, source text, source text hash |
| Translation output | Evaluation ID, source text hash, generated text, model identity, generation time, elapsed seconds |
| Scoring labels | Evaluation ID, course and group identity, activity flag, field, languages, source text hash, source character count, official target text, target text hash |

The translation input held no target text, target hash, course or group identity, activity flag or URL. The output held no target text or course identity. The labels stayed with the scoring process. The translation process had no database or embedding access during the evaluation. Scoring read the labels and used the one embedding provider.

Scoring validated the candidate model, the input hash, the label hash, the case order, the source hashes, the field and the target language before it made an embedding request. It also computed the output hash to bind the scored result. A mismatch stopped the run.

No evaluation artifact wrote a database row or overwrote official text. The generated text had to be non-blank and free of NUL. The run did not sanitize, normalize or repair it.

The first pass generated all 60 cases. The second pass, with the model runtime stopped, reused all 60. The output hashes were equal, so the second pass reproduced the first output byte for byte.

### Translation model and decoding

The model was TranslateGemma 12B instruction-tuned. The artifact used Q5_K_M, a 5-bit quantization. It ran on an AMD Radeon RX 9070 XT (16 GB model) through ROCm. VRAM is the GPU's own memory, and ROCm is its compute stack.

| Setting | Value |
|---|---|
| Model | google/translategemma-12b-it, instruction-tuned, Q5_K_M |
| Runtime | llama.cpp, with 49 of 49 layers offloaded to the GPU |
| Context | 16,384 tokens |
| Requests in flight | 1 |
| Temperature | 0 |
| Output cap | 8,192 tokens |
| Request timeout | 600 seconds |
| Attempts per request | 3, the first included |
| Retry delay | 1 second before the first retry, doubled for each further retry |
| Prompt | The model's official chat template with source and target language codes, no custom prompt |
| Top-p and top-k | Not set, so the runtime defaults applied |
| Streaming | Off |

The runtime was started and passed its health check before the first case. Each case was one request, and the cases ran one at a time in split order. Context is the token window of one request. Offloading means the layers ran on the GPU rather than the CPU. Each elapsed time covers the complete provider call, including any retry inside it, not the model load or the health check.

### Embedding and scoring

The scorer used BGE-M3 on the CPU. The scoring ran on a 4-core aarch64 server with 23.6 GB of RAM.

| Setting | Value |
|---|---|
| Model | BAAI/bge-m3, Q8_0 artifact |
| Vector dimension | 1,024 |
| Pooling | CLS |
| Normalization (`EMBEDDING_NORMALIZATION`) | 2 (unit length) |
| Threads | 2 |
| Context | 2,048 tokens |
| Logical batch | 2,048 |
| Physical batch | 2,048 |
| Parallel requests | 1 |
| Texts per request | 32 |
| Request timeout | 600 seconds |
| Attempts per request | 3, the first included |
| Retry delay | 0.5 seconds before the first retry, doubled for each further retry |
| Similarity | Raw cosine, no hub subtraction |
| Chunking | None, each generated text and each official target is one input |

Scoring embedded the 60 generated texts and the 60 official target texts in one list, through four requests of at most 32 texts. It then ranked each generated text against the 10 official targets of its own cell. CLS pooling uses the first token's vector as the text vector. The normalization setting scales each vector to unit length. The logical and physical batch values are the runtime's token capacities.

The configuration hash covers the model, the artifact checksum, the dimension, the pooling, the normalization and the runtime revision. It excludes the request timeout, the context and the batch size. A change to one of the covered values changes vector identity. A change to the excluded values changes how the work is sent.

The product's embedding stage makes 1,200-character chunks with a 120-character overlap, and semantic search subtracts the embedding hub before ranking them. A chunk is one piece of a field's text. The proxy does neither. It embeds each generated text and each official target as one input and compares raw cosine. Its values are not the product's hub-centred scores. Raw BGE-M3 vectors share a common direction, so raw cosines are high even for unrelated texts. The absolute values are not a quality scale.

### What was measured

| Measured | Not measured |
|---|---|
| Within-cell top-1 and mean reciprocal rank | Fluency, adequacy, terminology or reader preference |
| Mean paired cosine | Full-catalogue search |
| Per-case generation time | End-to-end wall clock |
| Embedding peak memory, idle CPU and warm latency | Translation runtime memory or VRAM use |

## Measured retrieval and throughput

### Retrieval

The cell results are in the table below. Top-1 rate is the share of cases whose paired official target had the highest cosine in its cell. A tie counts as top-1 because only a strictly higher cosine ranks above. Mean reciprocal rank is the mean of one divided by the rank of the paired target over the 10 cases. Mean paired cosine is the mean cosine between a generated text and its own official target.

| Field | Target | Source | Cases | Top-1 | Top-1 rate | Mean reciprocal rank | Mean paired cosine |
|---|---|---|---:|---:|---:|---:|---:|
| Name | Finnish | English | 10 | 9 | 0.900 | 0.925 | 0.6940 |
| Name | English | Finnish | 10 | 10 | 1.000 | 1.000 | 0.8627 |
| Content | Finnish | English | 10 | 10 | 1.000 | 1.000 | 0.8840 |
| Content | English | Finnish | 10 | 10 | 1.000 | 1.000 | 0.9114 |
| Learning outcomes | Finnish | English | 10 | 10 | 1.000 | 1.000 | 0.9154 |
| Learning outcomes | English | Finnish | 10 | 10 | 1.000 | 1.000 | 0.8971 |
| All cells | Finnish and English | Both | 60 | 59 | 0.9833 | 0.9875 | Not recorded |

Five cells returned top-1 on all 10 cases. The Finnish name cell returned nine of 10 and a mean reciprocal rank of 0.925. Nine first places and a fourth place produce that value, because the fourth place contributes 0.25 to the sum.

The overall result was 59 of 60 top-1, a rate of 0.9833, and an overall mean reciprocal rank of 0.9875.

The mean paired cosine was lowest in the Finnish name cell, 0.6940. The other five cells ranged from 0.8627 to 0.9154. Observed: the one miss and the lowest paired cosine fall in the same cell. The evaluation does not establish a cause.

The chart plots the top-1 rate and the mean reciprocal rank for the six cells.

![Top-1 rate and mean reciprocal rank for the six field and target-language cells, each with 10 cases. Five cells reach 1.0 on both measures, and the Finnish name cell is lower at 0.9 top-1 and 0.925 mean reciprocal rank.](/docs/charts/translation-retrieval-cells.svg)

The acceptance floors were an overall top-1 rate of at least 0.90, a top-1 rate of at least 0.80 in every cell, and a projected duration below 604,800 seconds. The result cleared all three. The lowest cell rate was 0.900, above the 0.800 floor. The verdict was accepted with no rejection reasons.

### Throughput and projection

Measured generation time was 156.008147444 seconds across the 60 cases, from 29,633 source characters. The time is the sum of the per-case provider call times. The second pass reported the same total because it summed the retained per-case times, so that total is one timing sample, not two.

At the run, 9,916 representative cells were pending, with 5,171,027 source characters.

| Quantity | Value |
|---|---:|
| Cases in the sample | 60 |
| Measured generation time | 156.008147444 seconds |
| Source characters in the sample | 29,633 |
| Pending cells in the full workload | 9,916 |
| Source characters in the full workload | 5,171,027 |
| Projection by item | 25,782.9465 seconds |
| Projection by character | 27,223.7824 seconds |
| Selected projection | 27,223.8 seconds |
| Acceptance ceiling | 604,800 seconds |

```text
projected_by_item = 156.008147444 s / 60 * 9,916 = 25,782.9465 s
projected_by_characters = 156.008147444 s / 29,633 * 5,171,027 = 27,223.7824 s
projected = max(25,782.9465 s, 27,223.7824 s) = 27,223.8 s
```

The projection rests on these assumptions.

- The measured time is the sum of per-case provider calls. It excludes model load, the health check, transfer, import, embedding and the surrounding controller work.
- The sample's per-case retry incidence holds for the full run.
- One request ran at a time, so the projection scales linearly.
- The sample's per-item and per-character rates hold for the full pending set.
- The full pending set has the same mix of fields and source lengths as the sample.
- The larger of the item and character projections is used, so the estimate is conservative on those two axes.

The projection selected the character-based value because it was larger. The ceiling was 604,800 seconds, or seven days. The projection is 27,223.8 seconds, below the ceiling.

Interpretation: the projection says the full pending workload fits the ceiling if the sample rate holds. It is not a measured full-run duration. The record of the later full pass gives no duration, so the projection was not checked against a measured full run.

## The embedding runtime correction

The retrieval values in this report come from the corrected embedding runtime. The correction changed the launch capacity and the request timeout, not the scoring rule.

An earlier feasibility measurement of the service recorded 1,117.51 MB peak resident memory, 0.0167% idle CPU and 0.0535 seconds warm p95. The corrected scoring runtime recorded 2,044.0 MB peak resident memory, 0.017% idle CPU and 0.074 seconds warm p95. A 120-text probe took 89.4 seconds. The corrected figures are the accepted run's runtime evidence. The earlier figures are the feasibility baseline.

| Measure | Earlier feasibility | Corrected scoring runtime |
|---|---:|---:|
| Peak resident memory | 1,117.51 MB | 2,044.0 MB |
| Idle CPU | 0.0167% | 0.017% |
| Warm query p95 | 0.0535 seconds | 0.074 seconds |
| 120-text probe | Not recorded | 89.4 seconds |
| Frozen service budget | Within budget | Within budget |

Peak resident memory is the highest resident memory of the embedding process. Idle CPU is the CPU use while the service was idle. Warm p95 is the 95th percentile of request latency after warmup.

A launch that left the batch sizes unset could not embed a text longer than 512 tokens whole. The corrected launch passed the configured 2,048-token value to the context and both batch sizes, and it embedded the complete generated and official texts.

Scoring observed contention on the embedding service. The request timeout is a validated finite value in the range greater than 0 and at most 600 seconds. The accepted run used 600 seconds. The timeout, context and batch size are outside the configuration hash that identifies vector semantics, so the correction did not change that hash.

The earlier feasibility measurement and the corrected runtime measurement are separate measurements. The corrected measurement used the configured 2,048-token batch capacity and a 120-text probe. The earlier feasibility measurement is not a like-for-like control for the corrected run. The difference is not evidence that the model became slower or used more memory for the same work.

Unsuccessful setup: the uncorrected launch did not pass the configured 2,048-token value to the batch sizes, so it is not the source of any value in this report. The accepted retrieval values and the corrected runtime figures come from the corrected launch.

Result that stands: 59 of 60 top-1, a mean reciprocal rank of 0.9875, and an accepted verdict. The earlier feasibility figures do not replace the corrected runtime figures.

## What the result supports

Interpretation: TranslateGemma 12B preserved retrieval on this cohort. The result supports its use for the translation stage, within the limits below. It does not show that the translations are good by human standards, and it does not show that 12B is the best available model.

The Finnish name cell is the weak point in this cohort. With 10 cases, one case moves the cell rate by 0.10. The cell is above the 0.80 floor. The result does not show why the miss happened.

The proxy is easier than the product's full search. It chooses among 10 official targets, not among 11,086 courses or 58,962 chunks. It uses raw cosine and whole fields, not the product's hub-centred chunk search. A translation that passes here can rank poorly in the full search. The [exact and approximate semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md) report covers the product's search read path, and the [lexical matching equivalence and collation](/docs/experiments/search-and-translation/lexical-matching-and-collation.md) report covers the lexical side.

The absolute cosine values are not a quality scale. The paired values are high because the vectors share a common direction. The ranking, not the absolute value, is the result.

## Why 27B and fine-tuning were not pursued

The candidate ladder held TranslateGemma 12B at Q5_K_M first and TranslateGemma 27B at Q4_K_M, a 4-bit quantization, only if 12B was rejected. Conditional fine-tuning was reserved for the case where both candidates failed. Fine-tuning means further training of the model on translation data. The 12B run cleared the overall floor, every cell floor and the duration ceiling. The verdict was accepted with no rejection reasons. The 27B artifact was not acquired or run, and no fine-tuning was started.

Consequence: this report has no 27B measurement and no fine-tuned measurement. It cannot say whether 27B would have scored higher, whether it would have fixed the Finnish name cell, or whether fine-tuning would have changed the result. Those questions are untested.

## Outcome and later use

The accepted model was used for the full translation pass over every missing representative field. That pass filled every translatable gap. The remaining per-language absence is source absence, not a failed translation. After the import, all 58,962 chunks across 11,086 representative versions were embedded, and an unchanged rerun generated nothing. No vectors were produced or transferred from the translation run. The record gives no end-to-end duration, so the 27,223.8-second projection remains a projection.

Within the evaluation, no database row was written and no official text was overwritten. The 60-case evaluation output was not imported into the dataset.

## Limitations

- The proxy is not human judgement. It measures retrieval, not fluency, adequacy, terminology or reader preference.
- One model was measured. The 27B candidate and a fine-tune were not run, so the result is not a model comparison.
- Each cell holds 10 cases. One case moves a cell rate by 0.10, and the cell values are coarse.
- The candidate set is 10 official targets from one field and language. The product's full search spans 11,086 courses and 58,962 chunks.
- The proxy embeds whole fields and uses raw cosine. The product's full search ranks 1,200-character chunks and subtracts the embedding hub.
- The scorer used the generated text exactly as returned. It did not strip alternatives, notes or trailing whitespace.
- The translation runtime's memory and VRAM use were not measured. The run recorded full layer offload, not memory.
- The full-run duration was not recorded, so the projection was not checked against a measured full run.
- The earlier feasibility measurement and the corrected runtime measurement are separate measurements, with a corrected launch and a different probe size.
- The split is deterministic and balanced by cell. It is not a random sample of the catalogue's field and length mix.

## Untested questions

- Whether TranslateGemma 27B at Q4_K_M raises the Finnish name cell or the overall mean reciprocal rank above the 12B result.
- Whether these translations preserve retrieval in the product's chunked, hub-centred semantic search over the full catalogue.
- Whether a human rating of fluency, terminology and adequacy agrees with the retrieval proxy.
