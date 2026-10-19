# Data preparation

The Data preparation tab holds the ingestion, translation and embedding stages with their controls, and the three reports over the selected dataset.

![The Data preparation tab with the three stage panels above the catalogue summary, teaching-text coverage and embedding coverage reports](/docs/screenshots/admin-console-data-preparation.png)

## The stage panels

The tab places the three stage panels in one row. Each panel reads its own status on the automatic interval and shows the same rows.

| Row | Meaning |
|---|---|
| **state** | The lifecycle state of the stage. |
| **session** | The identity of the current session. It reads **unknown** when the stage is idle. |
| **revision** | The checkout revision the session recorded. It reads **unknown** when the stage is idle. |
| **host** | **server** for ingestion and embedding, and **worker** for translation. |
| **active time** | The time the stage spent running, without the idle time between runs. |
| **rate** | The measured work per second. It reads **unknown** when no rate is measured. |
| **ETA** | The projected time to the end of the work. It reads **unknown** when no estimate exists. |

| State | Meaning |
|---|---|
| **idle** | No run is active. The stage holds the progress it recorded and reports no session identity. |
| **starting** | The stage prepares the run and launches it. |
| **running** | The run is working. |
| **paused** | The run ended at a checkpoint, and the session is held for a resume. |
| **stopped** | The stop ended the run, and the stage finalizes the work. |
| **completed** | The work of the session finished. |
| **failed** | The run ended with an error. |
| **interrupted** | A stage that was starting or running has no live process. |

The status read reports a stage that was starting or running with no live process as **interrupted**.

![The Ingestion stage panel in the idle state, with unknown session and revision, the server host, zero active time, unknown rate and ETA, and the Start, Pause, Resume and Stop controls](/docs/screenshots/admin-console-stage-panel.png)

### What each stage counts

Ingestion shows **responses**, **verified responses**, **verification total** and **normalized**. The **verification total** row appears when the source reports a total, and a progress bar then shows verified responses of that total. **normalized** reads **yes** or **no**.

Embedding shows **desired**, **completed** and **remaining**. The remaining count is the pending chunks and the failed chunks together, and a progress bar shows completed chunks of the desired chunks.

Translation shows **desired**, **completed**, **remaining** and **reboot due**. The counts and the flag come from the last worker status the session recorded, and the panel's read does not contact the worker. Before the stage holds a worker status, each of them reads **unknown**. A progress bar shows completed of desired when both counts are known.

### The action row

Each stage panel has **Start**, **Pause**, **Resume** and **Stop**.

| Action | What it does |
|---|---|
| **Start** | Begins a fresh session, or continues the session the stage retained. |
| **Pause** | Ends the run at its next checkpoint and holds the session for a resume. |
| **Resume** | Continues the session the stage retained. |
| **Stop** | Ends the run, finalizes the work it finished, releases the resources the run started and returns the stage to idle. |

Only **Stop** asks for confirmation. Its dialog names the stage, for example **Stop Ingestion** with **Stop the Ingestion stage.** **Cancel**, Escape and a click outside the dialog close it and run nothing. The other three actions start without a confirmation.

While an action runs, the four buttons of that panel are disabled. The panel then shows the status the action returned, and a failed action shows a failure message in the same panel. A successful stop of translation also returns the worker's finished copy as the selected dataset, and [Worker sessions](/docs/operations/worker-sessions.md#pause-stop-and-the-return) describes the return.

## The reports

Below the stages are the **Catalogue summary**, **Teaching-text coverage** and **Embedding coverage** panels. Each reads its own command on the automatic interval, so its marker shows **auto** and the time since the last successful read.

### Catalogue summary

The panel gives six counts of the selected dataset: **Curriculum periods**, **Canonical courses**, **Active courses**, **Course versions**, **Canonical modules** and **Module versions**. **Canonical courses** and **Canonical modules** count each course and module once, and the version rows count their official versions.

### Teaching-text coverage

The table has one row for each field and language of the [representative versions](/docs/reference/glossary.md#courses-and-the-catalogue), and an **All representative fields** row that sums each column.

| Column | Meaning |
|---|---|
| **Scope** | The field and language of the row. |
| **Official** | Text the university published. |
| **Derived** | A translation. |
| **Stale** | A translation whose source text changed. A stale translation is never used. |
| **Missing** | No effective text for the field and language. |

Under the table are four course counts. **Representative courses** counts the courses with a representative version, and **Courses without a representative** counts the courses with none. **Name-only courses** counts the courses whose representative version has a name but no content or learning outcomes in either language. **Unembeddable courses** counts the courses whose representative version has no effective name, content or learning outcomes in either language.

### Embedding coverage

The table has one row for each field, language and origin, and a **Total** row. Its columns are **Field, language, origin**, **pending**, **completed** and **failed**. The first column names the field, the language and the origin the report gives for the chunk. The counts are chunks of the selected dataset.

**Write hubs** computes both hubs from the current chunks and writes the two files that hold them. A dataset whose embedding coverage is incomplete fails before either file is written. A successful write names both files and the chunk count behind each hub, and it states that loading the hubs requires a web restart. The write starts at once and asks for no confirmation.

![The Embedding coverage panel with a row for each field, language and origin, a Total row and the Write hubs button](/docs/screenshots/admin-console-embedding-coverage.png)

The **Write hubs** button sits below the coverage table.

A web server whose site serves the embedding features reads the two hub files when its process starts and holds those values while it runs. A restart is therefore what loads the written hubs, and search and comparison use the written values after that restart. The [Operator menu](/docs/operations/operator-menu.md#writing-the-hubs) describes the same write for the command line.

## When a read fails

A failed stage status leaves the rows of the last successful read in place and shows the failure. A stage panel that has no successful read shows its heading, its **no read** marker and no rows. A report with no successful read shows its heading, the failure and **no read**, while a failure after a successful read leaves the last report in place. The next successful read clears the failure.
