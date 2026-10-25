# Setup and preflight

The setup and preflight entries prepare and maintain this copy, its worker, its containers, its configuration and its administration account.

The **Setup/preflight** entry holds the two setup operations, the read-only preflight, the guarded migration, the two cleanup entries, the configuration editor, the two rebuild scopes and the account password.

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

The preflight reads the branch and HEAD of the server checkout and of the worker checkout, checks the worker's locked environment, and reads the worker resources when that check passes. It installs nothing, and the machine command returns 1 when the locked environment or a resource is not ready.

The migration applies the migration head to the selected database as explicit maintenance. It requires every stage to be idle and the server database service to be running.

The worker setup and the preflight add one fixed notice when the server checkout's branch differs from its origin counterpart. The notice states that pushing is a separate manual step. The menu prints it after the report, and the machine command prints it to standard error.

## Cleanup of datasets and backups

Two entries delete one target the operator names, and the inference tool repeats the dataset entry as its choice 7.

**Dataset cleanup** lists the retained dataset chain and deletes one dataset. The machine commands are `uv run python scripts/admin.py datasets list` and `uv run python scripts/admin.py datasets delete DATASET_ID`.

**Backup cleanup** lists the files under `data/backups` and deletes one of them. The machine commands are `uv run python scripts/admin.py backups list` and `uv run python scripts/admin.py backups delete NAME`.

Both entries print the listing before they ask for a target, and `0` at the target prompt cancels the entry. An empty listing and a failed listing both return to the calling menu without a target prompt. An answer outside the printed listing, the selected dataset, a dataset outside the retained chain and, with the selection switch off, the dataset whose database the site serves are refused with one fixed line and delete nothing.

A target that the listing contains draws one confirmation titled with that exact target, `Delete dataset <id> (<database name>)?` or `Delete backup <name>?`, and it holds **1 Delete** and **0 Cancel**. Only the delete choice runs the deletion, and that owner's report is printed as it returns. A cancel and any other answer delete nothing and return to the calling menu. An end of input and an interrupt delete nothing, stop no running work, and leave the whole menu with exit status 0 and 130.

The two listing commands create no state. They read the receipts, the pointer, file metadata, and whether the database of a non-selected dataset without a retained dump exists. `backups list` requires access to the backup directory and reports an empty listing when that directory is absent. A dataset deletion requires a selected dataset, a target from its listing and the running server database service. A backup deletion requires a regular file from its listing and access to it. [Datasets](/docs/operations/datasets.md#manual-cleanup) states every refusal and what each deletion retains.

> [!CAUTION]
> A cleanup deletion is irreversible. The listing names each target, and the confirmation names the exact dataset or backup file that the deletion removes.

## Configuration

Choice 7 reads one configuration file and saves one key of it. The machine commands are `uv run python scripts/admin.py config list`, `uv run python scripts/admin.py config read FILE` and `uv run python scripts/admin.py config set FILE KEY VALUE`.

The entry lists the registered subsystem files in composition order with the environment file last, prints the listing, and asks for a file the listing carries. It then prints every key of the chosen file as that file holds it and asks for a key the report carries. The value prompt takes one JSON literal that matches the broad type the key holds, and the entry does not strip or echo it.

A save draws one confirmation titled `Save configuration <file> key <key>?` with **1 Save** and **0 Cancel**. The title names the file and the key and no value. Only **1 Save** runs the save, and the writer's report is printed as it returns. `0` at the file prompt or the key prompt cancels the entry, an answer outside either prompt writes nothing, and a value the owning settings family refuses prints the shared safe failure and guidance.

One save writes one key, so a file with several edits takes one save per key. The entry edits the keys the read displays, so it writes a key the chosen file already carries and appends nothing. The machine command accepts one more case: `config set` appends an absent environment alias that a settings family owns for that file as one quoted assignment that leaves every other byte as it is, and it refuses an absent subsystem-file key or an absent environment key that no settings family owns.

> [!CAUTION]
> The read prints every value of the chosen file in plain text, the environment file included.

A saved file reaches a running process when that process next builds its settings. [Configuration](/docs/backend/configuration.md#reading-and-writing-a-file) states the precedence between the files.

## The two rebuild scopes

Choice 8 rebuilds the app. Choice 10 rebuilds the administration panel. The two scopes are separate, each has its own confirmation, and neither reaches the other's process or its resources.

Choice 8 builds the site frontend, recreates the database and embedding containers, restarts the site's web server and checks its bind. The machine command is `uv run python scripts/admin.py rebuild`.

The entry asks one confirmation, `Rebuild this site's frontend, containers and web server?`, and holds **1 Rebuild** and **0 Cancel**. Only the rebuild choice runs the command. A cancel and any other answer run nothing and return to the calling menu, and an end of input and an interrupt run nothing and leave the whole menu with exit status 0 and 130.

The command runs four steps in this order, and the first failure stops it.

1. The frontend build, `npm --prefix web run build`, in the checkout. It builds from the installed dependencies.
2. The two prepared containers, `docker compose up -d --wait --force-recreate --no-build --pull never db embedding`. The step uses the prepared images, and the data volumes and databases are left as they are.
3. A restart of the site's own web unit through the manager `ADMIN_SITE_WEB_SERVICE_SCOPE` names: `systemctl --user restart` in the user manager, or `sudo -n /usr/bin/systemctl restart` in the system manager. A system-manager restart needs the exact passwordless grant the host installs for that one unit and command.
4. The bind check: the restarted process's main PID must own the configured `127.0.0.1:PORT` listener within `ADMIN_STARTUP_ATTEMPTS` polls spaced by `ADMIN_POLL_INTERVAL_SECONDS`. A listener that same process owns on an address that is not a loopback address fails at once. Listeners that another process owns on the same port belong to that process and are left alone.

The commands of the first three steps are bounded by `ADMIN_STOP_TIMEOUT_SECONDS`, and the bind wait by its poll count and interval. The report names the four steps and the verified bind, and it is the transient acknowledgment of the run. A failed step prints the shared safe failure and the rebuild guidance, and no further step runs. The rebuild leaves the checkout's Git state as it is, reaches no worker, and restarts only the site's own web unit.

The command validates the site's own loaded web unit, running from this checkout and executing this checkout's `scripts/run_web.sh`, before its first step. `ADMIN_SITE_WEB_SERVICE_UNIT` in the environment file names that unit, and `ADMIN_SITE_WEB_SERVICE_SCOPE` names the manager that owns it.

Choice 10 builds the administration frontend alone and then queues the restart of this checkout's own administration unit. The machine commands are `uv run python scripts/admin.py rebuild-admin` and `uv run python scripts/admin.py restart-admin`, and the entry runs the first and then the second.

The entry asks one confirmation, `Rebuild the admin panel? This signs all operators out.`, and holds **1 Rebuild** and **0 Cancel**. The warning states the sign-out because ending that backend process ends every session it holds in memory. Only the rebuild choice runs the sequence. A cancel and any other answer run nothing and return to the calling menu, and an end of input and an interrupt run nothing and leave the whole menu with exit status 0 and 130.

The sequence runs two commands in this order, and a failed build stops it before the restart.

1. `rebuild-admin` builds the administration frontend with `npm --prefix admin-web run build`, from the installed dependencies. It recreates no container, opens no database and reaches no worker.
2. `restart-admin` queues one non-blocking restart of this checkout's own administration unit and returns once that request is admitted.

Each command is bounded by `ADMIN_STOP_TIMEOUT_SECONDS`. The report the entry prints is the restart command's own acknowledgment that the restart is queued. It states no observed restart and no verified bind, so the console's own restart and the following sign-in are what show the outcome.

Both commands validate before they act that the administration unit named by `ADMIN_SITE_ADMIN_SERVICE_UNIT` in the environment file is loaded, runs from this checkout and executes this checkout's `scripts/run_admin_web.sh`. A unit from another directory or with another launcher is refused, and a refused build restarts nothing. [Command line](/docs/backend/interfaces/command-line.md#the-rebuild-commands) states each command's report and failure presentation.

## The administration password

Choice 9 stores the site's one administration account. The machine command is `uv run python scripts/admin.py password --username USERNAME`.

The entry asks `Username (0 to cancel): ` through the ordinary menu input, and `0` cancels it. It then asks for the password twice at the hidden prompts `Password: ` and `Repeat password: `, which the command itself owns, so no password is read from or written to the menu's own streams. Two different entries, a blank entry, an end of input and an interrupt each store nothing, and an end of input and an interrupt leave the whole menu with exit status 0 and 130.

```bash
uv run python scripts/admin.py password --username OPERATOR
```

The command prints one acknowledgment line and stores the account's username and an argon2id hash in `data/admin-web/password`. [Command line](/docs/backend/interfaces/command-line.md#the-administration-password) states the command, the file, and the failure presentation.

> [!IMPORTANT]
> The entry is a terminal provisioning step, and the account's own site authenticates with it. Each site holds its own account, so each deployment sets its own username and password.
