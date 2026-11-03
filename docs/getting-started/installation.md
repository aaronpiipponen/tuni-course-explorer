# Installation

Installation takes a fresh checkout to a site that serves the example dataset, then to an empty Selected database, through two setup workflows.

The steps run in this order: clone the checkout, prepare the environment, run the example workflow, and then run the real-database workflow.

## What the copy needs

- A checkout of this repository.
- Linux and a CPython 3.14.3 interpreter installed on the host that exposes `os.memfd_create` and `os.MFD_CLOEXEC`. `.python-version` pins that interpreter version and `pyproject.toml` requires Python 3.14 or higher, and neither selects a build's capabilities. The host interpreter can come from the distribution's package manager or from a CPython build against the Linux development headers. Not every build of 3.14.3 exposes these capabilities.
- [uv](https://docs.astral.sh/uv/), which installs the Python packages and the commands the steps run.
- Node.js 22.22.2 or higher within major version 22, or 24.15.0 or higher, with npm. `web/package.json` and `admin-web/package.json` declare those engine ranges as `^22.22.2 || >=24.15.0`.
- Docker with Docker Compose. The Compose wrapper runs `sudo docker compose` with the checkout as the project directory and `docker-compose.yml` at the checkout root as the file, so the account that runs the steps must be allowed to run Docker through sudo.
- The two shared libraries the compiled native modules load at run time: `libpq` and the C++ standard library `libstdc++`. The native build itself runs in a container, so the host needs no compiler. [Native libraries](/docs/architecture/native-libraries.md#what-the-host-provides) states which module links which library.
- Access to the Python and npm package registries, and to the model file at the download address that `EMBEDDING_ARTIFACT_URL` names.
- The GitHub CLI `gh` for the feedback sender, from a release whose `gh issue create` documents `--attach` and `--body-file -`.

The example workflow writes the working files in the table below and, when it creates the environment file, both generated database passwords. The real-database workflow requires those working files and the two running services, and it writes only its named database, its receipt and its artifacts. The copy starts from the tracked example assets under `examples/` and needs no manual file edit for the example path.

## What the workflows write

| Working path | Holds |
|---|---|
| `config/` | The registered subsystem files, the feedback definition and the wiki pages, copied from `examples/config/` |
| `.env` | The generated curriculum database password, the generated feedback application store's database password, and the optional feedback sender token, published at mode 0600 |
| `docker-compose.yml` | The PostgreSQL database with pgvector and the embedding service |
| `deploy/Caddyfile` | The HTTPS site template for a host that serves the copy over a domain |
| `deploy/*.service.in`, `deploy/*.timer.in` | The four systemd templates for the web server, the administration backend and the feedback sender |
| `data/admin-web/password` | The administration account's username and argon2id hash, written only when the account is absent |
| `models/bge-m3-q8_0.gguf` | The pinned embedding model, checked against `EMBEDDING_ARTIFACT_SHA256` |

A present working file is left byte for byte. A symlinked or non-regular working path is refused rather than followed. A present `config/` directory is an ordinary directory that receives the absent templates.

## Cloning the checkout

```bash
git clone REPOSITORY_ADDRESS course-explorer
cd course-explorer
```

## Preparing the environment

```bash
python3.14 -c 'import os, sys; assert sys.version_info[:3] == (3, 14, 3); fd = os.memfd_create("course-explorer-preflight", os.MFD_CLOEXEC); os.close(fd); print(sys.executable)'
uv sync --locked --no-managed-python --python "$(python3.14 -c 'import sys; print(sys.executable)')"
.venv/bin/python -c 'import os; fd = os.memfd_create("course-explorer-preflight", os.MFD_CLOEXEC); os.close(fd)'
npm --prefix web ci --engine-strict --no-audit --no-fund
npm --prefix admin-web ci --engine-strict --no-audit --no-fund
```

`python3.14` must be on the host PATH, and the first command must print the host interpreter's path and exit with status 0. That printed path is the host prerequisite, not this checkout's `.venv` and not a copied environment. The second command selects it and `--no-managed-python` stops uv from downloading another interpreter. `uv sync` writes the virtual environment `.venv` at the checkout root and installs the Python packages recorded in `uv.lock`, and the third command checks that the prepared interpreter creates and closes one shared memory file.

`npm ci` installs the browser packages recorded in `web/package-lock.json` into `web/node_modules`, and the console packages recorded in `admin-web/package-lock.json` into `admin-web/node_modules`. The unit templates, `scripts/run_web.sh` and `scripts/run_admin_web.sh` run their processes through `.venv/bin/python`, so the environment lives at the checkout root.

The example workflow checks the prepared interpreter's Linux shared-memory capability, both frontend package directories, the `node`, `npm`, `uv`, `curl`, `docker` and `docker compose` version commands, the two host native libraries and the loopback ports before it builds anything. It also writes the free space of the checkout's filesystem, without comparing that value with anything. The interpreter check runs before the model download and the container build. A missing item refuses the run with guidance before the model download, the container build or the frontend build. The copied working files, the generated database passwords and a created administration account are in place for the retry.

## Running the example workflow

The workflow materializes the absent working files, writes the device choices, builds and starts the database and the embedding service, migrates and loads the example dataset, prepares the feedback application store, builds the native libraries and both frontends, starts the two backends in the chosen mode, and proves both shells and the bootstrap catalogue.

The administration command opens the numbered menu:

```bash
uv run python scripts/admin.py
```

Choose **1 Setup/preflight**, then **12 Set up example site**. The entry asks for the site's external app address, the administration username, the startup mode, the pinned-model download confirmation and the optional publication choice, and it reads the token and the password at hidden prompts. [Operator menu](/docs/operations/operator-menu.md#setup-and-preflight) lists every prompt and [Setup and preflight](/docs/operations/setup-and-preflight.md#the-two-self-host-workflows) states what each answer does.

The machine command reads one JSON object from non-interactive standard input and takes no secret flag:

```bash
.venv/bin/python -c 'import getpass, json, warnings; warnings.simplefilter("error", getpass.GetPassWarning); print(json.dumps({"username":"OPERATOR","password":getpass.getpass("Administration password: "),"mode":"foreground","confirm_download":True}))' | uv run python scripts/admin.py self-host example
```

| Field | Holds |
|---|---|
| `app_url` | The feature site's external root address. An absent value or `null` uses the example's `WEB_APP_URL`. |
| `username` | The administration account's username |
| `password` | The administration account's password. It is hidden from the model's representation and its serialized form. |
| `mode` | `user` or `foreground` |
| `confirm_download` | Whether an absent pinned model may be downloaded |
| `publication_token` | The optional feedback sender token. It is hidden from the model's representation and its serialized form. |

A terminal standard input refuses with guidance to the menu, so no secret is read at a visible prompt. Fixed step names go to standard error and the one report goes to standard output.

The workflow refuses an example path whose `POSTGRES_DB` differs from `EXAMPLE_POSTGRES_DB`, and it refuses a state root that holds a dataset pointer or an enrollment record. It creates the account only when `data/admin-web/password` is absent, so a second run does not reset the account. The second run refuses at the example database's user-table check before it imports anything.

### User units or foreground

**User units** renders the four unit templates into the user manager, writes the two derived service names and the `user` scope into `config/admin_web.toml`, and enables and starts the two backend services. It installs the feedback sender timer and enables it when publication setup was requested and the configured destination is a real repository. **Foreground** starts both backends as children of the setup command until Ctrl-C.

[Self-hosting](/docs/getting-started/self-hosting.md#the-two-startup-modes) states both modes, the unit names, the lingering prerequisite and what each mode preserves.

### Editing a working file

The example workflow materializes the absent working templates in the table above from the tracked examples, and it leaves a present working file byte for byte. To change a value, save it with the configuration command, which takes one JSON literal per key, and restart the process that reads it. [Setup and preflight](/docs/operations/setup-and-preflight.md#configuration) states the command and [Self-hosting](/docs/getting-started/self-hosting.md#the-site-unit-identities) states the unit names and the host values the units read. A second run of the example workflow refuses, because the example database already holds tables.

The workflow creates the feedback role and database, applies the feedback chain and writes the attachment root at `FEEDBACK_ATTACHMENTS_ROOT`.

## Running the real-database workflow

This workflow creates one named empty database in the running container, enrolls it as the initial Selected dataset, builds its serving artifacts, starts the selected site, and proves its identity and catalogue. It does not edit `POSTGRES_DB`, and the example database is left in the container.

Choose **1 Setup/preflight**, then **13 Set up real empty database**.

| Prompt | Answer |
|---|---|
| `Database name [course_explorer_real]: ` | The named database, or an empty answer for the default |
| `Startup mode` | **1 User units** or **2 Foreground** |

```bash
printf '%s\n' '{"database_name":"course_explorer_real","mode":"foreground"}' | uv run python scripts/admin.py self-host real-database
```

The workflow needs the working files, the running database and embedding services, every stage idle, and, in foreground mode, both feature and administration ports free. In user mode it reads the configured owned web unit and its served identity before any mutation, and it restarts that unit through the shared restart owner. In foreground mode it asks the operator to end the example workflow's pair with Ctrl-C first.

The named enrollment requires a state root with no pointer and no enrollment record. The configured example name, a target database the service already holds and a protected name each refuse before mutation. A failed create or migration preserves whatever it created for explicit maintenance.

The empty database builds and serves with the example's embedding features enabled. Its catalogue, search, recommendation and study-structure results are empty, and the feature switches hold their example values.

A repeated call refuses inside the named enrollment owner before it creates another database, migrates, builds or restarts a server. The example database is not promoted, copied or pruned.

## The address and HTTPS

The example address is loopback HTTP, the only address at which the feature site accepts plain HTTP. The administration origin is an HTTPS origin even on loopback, so console sign-in needs the reverse proxy.

For an external feature address the workflow requires HTTPS through the shared web app settings, shows both configured origins, and names the example `deploy/Caddyfile` with one certificate per domain. A proxy, DNS and certificate are explicit operator prerequisites. The workflow installs no proxy. When the administration origin names a loopback host for external access, the workflow prints the exact edit:

```bash
uv run python scripts/admin.py config set config/admin_web.toml ADMIN_WEB_ORIGIN '"https://admin.example.org"'
```

## Check the running copy

Open `http://127.0.0.1:8037`, the address from `WEB_HOST` and `WEB_PORT` in `config/web.toml`. The top bar shows the tabs **Search**, **Compare**, **Prerequisites**, **Discover**, and **Structure of studies**, with **Docs** beside them. `WEB_EMBEDDINGS_ENABLED = false` in `config/web.toml` removes the **Compare** tab and the comparison controls. `WEB_INFERENCE_ENABLED = false` hides the **Inferred** controls and marks. **Docs** opens the documentation wiki inside the app, and a page the configuration does not select opens on GitHub.

The browser, console and Python checks are listed in [Local checks](/docs/testing/local-checks.md).

## Troubleshooting

| Refusal or message | Cause | Fix |
|---|---|---|
| `the example workflow requires POSTGRES_DB to equal EXAMPLE_POSTGRES_DB` | The configured database name differs from the example name. | Set both keys to the example name in `config/database.toml`. |
| `the example workflow requires a state root with no dataset pointers or records` | The state root holds a pointer or an enrollment record. | Use the real-database workflow, or clear the dataset state explicitly. |
| `an existing environment file keeps its feedback sender credential` | Publication was requested while `.env` holds its own token. | Set the token with `uv run python scripts/admin.py config set .env FEEDBACK_GITHUB_TOKEN '"TOKEN"'` and enable the timer explicitly, or start from an absent `.env`. |
| `publication needs a real feedback repository` | `FEEDBACK_GITHUB_REPOSITORY` names the example repository. | Set the destination with `uv run python scripts/admin.py config set config/feedback.toml FEEDBACK_GITHUB_REPOSITORY '"OWNER/REPOSITORY"'`. |
| `the checkout has no executable .venv/bin/python` | The Python environment is absent. | Run the environment step. |
| `the checkout's .venv/bin/python needs Linux CPython 3.14 or newer with os.memfd_create` | The prepared interpreter lacks the Linux shared-memory capability the server caches use. | Stop the processes that run this checkout's interpreter, remove only this checkout's `.venv`, prepare a host CPython 3.14.3 interpreter that exposes `os.memfd_create`, then repeat the environment step. |
| `the web packages are missing` or `the admin-web packages are missing` | A frontend package directory is absent. | Run the matching `npm --prefix <frontend> ci` command. |
| `Node 22 is not available`, `npm is not available`, `uv is not available`, `curl is not available`, `Docker is not available` or `Docker Compose is not available` | A version command failed. | Install the named tool and retry. |
| `the host native library libpq is missing` or `libstdc++ is missing` | A shared library the native modules load is absent. | Install it from the distribution's package manager. |
| `the configured feature web port PORT is used by another process` or `the configured administration port PORT is used by another process` | Another listener holds the port. | Stop that listener, or set another port in `config/web.toml` or `config/admin_web.toml`. |
| `the configured database port PORT is used by another process` or `the configured embedding port PORT is used by another process` | A process other than this project's Compose service holds the port. | Stop that process, or point the setting at a free port. |
| `the pinned embedding model is absent` | The model file is absent and the download was not confirmed. | Confirm the download in the menu or set `confirm_download` in the JSON input. |
| `the embedding artifact download does not report its length` | The download address reports no `Content-Length`. | Use an address that reports its length. |
| `the embedding artifact download must end at an HTTPS address` | The download address redirects to a non-HTTPS address. | Use an address that ends at HTTPS. |
| `the embedding download needs BYTES bytes and BYTES bytes are free` | The target filesystem has less free space than the download. | Free space and retry. |
| `the example database already holds tables` | The example database was imported once. | Use the real-database workflow, or clear the example database explicitly. |
| `the feedback store must be on the same local database cluster as the curriculum database` | The feedback host or port differs from the curriculum host or port. | Point both settings at the same local cluster. |
| `the feedback database name must differ from the curriculum database name` | Both names are equal. | Give the feedback application store its own database name in `config/feedback.toml`. |
| `the feedback database role could not be created` or `the feedback database could not be created` | The role or database creation statement failed. | Check the database service and the administration credentials, then retry. |
| `the checkout directory name must be a nonempty filesystem- and unit-safe basename` | The checkout directory name holds characters a unit name cannot carry. | Rename the checkout directory with letters, digits, `.`, `_`, `@` or `-`. |
| `user unit NAME exists with different contents` | A rendered unit differs from the template's rendering for this checkout. | Remove or restore that unit file, then retry. |
| `self-host setup needs the prepared working file PATH` | The real-database workflow ran before the working files existed. | Run the example workflow first. |
| `working path PATH must be a regular non-symlink file` | A working file the workflow materializes is a symlink or not a regular file. | Remove that path or replace it with a regular file, then retry. |
| `administration credential state must be a regular non-symlink file` | The administration credential path is a symlink or not a regular file. | Remove that path or replace it with a regular file, then retry. |
| `the database and embedding services must already be running` | The real-database workflow found a stopped service. | Start both services, then retry. |
| `stage STAGE is not idle` | A pipeline stage holds a live state. | Ordinary-stop that stage, then retry. |
| `the configured feature web port PORT is already in use` or `the configured administration port PORT is already in use` | The example workflow's foreground pair holds a port. | End that pair with Ctrl-C, then retry. |
| `the requested initial dataset database already exists` | The named database exists in the container. | Choose another name, or remove that database explicitly. |
| `named initial enrollment requires a state root with no dataset pointers or records` | The state root holds a pointer or an enrollment record. | Use the enrolled dataset owners for a second dataset. |
| `dataset database name must be a lowercase SQL identifier of at most 63 characters` | The supplied database name is not a lowercase SQL identifier of at most 63 characters. | Enter a lowercase name of letters, digits and underscores. |
| `the configured example database cannot be enrolled as a dataset` | The chosen name equals `EXAMPLE_POSTGRES_DB`. | Choose another name. |
| `refuse to drop a protected database` | The chosen name is a protected database. | Choose another name. |
| `installed artifact checksum does not match configuration` | The file at `EMBEDDING_ARTIFACT_PATH` does not match `EMBEDDING_ARTIFACT_SHA256`. | Replace the file with the pinned artifact. |
| `downloaded artifact checksum does not match configuration` | The downloaded bytes do not match `EMBEDDING_ARTIFACT_SHA256`. | Repeat the download and the checksum check. |
| `serving artifacts are missing at ...` | The current artifact build is absent. | On a bootstrap site that serves the example database, run `uv run python scripts/mock_data.py write-artifacts`. On a site with an enrolled Selected dataset, run `uv run python scripts/admin.py serving-artifacts`. |
| `the received database does not match the executing checkout's single Alembic head` | A database is not at the checkout's head revision. | Run `uv run python scripts/admin.py migrate selected` for the served dataset, `migrate working` for Working, or `migrate database` on a bootstrap site. [The schema head and migration](/docs/operations/datasets.md#the-schema-head-and-migration) states the guards. |

The example dataset is invented, and its courses, modules, prerequisites, and structure rules are not university data. [The example dataset](/docs/getting-started/example-dataset.md) describes the loader and the artifact actions in full.
