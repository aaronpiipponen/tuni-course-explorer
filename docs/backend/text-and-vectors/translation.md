# Translation

The translation stage runs on the worker and fills the missing name, content, and learning outcomes of representative versions from the same field in the other language.

## What the stage fills

Translation is a [Remote stage](/docs/reference/glossary.md#administration) of the preparation path. It works on the worker's own copy of the selected dataset, and the finished copy comes back at the dataset return.

For every represented course the stage reads six cells: the name, the content, and the learning outcomes, each in Finnish and in English. It fills a cell when the version holds no official text for that field and language and the same field holds official text in the other language. That official text is the source of the translation.

A cell whose field holds official text in neither language is left as it is, because the stage never builds one field from another. The prerequisite text and the additional information of a version are not teaching text, so the stage neither reads nor fills them.

Its output holds derived translation entries only, and those entries are kept apart from the official text. The official text, the embeddings, and the inference results of the dataset are written by their own stages, and the entries of this stage reach the store only through the import described in [The output it publishes](#the-output-it-publishes).

![The worker reads its own copy of the selected dataset. The selector queues the cells to translate, the translation runtime answers one cell per request, and the output file is republished after every entry. The import writes the entries into the translation store of the same copy, and the dataset return brings the whole copy back. The outlined frame marks the steps that run on the worker.](/docs/diagrams/translation-pipeline.svg)

## Which cells are queued

The selector decides one of four things for every representative cell.

| The cell | What the stage does |
|---|---|
| Holds official text | Nothing. The official text is the effective text. |
| Holds a translation that is current | Reuses it and translates nothing. |
| Holds no official text, and the same field holds no official text in the other language | Translates nothing, because there is no source text. |
| Anything else | Queues the cell for translation. |

A stored translation counts as current only when it was made from the exact official source text that is in force and, when a model produced it, by the model identity the configuration names. A translation made from an older official text, or by a translation model other than the configured one, is queued again. The selector changes no stored row and removes none.

The selector reads every course, active and inactive alike, so a course outside the activity window is translated as well. It reports, for each of the six cells, how many representatives hold official text, a current translation, queued work, and no source text, together with the counts of active and inactive represented courses.

## The output it publishes

A session writes one output file. Each entry names the course version, the field, the target language, the source language, the exact official source text, the translated text, the method it was made by, the model identity of a machine translation, and the time it was produced.

Each success republishes the whole output at once, so the file holds either the whole result or the result before that entry, and never a partly written entry. The retained output is the progress of the session, and the number of entries it holds is the completed count the operator reads.

The import into the [translation store](/docs/backend/text-and-vectors/teaching-text-store.md) is the only write path for a derived row. The import runs while the session is finalized, before the dataset returns, and the stage itself writes neither the store nor official text.

> [!IMPORTANT]
> The store validates the whole batch before it writes a single row, so one entry that is invalid, or whose recorded source text differs from the current official text of the selected representative, rejects the whole import. No part of that import reaches the table.

## The translation runtime

The stage asks one local model runtime on the worker for one translation per cell. The runtime is reached on loopback, and it is pinned by the configured model revision, runtime revision, and artifact checksum, so a translation is bound to one known model. A fresh launch of the runtime checks the pinned revision of the runtime checkout and the checksum of the model artifact.

One request carries the source text, the source language, and the target language, and it asks for the configured model alias with the configured temperature and output cap. Blank source text and two equal languages fail before any request leaves the stage.

Transport failures and 429 or 5xx statuses are retried inside the configured attempt budget, with a delay that doubles from one attempt to the next. A 200 response is checked against the configured runtime contract, and a response that does not match it is retried in the same budget. Any other 4xx status ends the run.

An error names the endpoint and either a status or an exception class. The source text, the translated text, the request, the response body, and any credential stay out of it.

Immediately before each request the stage reads the operator control again. A pause or a stop that arrived while the run was busy therefore takes effect before the next request instead of starting one more.

## Progress, pauses, and the failure record

The retained output is the progress of the session. A resumed session translates only the cells that hold no entry and reuses every entry it holds, and a session whose worker process is lost continues from the same retained output. A relaunch refuses a session whose runner is alive or whose work is complete.

Pause and stop act between two cells. The stage then unloads the model runtime, publishes a checkpoint with the completed count, and leaves the retained output in place. A periodic reboot of the worker ends the run at the same kind of checkpoint, and the session continues under the same identity. [Worker sessions](/docs/operations/worker-sessions.md) describes the session mechanics and [Stage lifecycle](/docs/operations/stage-lifecycle.md) describes the actions an operator runs.

A failed translation writes one failure record beside the output. The record holds the course version, the field, the target language, the error class, and one short safe reason. It holds no source text and no generated text, and the next run translates that cell again and removes the record when it succeeds.

## Configuration keys

`config/translation.toml` holds the values in this table. [Configuration](/docs/backend/configuration.md) describes how the settings owner reads them.

| Key | Meaning |
|---|---|
| `TRANSLATION_HOST` | The loopback address the runtime binds |
| `TRANSLATION_PORT` | The port the runtime answers on |
| `TRANSLATION_MODEL_ALIAS` | The model name every request asks the runtime for |
| `TRANSLATION_MODEL_REPOSITORY` | The repository identity of the pinned model, recorded in the identity of a stored translation |
| `TRANSLATION_MODEL_REVISION` | The pinned commit of the model |
| `TRANSLATION_ARTIFACT_PATH` | The path of the pinned model artifact on the worker |
| `TRANSLATION_ARTIFACT_SHA256` | The checksum of the pinned model artifact, checked before a fresh runtime launch |
| `TRANSLATION_ARTIFACT_QUANT` | The quantization of the pinned artifact, recorded in the identity of a stored translation |
| `TRANSLATION_RUNTIME_REVISION` | The pinned commit of the runtime |
| `TRANSLATION_CONTEXT_SIZE` | The text context the runtime serves |
| `TRANSLATION_PARALLEL` | How many requests the runtime serves at once |
| `TRANSLATION_GPU_LAYERS` | How many model layers the runtime offloads, or all of them |
| `TRANSLATION_REQUEST_TIMEOUT_SECONDS` | How long one translation request may take |
| `TRANSLATION_MAX_ATTEMPTS` | How many attempts one request gets, the first one included |
| `TRANSLATION_RETRY_BACKOFF_SECONDS` | The delay before the first retry, doubled for each further retry |
| `TRANSLATION_MAX_TOKENS` | The output cap of one translation |
| `TRANSLATION_TEMPERATURE` | The sampling temperature of one request |
| `TRANSLATION_CONTROLLER_STATE_ROOT` | The directory that holds the state of the translation stage |
| `TRANSLATION_CONTROLLER_HEALTH_ATTEMPTS` | How many times a session waits for the runtime to answer before it gives up |
| `TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS` | The wait between two such checks |
| `TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS` | How long the stop and the finalize of one session may take |

The example sets a context of 16384 tokens, an output cap of 8192 tokens, a temperature of 0, three attempts with a one-second delay before the first retry, and a request timeout of 600 seconds.
