# Local model hardware and throughput

This report records which local language models fitted the inference GPU, how much context each held, and how fast each ran.

**Evidence status:** Corrected.

The [Experiments overview](/docs/experiments/README.md) states the catalogue, the evidence labels and the hardware. This report covers one line of that work: the hardware and throughput measurements that decided which model, quantization and context the inference stage could use. The measured fit ceilings and the later demand estimate changed the sizing assumptions.

## The question

The [inference stage](/docs/backend/inference/inference.md) sends one complete target call per course. The call carries the target course, 50 candidate courses, a versioned system prompt and nine curated examples, and it must return one strict JSON result. On one AMD Radeon RX 9070 XT (16 GB model), the question was whether a 27B-class model, its KV cache for a long packet and the runtime could fit together, which quantization and KV cache type fitted, and how many seconds one complete target took.

The scale made the answer consequential. The catalogue holds 4,543 active target courses, and the run had to finish inside a month from its start. A rate that looked acceptable on a short prompt could still miss that ceiling once every packet carried tens of thousands of prompt tokens. The measurements therefore covered both fixed prompt lengths and the held-out packets.

A later question asked whether the same hardware could hold the catalogue's largest estimated prompt. That work produced an arithmetic estimate, not a measured prompt or a fit result. It is reported below beside the measured ceilings it exceeded.

## Setup

### Hardware and runtime

The runs used an AMD Radeon RX 9070 XT (16 GB model) on ROCm 7.2.1, in a machine with 33.4 GB of usable RAM. The 16 GB in that designation is the card's specification label, not a decimal measured value. It describes a binary capacity of 16 × 1,073,741,824 bytes, which is 17.2 GB in powers of ten. Every measured memory figure in this report uses decimal units.

The device target was `gfx1201`. The displays were moved to the integrated GPU, so the discrete card carried no desktop composition during a run. The environment of the measured runs had a 4.295 GB memory limit and 8.590 GB of swap, set with `memory=4GB` and `swap=8GB`.

The limit matters because the driver pages a near-full-VRAM model into system memory when it is idle, and the page cache plus those pages can exhaust system memory. A bounded rehearsal on a full copy of the catalogue measured the environment's preparation processes, not model runtime. It peaked at 2,597 MB of the 4,104 MB the environment reported, with no out-of-memory stop, and the GPU was never reached. The measured fit runs and the bounded rehearsal ran under this cap. No memory-cap record covers the full run.

Other GPU consumers had to be closed. One check found 6.3 GB of idle dedicated use, 4.1 GB of it from a running game. Before the measured load the aggregate dedicated total was 927 MB and no game ran. The fit measurements therefore used the aggregate GPU process commitment and free system RAM, not the runtime's free-VRAM report.

The runtime was llama.cpp at revision `4ff829ec2e2f526aa6afba529eebbfb3ef1f95ec`, served by `llama-server` on loopback. Every launch used full GPU offload, flash attention, `--jinja`, `--offline`, `--no-webui`, `--cache-ram 0`, `--ctx-checkpoints 0`, `--parallel 1`, 8 threads and 16 batch threads. The early fixed-prompt measurements sent one `/completion` request per measurement with `cache_prompt=false` and temperature 0.

The later packet runs used temperature 0, seed 0, a cap of 8,192 output tokens, thinking off and an active prefix cache. The shared system and examples prefix was about 13,000 tokens, and after the first request it was reused at about 800 to 880 prefill tokens per second.

### Models and artifacts

| Model | Artifact size | Keys, KV cache and context |
|---|---:|---|
| Qwen3.6-35B-A3B UD-IQ3_S | 13.7 GB | one key, `q4_0` KV, 212,992 tokens, n-gram speculation |
| Qwen3.8-27B IQ3-MIX | 12.6 GB | 131,072-token MTP key with `q4_0` KV, and 163,840-token no-MTP key with `q4_0` KV |
| Qwen3.8-27B IQ3_S ByteShape, 3.23 bits per weight | 11.0 GB | 118,784-token MTP key with `q8_0` KV, and 147,456-token no-MTP key with `q8_0` KV |
| gpt-oss-20b MXFP4 | 12.1 GB | 131,072-token native key with `q8_0` KV, and an early 196,608-token key with linear RoPE scaling |
| Nemotron-3-Nano-30B-A3B IQ4_XS | 18.1 GB of weights | 393,216 tokens with 16 expert layers on the CPU, `q8_0` KV |

The ByteShape artifact is a hybrid with full attention every fourth layer and a state-space component, 64 layers and an embedded MTP head. Its vision projector is a separate 931 MB file and was not loaded, so no VRAM went to it. The 11.0 GB artifact is smaller than the other 27B-class file, but its `q8_0` KV cache is larger per token.

The sizes are decimal GB. The Qwen3.6 file is 13,676,723,168 bytes, the MIX file 12,586,448,320 bytes, the ByteShape file 11,035,354,496 bytes and the gpt-oss file 12,109,566,624 bytes.

### Packet cohort

The held-out comparison used 200 packets built from the fixed curriculum snapshot. Each packet held the target course, 50 candidate descriptors and the shared prompt material. The candidate count was the configured final candidate count of 50 (`INFERENCE_SELECTION_FINAL_K`), drawn from a pool of 1,000 (`INFERENCE_SELECTION_POOL_K`). The retrieval and ranking stages that build the pool and the packet are described in [candidate retrieval and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md) and [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md). Official prerequisite labels were absent from every packet.

The 200 packets were split before any output. The 50 tuning packets were not part of the held-out comparison. The 150 complement was the held-out cohort. Within the 150, a deterministic size-quantile subset of 50 served as the shared comparison cohort and the distinct-target validation set, and the other 100 were the fit set. The split used the rendered user-prompt character length and the target identity, so the smallest and largest packets were included. The same fixed 50 went to each comparison model.

The measured prompt-token envelope of the 200 packets was 25,982 minimum, 45,323 median, 57,405 at the 90th percentile and 169,654 maximum. Those counts came from the DeepSeek tokenizer. The ByteShape tokenizer measured the smallest, median and largest probes at 26,834, 43,340 and 160,087 tokens. The largest complement packet was 92,815 ByteShape tokens, so all 150 fitted the 118,784-token ByteShape key. Only the tuning 50 held the one packet above 147,456 tokens.

The full run applied the same packet rule to every active target course. It is the only full-catalogue fit sample in this line.

### Metrics

Prefill is the prompt-processing rate, in tokens per second. Decode is the generation rate, in tokens per second. A complete validated target is one packet whose response passed the strict result schema. Its wall clock covers prefill and decode for that target, with no model load and no reboot pause. Mean and median are over the valid targets in the stated cohort.

Memory is reported with three aggregate GPU counters. Aggregate dedicated memory sums the adapter dedicated usage counter over every graphics adapter, and aggregate shared memory sums the adapter shared usage counter over the same adapters. Aggregate GPU process commitment sums the process total committed counter over every GPU process. A per-adapter split was not recorded, so the counters do not establish the discrete card's own allocation. Aggregate process commitment includes allocations backed by system memory. A model-sized rise in shared memory is a spill and fails the fit claim even when the runtime reports full offload.

The policy carried a 40 tokens per second floor for the synthetic runtime qualification, not for each measured target. The complete-target runs were judged on wall clock and ETA.

## The fit envelope

The card, not the model weights alone, was the binding constraint. An 11.0 to 13.7 GB artifact left a few GB for the KV cache and the compute buffers, and the KV cache grows with every token of context.

| Key | Context | KV cache | Batch and ubatch | Speculation | Placement | First failure |
|---|---:|---|---:|---|---|---:|
| Qwen3.6-35B-A3B | 212,992 | `q4_0` | 2048 / 2048 | n-gram | full GPU | 229,376 out of memory at inference |
| MIX, MTP | 131,072 | `q4_0` | 256 / 256 | MTP, 2 draft tokens | full GPU | 147,456 |
| MIX, no MTP | 163,840 | `q4_0` | 1024 / 1024 | none | full GPU | 180,224 |
| ByteShape, MTP | 118,784 | `q8_0` | 320 / 320 | MTP, 3 draft tokens | full GPU | 122,880 |
| ByteShape, no MTP | 147,456 | `q8_0` | 256 / 256 | none | full GPU | 152,576 at inference |
| gpt-oss-20b, native | 131,072 | `q8_0` | 4096 / 4096 | n-gram | full GPU | a request at 196,608 capped the slot |
| Nemotron-3-Nano-30B-A3B | 393,216 | `q8_0` | 2048 / 1024 | n-gram | 16 expert layers on the CPU | 458,752 |

The Qwen3.6 key at 196,608 tokens with `q8_0` KV was the earlier 192k configuration. Its KV cache alone was 2,139 MB, and about 763 MB of dedicated headroom remained. That key passed the prompt-readiness calls but did not become the applied key. The same artifact at `q4_0` KV reached 212,992 tokens, and 229,376 tokens ran out of memory at inference.

The MIX artifact used `q4_0` KV for both applied keys because the keys did not fit at `q8_0`. The MTP key stopped at 131,072 tokens and 147,456 failed. The no-MTP key stopped at 163,840 tokens and 180,224 failed. The quantization was a fit decision, not a marginal context gain.

The ByteShape `q8_0` KV cache cost about 35 MB per 1,000 tokens. Its full-GPU envelope was 118,784 tokens with MTP and 147,456 tokens without. A 160,000-token or 192,000-token context was impossible at `q8_0`. MTP made the ceiling tighter. At 160,000 tokens the MTP draft cache was 671 MB in f16, and `--spec-draft-type-k/-v q4_0` reduced it to 189 MB, but the target-side speculative buffers still overflowed. Lowering the ubatch to 64, 128 or 256 did not free enough. A ubatch below 256 also collapsed prefill to about 600 tokens per second, so the batch could not be reduced to buy context.

MTP cost context headroom and bought decode. At a 100,000-token prompt the ByteShape MTP key decoded at 26.2 tokens per second. At a 120,000-token prompt the no-MTP key decoded at 16.1 tokens per second. The prefill cost was small, 751 against 703 tokens per second.

The gpt-oss artifact has a native context of 131,072 tokens. An early key configured 196,608 tokens through linear RoPE scaling at scale 1.5, and 212,992 tokens returned HTTP 500. A later request at 196,608 reported `n_ctx_seq (196608) > n_ctx_train (131072)` and the runtime capped the slot to 131,072. The effective context of the key was therefore the native 131,072, not 196,608. The early 10,000-token and 120,000-token throughput rows still stand because both prompts fit 131,072.

The Nemotron artifact holds 18.1 GB of weights, which does not fit the card. It ran only with expert layers on the CPU. The lowest usable count was 13 CPU layers at 131,072 tokens, 14 at 163,840 and 16 at 196,608. Prefill ranged from 321 to 561 tokens per second and decode from 9.7 to 57.5. It was dropped before the held-out run.

## VRAM accounting

The memory measurement compared an idle baseline with ByteShape generating. The GPU counters are aggregate sums, as defined above, and the table gives each recorded value in decimal MB and GB.

| State | Aggregate dedicated | Aggregate shared | Aggregate GPU process commitment | Free system RAM |
|---|---:|---:|---:|---:|
| Idle before load | 927 MB | 353 MB | 1,501 MB | 24.3 GB |
| ByteShape loaded and generating | 16,922 to 16,926 MB | 338 to 387 MB | 18,299 to 18,349 MB | 20.7 GB |

The baseline check found no game running. ByteShape then took the aggregate dedicated total to 16,922 to 16,926 MB, about 98.5 percent of the card's capacity, whose 16 GB specification label denotes 17.2 GB in powers of ten. Because the sum covers every adapter, that percentage is an upper bound on the discrete card's share. Aggregate shared memory stayed at 338 to 387 MB, so the weights did not spill into system memory. The commitment total covers every GPU process, so it is not a per-model figure.

The card sat at its fit ceiling. One context-creation failure occurred, and the watchdog recovered it without a lost target. Clearing other VRAM would not have helped materially, because no game ran and the baseline aggregate was 927 MB. A planning estimate for ByteShape was 16,534 MB, and a free-memory reading at one point was 208 MB. The planning estimate is a separate arithmetic figure, not a measured counter.

The other two full-GPU models loaded with more headroom. Qwen3.6 loaded with about 15,737 MB and MIX with about 15,179 MB. MIX, the model selected for the run, loaded with the most headroom of the three.

Two measurement traps shaped the accounting. The runtime's free-VRAM report does not reflect the allocations in this environment, so it is not a fit signal. The driver also pages an idle model out of dedicated memory into system memory, so a passive shared figure can be high while nothing is generating. The fit check therefore read the aggregate GPU process commitment, free system RAM and an active generation.

## Throughput at fixed prompt lengths

The first throughput table measured prefill and decode on a single request at about 10,000 and 120,000 prompt tokens. Each row is one served configuration at its own context.

| Key | Context | Prefill at 10k | Decode at 10k | Prefill at 120k | Decode at 120k |
|---|---:|---:|---:|---:|---:|
| Qwen3.6-35B-A3B | 131,072 | 3666 | 66.7 | 2320 | 23.6 |
| Qwen3.6-35B-A3B | 163,840 | 3415 | 61.6 | 2260 | 23.8 |
| Qwen3.6-35B-A3B | 196,608 | 3650 | 68.0 | 2313 | 23.7 |
| MIX, MTP | 131,072 | 990 | 48.4 | 649 | 36.7 |
| MIX, no MTP | 163,840 | 1095 | 24.2 | 779 | 9.5 |
| ByteShape, MTP | 118,784 | 1006 | 40.5 | 751 at 100k | 26.2 at 100k |
| ByteShape, no MTP | 147,456 | 1083 | 26.6 | 703 | 16.1 |
| gpt-oss-20b | 131,072 | 5491 | 112.1 | 2173 | 59.4 |
| gpt-oss-20b, RoPE 1.25 | 163,840 | 5138 | 136.5 | 2117 | 162.9 |
| gpt-oss-20b, RoPE 1.5 | 196,608 | 5824 | 138.4 | 2223 | 216.0 |
| Nemotron, 16 CPU layers | 131,072 | 378 | 53.5 | 439 | 19.8 |
| Nemotron, 13 CPU layers | 131,072 | 524 | 57.5 | 561 | 19.1 |
| Nemotron, 14 CPU layers | 163,840 | 399 | 37.9 | 466 | 14.8 |
| Nemotron, 16 CPU layers | 196,608 | 321 | 29.7 | 404 | 9.7 |

The table's rates are tokens per second. The ByteShape MTP row is a 100,000-token prompt because a 120,000-token prompt does not fit its 118,784-token context.

gpt-oss-20b had the highest decode rate at both prompt lengths and the highest prefill on the short prompt. At its native key it prefilled at 5,491 and decoded at 112.1 tokens per second on the short prompt, and at 2,173 and 59.4 on the 120,000-token prompt. Qwen3.6 prefilled faster at 120,000 tokens, 2,260 to 2,320 against 2,117 to 2,223. The two RoPE rows configured 163,840 and 196,608 tokens, beyond the native 131,072, and the request correction above covers the 196,608-token key.

Qwen3.6 had the strongest prefill of the Qwen models, 3,415 to 3,666 tokens per second on the short prompt and 2,260 to 2,320 on the long prompt. Its decode fell from 61.6 to 68.0 at 10,000 tokens to 23.6 to 23.8 at 120,000. A larger configured context did not lower those rates in a consistent direction, and the 196,608-token key held the highest short-prompt decode of the three at 68.0.

The MIX MTP key decoded at 48.4 tokens per second on the short prompt and 36.7 on the long one. Its no-MTP key decoded at 24.2 and 9.5. MTP cost prefill, 990 against 1,095 on the short prompt and 649 against 779 on the long one, and bought decode at both lengths.

The ByteShape MTP key decoded at 40.5 on the short prompt and 26.2 at 100,000 tokens. The no-MTP key decoded at 26.6 and 16.1. Its prefill was lower than the Qwen models, 1,006 to 1,083 on the short prompt.

Nemotron had the lowest prefill of the set at every context and needed the CPU for part of the model. The lowest CPU-offload count of 12 layers was not measured in the 10k and 120k table. It appears in the middle-context table below.

The chart plots the decode values from the table for the 131,072-token Qwen3.6 key, both MIX keys, the no-MTP ByteShape key, the native gpt-oss key and the 16-layer Nemotron key. Every plotted key loses decode speed at the longer prompt, and gpt-oss-20b remains the fastest at both lengths.

![Six local model keys decode at about 10,000 and 120,000 prompt tokens. gpt-oss-20b decodes fastest at both lengths, and every key decodes more slowly at the longer prompt.](/docs/charts/inference-local-decode-throughput.svg)

### The middle context

A smaller set was measured at a 98,304-token context with a prompt of about 80,000 tokens.

| Key | Prefill | Decode |
|---|---:|---:|
| gpt-oss-20b | 2658 | 71.5 |
| Nemotron, 12 CPU layers | 518 | 44.1 |
| Qwen3.6-35B-A3B | 2501 | 30.5 |
| MIX, MTP | 696 | 43.3 |
| ByteShape, MTP | 797 | 30.2 |

The non-MTP configurations were not measured at this context. Decode is bound by context length, so their 120,000-token rows already carry the cost. The Nemotron row is the 12-layer setting, not the 16-layer setting used at the largest context.

## Throughput on the held-out packets

The fixed-prompt table excludes prompt reuse and carries one request per measurement. The held-out run measured complete targets on the held-out packets, with the prefix cache active.

| Model | Targets | Mean seconds | Median seconds | Range | Prefill tokens/s, median | Decode tokens/s, median | Valid |
|---|---:|---:|---:|---|---:|---:|---:|
| ByteShape v9 | 150 | 60.5 | 59.0 | 18 to 143 | 775 | 43.2 | 150 / 150 |
| MIX, first 50 | 50 | 59.7 | 58.5 | 30 to 144 | 729 | 37.1 | 50 / 50 |
| MIX, other 100 | 100 | 60.9 | 58.6 | 22.7 to 144.7 | 755 | 38.4 | 100 / 100 |
| MIX, combined | 150 | 60.5 | not recorded | not recorded | not recorded | not recorded | 150 / 150 |
| Qwen3.6-35B-A3B | 50 | 30.2 | 29.0 | 13 to 51 | 3049 | 49.0 | 48 / 50 |
| gpt-oss-20b | 50 | no valid target | not recorded | not recorded | not recorded | not recorded | 0 / 50 |

ByteShape and MIX took the same wall clock, about 60.5 seconds per complete target. MIX's 150 targets produced 9,071 seconds of generation. Qwen3.6 took about 30.2 seconds, roughly half the time, and had the highest median decode rate of the models with valid output. gpt-oss produced no valid target, so it has no rate in this table.

At 60.5 seconds per target the measured projection was about 1.7 hours per 100 locally fitting targets, about 4.0 hours per 240 and about 16.8 hours per 1,000, before model loads and reboot pauses. The full run's model attempts ran from 2026-10-09 06:19 to 2026-10-21 08:07 UTC across part-time runs. That elapsed span is not a generation rate, because it includes pauses, reboots and dataset transfers.

A model load took about 28 seconds in the acceptance run. One routing defect caused repeated loads. The fit check counted the prompt through the first ordered key and stopped the runtime before an oversize route, so every oversize target unloaded the generation model and the next local target reloaded it. A target that needed the larger key reloaded twice. The fix counted the prompt through the loaded key and kept the runtime loaded across the oversize call. The measured window then had one generation load for two local targets and one oversize target. This is a correction to the achieved throughput of a mixed window, not to the per-target model rate.

The full run completed 4,543 eligible targets. The two local keys served 4,520 targets. The other 23 went whole to DeepSeek V4.1 Flash on the run's explicit oversize route because their packets fitted neither key. There were no failed, skipped, pending or uncovered targets.

## Structured-output failures

The model with the fastest decode in the fixed-prompt measurements produced no usable output. Validity is a separate result from speed and from fit.

| Model | Attempts | Valid | Invalid | Observation |
|---|---:|---:|---:|---|
| ByteShape v9 | 150 | 150 | 0 | largest prompt 92,815 tokens, no skip |
| MIX | 150 | 150 | 0 | all at the 131,072-token MTP key, no larger key load |
| Qwen3.6-35B-A3B | 50 | 48 | 2 | invalid results retained, not repaired |
| gpt-oss-20b | 50 | 0 | 50 | empty content, analysis channel consumed the cap |
| Nemotron-3-Nano-30B-A3B, two-packet probe | 2 | 1 | 1 | largest packet 163,578 tokens, 8,192-token truncation, 1,654 seconds |

gpt-oss-20b failed on every attempt. The server returned HTTP 200 with `finish_reason=length`, 8,192 completion tokens and empty content, because the harmony analysis channel consumed the whole cap.

Raising the cap to 32,768 produced 32,768 tokens of reasoning and still no content. Reasoning off and low, server-default payloads, `enable_thinking`, `reasoning_effort`, `--reasoning-budget 0` and `--reasoning-format none` all failed. One shape returned HTTP 500 with `The model produced output that does not match the expected peg-native format`. Another moved the harmony control tokens into the content and still produced no valid JSON.

The JSON grammar forced an object while the model tried to emit channel tokens, and the output degenerated into repetition. Two older runtime revisions on the machine predate the `--reasoning` flag and fail to start for this model. No valid gpt-oss result exists.

Nemotron fitted the smallest packet and took 261 seconds. The largest packet was 163,578 prompt tokens, was truncated at 8,192 completion tokens and returned invalid JSON after 1,654 seconds. Qwen3.6 returned two invalid results out of 50. ByteShape returned none in the held-out run and none across 84 valid format-trial targets. Its only non-valid outcome was the one oversize packet in the tuning 50, which was reported as a context skip and never truncated.

The product treats model output as untrusted. A whole-target generation retries without a fixed attempt cap until one result is accepted or the run is stopped, while `INFERENCE_MAX_ATTEMPTS` bounds multiview selection, rerank and request preparation, and the example sets it to three. A route with a provider attempt cap stops at that cap. Each rejected attempt is recorded as a target failure, no invalid result becomes a proposal, and an accepted result is never repaired. [Generation and validation](/docs/backend/inference/inference.md#generation-and-validation) states the contract. The measured 0 invalid results for ByteShape sit well below the 5 percent invalid rate that the format target allowed, but that is a format-validity result, not a quality result.

## Sizing corrections

The context assumption moved from 65,536 tokens to 196,608 and then to the two applied keys. A later estimate raised the demand assumption above both applied keys without creating new capacity.

The first runtime proof used Qwen3.6-35B-A3B UD-IQ3_S at 65,536 tokens with `q8_0` KV and full offload. It passed a median generated rate above 40 tokens per second and selected no model for the run.

The prompt-readiness stage then used the same artifact at 196,608 tokens, the 192k key, with `q8_0` KV. That key passed 44 of 44 calls over the development targets and both packet alternatives. Its measured KV cache was 2,139 MB and about 763 MB of dedicated headroom remained. The result proved the provider interface and the prompt, not the capacity of the applied keys.

The model selected after the held-out benchmark was MIX. Its two keys are 131,072 tokens with MTP and 163,840 tokens without MTP, both with `q4_0` KV. The prompt was version 9 with schema version 2. The keys did not fit at `q8_0`, so the lower-precision KV cache was required. The selected policy put the MTP key first and loaded the no-MTP key only when the full packet, the 8,192-token output cap and the 1,024-token fit headroom did not fit the first key. That policy was applied to the full run, and [the fit rule](/docs/backend/inference/inference-scheduling.md#the-fit-rule) states the rule the product applies.

The later sizing work estimated that the catalogue's largest prompt needs 393,216 tokens of context. The arithmetic used the largest active representative's six-cell teaching-text sum, the configured final candidate count and the shared prompt material.

```text
A = 23753 characters, the largest active representative's six-cell sum
C = 23753 characters, the largest sum across all representatives
D = 60380 characters, the system text, separator and nine examples
K = 50 candidates
characters = A + K*C + D = 1271783
base_tokens = ceil(characters / 4) + 8192 + 1024 = 327162
buffered_tokens = (base_tokens * 120 + 99) // 100 = 392595
context_estimate = ceil(buffered_tokens / 16384) * 16384 = 393216
```

The estimate assumed 4 characters per token, a 20 percent safety margin and rounding up to a 16,384-token increment. It counted the largest representative's text for every one of the 50 candidates, counted all nine examples, and omitted target-specific JSON escaping and identity overhead, the result schema and chat-template and tokenizer effects. It performed no tokenizer call, no prompt assembly and no model run. It is demand arithmetic, not a measured prompt, a rendered request or an achieved context.

The estimate exceeds both measured local ceilings, 131,072 and 163,840. It did not create a 393,216-token key. A key whose configured context exceeded its achieved maximum would fail validation, and raising the achieved maximum from arithmetic would invent evidence. The configuration therefore kept 131,072 and 163,840. A packet that fits neither key fails as one capacity failure with the reason `context_exceeded`, and the product configuration has no fallback route. The full run supplied an explicit oversize route that sent such targets whole to DeepSeek V4.1 Flash. The full run's 23 oversize targets are the measured gap between the packets the runs met and the two local keys.

The estimate is the later correction to the sizing assumption, but it is not a correction to a measurement. The measured packet envelope, with a 169,654-token maximum over 200 packets, and the full run's 23 oversize targets are the evidence about the packet sizes the runs met. The 393,216-token figure is a conservative bound on the rendered prompt.

One earlier fit claim was corrected by later measurement, and one candidate was removed by a fit check. The gpt-oss 196,608-token key did not provide that context in a request, as described above, and the held-out run used the native 131,072-token key. Nemotron's 393,216-token context was achieved only with expert layers on the CPU, at a speed and validity cost that removed it from the comparison.

## What the numbers support

The local hardware could hold the selected model and a long packet, and it could do so at a rate that finished the catalogue. In the held-out run MIX ran at 60.5 seconds per complete target and fitted all 150 packets at its first key. In the full run it served 4,520 of the 4,543 targets. ByteShape also fitted all 150 packets, with one recovered context-creation failure. Its aggregate dedicated total reached 16,922 to 16,926 MB, about 98.5 percent of the card's capacity, whose 16 GB specification label denotes 17.2 GB in powers of ten. That percentage is an upper bound on the discrete card's share. MIX had more VRAM headroom and was the model selected for the run.

Throughput did not decide the model. gpt-oss-20b was the fastest by decode in the fixed-prompt measurements and produced no valid result at all. Qwen3.6 was the fastest per complete target, at about half the wall clock, and was not selected. MIX and ByteShape were the same speed per target. A token rate or a wall clock says how long a model takes, not whether its output is right, and this line of work kept those questions apart.

The selection rested on judged support, the share of a model's emitted findings that a blind judge marks supported by the teaching text. On the 150 held-out targets MIX supported 111 of 178 findings, 0.62 overall, with 54 of 100 required, 38 of 47 recommended and 19 of 31 equivalence findings supported. ByteShape supported 88 of 168, 0.52 overall, with 41 of 97 required, 15 of 24 recommended and 32 of 47 equivalence findings supported. Qwen3.6 supported 25 of 109, 0.23 overall. MIX also carried 15 outright unsupported required findings.

The corrected-reference whole-result score ran the other way, with MIX at 0.192 and ByteShape at 0.236, and it stayed a secondary diagnostic. These are single-night, single-sample observations on the declared cohorts. The reference answers, the judge and the verdict method are described in [reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md).

The selected policy was MIX alone, prompt version 9, schema version 2, the MTP key first and the no-MTP key only when needed. It kept every emitted recommendation and applied no confidence or flag cutoff. The full run published 4,543 inferred sets, of which 2,348 carry an expression and 2,195 are complete empty results, and 345 equivalence groups. The 15 unsupported required findings stayed as a known limit of the selected model.

## Limitations

The 393,216-token estimate is the main limitation of the sizing story. It is arithmetic over stored character counts, not a tokenizer measurement, and it cannot establish that any payload fits any key. The report keeps it separate from the measured ceilings and from the measured packet envelope.

The throughput measurements come from one machine and one runtime. The fixed-prompt table is one request per measurement with `cache_prompt=false`, so it excludes prefix reuse. The complete-target table includes prefix reuse, so the two tables are not directly comparable. The held-out cohort is 150 packets, with a shared 50-target comparison subset, and the support verdicts are single-sample. A different packet mix, a different prompt or a different runtime revision could change the rates.

The memory counters are aggregate sums over adapters and processes, and no per-adapter split was recorded. The measurement used binary divisors, 1,048,576 for each memory MB figure and 1,073,741,824 for each memory GB figure. This report converts each binary-sourced value to decimal MB and GB. The card's 16 GB specification label describes a binary capacity, 17.2 GB in powers of ten. The idle baseline also moved with other consumers, so the change from idle to loaded is the meaningful figure, not the absolute idle value.

The early gpt-oss 196,608-token row and the later request cap disagree on the usable context. The later request is the result that stands, and the early throughput values at 10,000 and 120,000 tokens remain because those prompts fit the native context. The report does not use the 196,608-token key as a fit result.

The full run's elapsed span is not a throughput measurement. It includes operator pauses, checkpoint reboots and dataset transfers, and the recorded result gives counts and routes rather than a per-target split of prefill, decode and load time. The 60.5-second mean from the held-out run is the generation figure.

## Setup details

The early benchmark sent one loopback `/completion` request per measurement with `cache_prompt=false` and temperature 0. The prompt lengths 10,000 and 120,000 are prompt token counts under the row's context. The 98,304-token row used a prompt of about 80,000 tokens. The rates are tokens per second, with prefill and decode reported separately.

The held-out packet run used the product request renderer with schema version 2, thinking off, temperature 0, seed 0, an 8,192-token output cap and a 300-second request timeout. Each target's raw request and response were retained. A valid result passed the strict schema and was counted once. The 50 comparison targets were the size quantiles at integer-floor indices over the 150 complement, so the smallest and largest packets were included.

The fit rule counted the rendered prompt tokens, added the 8,192-token output cap and the 1,024-token headroom, and compared the sum with each key's configured context and achieved maximum context. The first ordered key that fitted received the request. A packet that fitted neither key was never truncated.

The model load used the same runtime with the selected key's configured arguments. The measured load time was about 28 seconds. The full run restarted the machine at checkpoint boundaries and resumed pending work, so the generation rate and the elapsed run are different quantities.

The full run's counts are 4,543 eligible active targets, 4,520 local targets and 23 oversize targets, with 4,543 retained complete and published, no failures and no uncovered targets. The run supplied an explicit oversize route to DeepSeek V4.1 Flash.

## Untested follow-ups

A 393,216-token local key is untested. The estimate-sized key has no hardware qualification, and no key above 163,840 tokens was measured for the selected model.

The full run is the only full-catalogue fit sample. A tokenizer-measured distribution of catalogue packet sizes, rather than a conservative character bound, is untested.

A per-target split of prefill, decode and model load across the full run is untested. The recorded result gives counts and routes rather than a time split, so the share of the 60.5-second mean spent in each stage is unknown.
