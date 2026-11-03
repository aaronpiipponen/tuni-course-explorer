# Setup and preflight

The setup and preflight entries prepare and maintain this copy, its worker, its containers, its configuration and its administration account.

The **Setup/preflight** entry holds the setup operations, the copy to Working, the read-only preflight, the role migration, the two cleanup entries, the configuration editor, the two rebuild scopes and the account password.

| Choice | Entry | Machine command |
|---|---|---|
| 1 | Enroll/select dataset | `uv run python scripts/admin.py setup datasets` |
| 2 | Copy dataset to Working | `uv run python scripts/admin.py datasets copy-to-working SOURCE_DATASET_ID` |
| 3 | Worker setup/update | `uv run python scripts/admin.py setup worker` |
| 4 | Read-only worker preflight | `uv run python scripts/admin.py preflight` |
| 5 | Migrate dataset | `uv run python scripts/admin.py migrate selected` or `migrate working` |
| 6 | Dataset cleanup | `uv run python scripts/admin.py datasets list` and `datasets delete DATASET_ID [--confirm-working]` |
| 7 | Backup cleanup | `uv run python scripts/admin.py backups list` and `backups delete NAME` |
| 8 | Configuration | `uv run python scripts/admin.py config list`, `config read FILE` and `config set FILE KEY VALUE` |
| 9 | Rebuild app | `uv run python scripts/admin.py rebuild` |
| 10 | Administration password | `uv run python scripts/admin.py password --username USERNAME` |
| 11 | Rebuild admin panel | `uv run python scripts/admin.py rebuild-admin` and `restart-admin` |
| 12 | Set up example site | `uv run python scripts/admin.py self-host example` |
| 13 | Set up real empty database | `uv run python scripts/admin.py self-host real-database` |

The dataset enrollment starts the server database service, migrates the configured database to this checkout's migration head and enrolls it as the Selected initial dataset. An already-enrolled dataset is reused and returned as it is.

The copy lists every receipt-bearing dataset and asks for one source id. It confirms the exact dataset before it copies, requires every stage idle, creates the verified copy and publishes it as Working. The confirmation names the dataset and its database.

The worker setup fast-forwards the worker checkout to one origin branch, installs its locked environment, and prepares its pointed resources, including building the database service image through Compose. The menu reads the server checkout's branch first and asks for the origin branch only when that branch is not `main`. The question shows the server branch as its default, and an empty answer accepts it. The machine command sets the same branch with `--branch BRANCH`, and `--code-only` updates the code and its locked environment without preparing the pointed resources.

The preflight reads the branch and HEAD of the server checkout and of the worker checkout, checks the worker's locked environment, and reads the worker resources when that check passes. It installs nothing, and the machine command returns 1 when the locked environment or a resource is not ready.

The migration asks for Selected or Working, then applies the migration head to that role's database as explicit maintenance. A Working migration requires every stage to be idle. The server database service must already be running.

The worker setup and the preflight add one fixed notice when the server checkout's branch differs from its origin counterpart. The notice states that pushing is a separate manual step. The menu prints it after the report, and the machine command prints it to standard error.

## The two self-host workflows

Choice 12 opens the example workflow. It asks for the site's external app address with the example's address as its default, the administration username, the startup mode, the pinned-model download confirmation and the optional publication choice. It then reads the publication token at a hidden prompt when the publication choice is yes, followed by the administration password twice at the hidden prompts. A cancel, an end of input and an interrupt write nothing and run nothing.

Choice 13 opens the real-database workflow. It asks for the database name with `course_explorer_real` as its default and for the startup mode. The default is terminal wording alone, and the workflow owner accepts the name it is given.

The two machine commands read one JSON object from non-interactive standard input and take no secret flag. Fixed step names go to standard error and the one report goes to standard output.

```bash
.venv/bin/python -c 'import getpass, json, warnings; warnings.simplefilter("error", getpass.GetPassWarning); print(json.dumps({"username":"OPERATOR","password":getpass.getpass("Administration password: "),"mode":"user","confirm_download":True}))' | uv run python scripts/admin.py self-host example
printf '%s\n' '{"database_name":"course_explorer_real","mode":"foreground"}' | uv run python scripts/admin.py self-host real-database
```

A terminal standard input refuses with guidance to the menu, so no secret is read at a visible prompt.

The example workflow materializes the absent working templates, writes the supplied app address and the two generated database passwords, creates the administration account only when it is absent, checks the host, downloads the pinned model after the confirmation, builds and starts the database and embedding services, migrates and loads the example dataset, prepares the feedback application store, builds the native libraries and both frontends, starts the two backends in the chosen mode, and proves both shells and the bootstrap catalogue and identity.

The host check runs the prepared `.venv/bin/python` once to require Linux CPython 3.14 or newer with `os.memfd_create`, before the model download, the container build or the frontend build. An interpreter without that capability refuses with the environment-preparation guidance and runs none of them.

The real-database workflow requires the working files, the running database and embedding services, every stage idle, and, in foreground mode, free feature and administration ports. It creates the named database, enrolls it as the initial Selected dataset, builds its serving artifacts, starts or restarts the site, and proves the selected catalogue and a changed identity. `POSTGRES_DB` is not edited, and the example database is left in the container.

A repeated example run refuses at the example database's user-table check before it imports anything. A repeated real-database run refuses inside the named enrollment owner before it creates another database, migrates, builds or restarts a server. A failed create or migration preserves whatever it created for explicit maintenance. A failed build or proof leaves the created dataset, its dump and its artifacts for explicit deletion.

A failed example import leaves the copied working files, the generated environment file, the administration account and the migrated example schema in place. Clear the example database through the database service before a retry. A failed real-database build or proof leaves the named database, its initial receipt and the Selected pointer. `uv run python scripts/admin.py datasets list` names them, and the dataset owners provide the explicit maintenance.

## Cleanup of datasets and backups

Two entries delete one target the operator names.

**Dataset cleanup** lists every receipt-bearing dataset and deletes one dataset. The machine commands are `uv run python scripts/admin.py datasets list` and `uv run python scripts/admin.py datasets delete DATASET_ID [--confirm-working]`.

**Backup cleanup** lists the files under `data/backups` and deletes one of them. The machine commands are `uv run python scripts/admin.py backups list` and `uv run python scripts/admin.py backups delete NAME`.

Both entries print the listing before they ask for a target, and `0` at the target prompt cancels the entry. An empty listing and a failed listing both return to the calling menu without a target prompt. An answer outside the printed listing, Selected and any dataset without a receipt in the listing are refused with one fixed line and delete nothing.

A target that the listing contains draws one confirmation titled with that exact target. A non-role target and a backup use `Delete dataset <id> (<database name>)?` and `Delete backup <name>?`. A Working target uses `Delete Working dataset <id> (<database name>)? Working becomes absent.` The confirmation holds **1 Delete** and **0 Cancel**, and the menu passes the Working confirmation only after that titled choice. Only the delete choice runs the deletion, and that owner's report is printed as it returns. A cancel and any other answer delete nothing and return to the calling menu. An end of input and an interrupt delete nothing, stop no running work, and leave the whole menu with exit status 0 and 130.

The two listing commands create no state. The dataset listing reads every receipt and the role pointers, then probes every known database name once. A stopped service produces a typed unavailable presence rather than a failed listing. `backups list` requires access to the backup directory and reports an empty listing when that directory is absent. A dataset deletion requires a Selected dataset, a target from its listing and the running server database service. A Working target also requires every stage idle. A backup deletion requires a regular file from its listing and access to it. [Datasets](/docs/operations/datasets.md#manual-cleanup) states every refusal and what each deletion retains.

> [!CAUTION]
> A cleanup deletion is irreversible. The listing names each target, and the confirmation names the exact dataset or backup file that the deletion removes.

## Configuration

Choice 8 reads one configuration file and saves one key of it. The machine commands are `uv run python scripts/admin.py config list`, `uv run python scripts/admin.py config read FILE` and `uv run python scripts/admin.py config set FILE KEY VALUE`.

The entry lists the registered subsystem files in composition order with the environment file last, prints the listing, and asks for a file the listing carries. It then prints every key of the chosen file as that file holds it and asks for a key the report carries. The value prompt takes one JSON literal that matches the broad type the key holds, and the entry does not strip or echo it.

A save draws one confirmation titled `Save configuration <file> key <key>?` with **1 Save** and **0 Cancel**. The title names the file and the key and no value. Only **1 Save** runs the save, and the writer's report is printed as it returns. `0` at the file prompt or the key prompt cancels the entry, an answer outside either prompt writes nothing, and a value the owning settings family refuses prints the shared safe failure and guidance.

One save writes one key, so a file with several edits takes one save per key. The entry edits the keys the read displays, so it writes a key the chosen file already carries and appends nothing. The machine command accepts one more case: `config set` appends an absent environment alias that a settings family owns for that file as one quoted assignment that leaves every other byte as it is, and it refuses an absent subsystem-file key or an absent environment key that no settings family owns.

> [!CAUTION]
> The read prints every value of the chosen file in plain text, the environment file included.

A saved file reaches a running process when that process next builds its settings. [Configuration](/docs/backend/configuration.md#reading-and-writing-a-file) states the precedence between the files.

## The two rebuild scopes

Choice 9 rebuilds the app. Choice 11 rebuilds the administration panel. The two scopes are separate, each has its own confirmation, and neither reaches the other's process or its resources.

Choice 9 builds the site frontend, recreates the database and embedding containers, restarts the site's web server and checks its bind. The machine command is `uv run python scripts/admin.py rebuild`.

The entry asks one confirmation, `Rebuild this site's frontend, containers and web server?`, and holds **1 Rebuild** and **0 Cancel**. Only the rebuild choice runs the command. A cancel and any other answer run nothing and return to the calling menu, and an end of input and an interrupt run nothing and leave the whole menu with exit status 0 and 130.

The command runs four steps in this order, and the first failure stops it.

1. The frontend build, `npm --prefix web run build`, in the checkout. It builds from the installed dependencies.
2. The two prepared containers, `docker compose up -d --wait --force-recreate --no-build --pull never db embedding`. The step uses the prepared images, and the data volumes and databases are left as they are.
3. A restart of the site's own web unit through the manager `ADMIN_SITE_WEB_SERVICE_SCOPE` names: `systemctl --user restart` in the user manager, or `sudo -n /usr/bin/systemctl restart` in the system manager. A system-manager restart needs the exact passwordless grant the host installs for that one unit and command.
4. The bind check: the restarted process's main PID must own the configured `127.0.0.1:PORT` listener within `ADMIN_STARTUP_ATTEMPTS` polls spaced by `ADMIN_POLL_INTERVAL_SECONDS`. A listener that same process owns on an address that is not a loopback address fails at once. Listeners that another process owns on the same port belong to that process and are left alone.

The commands of the first three steps are bounded by `ADMIN_STOP_TIMEOUT_SECONDS`, and the bind wait by its poll count and interval. The report names the four steps and the verified bind, and it is the transient acknowledgment of the run. A failed step prints the shared safe failure and the rebuild guidance, and no further step runs. The rebuild leaves the checkout's Git state as it is, reaches no worker, and restarts only the site's own web unit.

The command validates the site's own loaded web unit, running from this checkout and executing this checkout's `scripts/run_web.sh`, before its first step. `ADMIN_SITE_WEB_SERVICE_UNIT` in `config/admin_web.toml` names that unit, and `ADMIN_SITE_WEB_SERVICE_SCOPE` names the manager that owns it.

Choice 11 builds the administration frontend alone and then queues the restart of this checkout's own administration unit. The machine commands are `uv run python scripts/admin.py rebuild-admin` and `uv run python scripts/admin.py restart-admin`, and the entry runs the first and then the second.

The entry asks one confirmation, `Rebuild the admin panel? This signs all operators out.`, and holds **1 Rebuild** and **0 Cancel**. The warning states the sign-out because ending that backend process ends every session it holds in memory. Only the rebuild choice runs the sequence. A cancel and any other answer run nothing and return to the calling menu, and an end of input and an interrupt run nothing and leave the whole menu with exit status 0 and 130.

The sequence runs two commands in this order, and a failed build stops it before the restart.

1. `rebuild-admin` builds the administration frontend with `npm --prefix admin-web run build`, from the installed dependencies. It recreates no container, opens no database and reaches no worker.
2. `restart-admin` queues one non-blocking restart of this checkout's own administration unit and returns once that request is admitted.

Each command is bounded by `ADMIN_STOP_TIMEOUT_SECONDS`. The report the entry prints is the restart command's own acknowledgment that the restart is queued. It states no observed restart and no verified bind, so the console's own restart and the following sign-in are what show the outcome.

Both commands validate before they act that the administration unit named by `ADMIN_SITE_ADMIN_SERVICE_UNIT` in `config/admin_web.toml` is loaded, runs from this checkout and executes this checkout's `scripts/run_admin_web.sh`. A unit from another directory or with another launcher is refused, and a refused build restarts nothing. [Administration commands](/docs/backend/interfaces/administration-commands.md#the-rebuild-commands) states each command's report and failure presentation.

## The administration password

Choice 10 stores the site's one administration account. The machine command is `uv run python scripts/admin.py password --username USERNAME`.

The entry asks `Username (0 to cancel): ` through the ordinary menu input, and `0` cancels it. It then asks for the password twice at the hidden prompts `Password: ` and `Repeat password: `, which the command itself owns, so no password is read from or written to the menu's own streams. Two different entries, a blank entry, an end of input and an interrupt each store nothing, and an end of input and an interrupt leave the whole menu with exit status 0 and 130.

```bash
uv run python scripts/admin.py password --username OPERATOR
```

The command prints one acknowledgment line and stores the account's username and an argon2id hash in `data/admin-web/password`. [Administration commands](/docs/backend/interfaces/administration-commands.md#the-administration-password) states the command, the file, and the failure presentation.

> [!IMPORTANT]
> The entry is a terminal provisioning step, and the account's own site authenticates with it. Each site holds its own account, so each deployment sets its own username and password.
