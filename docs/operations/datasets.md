# Datasets

A dataset is one complete database of courses, modules, and derived data, where the web server serves Selected and the pipeline stages write Working.

## The two pointers and their receipts

Two pointers under `ADMIN_STATE_ROOT` name the two roles. `selected-dataset.json` names the dataset the site serves. `working-dataset.json` names the dataset the stages use. `ADMIN_STATE_ROOT` is in `config/database.toml`.

One receipt per dataset records what that dataset is. A receipt names the dataset id, the database name, the kind, the digest of its retained dump when it has one, the predecessor that the copy or return was built from, and the verification read from the database. The receipt records no role. A role is only its pointer.

| Kind | What the receipt names |
|---|---|
| Initial | The zero dataset id, no predecessor, and no dump |
| Returned | The session that produced it, its predecessor, and the digest of the returned dump |
| Copied | The source dataset, its predecessor, and the digest of the copied dump |

![The state root's two pointer files name the Selected and Working datasets, and each dataset holds one initial, copied or returned receipt. A copied receipt names its source and dump, a returned receipt names its session and dump, and a chain ends at the zero-id initial receipt. Copy to Working and a dataset return publish the Working pointer, and rotation keeps each role's dataset and its predecessor.](/docs/diagrams/dataset-roles.svg)

A pointer without its receipt, a receipt whose id differs from its pointer, and a Working pointer that names the Selected dataset or database all fail loudly. A role read creates no file.

A state root is bootstrap when neither pointer exists, no dataset directory holds a receipt or retained dump, and no session directory holds `session.json`. Bootstrap serves the configured `POSTGRES_DB` directly, and the stages refuse because no Working dataset exists. Empty collection directories, unrelated stage directories and `controller.lock` establish no enrollment.

A missing Selected pointer beside dataset or session records fails with setup guidance. A Working pointer without a Selected pointer fails loudly. The application and its loaders never enroll a dataset at startup.

## Enrolling a dataset

```bash
uv run python scripts/admin.py setup datasets
```

The explicit command migrates the configured database to the migration head of the checkout, verifies it, writes the initial receipt, and selects it. It starts the server database service when the service is not running. With a dataset already selected it returns the receipt it holds and writes nothing.

An enrollment interrupted between the initial receipt and the pointer is published from that retained receipt alone when it is the sole enrolled dataset, matches the configured database and leaves no Working pointer or recorded session. Any other retained state fails rather than being enrolled over.

```bash
uv run python scripts/admin.py datasets ensure-selected
```

This deploy command reuses a valid Selected dataset and raises on inconsistent enrollment. On a bootstrap state root it leaves the configured database unenrolled when its name equals `EXAMPLE_POSTGRES_DB`, and otherwise enrolls it through the same explicit owner. It performs no interrupted-enrollment repair.

### A named empty initial database

The real-database setup workflow creates one absent database by name and enrolls it as the initial Selected dataset through `course_explorer_admin.datasets.create_empty_selected_dataset`.

The name is validated against the dataset database-name type and the protected-name list. A state root with any pointer or enrollment record refuses, the configured example name refuses, and a target database that the service already holds refuses. The absent database is created from `template0` through the configured Compose service, then the shared locked initial-enrollment core migrates it, verifies it, writes the zero-id initial receipt and publishes Selected. The receipt format is the same initial receipt that `setup datasets` writes.

A failed create or migration preserves whatever it created for explicit maintenance, and a repeat refuses before another create. The example database stays in the container, and the workflow promotes no copy and prunes no dataset.

## The schema head and migration

A stage start, a worker session, and every dataset verification require the database to be at the single migration head of the executing checkout. A database whose current head differs, or that carries no version, is refused with fixed guidance, and no processing and no automatic migration happens.

```bash
uv run python scripts/admin.py migrate selected
uv run python scripts/admin.py migrate working
uv run python scripts/admin.py migrate database
```

`migrate selected` and `migrate working` apply the migration head to the named role's database and return a fresh verification. A Working migration requires all four stages idle with no live recorded process before it applies. A Selected migration does not read the stage state. `migrate database` applies the same head to the configured database of a bootstrap state root and refuses an enrolled deployment.

All three commands apply the head on one caller-owned connection in the interpreter that runs the command. They neither rewrite a receipt nor change a pointer.

> [!IMPORTANT]
> A role migration requires the server database service running, and a Working migration also requires every stage idle. Each refuses before it changes anything when its guard fails.

## Snapshots and verification

A [database snapshot](/docs/reference/glossary.md#administration) is a verified dump of one database. A worker session takes one when it starts, as the input snapshot of the Working dataset, and one when it returns, as the export of the worker database.

| Record | What it holds |
|---|---|
| Database snapshot | The session, the database name, the digest of one dump, and the verification read from that database |
| Dataset verification | The migration head, the row count of every table, the catalogue summary, and the teaching-text, embedding, and inference coverage reads |
| Dataset receipt | The identity of one enrolled dataset |

A dump lands in a destination that must not already exist, at mode 0600, and its listing is checked against the embedding-data policy. The input snapshot and the return snapshot include the embedding table data, and a dump without it is refused. A failure removes only the temporary file of the dump.

One confined path holds each dataset's retained dump. A return downloads the worker's dump into that path and reuses a dump already there, and the restore then validates whichever file it receives against the return snapshot digest. The restore requires a regular non-symlink dump file, and it checks the file's listing against the requested embedding policy. An absent target database is created and restored, and a present target is refused unless an expected verification matches a fresh verification of that database.

## Copy to Working

```bash
uv run python scripts/admin.py datasets copy-to-working SOURCE_DATASET_ID
```

Copy to Working creates a new dataset from an enrolled source, verifies the restored copy, writes a copied receipt, and publishes the Working pointer last. The source may be Selected, Working or any retained dataset whose database is present. Every stage must be idle before any copy mutation.

The copy has its own dataset id and derived server database name. It reads the source's current schema head before one dump, restores that dump into a fresh derived database, and reads the restored database's verification for the receipt. The dump's producer digest is stored in the receipt, and the same-operation restore records a fresh verification of the restored database without comparing it with the source. The source rows, its pointer and its artifact namespace do not change. Artifact files are not read or copied. A copy neither rotates nor deletes a dataset, and it starts or restarts no service.

A failed copy leaves both role pointers unchanged. Its generated dataset directory may hold a dump without a receipt, and its derived database may remain. The normal inventory does not treat that directory as an enrolled dataset.

The unassigned copy primitive creates the same verified dataset without publishing Working. It is the copy path that a promotion uses before its build and serving proof.

## Promotion to Selected

```bash
uv run python scripts/admin.py datasets copy-to-selected SOURCE_DATASET_ID --confirm-restart
```

Promotion copies one enrolled source, builds and verifies the copy, publishes it as Selected, restarts the site's web unit and proves the restarted site serves the copy. The source may be Selected, Working or any retained dataset whose database is present. Every running stage is left alone.

The confirmation is required before any copy. Without `--confirm-restart` the command refuses and mutates nothing. A bootstrap state root refuses with the enrollment guidance.

The command reads the previous Selected dataset, the checkout's own web unit and that unit's current dataset identity before the copy. It then dumps and restores the copy, builds the copy's serving artifacts for the site's configured embedding mode, and only after that build publishes the Selected pointer. The web unit is the only unit restarted, and its loopback bind is verified. The proof requires a nonempty dataset identity that differs from the previous one, and the served catalogue body to equal the new artifact with that identity appended.

A failed build switches nothing and restarts nothing. A failed restart or proof restores the previous Selected pointer, restarts the web unit and proves the previous catalogue and feature readiness. The promotion failure is then raised again. When that rollback also fails, the command raises both errors together.

The owner reports six coarse steps to an optional observer: `copy`, `build`, `switch`, `restart`, `prove` and, once before a rollback restores the previous pointer, `rollback`. Each step arrives immediately before that step's work, and no step carries a fraction, an elapsed estimate or an accumulated history. The machine command and every other caller supply no observer and print the one final receipt, so the report and the stored formats are the same with or without it.

Every failed attempt keeps its created dataset, dump, receipt and completed artifacts for manual deletion. Promotion performs no rotation, no prune and no automatic deletion, and it neither changes the Working pointer nor requires the stages to be idle.

![Promotion copies one source dataset, builds the copy's serving artifacts, publishes the Selected pointer, restarts the web unit and proves the catalogue and a changed identity. A failed restart or proof restores the previous Selected pointer, restarts the unit and proves the previous catalogue.](/docs/diagrams/dataset-promotion.svg)

A standalone `serving-artifacts` build is the separate setup and maintenance action, and `serving-artifacts --prune` is its separate housekeeping action.

## The return and the Working role

A return restores the verified dump of the returned worker database into the derived server database, checks the restored database against the return snapshot, writes the returned receipt, publishes it as Working, and rotates older Working ancestors. The Selected pointer is not read for the source and is never changed. [Worker sessions](/docs/operations/worker-sessions.md) describes the session that produces the returned dump.

The names are derived from the session id. `ADMIN_DATASET_DATABASE_PREFIX` derives the server database of a returned dataset, `ADMIN_WORKER_DATABASE_PREFIX` derives the worker database, and both prefixes are in `config/worker.toml`.

A return that was already retained is reused rather than repeated, including when its snapshot and its dump are absent. The first return of a session needs both the snapshot and the dump, and it refuses without them.

> [!IMPORTANT]
> The pipeline writes Working, and the served dataset stays Selected. A return changes only the Working pointer. The reports read the role each command names, and the site continues to serve the Selected dataset.

## Rotation

Rotation runs after a verified dataset return. It keeps each role's current dataset and its immediate predecessor, and deletes older Working ancestors outside those two pairs.

Before any deletion every chain is walked from its starting receipt through each named predecessor and validated. Only a returned or copied receipt may name a predecessor, a cycle refuses, and a chain must end at the zero-id initial receipt. A chain that fails the walk refuses before the first deletion.

The keep set is the union of Selected and its immediate predecessor plus Working and its immediate predecessor. Other branches created by manual copies remain for manual deletion. Inside the keep set the database and the retained dump of each dataset stay. Outside it the database is dropped, the retained dump is removed, and its derived artifact namespace is removed. Every dataset keeps its receipt.

Two guards protect other databases. A database name on the fixed protected list is never dropped, and a returned or copied dataset whose database name is not the configured derived name refuses before any drop. A state tree that traverses a symlink or a non-directory refuses before any lock, receipt, dump, or database action.

> [!WARNING]
> Rotation retains only the two role pairs. An older Working ancestor outside them loses its database, its dump and its artifact namespace, so its rows are not recoverable from the chain.

## The dataset listing

```bash
uv run python scripts/admin.py datasets list
```

The listing discovers every receipt-bearing dataset directory, so replacing Working from another source cannot hide an older manual copy. It prints role datasets even when their resources are missing, and any other dataset when it holds a retained dump, a derived artifact namespace or a present database. With the database probe unavailable it lists every known receipt and marks each database presence unavailable.

One entry carries the dataset id, the kind, the database name, the predecessor, the recorded migration head of its receipt, the repository-relative retained dump path, whether the dataset is Selected, whether it is Working, its typed database presence (`present`, `absent` or `unavailable`), and whether its artifact namespace exists. The report states `bootstrap`, `enrolled` or `unavailable`, whether the probe was `available` or `unavailable`, the configured database of a bootstrap root, and whether each of the four stages is busy.

A stage is busy when its durable lifecycle is not idle or when it records a live process. The listing and every guarded dataset action read that one predicate, so the console's stage row set and an owner's refusal cannot disagree. A bootstrap root adds the configured database to the same probe, so a stopped database service reports the typed unavailable probe even with no receipt to probe.

The listing reads local receipts and files first and then probes every known database name in one call. A stopped database service returns the typed unavailable state rather than an exception. A bootstrap root returns an empty role inventory and a probe state. A state root that the guard refuses returns the `unavailable` mode with an empty dataset list, so the panel states the refusal. The read creates no file, directory or lock and holds no lock.

## Manual cleanup

Manual cleanup deletes one target the operator names, and it leaves the automatic rule of the rotation above alone.

```bash
uv run python scripts/admin.py datasets delete DATASET_ID
uv run python scripts/admin.py datasets delete DATASET_ID --confirm-working
uv run python scripts/admin.py backups list
uv run python scripts/admin.py backups delete NAME
```

`datasets delete DATASET_ID` drops the named dataset's server database, removes its retained dump and removes its derived artifact namespace across academic years. Every receipt-bearing dataset except Selected is eligible, the initial dataset included. Working additionally requires `--confirm-working` and every stage idle, and a successful Working deletion clears only the Working pointer. A later stage refuses until a new copy to Working.

| Refused target | The rule that refuses it |
|---|---|
| An id with no receipt-bearing dataset directory | Only an enrolled dataset is a cleanup target |
| Selected, and a receipt naming the Selected database | The Selected dataset is the copy the server reads |
| Working without `--confirm-working` | Working deletion is a separate explicit choice |
| Working while a stage is not idle | The Working dataset can be in use by a running stage |
| A returned or copied receipt whose database name is not `ADMIN_DATASET_DATABASE_PREFIX` and its own id joined by an underscore | The derived name is the proof that the receipt describes the server copy |
| A database name on the fixed protected list | The protected names cover databases that no dataset enrollment produced |
| A retained dump that is a symlink or not a regular file | The dump path is confined to the dataset directory of that receipt |
| A derived artifact namespace that is a symlink or not a directory | The namespace is derived solely from the database name |
| A bootstrap state root with no Selected dataset | No dataset is enrolled, so no dataset cleanup target exists |

The command resolves both roles and the requested receipt again under the dataset action lock, so a listing printed earlier is presentation rather than delete authority. A deletion removes exactly the named database, that dataset's dump and that derived artifact namespace, and it leaves the receipt, every other pointer, the Selected dataset and every other database namespace in place. A repeated command over the same absent resources reports the same result.

### A failed copy left no receipt

A copy failure can leave a generated dataset directory without `receipt.json` and a derived database or dump under that generated id. The inventory ignores that directory because it has no receipt.

Inspect the directory and its name first. The database name is the configured server prefix and that id joined by an underscore, and the artifact namespace is the whole database namespace under the state root. If a receipt or either role names that id, do not remove anything. As separately authorized operator maintenance, drop that exact derived database and remove that exact unreceipted directory. No product command performs this repair.

`backups list` prints every regular file beneath `data/backups`, nested files included, in lexical relative-path order, with the size and the last modification time of each file. The listing reads file metadata alone, reports no backups for an absent directory, and creates nothing. A symlinked entry, a special file and a symlinked directory refuse the listing.

`backups delete NAME` removes the one file that relative name identifies under `data/backups`, and the name is the one the listing prints. Empty and absolute names, a backslash, a NUL, an empty, dot or dot-dot segment, a parent that is a symlink or not a directory, and a target that is missing, a symlink or not a file are all refused. Nothing else under the directory changes, and rotation reads and removes no backup file.

The automatic rotation and this cleanup share one drop path, so both drop a database through the same Compose command with the same protected-name check, the same operation timeout and the same artifact namespace removal. The [Setup and preflight](/docs/operations/setup-and-preflight.md#cleanup-of-datasets-and-backups) menu entries hold the two deletions behind a listing and a confirmation that names the exact dataset or backup file. A Working deletion names Working and states that Working becomes absent.

## Backups and the chain

Files kept under `data/backups` are outside every dataset chain, and rotation deletes nothing there. The administrative state root must not lie inside that directory.

## Failure outcomes

A failed return leaves both role pointers in place, retains the returned dump, and writes no receipt, so the return can run again over the retained dump. A failed restore leaves the target database in place. A failed migration changes no data and no file, and a rotation that cannot validate its chain refuses before the first deletion.

The worker's own copy is separate from every server dataset. Its cleanup drops the exact worker database only after the returned dataset receipt and the recorded return snapshot agree on their session and database identity.

## Reading a dataset role

The read-only reports and migrations name their role.

```bash
uv run python scripts/admin.py summary catalogue --role selected
uv run python scripts/admin.py summary inference --role working
uv run python scripts/admin.py coverage teaching-text --role working
uv run python scripts/admin.py coverage embedding --role selected
uv run python scripts/admin.py coverage inference --role working
uv run python scripts/admin.py serving-artifacts
```

A Selected read resolves the Selected pointer and serves the configured database in bootstrap. A Working read requires the Working pointer and fails with copy guidance when it is absent. The catalogue summary and the coverage reports describe the stored courses, modules, translations, vectors, and inferred prerequisites of the named role.

`serving-artifacts` builds the Selected dataset, or a named `--dataset` receipt. It builds a versioned build directory and switches the artifact family's `current` build last. On a site that serves the embedding features it also writes the embedding hub pair, the course centroids and the shared stores into the family's embedding directory of the running configuration, and replaces the centroid rows, the stored neighbour rows and the packed search relation in one transaction. On a site with them off it writes the catalogue artifact and the study fragments alone and leaves the embedding directory and the tables as they are. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md) states the files and the transaction.

The four preparation stages write Working, so their rows are not served and need no build or restart. A build over a Working receipt writes that dataset's artifacts without changing the Selected dataset or what the site serves.

A selected-dataset change reaches the site through `datasets copy-to-selected SOURCE_DATASET_ID --confirm-restart`, which builds the copy before publishing it, restarts only the web unit and proves the served catalogue. [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states the sequence. After that restart, `serving-artifacts --prune` removes the target database's obsolete builds, the other year families' builds, and owned temporary outputs without building or switching anything, while keeping the active current build, unknown names and other database namespaces. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-artifact-family-the-build-directory-and-the-embedding-directory) states which embedding directories it retains in each mode.

[Operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) lists four reports. Each report asks for Selected or Working first. The `coverage inference` command is machine-only.

## Dataset, snapshot, and backup

| Thing | What it is |
|---|---|
| Dataset | One complete database of courses, modules, and derived data |
| Database snapshot | One verified dump of a database, taken when a worker session starts or when it returns |
| Backup | A separate copy kept under `data/backups`, outside every dataset chain |
