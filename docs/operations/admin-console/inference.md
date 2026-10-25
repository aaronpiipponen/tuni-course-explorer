# Inference

The Inference tab holds the inference run, its publication reports, the target decisions and the dataset cleanup for the selected dataset.

![The Inference tab with the inference run, its publication and coverage reports, the generation identities, and the target decisions, dataset cleanup and failures panels](/docs/screenshots/admin-console-inference.png)

## The inference run

The **Inference run** panel mirrors the worker's progress and holds the controls for the run. Its status reads automatically, and the marker shows the time since the last successful read.

| Row | Meaning |
|---|---|
| **cycle** | The worker's coverage cycle, or **unknown** when the worker reports none. |
| **stage** | The stage the worker reports, or the run's lifecycle state when the worker reports none. |
| **session** | The session identity, or **unknown** when no session is active. |
| **active time** | The time the run has spent running. |
| **rate** | The measured work per second, or **unknown** when no rate is measured. |
| **ETA** | The projected time to the end of the work, or **unknown** when no estimate exists. |
| **reboot due** | Whether the worker reports that a reboot is due. It reads **unknown** while the report holds no worker status. |
| **preparation** | The preparation step of the run, shown while a step is reported. |

Below the rows, one line per reported stage shows the stage name, a progress bar and the done, total and remaining counts.

## The lifecycle actions

The run offers **Start**, **Pause**, **Resume** and **Stop**.

Only **Stop** asks for confirmation. Its dialog names the inference run, and **Cancel**, Escape and a click outside the dialog close it and run nothing. The other three actions run at once.

While an action runs, the four controls are disabled. A successful action shows the status it returned, and a failed action shows its failure in the panel.

The run starts the inference stage on the worker. [Worker sessions](/docs/operations/worker-sessions.md) describes the worker session, its copy of the dataset and the return.

## When the selected dataset is not enabled

The report panels and the dataset cleanup depend on the selected dataset. When the site reports that dataset as not enabled, they show **The selected dataset is not enabled on this site.** in place of their rows. The console reads no summary and no dataset listing in that state.

The inference run reads its status independently of the selection state.

## Publication diagnostics

The **Publication diagnostics** panel reports the counts of the publication and the policies in force. The counts cover the targets eligible for the publication.

| Row | Meaning |
|---|---|
| **selected** | The target courses selected for the publication. |
| **processed** | The target courses the run processed. |
| **accepted** | The target courses whose proposal the publication uses. |
| **published** | The target courses whose inferred set is published. |
| **route local** | The targets the publication routed to the local route. |
| **route other** | The targets the publication routed outside the local route. |
| **packet candidates observed** | The packet candidates the report observed. |
| **packet candidates expected** | The packet candidates the report expected. |
| **transitive warnings** | The number of transitive warnings in the publication report. |
| **routing policy** | The configured routing policy. |
| **recommendation policy** | The configured recommendation policy. |
| **finding filter policy** | The configured finding filter policy. |

## Inference coverage

The **Coverage** panel counts the inferred results the selected dataset retains on the server.

| Row | Meaning |
|---|---|
| **eligible targets** | The target courses eligible for inferred results. |
| **retained complete** | The targets with a complete retained result, including the targets an operator marked DONE. |
| **published** | The targets whose retained result is part of the current publication. |
| **uncovered** | The eligible targets with no complete retained result. |
| **pending** | The targets that wait for a result. |
| **failed** | The targets with a recorded failure. |
| **operator DONE** | The targets an operator marked DONE. |
| **equivalence groups** | The equivalence groups in the retained result. |
| **proposal rows** | The proposal rows the dataset retains. |
| **cycle** | The retained coverage cycle, or **unknown**. |
| **stage** | The retained stage, or **unknown**. |

## Generation identities

The **Generation identities** panel groups the retained results by the run that produced them.

| Column | Meaning |
|---|---|
| **Model** | The model identity. |
| **Prompt** | The prompt version. |
| **Schema** | The schema version. |
| **Pipeline** | The pipeline version. |
| **Route** | The route that produced the result. |
| **Targets** | The number of target courses in the group. |

A target an operator marked DONE adds no row, because it carries no generation identity.

## Target decisions

The **Target decisions** panel records one decision for one canonical target: **NOTHING**, **DONE** or **FAILED**. Before a lookup, it shows **Search for a target identity before recording a decision.**

![The Target decisions panel with an empty canonical target group id, the prompt to search, the NOTHING, DONE and FAILED choices and the disabled Record decision button](/docs/screenshots/admin-console-inference-target-decisions.png)

1. Enter the canonical target group identity in the input and select **Search**.
2. The panel shows the dataset, the canonical group, the official code, the English name and the recorded decision.
3. Choose **NOTHING**, **DONE** or **FAILED**.
4. Select **Record decision**.

**NOTHING** records immediately. **DONE** and **FAILED** open a confirmation first. The DONE confirmation states that the target course is completed with no inferred output. The FAILED confirmation states that the decision is terminal and that the cycle is incomplete while the decision is in place.

A decision applies only to the identity the lookup resolved. Editing the input after a lookup shows **The input differs from the recorded identity.** and disables the decision controls until **Search** runs again. A recorded decision replaces the shown decision and refreshes the summary panels.

The lookup requires the selected-dataset switch `SELECTED_DATASET_ENABLED` in `config/database.toml` enabled, and the selected database at the migration head. The decision additionally requires a verified returned dataset and every stage idle. A refusal appears in the panel.

## Dataset cleanup

The **Dataset cleanup** panel lists the retained datasets that hold a database or a retained dump, and deletes one that the site does not serve.

| Column | Meaning |
|---|---|
| **Dataset** | The dataset identity. |
| **Database** | The database name. |
| **Dump** | The retained dump path, or **unknown** when no dump is retained. |

The selected dataset is listed first and carries the **selected** marker in place of the **Delete** control. Every other row offers **Delete**.

**Delete** opens the **Delete retained dataset** dialog, which names the dataset identity and the database name. **Cancel**, Escape and a click outside the dialog close it and change nothing. **Confirm** drops the database and removes the retained dump, then the listing reloads. A failed deletion leaves the row and shows the failure in the panel.

## Failures

The **Failures** panel lists the failure records the selected dataset retains.

| Column | Meaning |
|---|---|
| **Target** | The canonical target group identity. |
| **stage** | The stage that failed. |
| **Attempts** | The number of attempts. |
| **Error** | The error type. |
| **Reason** | The recorded reason. |
| **Exhausted** | **yes** when the record is marked exhausted, otherwise **no**. |
| **Created** | When the record was created, in UTC to the whole minute. |

## When a read fails

A failed read shows its failure in the panel it belongs to, or once above the panels when the read fills several of them. A failed read leaves the last successful report and its marker in place, and the next successful read clears the failure. A panel with no successful read shows no rows.

The [Administration console](/docs/operations/admin-console/README.md) describes the sign-in, the header, the confirmation dialog and the read markers.
