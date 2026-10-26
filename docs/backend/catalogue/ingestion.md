# Ingestion

Ingestion captures the public curriculum source unchanged and converts one completed capture into the official catalogue of the selected dataset.

## What ingestion does

Ingestion runs as one stage with two steps. The [Capture](/docs/reference/glossary.md#capture-and-data-preparation) reads the anonymous public curriculum source and keeps exactly what it received. [Normalization](/docs/reference/glossary.md#capture-and-data-preparation) then validates the completed capture and converts it into official courses, modules, their versions, and their rules. The result is the official catalogue of the selected dataset: canonical courses and modules, exact versions, curriculum periods, official teaching text, prerequisite options, substitution options, and module rule trees.

The capture reads the public JSON interface anonymously. The configured source base must be the canonical public HTTPS base with no credentials in it, a read outside the source's public query paths is refused, and a redirect is not followed. An error response is retried inside the configured attempt budget, and only a 429 or 5xx status is retried. A successful response whose body is not the JSON the source contract describes ends the run instead of being retried, because the same request returns the same body again. A search result set that cannot be enumerated completely is refused rather than accepted in part, so the capture never records a partial catalogue.

## Captures are immutable and verified

Each capture writes one manifest and one stored response for every response it received. A stored response holds the exact bytes of one source response, is named by the request it answered and by the hash of its body, and is never overwritten, so the same response always lands in the same file with the same bytes. The manifest records every response it holds, with the stored name, the body hash, the body size, and one entry per source object carrying the source identity, the group identity, the position inside the response, and the content hash. A Source snapshot is one such object entry tied to the capture that produced it.

A capture commits its responses in bounded batches of `CAPTURE_CHECKPOINT_RESPONSE_COUNT` responses and publishes each batch together with the manifest update that records it. An interrupted capture therefore holds every committed batch and no partial one.

Verification decides whether the stored evidence matches the manifest. It re-reads every stored response, checks its bytes, its size, and its body hash against the manifest, checks the object positions and content hashes inside it against the manifest entries, and refuses a file in the capture directory that is not a stored response or that a completed manifest does not name. A capture reopened after a failure re-checks its retained responses from the beginning before it does any other work, and a completed capture refuses any change to its evidence.

A stopped or failed capture continues from its own evidence. The continuation re-verifies the retained responses, then fetches the source objects it does not already hold and nothing else, so a retried capture never downloads an object it has. A capture that finished its downloads continues into normalization without reading the source again. The [Curriculum capture and replay](/docs/experiments/runtime-storage-and-serving/curriculum-capture-and-replay.md) report records the scale of a full-catalogue capture and two source-free replays that reproduced the same normalized course versions and table counts.

![The public curriculum source is read by a capture that writes the stored responses with the manifest. The capture and the verification step are marked as resume points with a dashed outline, because a stopped run continues from a committed checkpoint. Verification checks every stored response, and normalization then converts the whole capture into the official catalogue of the selected dataset in one transaction.](/docs/diagrams/ingestion-pipeline.svg)

## Pause, stop, and the normalization transaction

Pause and stop act only at the durable boundaries of the run: after a committed batch of responses and before the next source request, between two stored responses during verification, and between a completed capture and normalization. A run that pauses or stops at one of those boundaries keeps the manifest and the stored responses it has and is not marked failed, so the next run continues rather than starts over.

Normalization is one transaction. It reads the completed capture, validates it, and writes the whole batch, and no control request interrupts it. The run report reconciles the captured object counts with the versions the batch wrote plus the versions it left out, so a batch that lost an object fails instead of publishing a partial catalogue.

> [!NOTE]
> A normalization that fails writes no row and keeps the capture it read, so the same verified capture can be normalized again without reading the source.

When a stopped stage returns to idle, its cleanup removes the capture runs it does not retain under the raw data root and keeps the run the stage continues from.

The stage runs through the administration command. A start needs the selected dataset enrolled with its database at the single migration head, and `config/curriculum.toml` naming the public source base and the university root.

```bash
uv run python scripts/admin.py ingestion start
uv run python scripts/admin.py ingestion status
```

The start action begins the stage and the status action reports its lifecycle state. The steps the operator runs are described in [Stage lifecycle](/docs/operations/stage-lifecycle.md) and the [Operator menu](/docs/operations/operator-menu.md).

## What a refresh changes

A refresh reads the source again and may receive responses that an earlier capture already holds. The capture deletes nothing and overwrites nothing, and a stored response keeps its exact bytes.

Normalization then compares the content hash of each captured object with the hash of the version already stored for that exact source identity. An identical version is left as it is, including its teaching text, its prerequisite and substitution options, its curriculum-period memberships, and its module rule nodes, so the derived work made from it stays valid. A changed version keeps its exact source identity and its record, and its dependent rows are written from the capture. A version the catalogue did not hold is added.

Activity is decided again for every course the batch touches, so a version that moved outside the activity window makes its course an inactive course, and the representative version of that course is chosen again from the versions that remain eligible.

A course version whose official code is null is dropped from the catalogue together with its teaching text, its curriculum-period memberships, and its options, and a course left with no coded version is dropped with it. Its stored response and source snapshot stay, and normalization reports the exclusion.

Downstream work is invalidated by changed content. A Translation records the hash of the official text it was made from, so a changed official text leaves the stored translation in place and reports it as a stale translation, which is never used. An embedding chunk records the representative version's source hash and the text it was made from, so the next embedding run rewrites the chunks whose inputs changed and removes the chunks of a version that is not the representative. [Translation](/docs/backend/text-and-vectors/translation.md) and [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describe those two stages.

## The catalogue summary

A Catalogue summary reports the counts of one dataset: curriculum periods, canonical courses, active courses, course versions, canonical modules, and module versions. The counts are read from the normalized tables of the selected dataset, so they describe what the last successful normalization published.

The operator menu reports the catalogue summary of the selected dataset, and a dataset verification records the same counts with the teaching-text, embedding, and inference coverage of that dataset. [Operator menu](/docs/operations/operator-menu.md) describes the report, and [Data model](/docs/backend/catalogue/data-model.md) describes the tables behind it.

## Configuration keys

`config/curriculum.toml` owns the capture and normalization values. The keys an operator sets are:

| Key | Meaning |
|---|---|
| `RAW_DATA_ROOT` | The repository-relative directory that holds the capture runs |
| `CAPTURE_CHECKPOINT_RESPONSE_COUNT` | How many responses one committed checkpoint covers |
| `KORI_BASE_URL` | The canonical public source base |
| `TUNI_UNIVERSITY_ID` | The university root that the requests name |
| `KORI_FIRST_ACADEMIC_YEAR` | The earliest academic year whose curriculum periods are captured |
| `CURRENT_ACADEMIC_YEAR` | The current academic year, which sets the activity window and the representative preference |
| `ACTIVE_ACADEMIC_YEAR_WINDOW` | The number of academic years inside which a listed version keeps a course active |
| `COURSE_GUIDE_BASE_URL` | The base of the official page URL built for a course version |
| `KORI_SEARCH_PAGE_SIZE` | How many search results one page holds |
| `KORI_BATCH_SIZE` | How many exact versions one request asks for |
| `KORI_REQUEST_TIMEOUT_SECONDS` | How long one source request may take |
| `KORI_MAX_ATTEMPTS` | How many attempts one source request gets, the first attempt included |
| `KORI_RETRY_BACKOFF_SECONDS` | The delay before the first retry, doubled for each further retry |
| `KORI_CONCURRENCY` | How many source requests run at once |
| `KORI_MAX_PARTITION_DEPTH` | The greatest partition-prefix length a truncated search query may reach before the capture fails |
| `INGESTION_CONTROLLER_STATE_ROOT` | The repository-relative directory of the ingestion stage state |

The example sets a checkpoint of 100 responses, a search page of 1000 results, an exact batch of 100 versions, three attempts, and four concurrent requests.

The capture and normalization internals are described in [Capture and normalization](/docs/backend/catalogue/capture-and-normalization.md), and the reads that consume the catalogue are described in [Representative versions and activity](/docs/backend/catalogue/representative-versions.md).
