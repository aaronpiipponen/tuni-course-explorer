# Operations

Operations covers the administration command, its four preparation stages, the state each stage holds, and the worker work that fills the selected dataset.

## The operator's surface

Every stage runs because an operator starts it. The entry point is `scripts/admin.py`, run either as the numbered operator menu or as one machine command, and both forms reach the same dispatcher. No stage starts itself, and the read-only web server cannot start, stop, or reach one.

Each stage acts on the operator's request alone. A start either continues work the stage retained from an earlier run or begins a fresh session, a pause and a stop end the run at a durable boundary, and a report reads the recorded state and stored data without changing anything.

The command reads every registered configuration file and every key of the device-local environment file as those files hold their values, and it saves one key of one file through a writer that validates the whole candidate and leaves the file's comments as they are. One save writes one key. A saved file reaches a running process when that process next builds its settings, so restart a serving copy after a save that changes a bind, a port or a credential. [Configuration](/docs/backend/configuration.md#reading-and-writing-a-file) states the reads, the write and the precedence between the files.

## The two operator surfaces

An operator works through two surfaces. The numbered operator menu and the machine commands of `scripts/admin.py` reach the four stage owners through the administration command's dispatcher. The [administration console](/docs/operations/admin-console/README.md) is a separate signed-in browser application with its own administration backend, and it runs those same fixed commands over those same owners. Both surfaces run only the commands the administration command defines, and an operator supplies each command's values rather than command text.

| Tab | What it holds |
|---|---|
| [Dashboard](/docs/operations/admin-console/dashboard.md) | The serving state, the website, the host, the database and the embedding runtime |
| [Data preparation](/docs/operations/admin-console/data-preparation.md) | The ingestion, translation and embedding stages, their reports, and the embedding coverage and hub write |
| [Inference](/docs/operations/admin-console/inference.md) | The inference run, its reports, the per-target decisions and the dataset cleanup |
| [Logs](/docs/operations/admin-console/logs.md) | The command log, the session and runtime log reads, and the usage report |
| [Settings](/docs/operations/admin-console/settings.md) | The configuration editor, the feature switches, the backup cleanup, the two rebuild scopes, the dataset enrollment and migration, and the worker provisioning |

Sign-in and the administration session belong to the administration backend. The administration lock is the file `data/admin-web/lock` that three consecutive failed sign-ins create, and an operator clears it by deleting that file. The command log holds the fixed commands the backend ran and its sign-in, failed sign-in and lock events. The request records are the web server's lines, and the usage report summarizes one window of hours. [Console access and records](/docs/operations/admin-console/access-and-records.md) states the admission order, the sessions, the lock and both records.

The three `config` machine commands list the registered files, read one file, and save one key, and the Configuration entry runs the same three. Only `config set` writes, and it validates the whole candidate through one writer that preserves the comments of the file. [Operator menu](/docs/operations/operator-menu.md#configuration) lists the commands and the entry. A manual cleanup deletes one named dataset or backup file, and [Datasets](/docs/operations/datasets.md#manual-cleanup) states its commands and refusals. The account password is set by one fixed command over the hidden terminal, and [Operator menu](/docs/operations/operator-menu.md#the-administration-password) states the entry and its prompts. The app rebuild and the administration rebuild are separate scopes, and a successful administration rebuild signs every operator out because the administration backend restarts. [Operator menu](/docs/operations/operator-menu.md#the-two-rebuild-scopes) states both scopes and their confirmations.

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
> A web server whose site serves embedding features reads both hub files when its process starts and holds those values while it runs. Restart a serving copy after the files are written.

[Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes the hubs and the files, and the [Operator menu](/docs/operations/operator-menu.md#writing-the-hubs) describes the write.

## Where to read next

The [Operator menu](/docs/operations/operator-menu.md) lists the numbered entries, the machine command behind each one, and what each entry needs before it runs. [Stage lifecycle](/docs/operations/stage-lifecycle.md) states the five shared actions, the durable states, the boundaries at which a pause or a stop takes effect, and how a failure recovers. [Lifecycle core](/docs/operations/lifecycle-core.md) describes the contracts and the detached process behind that behavior. [Worker transport and datasets](/docs/operations/worker-transport.md) maps the modules that carry a worker session over the transport boundary and own the dataset receipts, snapshots, and rotation.
