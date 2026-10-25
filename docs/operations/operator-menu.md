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

This entry holds the two setup operations, the read-only preflight, the guarded migration, the two cleanup entries, the configuration editor, the two rebuild scopes and the account password.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Enroll/select dataset | `uv run python scripts/admin.py setup datasets` |
| 2 | Worker setup/update | `uv run python scripts/admin.py setup worker` |
| 3 | Read-only worker preflight | `uv run python scripts/admin.py preflight` |
| 4 | Migrate selected dataset | `uv run python scripts/admin.py migrate datasets` |
| 5 | Dataset cleanup | `uv run python scripts/admin.py datasets list` and `datasets delete DATASET_ID` |
| 6 | Backup cleanup | `uv run python scripts/admin.py backups list` and `backups delete NAME` |
| 7 | Configuration | `uv run python scripts/admin.py config list`, `config read FILE` and `config set FILE KEY VALUE` |
| 8 | Rebuild app | `uv run python scripts/admin.py rebuild` |
| 9 | Administration password | `uv run python scripts/admin.py password --username USERNAME` |
| 10 | Rebuild admin panel | `uv run python scripts/admin.py rebuild-admin` and `restart-admin` |

The dataset enrollment starts the server database service, migrates the configured database to this checkout's migration head and enrolls it as the initial dataset. An already-enrolled dataset is reused and returned as it is.

The worker setup fast-forwards the worker checkout to one origin branch, installs its locked environment, and prepares its pointed resources. The menu reads the server checkout's branch first and asks for the origin branch only when that branch is not `main`. The question shows the server branch as its default, and an empty answer accepts it. The machine command sets the same branch with `--branch BRANCH`, and `--code-only` updates the code and its locked environment without preparing the pointed resources.

The preflight reads the prepared code and the worker resources and installs nothing. It is the read-only check of the prepared worker, and the machine command returns 1 when the resources are not ready.

The migration applies the migration head to the selected database as explicit maintenance. It requires every stage to be idle and the server database service to be running.

The worker setup and the preflight add one fixed notice when the server checkout's branch differs from its origin counterpart. The notice states that pushing is a separate manual step. The menu prints it after the report, and the machine command prints it to standard error.

### Cleanup of datasets and backups

Two entries delete one target the operator names, and the inference tool repeats the dataset entry as its choice 7.

**Dataset cleanup** lists the retained dataset chain and deletes one dataset. The machine commands are `uv run python scripts/admin.py datasets list` and `uv run python scripts/admin.py datasets delete DATASET_ID`.

**Backup cleanup** lists the files under `data/backups` and deletes one of them. The machine commands are `uv run python scripts/admin.py backups list` and `uv run python scripts/admin.py backups delete NAME`.

Both entries print the listing before they ask for a target, and `0` at the target prompt cancels the entry. An empty listing and a failed listing both return to the calling menu without a target prompt. An answer outside the printed listing, the selected dataset, a dataset outside the retained chain and, with the selection switch off, the dataset whose database the site serves are refused with one fixed line and delete nothing.

A target that the listing contains draws one confirmation titled with that exact target, `Delete dataset <id> (<database name>)?` or `Delete backup <name>?`, and it holds **1 Delete** and **0 Cancel**. Only the delete choice runs the deletion, and that owner's report is printed as it returns. A cancel and any other answer delete nothing and return to the calling menu. An end of input and an interrupt delete nothing, stop no running work, and leave the whole menu with exit status 0 and 130.

The two listing commands create no state: they read the receipts, the pointer and file metadata. `backups list` requires access to the backup directory and reports an empty listing when that directory is absent. A dataset deletion requires a selected dataset, a target from its listing and the running server database service. A backup deletion requires a regular file from its listing and access to it. [Datasets](/docs/operations/datasets.md#manual-cleanup) states every refusal and what each deletion keeps.

> [!CAUTION]
> A cleanup deletion is irreversible, and the confirmation names the exact dataset or backup file. Read the listing and name the one target to remove.

### Configuration

Choice 7 reads one configuration file and saves one key of it. The machine commands are `uv run python scripts/admin.py config list`, `uv run python scripts/admin.py config read FILE` and `uv run python scripts/admin.py config set FILE KEY VALUE`.

The entry lists the registered subsystem files in composition order with the environment file last, prints the listing, and asks for a file the listing carries. It then prints every key of the chosen file as that file holds it and asks for a key the report carries. The value prompt takes one JSON literal that matches the broad type the key holds, and the entry does not strip or echo it.

A save draws one confirmation titled `Save configuration <file> key <key>?` with **1 Save** and **0 Cancel**. The title names the file and the key and no value. Only **1 Save** runs the save, and the writer's report is printed as it returns. `0` at the file prompt or the key prompt cancels the entry, an answer outside either prompt writes nothing, and a value the owning settings family refuses prints the shared safe failure and guidance. One save writes one key, so a file with several edits takes one save per key. The entry edits the keys the read displays, so it writes a key the chosen file already carries and appends nothing. The machine command accepts one more case: `config set` appends an absent environment alias that a settings family owns for that file as one quoted assignment that leaves every other byte as it is, and it refuses an absent subsystem-file key or an absent environment key that no settings family owns.

> [!CAUTION]
> The read prints every value of the chosen file in plain text, the environment file included.

A saved file reaches a running process when that process next builds its settings, which the configuration pages state with the precedence between the files.

### The two rebuild scopes

Choice 8 rebuilds the app. Choice 10 rebuilds the administration panel. The two scopes are separate, each has its own confirmation, and neither reaches the other's process or its resources.

Choice 8 builds the site frontend, recreates the database and embedding containers, restarts the site's web server and checks its bind. The machine command is `uv run python scripts/admin.py rebuild`.

The entry asks one confirmation, `Rebuild this site's frontend, containers and web server?`, and holds **1 Rebuild** and **0 Cancel**. Only the rebuild choice runs the command. A cancel and any other answer run nothing and return to the calling menu, and an end of input and an interrupt run nothing and leave the whole menu with exit status 0 and 130.

The command runs four steps in this order, and the first failure stops it.

1. The frontend build, `npm --prefix web run build`, in the checkout. It builds from the installed dependencies.
2. The two prepared containers, `docker compose up -d --wait --force-recreate --no-build --pull never db embedding`. The step uses the prepared images, and the data volumes and databases are left as they are.
3. A restart of the site's own web unit through the manager `ADMIN_SITE_WEB_SERVICE_SCOPE` names: `systemctl --user restart` in the user manager, or `sudo -n /usr/bin/systemctl restart` in the system manager. A system-manager restart needs the exact passwordless grant the host installs for that one unit and command.
4. The bind check: the restarted process's main PID must own the configured `127.0.0.1:PORT` listener within `ADMIN_STARTUP_ATTEMPTS` polls spaced by `ADMIN_POLL_INTERVAL_SECONDS`. A listener that same process owns on an address that is not a loopback address fails at once. Listeners that another process owns on the same port belong to that process and are left alone.

Each step is bounded by `ADMIN_STOP_TIMEOUT_SECONDS`. The report names the four steps and the verified bind, and it is the transient acknowledgment of the run. A failed step prints the shared safe failure and the rebuild guidance, and no further step runs. The rebuild leaves the checkout's Git state as it is, reaches no worker, and restarts only the site's own web unit.

The command validates the site's own loaded web unit, running from this checkout and executing this checkout's `scripts/run_web.sh`, before its first step. `ADMIN_SITE_WEB_SERVICE_UNIT` in the environment file names that unit, and `ADMIN_SITE_WEB_SERVICE_SCOPE` names the manager that owns it.

Choice 10 builds the administration frontend alone and then queues the restart of this checkout's own administration unit. The machine commands are `uv run python scripts/admin.py rebuild-admin` and `uv run python scripts/admin.py restart-admin`, and the entry runs the first and then the second.

The entry asks one confirmation, `Rebuild the admin panel? This signs all operators out.`, and holds **1 Rebuild** and **0 Cancel**. The warning states the sign-out because ending that backend process ends every session it holds in memory. Only the rebuild choice runs the sequence. A cancel and any other answer run nothing and return to the calling menu, and an end of input and an interrupt run nothing and leave the whole menu with exit status 0 and 130.

The sequence runs two commands in this order, and a failed build stops it before the restart.

1. `rebuild-admin` builds the administration frontend with `npm --prefix admin-web run build`, from the installed dependencies. It recreates no container, opens no database and reaches no worker.
2. `restart-admin` queues one non-blocking restart of this checkout's own administration unit and returns once that request is admitted.

Each command is bounded by `ADMIN_STOP_TIMEOUT_SECONDS`. The report the entry prints is the restart command's own acknowledgment that the restart is queued. It states no observed restart and no verified bind, so the console's own restart and the following sign-in are what show the outcome.

Both commands validate before they act that the administration unit named by `ADMIN_SITE_ADMIN_SERVICE_UNIT` in the environment file is loaded, runs from this checkout and executes this checkout's `scripts/run_admin_web.sh`. A unit from another directory or with another launcher is refused, and a refused build restarts nothing.

### The administration password

Choice 9 stores the site's one administration account. The machine command is `uv run python scripts/admin.py password --username USERNAME`.

The entry asks `Username (0 to cancel): ` through the ordinary menu input, and `0` cancels it. It then asks for the password twice at the hidden prompts `Password: ` and `Repeat password: `, which the command itself owns, so no password is read from or written to the menu's own streams. Two different entries, a blank entry, an end of input and an interrupt each store nothing, and an end of input and an interrupt leave the whole menu with exit status 0 and 130.

```bash
uv run python scripts/admin.py password --username OPERATOR
```

The command prints one acknowledgment line and stores the account's username and an argon2id hash in `data/admin-web/password`. It neither deletes the site's lock nor resets the failed-attempt count, and the value it writes is not configuration: the site's credential state, its failed-attempt count, its lock and its command log are operational state under `data/admin-web/`. [Command line](/docs/backend/interfaces/command-line.md#the-administration-password) states the command, the file, and the failure presentation.

> [!IMPORTANT]
> The entry is a terminal provisioning step, and the account's own site authenticates with it. Each site holds its own account, so each deployment sets its own username and password.

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

This entry holds the server status report, the fixed log reads and the usage and command-log reports.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Server status | `uv run python scripts/admin.py server status` |
| 2 | Session log | `uv run python scripts/admin.py logs sessions` and `logs read STAGE SESSION_ID SOURCE --lines N` |
| 3 | Embedding log | `uv run python scripts/admin.py logs embedding --lines N` |
| 4 | Usage | `uv run python scripts/admin.py usage --hours HOURS` |
| 5 | Command log | `uv run python scripts/admin.py logs commands` |

### The server status report

`server status` prints one read-only report of the server this command runs on. It contacts no worker and retains nothing. The report holds six members.

| Member | Facts |
|---|---|
| `website` | The site's own web unit: its measured systemd state, its main PID, its start time and uptime, the configured loopback bind and process count, the checkout-relative entry point, and the branch and revision of the checkout this command reads |
| `host` | The host's measured uptime, CPU usage sampled over a short interval, total and used memory, the filesystem total and free bytes, and the total bytes of `data`, `models` and `data/backups` |
| `database` | The database service's container state, image and health, the resolved database name, the database's own migration revision beside this checkout's expected head, its size, its connection count, and the container's shared-memory size |
| `embedding` | The embedding service's container state, image and health, and the configured model, artifact path, bind, context size, thread count, pooling and normalization |
| `serving` | Whether the selected-dataset switch resolves a dataset, and the selected receipt's id, kind, predecessor, pointer and recorded database head |
| `hubs` | Both embedding hub files: their alias, their repository-relative path, their modification time, and whether each is newer than the measured web start |

An optional fact the report finds none of is `null`: a service the Compose listing does not contain is reported as `absent`, a hub reference that names no file has no modification time, and every receipt fact is `null` while the selected-dataset switch resolves no dataset. A read, parse or stat failure fails the whole command rather than becoming an unknown fact, and a hub reference that names something other than a regular file fails the command.

The `serving` member records the database head the selected receipt's verification carries, which is neither the live database's own revision nor this checkout's expected head.

The database size, connection count and revision are reported while the database container runs, and a running container whose read fails fails the whole command rather than reporting a guessed value. The web unit must be loaded, must run from this checkout, and must execute this checkout's `scripts/run_web.sh`, so the report never describes another site's service. The branch and the revision are the identity of the checkout this command reads, and the hub comparison is a restart hint rather than proof of the served process's values.

The configured bind and process count are the values `WEB_HOST`, `WEB_PORT` and `WEB_WORKERS` set, and the report labels them as configured facts.

### The fixed log reads

`logs sessions` lists the sessions the four stage roots hold, newest first, with each session's stage, identity and receipt time. It reads the recorded receipts and creates nothing. Only a genuinely absent stage root contributes no entry, and a stage root behind a redirect is refused rather than reported as an empty listing.

`logs read STAGE SESSION_ID SOURCE --lines N` prints the last `N` lines of one fixed source of one listed session. `--lines` is required, and its value is a positive whole number.

| Source | What it reads |
|---|---|
| `server-stdout` | The stage's `runner.out` beside its session receipt |
| `server-stderr` | The stage's `runner.err` beside its session receipt |
| `keepalive` | The session's `keepalive.log` in the shared administrative session directory |
| `worker-runner` | The session's `runner.log` on the worker, read on demand |
| `worker-runtime` | The session's `runtime.log` on the worker, read on demand |

`server-stdout` and `server-stderr` belong to every stage, and the other three belong to the translation and inference stages alone. The read resolves the session receipt of the chosen stage first, and a session identity that stage never recorded is refused. Every directory from the filesystem root through the session directory must be a real directory, so a symlink or another redirect anywhere in that unresolved chain is refused before a log path is read.

A session that failed before it prepared its worker resources has no shared worker receipt, so a keepalive or worker read of that listed lifecycle-only session reports the log unavailable without loading worker settings or opening the transport. A malformed, symlinked or non-regular receipt is refused.

The remaining outcomes are:

- An absent log is reported as unavailable with no text.
- A log file that holds no lines is reported as available with empty text.
- A log that is a symlink or not a regular file is refused.

The stage, the source and the session identity select one fixed file, so no call reads an arbitrary path or runs an arbitrary command.

The `keepalive.log` of a session exists while that session's keepalive runs, and a stop removes it. The inference stage launches its server process with its output sent to the null device, so its two runner streams are reported as unavailable.

The two worker sources read over the same SSH/WSL transport the stages use, on demand. The read walks the derived path's ancestors on the worker and refuses a symlink or an unsearchable directory, and a path the worker does not hold at all is the one reported absence. A read failure, an unreachable worker and a timeout print the shared safe failure and the log guidance, and no captured log text reaches that line. The worker read installs nothing, prepares nothing and retries nothing.

`logs embedding --lines N` prints the last `N` lines of the embedding service's own container log. The read does not start the service, and a failed Compose command prints the shared safe failure and the log guidance.

The menu entry prints the session listing, then asks for a stage and a session the listing holds, a source from the fixed choices of that stage, and a positive line count. An answer outside the listing, a source outside the choices and a line count that is not a positive whole number each write nothing and read nothing. An end of input and an interrupt write nothing and leave the whole menu with exit status 0 and 130.

### The command-log read

Choice 5 prints the retained entries of the sole administration command log, oldest first, and runs no other operation. Each entry holds its time, its fixed command label, its exit code, its elapsed duration, its outcome token and its one safe failure line when it has one. The `failed-login` and `lock` outcomes are the authentication events of the same file, and no entry holds captured output, a password, a key value or a free-form argument.

An entry records one explicit command, one failed automatic read, or one of the sign-in, failed sign-in and lock events. A console read that the panel loop ran automatically and that succeeded records no entry, so the polls of an open administration console do not fill the record.

The read creates no file, so an absent command log prints an empty entry list, and it rewrites no entry. [Administration backend](/docs/backend/interfaces/admin-backend.md#the-command-log) states the owner, the bound and the record shape.

### The usage report

`usage --hours HOURS` prints one report of the recorded web requests and prunes the records past the configured retention. The window is whole hours back from the current rounded UTC hour inclusive, and `--hours` is required and takes an integer.

The report holds the window bounds, the request count, the mean duration and one row per route with that route's request count and mean duration, sorted by route. A window with no recorded request reports zero requests, no mean duration and no route rows, and an absent usage file is that same report and creates no file.

`USAGE_RETENTION_DAYS` of `config/web.toml` bounds the window and the file: a count that is not positive or is longer than the retention in hours fails the command before it opens the file, and the same read keeps every record from the current hour back the retention in days and drops the older ones. A malformed line fails the command without rewriting the file, and no line's content reaches the failure line.

[Web server](/docs/backend/interfaces/web-server.md#the-request-usage-record) describes the records the front router appends, and [Command line](/docs/backend/interfaces/command-line.md#the-request-usage-report) states the window and the report fields.

The menu entry asks `Hours (0 to cancel): ` and runs the same command once. A cancel, an end of input, an interrupt and an answer that is not a positive whole number each write nothing and prune nothing.

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
| `setup datasets` | A reachable configured database and a checkout with a readable HEAD for first enrollment |
| `setup worker` | The configured origin matching the server checkout origin, a clean worker checkout on a branch, and passwordless `sudo` on the worker |
| `preflight` | The prepared checkout and the worker connection |
| `migrate datasets` | Every stage idle, a selected dataset, and the running server database service |
| A stage start | The stage state root, the selected dataset when `SELECTED_DATASET_ENABLED` is true, and a database at this checkout's migration head |
| An ingestion start | A stage start, plus the configured source base and university root |
| A translation or inference start | A stage start, plus the worker connection and the prepared worker checkout with its locked environment |
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
| `target inference ...` | Every stage idle, a verified returned selected dataset, and the current schema head |
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
