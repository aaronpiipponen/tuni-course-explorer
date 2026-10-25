# Datasets

A dataset is one complete database of courses, modules, and derived data, and the selected dataset is the one the web server and the stages read.

## The pointer and the receipt

One dataset is selected at a time. The pointer under `ADMIN_STATE_ROOT` names one dataset id, and one receipt per dataset records what that dataset is. `ADMIN_STATE_ROOT` is in `config/database.toml`.

A receipt names the dataset id, the database name, the kind of the enrollment, the revision of the checkout that produced it, the digest of its retained dump when it has one, and the verification that was read from the database.

| Kind | What the receipt names |
|---|---|
| Initial | The zero dataset id, no predecessor, and no dump |
| Returned | The session that produced it, its predecessor, and the digest of the returned dump |

A predecessor is the dataset that a returned receipt was built from, and it is the dataset that was selected when that return ran. Each returned dataset names one predecessor, and that link orders the chain.

The pointer and the receipt are the authority for every read. A missing pointer fails with setup guidance, and a pointer whose receipt is missing, malformed, or names a different dataset fails loudly.

`SELECTED_DATASET_ENABLED` in `config/database.toml` decides whether a process resolves the pointer or reads the configured database alone. The example sets it to false, so the example copy reads its configured database.

## Enrolling a dataset

```bash
uv run python scripts/admin.py setup datasets
```

The command migrates the configured database to the migration head of the checkout, verifies it, records the checkout revision, writes the initial receipt, and selects it. It starts the server database service when the service is not running.

Enrollment is idempotent. With a dataset already selected it returns the receipt it holds and writes nothing, and an enrollment interrupted between the receipt and the pointer publishes the pointer from the retained receipt alone, without repeating the migration or the verification. Enrollment compares the dataset identity, so a change of checkout revision alone is not a mismatch.

## The schema head and migration

A stage start, a worker session, and every dataset verification require the database to be at the single migration head of the executing checkout. A database whose current head differs, or that carries no version, is refused with fixed guidance, and no processing and no automatic migration happens.

```bash
uv run python scripts/admin.py migrate datasets
```

The migration applies the migration head to the selected database as explicit maintenance, then returns a fresh verification of that database.

> [!IMPORTANT]
> The migration requires all four stages to be idle with no live recorded process, and the server database service running. It refuses before it changes anything when a stage is not idle.

## Snapshots and verification

A [database snapshot](/docs/reference/glossary.md#administration) is a verified dump of one database. A worker session takes one when it starts, as the input snapshot of the selected dataset, and one when it returns, as the export of the worker database.

| Record | What it holds |
|---|---|
| Database snapshot | The session, the revision, the database name, the digest of one dump, and the verification read from that database |
| Dataset verification | The migration head, the row count of every table, the catalogue summary, and the teaching-text, embedding, and inference coverage reads |
| Dataset receipt | The identity of one enrolled dataset |

A dump lands in a destination that must not already exist, at mode 0600, and its listing is checked against the embedding-data policy. The input snapshot and the return snapshot include the embedding table data, and a dump without it is refused. A failure removes only the temporary file of the dump.

A restore requires a regular dump file with the expected digest and the requested embedding policy. An absent target database is created and restored, and a present target is refused unless an expected verification matches a fresh verification of that database.

> [!CAUTION]
> A restore into a database that already exists is refused unless its fresh verification equals the expected snapshot, and a mismatching database is left in place. The selected dataset therefore changes only through a verified promotion.

## The return and the retained pair

A return restores the verified dump of the returned worker database into the derived server database, checks the restored database against the return snapshot, writes the returned receipt, selects the returned dataset, and rotates older datasets. [Worker sessions](/docs/operations/worker-sessions.md) describes the session that produces the returned dump.

The names are derived from the session id. `ADMIN_DATASET_DATABASE_PREFIX` derives the server database of a returned dataset, `ADMIN_WORKER_DATABASE_PREFIX` derives the worker database, and both prefixes are in `config/worker.toml`.

A return that was already retained is reused rather than repeated, including when its snapshot and its dump are absent. The first return of a session needs both the snapshot and the dump, and it refuses without them.

> [!IMPORTANT]
> The stages that run on the worker write their own copy of the dataset. The selected dataset changes only at a verified return, so the reports and the web server read one whole dataset and never partial work.

## Rotation

[Dataset rotation](/docs/reference/glossary.md#administration) keeps the selected dataset and the one before it, and deletes the older datasets of the receipt chain.

Before any deletion the whole chain is walked from the selected receipt back through each named predecessor and validated. Only a returned receipt may name a predecessor, a cycle refuses, and the chain must end at the zero-id initial receipt. A chain that fails the walk refuses before the first deletion.

Inside the retained pair the database and the retained dump of each dataset stay. Outside it the database is dropped and the retained dump is removed, and every dataset keeps its receipt.

![The selected dataset names its predecessor back to the zero-id initial receipt, and every dataset in that chain keeps its small receipt. The selected dataset and its immediate predecessor keep their database and dump, while older datasets lose their database and dump. The backups directory sits outside the chain and is not rotated.](/docs/diagrams/dataset-rotation.svg)

Two guards protect other databases. A database name on the fixed protected list is never dropped, and a returned dataset whose database name is not the configured derived name refuses the rotation. A state tree that traverses a symlink or a non-directory refuses before any lock, receipt, dump, or database action.

> [!WARNING]
> Rotation retains the selected dataset and its immediate predecessor alone. Every older dataset in the chain loses its database and its dump, so the rows of a dataset outside the retained pair are not recoverable from the chain.

## Manual cleanup

Manual cleanup deletes one target the operator names, and it leaves the automatic rule of the rotation above alone.

```bash
uv run python scripts/admin.py datasets list
uv run python scripts/admin.py datasets delete DATASET_ID
uv run python scripts/admin.py backups list
uv run python scripts/admin.py backups delete NAME
```

`datasets list` prints the datasets of the retained chain that hold a database or a dump, in the order the chain walk produces: the selected dataset first, then each predecessor after the dataset that was built from it. One entry carries the dataset id, the kind, the database name, the repository-relative path of the retained dump, and whether the dataset is the selected one.

The selected dataset is always listed. Any other dataset is listed when its server database exists or its retained dump is present. A dataset with neither, as after rotation or a deletion, has a receipt and no entry. The database service answers the existence check for a non-selected dataset without a retained dump, so only that probe needs the service running.

The database name repeats the name the receipt records. A dataset without a retained dump reports no path, which is the ordinary state of the initial dataset. The listing creates no file and follows the receipts for the chain, so a dump directory that no receipt names is outside the report.

`datasets delete DATASET_ID` drops the named dataset's server database and removes that dataset's retained dump. Every retained dataset except the selected one is eligible, the initial dataset included, and the command refuses a target before it changes any resource.

| Refused target | The rule that refuses it |
|---|---|
| An id outside the retained chain | The chain the pointer resolves is the authority for what cleanup reaches |
| The selected dataset, and a receipt naming the selected database | The selected dataset is the copy the server reads |
| With `SELECTED_DATASET_ENABLED` false, a receipt naming the database the site serves | The site reads that configured database directly, so it is not a deletable retained copy |
| A returned receipt whose database name is not `ADMIN_DATASET_DATABASE_PREFIX` and its own id joined by an underscore | The derived name is the proof that the receipt describes the server copy |
| A database name on the fixed protected list | The protected names cover databases that no dataset enrollment produced |
| A retained dump that is a symlink or not a regular file | The dump path is confined to the dataset directory of that receipt |

The command reads the pointer and the requested receipt again under the dataset action lock, so a listing printed earlier is presentation rather than delete authority. A deletion removes exactly the named database and that dataset's dump, and it leaves the receipt, the pointer, the selected dataset and every database outside the retained chain in place. A repeated command over the same absent pair reports the same result.

`backups list` prints every regular file beneath `data/backups`, nested files included, in lexical relative-path order, with the size and the last modification time of each file. The listing reads file metadata alone, reports no backups for an absent directory, and creates nothing. A symlinked entry, a special file and a symlinked directory refuse the listing.

`backups delete NAME` removes the one file that relative name identifies under `data/backups`, and the name is the one the listing prints. Empty and absolute names, a backslash, a NUL, an empty, dot or dot-dot segment, a parent that is a symlink or not a directory, and a target that is missing, a symlink or not a file are all refused. Nothing else under the directory changes, and rotation reads and removes no backup file.

The automatic rotation and this cleanup share one drop path, so both drop a database through the same Compose command with the same protected-name check and the same operation timeout. The [Operator menu](/docs/operations/operator-menu.md#cleanup-of-datasets-and-backups) holds the two deletions behind a listing and a confirmation that names the exact dataset or backup file.

## Backups and the chain

Files kept under `data/backups` are outside the dataset chain, and rotation deletes nothing there. The administrative state root must not lie inside that directory.

## Failure outcomes

A failed return leaves the selection in place, retains the returned dump, and writes no receipt, so the return can run again over the retained dump. A failed restore leaves the target database in place. A failed migration changes no data and no file, and a rotation that cannot validate the chain refuses before the first deletion.

The worker's own copy is separate from the server dataset. Its cleanup drops the exact worker database only after the returned dataset receipt and the recorded return snapshot agree.

## Reading the selected dataset

The read-only reports and the hub write resolve the selected dataset and require `SELECTED_DATASET_ENABLED`.

```bash
uv run python scripts/admin.py summary catalogue
uv run python scripts/admin.py summary inference
uv run python scripts/admin.py coverage teaching-text
uv run python scripts/admin.py coverage embedding
uv run python scripts/admin.py coverage inference
uv run python scripts/admin.py hubs
```

The catalogue summary and the coverage reports describe the stored courses, modules, translations, vectors, and inferred prerequisites. `hubs` computes both embedding hub means from the stored chunk vectors and writes the two files that `EMBEDDING_HUB_VECTOR` and `EMBEDDING_OUTCOMES_HUB_VECTOR` in `config/search.toml` name. [Operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) lists four reports: the catalogue summary, teaching-text coverage, embedding coverage and the inference summary. The `coverage inference` command is machine-only.

## Dataset, snapshot, and backup

| Thing | What it is |
|---|---|
| Dataset | One complete database of courses, modules, and derived data |
| Database snapshot | One verified dump of a database, taken when a worker session starts or when it returns |
| Backup | A separate copy kept under `data/backups`, outside the dataset chain |
