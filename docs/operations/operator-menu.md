# Operator menu

The operator menu is the numbered surface of the administration command, and every entry delegates once to one owner and prints that owner's report.

## Starting the menu

```bash
uv run python scripts/admin.py
uv run python scripts/admin.py menu
```

Both forms start the numbered menu, and the two are the same command. The menu command takes no other argument.

The menu runs until one of three things happens. Choosing **0 Exit** returns 0, an end of input returns 0, and an interrupt returns 130. None of the three stops running work, and none of them starts one. A failed operation prints its failure and the menu continues running.

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
| 0 | Exit | Ends the menu |

Every other menu draws **0 Back**, which returns to the main menu without starting anything. The **Dispose target** menu draws **0 Cancel** in its place.

## Setup and preflight

This entry holds the two setup operations, the read-only preflight, and the guarded migration.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Enroll/select dataset | `uv run python scripts/admin.py setup datasets` |
| 2 | Worker setup/update | `uv run python scripts/admin.py setup worker` |
| 3 | Read-only worker preflight | `uv run python scripts/admin.py preflight` |
| 4 | Migrate selected dataset | `uv run python scripts/admin.py migrate datasets` |

The dataset enrollment starts the server database service, migrates the configured database to this checkout's migration head and enrolls it as the initial dataset. An already-enrolled dataset is reused and returned as it is.

The worker setup fast-forwards the worker checkout to one origin branch, installs its locked environment, and prepares its pointed resources. The menu reads the server checkout's branch first and asks for the origin branch only when that branch is not `main`. The question shows the server branch as its default, and an empty answer accepts it. The machine command sets the same branch with `--branch BRANCH`, and `--code-only` updates the code and its locked environment without preparing the pointed resources.

The preflight reads the prepared code and the worker resources and installs nothing. It is the read-only check of the prepared worker, and the machine command returns 1 when the resources are not ready.

The migration applies the migration head to the selected database as explicit maintenance. It requires every stage to be idle and the server database service to be running.

The worker setup and the preflight add one fixed notice when the server checkout's branch differs from its origin counterpart. The notice states that pushing is a separate manual step. The menu prints it after the report, and the machine command prints it to standard error.

## The stage tools

The four stage tools share five entries, and two of them add one more.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Start | `uv run python scripts/admin.py <stage> start` |
| 2 | Pause | `uv run python scripts/admin.py <stage> pause` |
| 3 | Resume | `uv run python scripts/admin.py <stage> resume` |
| 4 | Status | `uv run python scripts/admin.py <stage> status` |
| 5 | Stop | `uv run python scripts/admin.py <stage> stop` |
| 0 | Back | Returns to the main menu |

The inference tool inserts **6 Dispose target** before **0 Back**, and the embedding tool inserts **6 Write hubs** there.

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

Cancel, an unrecognised answer, an end of input, and an interrupt all change nothing and stop nothing. The machine command is `uv run python scripts/admin.py dispose inference TARGET_ID {nothing|done|failed}`, where `nothing` clears the decision.

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

The fixed line states the scope of every report in this entry: they read the selected dataset, and the progress of a remote stage that has not returned is read from that stage's Status entry instead. The `coverage` and `summary` machine commands print the same line to standard error.

The reports require the selected-dataset switch `SELECTED_DATASET_ENABLED` in `config/database.toml`, so they fail with fixed guidance when the copy reads its configured database alone.

## Writing the hubs

Choice 6 under Embedding computes both embedding hub means from the current chunk vectors of the selected dataset and writes the two files that the hub keys in `config/search.toml` name. The machine command is the same write.

```bash
uv run python scripts/admin.py hubs
```

Both means are computed before the first file is written, so incomplete coverage or a computation failure stops the write before any file is updated. The two files are published as one write: each hub is written to a temporary file beside its destination, the staged files then replace both destinations, and a failed write deletes every temporary file, so both files change together or not at all. The write requires the selected dataset and complete current embedding coverage: every desired chunk of a represented course must be a completed chunk with a compatible vector, and at least one learning-outcomes chunk must exist.

> [!IMPORTANT]
> A web server reads both hub files when its process starts and holds those values while it runs. Restart the web server after writing the hubs so it reads the files again.

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
| Dispose target | The target's durable decision and the published cohort | No |
| The four reports under Coverage/summaries | Nothing | No |
| Write hubs | The two hub files | No |

## What an entry needs

| Operation | Requires before it runs |
|---|---|
| `setup datasets` | A reachable configured database and a checkout on a branch |
| `setup worker` | The configured origin matching the server checkout origin, a clean worker checkout on a branch, and passwordless `sudo` on the worker |
| `preflight` | The prepared checkout and the worker connection |
| `migrate datasets` | Every stage idle, a selected dataset, and the running server database service |
| A stage start | The stage state root, a database at this checkout's migration head, and, for ingestion, the configured source base and university root |
| An embedding start | The pinned model artifact file present and matching `EMBEDDING_ARTIFACT_SHA256` |
| A stage status | The configured stage state root |
| `dispose inference ...` | Every stage idle, a verified returned selected dataset, and the current schema head |
| `hubs` | The selected dataset with complete current embedding coverage |
| `coverage` and `summary` | The selected-dataset switch `SELECTED_DATASET_ENABLED` enabled |

## Failures and exit status

A failed operation prints one JSON line holding the exception's class name, plus its integer return code for a checked subprocess failure, and then one fixed line of guidance. Neither line carries an input value, a failure message, or a path from the failure. The menu prints both lines in its own output and continues, and a machine command prints them to standard error.

The command returns 0 after a success, 1 after a failure, and 130 on an interrupt. A not-ready `preflight` prints its report and returns 1.

> [!NOTE]
> Fixed guidance names the next step for the failed operation. A configuration value that is missing or malformed produces the configuration guidance instead.
