# Operator menu

The operator menu is the numbered surface of the administration command, and each entry runs fixed commands over its owning services.

An entry prints the report of the command it runs, apart from the administration rebuild. The administration rebuild runs two fixed commands in sequence, the administration build and its own-unit restart, and it prints the restart command's acknowledgment alone.

## Starting the menu

```bash
uv run python scripts/admin.py
uv run python scripts/admin.py menu
```

Both forms start the numbered menu, and the two are the same command. The menu command takes no other argument.

The menu runs until one of three things happens. Choosing **0 Exit** returns 0, an end of input returns 0, and an interrupt returns 130. None of the three stops running work, and none of them starts one. An end of input and an interrupt leave the whole menu rather than the entry they were entered from. A failed operation prints its failure and the menu continues running.

## The main menu

The main menu draws its title and its numbered entries.

| Choice | Entry | What it opens |
|---|---|---|
| 1 | Setup/preflight | The setup and preflight entries |
| 2 | Ingestion | The ingestion stage tool |
| 3 | Translation | The translation stage tool |
| 4 | Embedding | The embedding stage tool |
| 5 | Inference | The inference stage tool |
| 6 | Coverage/summaries | The four read-only reports |
| 7 | Server/logs | The server status report, the log reads and the usage and command-log reports |
| 0 | Exit | Ends the menu |

Every other menu draws **0 Back**, which returns to the main menu without starting anything. The **Dispose target** menu draws **0 Cancel** in its place.

## Setup and preflight

Choice 1 opens the 13 setup and preflight entries.

| Choice | Entry | Asks for |
|---|---|---|
| 1 | Enroll/select dataset | Nothing |
| 2 | Copy dataset to Working | `Dataset id to copy to Working (0 to cancel): `, then `Copy dataset <id> (<database name>) to Working?` |
| 3 | Worker setup/update | `Origin branch [<server branch>]:` when the server checkout is not on `main` |
| 4 | Read-only worker preflight | Nothing |
| 5 | Migrate dataset | `Dataset role` with **1 Selected**, **2 Working** and **0 Cancel** |
| 6 | Dataset cleanup | `Dataset id: `, then `Delete dataset <id> (<database name>)?` or `Delete Working dataset <id> (<database name>)? Working becomes absent.` |
| 7 | Backup cleanup | `Backup file name: `, then `Delete backup <name>?` |
| 8 | Configuration | `Configuration file (0 to cancel): `, `Configuration key (0 to cancel): `, `JSON value: `, then `Save configuration <file> key <key>?` |
| 9 | Rebuild app | `Rebuild this site's frontend, containers and web server?` |
| 10 | Administration password | `Username (0 to cancel): `, then the command's hidden `Password: ` and `Repeat password: ` prompts |
| 11 | Rebuild admin panel | `Rebuild the admin panel? This signs all operators out.` |
| 12 | Set up example site | `App URL [<example address>]: `, `Administration username (0 to cancel): `, `Startup mode`, `Download the pinned embedding model if it is absent?`, `Set up feedback publication?`, then the hidden token prompt after a publication choice and the hidden password prompts |
| 13 | Set up real empty database | `Database name [course_explorer_real]: ` and `Startup mode` |

Except for the administration rebuild, each entry prints the report of the command it runs. [Setup and preflight](/docs/operations/setup-and-preflight.md) states what each entry does, the machine command behind it, and its prompts and confirmations.

Choices 12 and 13 run the two self-host workflows. The administration console offers no action for either workflow.

## The stage tools

The four stage tools share five entries. The inference tool adds one, and the embedding tool adds one.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Start | `uv run python scripts/admin.py <stage> start` |
| 2 | Pause | `uv run python scripts/admin.py <stage> pause` |
| 3 | Resume | `uv run python scripts/admin.py <stage> resume` |
| 4 | Status | `uv run python scripts/admin.py <stage> status` |
| 5 | Stop | `uv run python scripts/admin.py <stage> stop` |
| 0 | Back | Returns to the main menu |

The inference tool inserts **6 Dispose target** before **0 Back**, and the embedding tool inserts **6 Build serving artifacts** there.

Start reserves the stage, prepares its services and database, and launches one detached worker. The command returns once the launch is acknowledged, and the work continues in that worker. Resume re-arms a session the stage retained and launches its worker again. A stage that finalizes its work at a stop has nothing to resume, and resume is refused with a safe error.

Pause publishes a pause request, waits for the owned worker to exit, and unloads the resources the session started. The session, its receipt, and its progress are retained, so the work can continue from its own checkpoints. A pause never overwrites a pending stop.

Stop publishes a stop request, waits for the owned worker to exit, finalizes the completed work through its owning writer, releases the resources the session owns, and returns the stage to idle. A stop with partial coverage is valid, and the pending work is left for the next start.

Status reads the recorded state and the owned process and writes nothing. It starts no service and contacts no worker, so a remote stage reports the last status its run recorded. The report carries the lifecycle state, the session identity, the progress of the stage, and a measured rate and a projected remaining time when the recorded progress supports them.

> [!IMPORTANT]
> A start needs an already-provisioned copy. It starts services that are already built, never builds or pulls one, and fails when a requested service does not become healthy.

The wait for an owned worker to exit is bounded by `ADMIN_STOP_TIMEOUT_SECONDS`, and a launch is acknowledged within `ADMIN_STARTUP_ATTEMPTS` polls spaced by `ADMIN_POLL_INTERVAL_SECONDS`. All three keys are in `config/worker.toml`, and the example sets 660 seconds, 120 polls, and 0.5 seconds.

## Inference decisions

Choice 6 under Inference records one operator decision for one target course. It asks for the target's canonical group identity, then reads the target and its current decision and prints the official code, the English name, and the current decision before it asks for a decision.

| Choice | Decision |
|---|---|
| 1 | NOTHING (automatic/no override) |
| 2 | DONE (no inferred output) |
| 3 | FAILED (terminal) |
| 0 | Cancel |

Cancel, an unrecognised answer, an end of input, and an interrupt all change nothing and stop nothing. The machine command is `uv run python scripts/admin.py dispose inference TARGET_ID {nothing|done|failed}`, where `nothing` clears the decision. The read the entry performs before it asks is also a machine command, `uv run python scripts/admin.py target inference TARGET_ID`, and it prints the target's identity and current decision alone, so an operator can read a decision state without a decision to record.

> [!WARNING]
> A **done** decision completes the target course with no inferred output, and a **failed** decision leaves the cycle incomplete while it stands. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md#operator-disposition) states what each decision does to the scheduling and to the published results.

A decision write requires every stage to be idle, a verified returned or copied Working dataset, and the current schema head.

## Coverage and summaries

This entry holds the four read-only reports, and it prints one fixed line before its entries.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Catalogue summary | `uv run python scripts/admin.py summary catalogue --role <selected|working>` |
| 2 | Teaching-text/translation coverage | `uv run python scripts/admin.py coverage teaching-text --role <selected|working>` |
| 3 | Embedding coverage | `uv run python scripts/admin.py coverage embedding --role <selected|working>` |
| 4 | Inference summary | `uv run python scripts/admin.py summary inference --role <selected|working>` |

Every report choice asks `Dataset role` with **1 Selected**, **2 Working** and **0 Cancel** first. The fixed line states the scope of every report in this entry: it reads the named role, and the progress of a remote stage that has not returned is read from that stage's Status entry instead. The `coverage` and `summary` machine commands print the same line to standard error. The inference summary carries the retained coverage, the publication diagnostics and the failures, and it states the three configured inference policy values `routing_policy`, `recommendation_policy` and `finding_filter_policy` from the loaded generation settings.

A Working report fails with copy guidance when no Working dataset exists. A stage action and a Working migration name the same copy when no Working dataset exists. A Selected report fails with setup guidance when the state root holds enrollment records without a Selected pointer, and reads the configured database in bootstrap.

## Server and log reads

This entry holds five entries, and each prints the report of the read it runs.

| Choice | Entry | Asks for |
|---|---|---|
| 1 | [Server status](/docs/backend/interfaces/administration-commands.md#the-server-status-report) | Nothing |
| 2 | [Session log](/docs/backend/interfaces/administration-commands.md#the-fixed-log-reads) | `Stage (0 to cancel): `, `Session id (0 to cancel): `, the `Log source` menu and `Lines (0 to cancel): ` |
| 3 | [Embedding log](/docs/backend/interfaces/administration-commands.md#the-fixed-log-reads) | `Lines (0 to cancel): ` |
| 4 | [Usage](/docs/backend/interfaces/administration-commands.md#the-request-usage-report) | `Hours (0 to cancel): ` |
| 5 | [Command log](/docs/backend/interfaces/administration-commands.md#the-command-log-read) | Nothing |

The session log entry prints the session listing before it asks for the stage, the session, the source and the line count. An answer outside the listing, a source outside the choices of that stage and a line count that is not a positive whole number each write nothing and read nothing.

The usage entry runs one usage report and prunes the records past the retention. A cancel and an answer that is not a positive whole number each write nothing and prune nothing.

An end of input and an interrupt at any prompt write nothing and leave the whole menu with exit status 0 and 130. [Administration commands](/docs/backend/interfaces/administration-commands.md#server-status-log-reads-and-rebuild) states the commands, the report fields, the refusals and the guidance of every read.

## Building the serving artifacts

Choice 6 under Embedding builds the served dataset's serving artifact set for the site's embedding switch. The machine command is the same build, and the embedding menu and the console preparation action run it for the served dataset without asking for a second command. The four preparation stages write Working, so a stage run changes nothing the site serves and needs no build or restart. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-embedding-switch) states the files it writes, the artifact family and the transaction, and [Administration commands](/docs/backend/interfaces/administration-commands.md#the-serving-artifact-command) states what a failed build restores, including the interrupted build that no `current` names and that `--prune` collects.

```bash
uv run python scripts/admin.py serving-artifacts
```

`--dataset ID` builds an in-pipeline dataset. `--prune` is housekeeping after a successful restart. It builds nothing, changes no table or `current` target, and removes the target database's obsolete or failed builds, the other year families' builds, and owned temporary files, including temporary files inside the kept build. It retains the active family's current build, unknown names and other database namespaces.

The embedding directories the prune retains follow the resolved embedding mode, as [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-artifact-family-the-build-directory-and-the-embedding-directory) states.

On a site that serves the embedding features the build requires the target dataset and complete current embedding coverage: every desired chunk of a represented course must be a completed chunk with a compatible vector. A dataset with no current chunk builds with two empty hubs and zero counts, and a dataset that has current chunks needs at least one learning-outcomes chunk among them. An embeddings-off site builds without that coverage.

> [!IMPORTANT]
> A completed build reaches the site after the full supervisor restart that [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states, and `serving-artifacts --prune` runs after that restart succeeds. The supervisor opens the build before it forks its workers, as [Web supervisor](/docs/backend/interfaces/web-supervisor.md#startup-and-validation) describes. The artifact command replaces no running worker and restarts no unit.

## The menu entries and the console tabs

The [administration console](/docs/operations/admin-console/README.md) runs the menu entries' fixed commands, and each tab groups one part of them. The Feedback tab runs the feedback listing, attachment read and deletion, which the menu does not offer.

| Tab | Menu entries that run the same commands |
|---|---|
| [Dashboard](/docs/operations/admin-console/dashboard.md) | Server/logs choice 1, the server status report |
| [Data preparation](/docs/operations/admin-console/data-preparation.md) | The ingestion, translation and embedding stage tools, Coverage/summaries choices 1 to 3, and Embedding choice 6, the serving-artifact build |
| [Inference](/docs/operations/admin-console/inference.md) | The inference stage tool, Inference choice 6 with its target read, and Coverage/summaries choice 4 |
| [Logs](/docs/operations/admin-console/logs.md) | Server/logs choices 2 to 5, including the embedding runtime log that `logs embedding` reads |
| [Settings](/docs/operations/admin-console/settings.md) | Setup choices 1, 2, 3, 4, 5, 6, 7, 8, 9 and 11, the enrollment, the copy to Working, the role migrations, the dataset cleanup, the worker setup and preflight, the backup cleanup, the configuration editor and the two rebuild scopes |

The Settings tab holds the [Dataset roles](/docs/operations/admin-console/dataset-roles.md) panel.

The [Operations](/docs/operations/README.md#the-two-operator-surfaces) overview states how the two surfaces relate, and each tab page states the panels it shows and the actions it offers.

## What each entry writes

| Entry | Writes | Waits for work |
|---|---|---|
| Enroll/select dataset | The initial receipt and the Selected pointer | No |
| Set up example site | The absent working files, both generated database passwords, the administration account when absent, the pinned model after confirmation, the database and embedding services, the example data, the feedback application store, the built artifacts and frontends, and the chosen startup mode's units or children | No |
| Set up real empty database | One named database, the initial receipt and the Selected pointer, the serving artifacts, and the chosen startup mode's units or children | No |
| Copy dataset to Working | The copied receipt and the Working pointer | No |
| Worker setup/update | The worker checkout, its locked environment, and its pointed resources | No |
| Read-only worker preflight | Nothing | No |
| Migrate dataset | The named role's database schema | A Working migration only |
| Start and Resume | The stage state, and one detached worker launch | Returns once the launch is acknowledged |
| Pause and Stop | The stage state and the resources the session owns | Returns once the owned worker exits |
| Status | Nothing | No |
| Dataset cleanup | The named dataset's server database, retained dump, artifact namespace and, for Working, its pointer | A Working target only |
| Backup cleanup | The named backup file | No |
| Configuration | The one chosen key of the chosen file | No |
| Administration password | The account's credential file | No |
| Dispose target | The target's durable decision and the published cohort | No |
| The four reports under Coverage/summaries | Nothing | No |
| Server status | Nothing | No |
| Session log, Embedding log and Command log | Nothing | No |
| Usage | The usage file, with the retained records | No |
| Rebuild app | The built site frontend, the two recreated containers, and the restarted web unit | No |
| Rebuild admin panel | The built administration frontend, and the administration unit's queued restart | No |
| Build serving artifacts | The versioned artifact directory with its study fragments and catalogue artifact, and, on a site that serves the embedding features, its hub pair, shared stores and packed search relation, the course centroid table and the stored neighbour table | No |

## What an entry needs

| Operation | Requires before it runs |
|---|---|
| `setup datasets` | A reachable configured database |
| `self-host example` | A prepared checkout with both frontend package directories, the host tools, the native libraries, free loopback ports, disk space for the pinned model, an example database name, and a state root with no pointer or enrollment record |
| `self-host real-database` | The working files, the running database and embedding services, every stage idle, free feature and administration ports in foreground mode, and a state root with no pointer or enrollment record |
| `setup worker` | A non-detached server checkout whose origin matches the configured origin, a non-detached worker checkout whose origin matches the configured origin, and passwordless `sudo` on the worker |
| `preflight` | A non-detached server checkout whose origin matches the configured origin, the worker connection, and a non-detached worker checkout |
| `migrate selected` | A Selected dataset and the running server database service |
| `migrate working` | Every stage idle, a Working dataset, and the running server database service |
| A stage start | The stage state root, a Working dataset, and its database at this checkout's migration head |
| An ingestion start | A stage start, plus the configured source base and university root |
| A translation or inference start | A stage start, plus the worker connection, the locked environment installed on the worker, and the received worker database at the worker code's migration head |
| An embedding start | A stage start, plus the pinned model artifact file present and matching `EMBEDDING_ARTIFACT_SHA256` |
| A stage status | The configured stage state root |
| `datasets list` | Nothing, because a bootstrap state root lists no dataset and an unreachable database reports a typed unavailable probe |
| `datasets delete DATASET_ID` | A Selected dataset, any other receipt-bearing target, every stage idle for a Working target, and the running server database service |
| `backups list` | Access to the backup directory (an absent directory reports an empty listing) |
| `backups delete NAME` | A regular file from the listing, and access to it |
| `config list` | Nothing, because the listing reads no file |
| `config read FILE` | A listed regular file |
| `config set FILE KEY VALUE` | A listed regular file, a key that file carries or an environment key a settings family owns, a JSON literal of the broad type the key holds, and readable valid candidate inputs |
| `password --username USERNAME` | A nonblank username, a terminal that hides the entry, and write access to the administration state directory |
| `dispose inference ...` | Every stage idle, a verified returned or copied Working dataset, and the current schema head |
| `target inference ...` | A Working dataset and the current schema head |
| `server status` | A loaded site web unit from this checkout, `ADMIN_SITE_WEB_SERVICE_UNIT` in `config/admin_web.toml`, the Compose services of this checkout, and passwordless `sudo` for Compose |
| `logs sessions` | The four stage state roots (an absent root contributes no entry) |
| `logs commands` | Access to the administration state directory (an absent log reports an empty entry list) |
| `logs read` | A listed session of the chosen stage, the recorded worker session when one exists, and the worker connection for a worker source with a receipt |
| `logs embedding` | The Compose services of this checkout, and passwordless `sudo` for Compose |
| `usage --hours HOURS` | A positive hour count at most the configured retention, and write access to the usage file (an absent file reports an empty window) |
| `rebuild` | The prepared frontend, the two prepared container images, the site's own loaded web unit from this checkout, the manager that owns that unit with its passwordless grant when the manager is the system manager, and passwordless `sudo` for Compose |
| `rebuild-admin` | The installed administration frontend dependencies, and the loaded administration unit of this checkout named by `ADMIN_SITE_ADMIN_SERVICE_UNIT` in `config/admin_web.toml` |
| `restart-admin` | The loaded administration unit of this checkout named by `ADMIN_SITE_ADMIN_SERVICE_UNIT` in `config/admin_web.toml`, and the systemd user manager that owns it |
| `serving-artifacts` | The Selected dataset, or the named `--dataset` target. On a site that serves the embedding features it also needs complete current embedding coverage. |
| `coverage` and `summary` | The named dataset role and its database at the current schema head |

## Failures and exit status

A failed operation prints one JSON line holding the exception's class name, plus its integer return code for a checked subprocess failure, and then one fixed line of guidance. Neither line carries an input value, a failure message, or a path from the failure. The menu prints both lines in its own output and continues, and a machine command prints them to standard error.

The command returns 0 after a success, 1 after a failure, and 130 on an interrupt. A not-ready `preflight` prints its report and returns 1.

> [!NOTE]
> Fixed guidance names the next step for the failed operation. A configuration value that is missing or malformed produces the configuration guidance instead.
