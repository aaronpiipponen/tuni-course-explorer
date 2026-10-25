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

Choice 1 opens the ten setup and preflight entries.

| Choice | Entry | Asks for |
|---|---|---|
| 1 | Enroll/select dataset | Nothing |
| 2 | Worker setup/update | `Origin branch [<server branch>]:` when the server checkout is not on `main` |
| 3 | Read-only worker preflight | Nothing |
| 4 | Migrate selected dataset | Nothing |
| 5 | Dataset cleanup | `Dataset id: `, then `Delete dataset <id> (<database name>)?` |
| 6 | Backup cleanup | `Backup file name: `, then `Delete backup <name>?` |
| 7 | Configuration | `Configuration file (0 to cancel): `, `Configuration key (0 to cancel): `, `JSON value: `, then `Save configuration <file> key <key>?` |
| 8 | Rebuild app | `Rebuild this site's frontend, containers and web server?` |
| 9 | Administration password | `Username (0 to cancel): `, then the command's hidden `Password: ` and `Repeat password: ` prompts |
| 10 | Rebuild admin panel | `Rebuild the admin panel? This signs all operators out.` |

Except for the administration rebuild, each entry prints the report of the command it runs. [Setup and preflight](/docs/operations/setup-and-preflight.md) states what each entry does, the machine command behind it, and its prompts and confirmations.

## The stage tools

The four stage tools share five entries. The inference tool adds two, and the embedding tool adds one.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Start | `uv run python scripts/admin.py <stage> start` |
| 2 | Pause | `uv run python scripts/admin.py <stage> pause` |
| 3 | Resume | `uv run python scripts/admin.py <stage> resume` |
| 4 | Status | `uv run python scripts/admin.py <stage> status` |
| 5 | Stop | `uv run python scripts/admin.py <stage> stop` |
| 0 | Back | Returns to the main menu |

The inference tool inserts **6 Dispose target** and **7 Dataset cleanup** before **0 Back**, and the embedding tool inserts **6 Write hubs** there.

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

A decision write requires every stage to be idle, a verified returned selected dataset, and the current schema head.

## Coverage and summaries

This entry holds the four read-only reports, and it prints one fixed line before its entries.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Catalogue summary | `uv run python scripts/admin.py summary catalogue` |
| 2 | Teaching-text/translation coverage | `uv run python scripts/admin.py coverage teaching-text` |
| 3 | Embedding coverage | `uv run python scripts/admin.py coverage embedding` |
| 4 | Inference summary | `uv run python scripts/admin.py summary inference` |

The fixed line states the scope of every report in this entry: they read the selected dataset, and the progress of a remote stage that has not returned is read from that stage's Status entry instead. The `coverage` and `summary` machine commands print the same line to standard error. The inference summary carries the retained coverage, the publication diagnostics and the failures, and it states the three configured inference policy values `routing_policy`, `recommendation_policy` and `finding_filter_policy` from the loaded generation settings.

The reports require the selected-dataset switch `SELECTED_DATASET_ENABLED` in `config/database.toml`, so they fail with fixed guidance when the copy reads its configured database alone.

## Server and log reads

This entry holds five entries, and each prints the report of the read it runs.

| Choice | Entry | Asks for |
|---|---|---|
| 1 | [Server status](/docs/backend/interfaces/command-line.md#the-server-status-report) | Nothing |
| 2 | [Session log](/docs/backend/interfaces/command-line.md#the-fixed-log-reads) | `Stage (0 to cancel): `, `Session id (0 to cancel): `, the `Log source` menu and `Lines (0 to cancel): ` |
| 3 | [Embedding log](/docs/backend/interfaces/command-line.md#the-fixed-log-reads) | `Lines (0 to cancel): ` |
| 4 | [Usage](/docs/backend/interfaces/command-line.md#the-request-usage-report) | `Hours (0 to cancel): ` |
| 5 | [Command log](/docs/backend/interfaces/command-line.md#the-command-log-read) | Nothing |

The session log entry prints the session listing before it asks for the stage, the session, the source and the line count. An answer outside the listing, a source outside the choices of that stage and a line count that is not a positive whole number each write nothing and read nothing.

The usage entry runs one usage report and prunes the records past the retention. A cancel and an answer that is not a positive whole number each write nothing and prune nothing.

An end of input and an interrupt at any prompt write nothing and leave the whole menu with exit status 0 and 130. [Command line](/docs/backend/interfaces/command-line.md#server-status-log-reads-and-rebuild) states the commands, the report fields, the refusals and the guidance of every read.

## Writing the hubs

Choice 6 under Embedding computes both embedding hub means from the current chunk vectors of the selected dataset and writes the two files that the hub keys in `config/search.toml` name. The machine command is the same write.

```bash
uv run python scripts/admin.py hubs
```

Both means are computed before the first file is written, so incomplete coverage or a computation failure stops the write before any file is updated. The two hubs are then staged as temporary files beside their destinations, and the staged files replace their destinations in sequence. A failure during that replacement can leave the two destinations in different states, with the first file updated and the second holding its earlier content, and removing the remaining temporary files does not undo the first replacement. The write requires the selected dataset and complete current embedding coverage: every desired chunk of a represented course must be a completed chunk with a compatible vector, and at least one learning-outcomes chunk must exist.

> [!IMPORTANT]
> A web server whose site serves embedding features reads both hub files when its process starts and holds those values while it runs. Restart the web server after writing the hubs so it reads the files again.

## The menu entries and the console tabs

The [administration console](/docs/operations/admin-console/README.md) runs the same fixed commands as the menu entries, and each tab groups one part of them.

| Tab | Menu entries that run the same commands |
|---|---|
| [Dashboard](/docs/operations/admin-console/dashboard.md) | Server/logs choice 1, the server status report |
| [Data preparation](/docs/operations/admin-console/data-preparation.md) | The ingestion, translation and embedding stage tools, Coverage/summaries choices 1 to 3, and Embedding choice 6, the hub write |
| [Inference](/docs/operations/admin-console/inference.md) | The inference stage tool, Inference choice 6 with its target read, Coverage/summaries choice 4, and Inference choice 7, the dataset cleanup |
| [Logs](/docs/operations/admin-console/logs.md) | Server/logs choices 2 to 5, including the embedding runtime log that `logs embedding` reads |
| [Settings](/docs/operations/admin-console/settings.md) | Setup choices 1, 2, 3, 4, 6, 7, 8 and 10 |

The [Operations](/docs/operations/README.md#the-two-operator-surfaces) overview states how the two surfaces relate, and each tab page states the panels it shows and the actions it offers.

## What each entry writes

| Entry | Writes | Waits for work |
|---|---|---|
| Enroll/select dataset | The dataset receipt and the selected-dataset pointer | No |
| Worker setup/update | The worker checkout, its locked environment, and its pointed resources | No |
| Read-only worker preflight | Nothing | No |
| Migrate selected dataset | The selected database schema | No |
| Start and Resume | The stage state, and one detached worker launch | Returns once the launch is acknowledged |
| Pause and Stop | The stage state and the resources the session owns | Returns once the owned worker exits |
| Status | Nothing | No |
| Dataset cleanup | The named dataset's server database and its retained dump | No |
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
| Write hubs | The two hub files | No |

## What an entry needs

| Operation | Requires before it runs |
|---|---|
| `setup datasets` | A reachable configured database |
| `setup worker` | A non-detached server checkout whose origin matches the configured origin, a non-detached worker checkout whose origin matches the configured origin, and passwordless `sudo` on the worker |
| `preflight` | A non-detached server checkout whose origin matches the configured origin, the worker connection, and a non-detached worker checkout |
| `migrate datasets` | Every stage idle, a selected dataset, and the running server database service |
| A stage start | The stage state root, the selected dataset when `SELECTED_DATASET_ENABLED` is true, and a database at this checkout's migration head |
| An ingestion start | A stage start, plus the configured source base and university root |
| A translation or inference start | A stage start, plus the worker connection, the locked environment installed on the worker, and the received worker database at the worker code's migration head |
| An embedding start | A stage start, plus the pinned model artifact file present and matching `EMBEDDING_ARTIFACT_SHA256` |
| A stage status | The configured stage state root |
| `datasets list` | A selected dataset, and the running database service for a non-selected dataset without a retained dump |
| `datasets delete DATASET_ID` | A selected dataset, a non-selected target from the listing that is not the database the site serves while the selection switch is off, and the running server database service |
| `backups list` | Access to the backup directory (an absent directory reports an empty listing) |
| `backups delete NAME` | A regular file from the listing, and access to it |
| `config list` | Nothing, because the listing reads no file |
| `config read FILE` | A listed regular file |
| `config set FILE KEY VALUE` | A listed regular file, a key that file carries or an environment key a settings family owns, a JSON literal of the broad type the key holds, and readable valid candidate inputs |
| `password --username USERNAME` | A nonblank username, a terminal that hides the entry, and write access to the administration state directory |
| `dispose inference ...` | Every stage idle, a verified returned selected dataset, and the current schema head |
| `target inference ...` | The selected-dataset switch `SELECTED_DATASET_ENABLED` enabled, a selected dataset, and the current schema head |
| `server status` | A loaded site web unit from this checkout, `ADMIN_SITE_WEB_SERVICE_UNIT` in the environment file, the Compose services of this checkout, and passwordless `sudo` for Compose |
| `logs sessions` | The four stage state roots (an absent root contributes no entry) |
| `logs commands` | Access to the administration state directory (an absent log reports an empty entry list) |
| `logs read` | A listed session of the chosen stage, the recorded worker session when one exists, and the worker connection for a worker source with a receipt |
| `logs embedding` | The Compose services of this checkout, and passwordless `sudo` for Compose |
| `usage --hours HOURS` | A positive hour count at most the configured retention, and write access to the usage file (an absent file reports an empty window) |
| `rebuild` | The prepared frontend, the two prepared container images, the site's own loaded web unit from this checkout, the manager that owns that unit with its passwordless grant when the manager is the system manager, and passwordless `sudo` for Compose |
| `rebuild-admin` | The installed administration frontend dependencies, and the loaded administration unit of this checkout named by `ADMIN_SITE_ADMIN_SERVICE_UNIT` |
| `restart-admin` | The loaded administration unit of this checkout named by `ADMIN_SITE_ADMIN_SERVICE_UNIT`, and the systemd user manager that owns it |
| `hubs` | The selected dataset with complete current embedding coverage |
| `coverage` and `summary` | The selected-dataset switch `SELECTED_DATASET_ENABLED` enabled |

## Failures and exit status

A failed operation prints one JSON line holding the exception's class name, plus its integer return code for a checked subprocess failure, and then one fixed line of guidance. Neither line carries an input value, a failure message, or a path from the failure. The menu prints both lines in its own output and continues, and a machine command prints them to standard error.

The command returns 0 after a success, 1 after a failure, and 130 on an interrupt. A not-ready `preflight` prints its report and returns 1.

> [!NOTE]
> Fixed guidance names the next step for the failed operation. A configuration value that is missing or malformed produces the configuration guidance instead.
