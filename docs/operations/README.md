# Operations

Operations covers the administration command, its four preparation stages, the state each stage holds, and the worker work that fills the Working dataset.

## The operator's surface

Every stage runs because an operator starts it. The entry point is `scripts/admin.py`, run either as the numbered operator menu or as one machine command, and both forms reach the same dispatcher. No stage starts itself, and the read-only web server cannot start, stop, or reach one.

Each stage acts on the operator's request alone. A start either continues work the stage retained from an earlier run or begins a fresh session, a pause and a stop end the run at a durable boundary, and a report reads the recorded state and stored data without changing anything.

The command reads every registered configuration file and every key of the device-local environment file as those files hold their values, and it saves one key of one file through a writer that validates the whole candidate and leaves the file's comments as they are. One save writes one key. A saved file reaches a running process when that process next builds its settings, so restart a serving copy after a save that changes a bind, a port or a credential. [Configuration](/docs/backend/configuration.md#reading-and-writing-a-file) states the reads, the write and the precedence between the files.

## The two operator surfaces

An operator works through two surfaces. The numbered operator menu and the machine commands of `scripts/admin.py` run the administration command's fixed commands through its dispatcher. The [administration console](/docs/operations/admin-console/README.md) is a separate signed-in browser application with its own administration backend, and that backend runs the administration command's fixed commands through the dispatcher, including the feedback commands, which the menu does not offer. Both surfaces run only the commands the administration command defines, and an operator supplies each command's values rather than command text.

| Tab | What it holds |
|---|---|
| [Dashboard](/docs/operations/admin-console/dashboard.md) | The serving state, the website, the host, the database and the embedding runtime |
| [Data preparation](/docs/operations/admin-console/data-preparation.md) | The ingestion, translation and embedding stages, their reports, and the embedding coverage and serving-artifact build |
| [Inference](/docs/operations/admin-console/inference.md) | The inference run, its reports and the per-target decisions |
| [Logs](/docs/operations/admin-console/logs.md) | The command log, the session and runtime log reads, and the usage report |
| [Settings](/docs/operations/admin-console/settings.md) | The configuration editor, the feature switches, the dataset roles and their actions, the backup cleanup, the two rebuild scopes and the worker provisioning |
| [Feedback](/docs/operations/admin-console/feedback.md) | The stored feedback submissions, their configured answers and images, their current publication outcome and issue link, and named local deletion |

The Settings tab holds the [Dataset roles](/docs/operations/admin-console/dataset-roles.md) panel.

A feedback submission travels through its own path, outside the four preparation stages. The anonymous form writes it to the separate feedback application store, and a separately scheduled sender publishes at most one opted-in submission per activation to the configured GitHub repository. The sender runs as its own short operation under its own user timer. The console reads the stored records and recorded outcomes from the feedback application store. [Feedback publication](/docs/backend/feedback-publication.md) states the rendering, the single attempt and the recorded outcomes.

Sign-in and the administration session belong to the administration backend. The administration lock is the file `data/admin-web/lock` that three consecutive failed sign-ins create, and an operator clears it by deleting that file. The command log holds the fixed commands the backend ran and its sign-in, failed sign-in and lock events. The request records are the web server's lines, and the usage report summarizes one window of hours. [Console access and records](/docs/operations/admin-console/access-and-records.md) states the admission order, the sessions, the lock and both records.

The three `config` machine commands list the registered files, read one file, and save one key, and the Configuration entry runs the same three. Only `config set` writes, and it validates the whole candidate through one writer that preserves the comments of the file. [Setup and preflight](/docs/operations/setup-and-preflight.md#configuration) lists the commands and the entry.

A manual cleanup deletes one named dataset or backup file, and [Datasets](/docs/operations/datasets.md#manual-cleanup) states its commands and refusals. The account password is set by one fixed command over the hidden terminal, and [Setup and preflight](/docs/operations/setup-and-preflight.md#the-administration-password) states the entry and its prompts.

The app rebuild and the administration rebuild are separate scopes, and a successful administration rebuild signs every operator out because the administration backend restarts. [Setup and preflight](/docs/operations/setup-and-preflight.md#the-two-rebuild-scopes) states both scopes and their confirmations.

## The four stages

The four stages of the preparation path fill the Working dataset. Two run on the machine that runs the administration command and two run on the worker.

Each stage owns its own state and its own action lock, so the stages run independently of one another and two actions on one stage are serialized.

| Stage | Runs on | Fills | Session retained after a stop |
|---|---|---|---|
| Ingestion | The machine that runs the administration command | Official courses, modules, versions, and prerequisite rules | Yes |
| Embedding | The same machine | Teaching-text chunks and their vectors | Yes |
| Translation | The worker | Translated teaching text beside the official text | No |
| Inference | The worker | Inferred prerequisites and equivalence groups | No |

A local stage reads and writes the Working dataset in place. A remote stage works on its own copy and returns it, so Working changes as one whole and Selected keeps serving. The [Operator menu](/docs/operations/operator-menu.md) drives all four, and [Stage lifecycle](/docs/operations/stage-lifecycle.md) states the actions and the durable state behind them.

## Lifecycle state and coverage

Two different facts describe a stage. Its [lifecycle](/docs/reference/glossary.md#administration) is the state of the stage itself: idle, starting, running, paused, stopped, completed, or failed. Its coverage counts the rows the stage has already stored, with the pending, completed, and failed counts of each part of the work.

The two facts are independent. A stop after the work finished returns the stage to idle and records the work as complete. A stop with partial coverage also returns the stage to idle, and the pending work is left for the next start. A stage that reports an idle state therefore reports coverage as well, and an idle state with pending rows is the ordinary state between two runs.

The [Catalogue summary](/docs/reference/glossary.md#administration) and the [Coverage report](/docs/reference/glossary.md#administration) are the read-only reports over that data. The [Operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) lists them.

## The dataset roles

The web server and ordinary feature reads use the Selected dataset. The four stages use the Working dataset. Each role is one pointer under `ADMIN_STATE_ROOT`, and one receipt per dataset records its identity. A state root with no pointer is bootstrap and serves the configured database directly, and the stages refuse because no Working dataset exists. A local stage writes Working, and its reports read Working, not the progress of a remote stage that has not returned.

## The worker round trip

A remote stage leaves the Working dataset as it is while it runs and changes it once at the verified return, which [Worker sessions](/docs/operations/worker-sessions.md#pause-stop-and-the-return) and [Datasets](/docs/operations/datasets.md#the-return-and-the-working-role) describe.

The [Full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md) report covers a remote stage run that stopped part-way and resumed to a complete cycle, and the [Curriculum capture and replay](/docs/experiments/runtime-storage-and-serving/curriculum-capture-and-replay.md) report covers the capture and replay of a full catalogue.

## Derived files, served data and the web restart

Search and comparison subtract an [embedding hub](/docs/reference/glossary.md#capture-and-data-preparation) from every vector before measuring similarity, so the hub files are computed from the served dataset and change when its chunk vectors change. The build targets the Selected dataset, which is the configured database in bootstrap, and its hubs come from that dataset. `serving-artifacts` always writes the study fragments and the catalogue artifact, and [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-embedding-switch) states what each embedding mode writes. The embedding menu and console preparation action run the same build for the served dataset.

The four preparation stages write Working and change no served vector, artifact file or serving identity. A Working embedding run therefore needs no serving build and no restart. The site serves a dataset's vectors after that dataset is assigned to Selected and its serving artifacts are built for it.

The feature web server also bounds its reported dataset identity by the generation value it creates at start. The browser scopes its cached reads to that identity, so a restarted feature web server changes the identity a browser reads next.

A served dataset changes through one confirmed promotion.

```bash
uv run python scripts/admin.py datasets copy-to-selected SOURCE_DATASET_ID --confirm-restart
```

The command copies the source, builds and verifies the copy, publishes it as Selected, restarts only the feature web unit and proves the served catalogue and its identity. A failed build switches nothing and restarts nothing. A failed restart or proof restores the previous selection, restarts the unit and proves the previous catalogue. [Datasets](/docs/operations/datasets.md#promotion-to-selected) states the confirmation, the refusals, the rollback and the preserved failed-copy resources.

Run `uv run python scripts/admin.py serving-artifacts --prune` after a successful restart, to remove the target database's superseded builds, the other year families' builds, and owned temporary outputs. A standalone `serving-artifacts` build is the setup and maintenance action for the served dataset or a named `--dataset`. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-artifact-family-the-build-directory-and-the-embedding-directory) states which embedding directories the prune retains in each mode.

A deployment enrolls the configured database as Selected unless its name is the configured example database, then migrates and builds Selected. It refuses before any build while a stage is running or not idle. When a push to the main branch of `aaronpiipponen/tuni-course-explorer` passes the checks of its workflow, `deploy/deploy.sh` builds the database image and the native libraries, runs that enrollment, migrates the served role, builds its serving artifacts, builds both frontends, restarts the web server and the administration backend, proves their loopback listeners and HTTP answers, and then prunes the superseded builds.

The restart is required because the supervisor resolves its settings bundle, opens the artifact set and creates the shared caches and the lookup projection before it forks its workers, and because every worker inherits that set rather than opening it again. After a standalone build, restart the unit `ADMIN_SITE_WEB_SERVICE_UNIT` names through the manager `ADMIN_SITE_WEB_SERVICE_SCOPE` selects: `systemctl --user restart <unit>` under the user manager, or `sudo systemctl restart <unit>` under the system manager. [Web supervisor](/docs/backend/interfaces/web-supervisor.md) states the supervisor lifetime and the startup checks. The artifact command replaces no running worker and restarts no unit.

The restart notifies no idle tab, so an in-place change to the served data reaches the browser on its next uncached read or reload. This holds for an enrolled site and for a bootstrap site that serves its configured database.

[Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes the hubs, the centroids and the files, and the [Operator menu](/docs/operations/operator-menu.md#building-the-serving-artifacts) describes the build.

## Where to read next

The [Operator menu](/docs/operations/operator-menu.md) lists the numbered entries, the machine command behind each one, and what each entry needs before it runs. [Stage lifecycle](/docs/operations/stage-lifecycle.md) states the five shared actions, the durable states, the boundaries at which a pause or a stop takes effect, and how a failure recovers. [Lifecycle core](/docs/operations/lifecycle-core.md) describes the contracts and the detached process behind that behavior. [Worker transport and datasets](/docs/operations/worker-transport.md) maps the modules that carry a worker session over the transport boundary and own the dataset receipts, snapshots, and rotation.
