# Operations

Operations covers the administration command, its four preparation stages, the state each stage holds, and the worker work that fills the selected dataset.

## The operator's surface

Every stage runs because an operator starts it. The entry point is `scripts/admin.py`, run either as the numbered operator menu or as one machine command, and both forms reach the same dispatcher. No stage starts itself, and the read-only web server cannot start, stop, or reach one.

Each stage acts on the operator's request alone. A start either continues work the stage retained from an earlier run or begins a fresh session, a pause and a stop end the run at a durable boundary, and a report reads the recorded state and stored data without changing anything.

## The four stages

The four stages of the preparation path fill the selected dataset. Two run on the machine that runs the administration command and two run on the worker.

Each stage owns its own state and its own action lock, so the stages run independently of one another and two actions on one stage are serialized.

| Stage | Runs on | Fills | Session retained after a stop |
|---|---|---|---|
| Ingestion | The machine that runs the administration command | Official courses, modules, versions, and prerequisite rules | Yes |
| Embedding | The same machine | Teaching-text chunks and their vectors | Yes |
| Translation | The worker | Translated teaching text beside the official text | No |
| Inference | The worker | Inferred prerequisites and equivalence groups | No |

A local stage reads and writes the selected dataset in place. A remote stage works on its own copy and returns it, so the selected dataset changes as one whole. The [Operator menu](/docs/operations/operator-menu.md) drives all four, and [Stage lifecycle](/docs/operations/stage-lifecycle.md) states the actions and the durable state behind them.

## Lifecycle state and coverage

Two different facts describe a stage. Its [lifecycle](/docs/reference/glossary.md#administration) is the state of the stage itself: idle, starting, running, paused, stopped, completed, or failed. Its coverage counts the rows the stage has already stored, with the pending, completed, and failed counts of each part of the work.

The two facts are independent. A stop after the work finished returns the stage to idle and records the work as complete. A stop with partial coverage also returns the stage to idle, and the pending work is left for the next start. A stage that reports an idle state therefore reports coverage as well, and an idle state with pending rows is the ordinary state between two runs.

The [Catalogue summary](/docs/reference/glossary.md#administration) and the [Coverage report](/docs/reference/glossary.md#administration) are the read-only reports over that data. The [Operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) lists them.

## The selected dataset

One dataset is selected at a time, and the web server, the four stages, and the operator reports all read it. `SELECTED_DATASET_ENABLED` in `config/database.toml` decides whether a process reads the configured database or the dataset that the pointer under `ADMIN_STATE_ROOT` names. A local stage writes that dataset, and the stage reports read the dataset the pointer names, not the progress of a remote stage that has not returned.

## The worker round trip

A remote stage leaves the selected dataset as it is while it runs, and the selected dataset changes once, at the return:

1. The start of a remote stage takes a snapshot of the selected dataset.
2. The worker prepares its own copy from that snapshot, and the stage writes only that copy.
3. On a stop, the finished copy returns as one whole and is checked against the snapshot.
4. The returned copy is restored and becomes the selected dataset.
5. The worker's database is dropped once the server receipt exists, and the [dataset rotation](/docs/reference/glossary.md#administration) retains the selected dataset and the one before it.

[Worker sessions](/docs/operations/worker-sessions.md) describes the session and its return, and [Datasets](/docs/operations/datasets.md) describes the retained datasets and their reports.

## Derived files and the web restart

Search and comparison subtract an [embedding hub](/docs/reference/glossary.md#capture-and-data-preparation) from every vector before measuring similarity, so the two hub files are computed from the selected dataset and change when its chunk vectors change. The administration command computes both hub means from the current chunk vectors and writes the two files that `EMBEDDING_HUB_VECTOR` and `EMBEDDING_OUTCOMES_HUB_VECTOR` in `config/search.toml` name.
> [!IMPORTANT]
> A web server reads both hub files when its process starts and holds those values while it runs. Restart a serving copy after the files are written.

[Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes the hubs and the files, and the [Operator menu](/docs/operations/operator-menu.md#writing-the-hubs) describes the write.

## Where to read next

The [Operator menu](/docs/operations/operator-menu.md) lists the numbered entries, the machine command behind each one, and what each entry needs before it runs. [Stage lifecycle](/docs/operations/stage-lifecycle.md) states the five shared actions, the durable states, the boundaries at which a pause or a stop takes effect, and how a failure recovers. [Lifecycle core](/docs/operations/lifecycle-core.md) describes the contracts and the detached process behind that behavior. [Worker transport and datasets](/docs/operations/worker-transport.md) maps the modules that carry a worker session over the transport boundary and own the dataset receipts, snapshots, and rotation.
