# Administration console panels

Each administration console panel reads one fixed route through a typed client and presents the report that route returned.

The panels sit under the console's six tabs, and [Administration console code](/docs/frontend/admin-console.md) describes the separate build, the shared clients, the session flow and the read loops that drive them.

## Panel routes

Every panel reads through one typed client, and each client names one route and one request body.

| Panel group | Read | Kind |
|---|---|---|
| Dashboard | `GET /api/dashboard` | One automatic read in the signed-in shell |
| Preparation stages | `GET /api/preparation/status/{stage}` | One automatic read per stage |
| Preparation reports | `GET /api/preparation/report/{report}` | One automatic read per report |
| Preparation actions | `POST /api/preparation/action` | Explicit |
| Serving artifacts | `POST /api/preparation/serving-artifacts` | Explicit |
| Inference run | `GET /api/inference/status` | Automatic |
| Inference summary panels | `GET /api/inference/summary` | One automatic read shared by four panels, gated by the dashboard |
| Inference actions | `POST /api/inference/action` | Explicit |
| Target decisions | `POST /api/inference/target/read` | Explicit |
| Target decision | `POST /api/inference/target/decision` | Explicit |
| Dataset roles and inventory | `GET /api/datasets` | One automatic read in the signed-in shell, rendered by the Settings panel |
| Dataset role actions | `POST /api/datasets/setup`, `POST /api/datasets/migrate`, `POST /api/datasets/delete`, `POST /api/datasets/copy-to-working` | Explicit |
| Dataset promotion | `POST /api/datasets/copy-to-selected` | Explicit, one newline-delimited stream |
| Command log | `GET /api/logs/commands` | Automatic |
| Session and runtime logs | `GET /api/logs/sessions`, `POST /api/logs/read`, `POST /api/logs/embedding` | Inventory automatic, worker logs on demand |
| Usage | `POST /api/logs/usage` | Automatic for the applied window |
| Configuration | `GET /api/settings/config/files`, `POST /api/settings/config/read` | List automatic, open file automatic |
| Feature switches | `POST /api/settings/config/read` | Automatic read, explicit writes through `POST /api/settings/config/set` |
| Backups | `GET /api/settings/backups`, `POST /api/settings/backups/delete` | List automatic, delete explicit |
| Rebuild | `POST /api/settings/rebuild`, `POST /api/settings/rebuild-admin` | Explicit |
| Worker provisioning | `POST /api/settings/worker/setup`, `POST /api/settings/worker/preflight` | Explicit |
| Feedback inbox | `POST /api/feedback/list` | Automatic for the whole inbox, which the committed search and filters narrow in the browser |
| Feedback image | `POST /api/feedback/attachment` | Explicit per image |
| Feedback deletion | `POST /api/feedback/delete` | Explicit |

## Dashboard

The signed-in shell's one read feeds the tab's five panels. Serving state renders `serving` and `hubs`, with the restart hint only for a hub whose `newer_than_web_start` is true. The three hub rows render only when `serving.embeddings_enabled` is true, and the panel shows the `wording.dashboard.embeddingsOff` note in their place when it is false. The website panel shows `configured_workers` as configured processes and the checkout branch and revision as the checkout identity. The host, database and embedding runtime show their own measured and configured members. The host's CPU usage renders as the aggregate busy share of all CPUs over one short sample, between 0% and 100%. Every nullable fact renders as unknown.

The Dashboard does not report artifact build counts. A successful serving-artifact build on the Data preparation tab reports the paths and counts of the set the site serves. On a site that serves the embedding features it reports the two hub paths with their chunk counts, the packed search group and block counts, the centroid and neighbour counts and the projectable study roots. On a site with them off it reports the catalogue artifact path and the projectable study roots, and states that the switch is off. It also states that the web server reads the artifacts at start and asks for a restart. The separate restart procedure requires the full supervisor.

## Data preparation

Each of the three stage panels reads its own status with an automatic marker. The panel takes its top-level lifecycle, session, revision, active time, rate and ETA as authoritative, and the host row names the stage's execution host, worker for translation and server for ingestion and embedding.

Ingestion shows its response and verified counts, its verification total when the owner supplies one, and its normalized flag. Embedding shows its desired and completed counts and its remaining count as pending plus failed. Translation shows its mirrored worker desired, completed and remaining counts, and its reboot flag reads unknown while the stage reports no worker status.

A successful lifecycle action installs the status it returned through the hook's `apply`, so the panel shows the returned state without another status read. Start, Pause and Resume run at once, and Stop asks for confirmation naming the stage. The four actions are disabled when the shell's inventory read reports no Working dataset, and the tab then shows its working-absent notice while the status rows and marker keep updating. An inventory read that has not succeeded leaves the actions enabled.

The three reports have their own automatic reads. Each read resolves Working first and Selected when Working is absent, names the role in the panel, and renders no report body in a bootstrap state. The catalogue report is the six `CatalogueSummary` counts. The teaching-text report shows one row per field and language with its official, derived, stale and missing counts, one all-representative-fields row that sums each column, and the representative, no-representative, name-only and unembeddable course counts. The embedding report shows one row per coverage entry, whose first column names the field, the uppercase language and the reported origin, plus the report's own total pending, completed and failed counters.

The artifact build posts one empty `POST /api/preparation/serving-artifacts` and reports the returned set. An embeddings-on site returns the artifact and hub paths and its counts, including the projectable study-root count. An embeddings-off site returns the catalogue path and the projectable study-root count, with a statement that the switch is off. The message states that a running web server reads the artifacts at start.

## Inference

The run panel reads its own status with an automatic marker. It shows the cycle from `worker.coverage.cycle_id` when present and unknown otherwise, the current stage, the session, the active time, the supplied top-level rate and ETA, the reboot flag, the preparation step when present, and one line per `worker.stages` entry with its done, total and remaining counts. Start, Pause and Resume run at once, and Stop asks for confirmation naming the run. The four actions are disabled when the shell's inventory read reports no Working dataset, with the tab's working-absent notice shown, while the run rows and marker keep updating.

One `GET /api/inference/summary` read feeds publication diagnostics, coverage, generation identities and failures. The read runs only while the dashboard reports the selection enabled. A `null` selection state shows the automatic reading state in each panel's header marker and no body note. A `false` state renders the disabled note without a report body or an automatic marker, and an `"unavailable"` state renders the dataset-state note the same way.

Diagnostics shows the publication state counts, the candidate counts, the warning count and the three configured policy fields, with the non-local route count under Route other read from either of its two field names. Coverage renders the role strip from the read's resolved role before the retained-server note, then the coverage counts and the summary's own `operator_done_targets`. Generation rows are the coverage `generation_counts` entries alone, with the model, prompt, schema, pipeline, route and target count of each, and each route occupies one line. Each failure row shows its canonical `target_group_id`, stage, attempt count, error type, reason, exhausted flag and creation time from the retained record.

The target decisions input starts empty, and a report appears only after a successful `POST /api/inference/target/read`. The panel shows the dataset id, the canonical group id, the official code, the English name and the current decision, where a null decision reads as NOTHING. The decisions are available only for the identity the read resolved. DONE and FAILED confirm first with the panel's own confirmation text, NOTHING records immediately, and a recorded decision installs the returned report and refreshes the shared summary.

## Logs

The command log reads automatically and renders newest first from a display copy of the report's own oldest-first order. Each row shows the entry's time, fixed command label, exit code, duration, outcome token and the one safe failure line that belongs to it. A login, failed-login or lock event is one of those entries.

The session and runtime panels share one `GET /api/logs/sessions` inventory, so the console discovers the stage sessions once. The session panel initially selects the first listed stage and session and `server-stdout`. It offers `server-stdout` and `server-stderr` for every stage, and `keepalive` and `worker-runner` for the translation and inference stages through the shared picker. The selected server stream and the keepalive file read automatically, and the worker's `runner.log` is read only by the panel's Read control. Selecting another session or source clears the displayed log. The line-count control starts at 200 and shows its `lines` unit.

The runtime panel offers the embedding service's own container log and each listed translation or inference session through the shared picker. The embedding log reads automatically, and a listed session's `runtime.log` is read over the transport only by the panel's Read control.

The usage panel reads one `POST /api/logs/usage` for the applied window, which it initially sets to 24 hours, and its hour control shows its `hours` unit. It shows the window bounds, the total requests, the mean, p95 and p99 duration and one row per returned route with the route's request count and its mean, p95 and p99 duration. A window with no recorded request reports zero requests, an unknown mean, p95 and p99 and no route row, and the panel counts course-exploration requests alone.

## Settings

The configuration panel reads `GET /api/settings/config/files`, and one `POST /api/settings/config/read` of the file the operator selects. It opens no file on arrival and one file at a time. Every key renders as a visible text control, a string key edits its own contents and the other keys edit JSON text, and the open file reads automatically while its drafts match the reported values and no save runs.

Save parses every changed draft before the first request, then saves the changed keys one at a time in the report's own order through `POST /api/settings/config/set`. The first refused key stops the sequence and reports the saved and unsaved counts, and the panel holds the unsaved drafts. A retry saves the refused key and the keys after it. An edit of a draft clears the save summary. Selecting another file fades the detail body in over 180 ms, and the keys stagger into place as their read reports them.

### Dataset roles

The **Datasets** panel renders the shell's one `GET /api/datasets` read. The read runs whether or not the dashboard reports a Selected pointer, so a bootstrap deployment and a stopped database service answer their own typed state, and before its first success every role fact reads unknown.

An enrolled report renders both roles as prominent cards: each card carries its **SELECTED** or **WORKING** tag, the dataset identity and the database, predecessor, recorded receipt head, dump path and artifact presence, with the role action in the card. An absent Working pointer renders an empty Working card with the missing-Working title and hint. A thin rule separates the roles from the retained inventory. The inventory renders cards two per row: each holds the dataset identity, the database, the dump path and the artifact presence, and ends with its controls and its role pills immediately after them, where the delete control would sit. The two-card rows become one card per row before any fact value would wrap, so a value is never clipped. Copy to Working is disabled while a reported stage is busy, and so are the Working row's deletion and the Working migration, while Copy to Selected and the Selected migration are available.

A report that states the dataset state unavailable renders that note in place of the inventory cards and unknown facts on both role cards, and offers no role action. A bootstrap report renders the configured database the site serves and the two available actions. The panel renders copy and delete controls on an inventory row only while the read reports enrolled, so a bootstrap inventory and the interrupted state with an initial receipt but no Selected pointer show no row control.

Each confirmed action posts its own route and reloads the inventory and the dashboard. The promotion posts the streamed route with one component-owned abort signal that the panel aborts on unmount or sign-out, marks each reported step in its five-step list with an indeterminate marker on the current one, appends the rollback step when the owner reports it, and clears the list when the terminal result arrives. A failed or interrupted action shows the owning guidance line and reloads both reads. A state update and a reload stop after unmount, and the server retains the admitted mutation.

The inventory's Working presence is the value the shell passes to the stage panels.

The feature switches panel reads `config/web.toml` and reports `WEB_INFERENCE_ENABLED` and `WEB_EMBEDDINGS_ENABLED`, and each switch writes its own key through `POST /api/settings/config/set`. A switch shows the written position only after the command acknowledged it, and a refused write leaves the value the file holds. A value the file does not report as a boolean renders as an unknown note in its row. A saved switch reports that a rebuild or restart applies it to serving. A saved switch updates the editor's own value of the same key, and an editor save of that file reloads the switches.

The backups panel reads `GET /api/settings/backups` for the actual file names, modification times and sizes. Every listed row offers deletion, the confirmation names the exact listed name, cancelling posts nothing, and confirming closes the dialog and posts that one name through `POST /api/settings/backups/delete`. A successful deletion reloads the listing, and a failed one leaves the row in place and shows the command's failure in the panel. The empty note renders only after a successful report lists no backup file.

The rebuild panel shows the four fixed steps of the site rebuild in their own order, with **Rebuild app** first on the panel's left and **Rebuild admin panel** beside it as a second action with its own confirmation, which states that the action signs all operators out. Pending covers the operation as a whole, and one pending operation disables both actions. The site action posts `POST /api/settings/rebuild` and renders the returned steps and its verified bind. The administration action posts `POST /api/settings/rebuild-admin` and reports a completed build to the shell.

The worker provisioning panel starts with an empty origin branch input and a code-only choice that is off. The choice uses the same switch the feature switches use, and a setup needs a branch before its confirmation. `POST /api/settings/worker/setup` carries exactly that branch and that boolean, and `POST /api/settings/worker/preflight` is the read-only preflight of the panel's own Preflight control. A setup report and a preflight report render separately, each from the report its own command returned, and a request reaches the worker only through an explicit action.

The administration rebuild completes differently from the site rebuild, because the backend that answered it restarts next. The panel reports a successful administration build to `App` through the callback the shell passes down to the Settings tab. `App` then clears the session, the failure and every protected tab tree and shows `SignIn` with no session and the restart notice, so no session request reaches the process that is restarting. The next credential submission on that screen reads `GET /auth/session` once for a fresh anonymous session and posts the login over that session's CSRF token. A failed administration build renders the command's own safe failure in the panel and leaves the protected session, its reports and its drafts in place.

## Feedback

The feedback panel reads `POST /api/feedback/list` once for the whole inbox and narrows that report in the browser. The search field and the **Filters** block commit on **Apply**. Committing changes only the rendered submissions and issues no further read. The block holds one labelled picker per configured select field in the feedback definition's order, so any number of configured fields wraps into rows instead of widening the toolbar, and it folds open and closed in place. **Filters** always shows the number of selected filters, including zero, and **Clear filters** inside the block resets every picker without closing the block. Its row stays in the layout, so the block keeps its height as selections appear and clear. **All** is the absent filter value. The committed search is a literal case-insensitive substring of every current text and textarea answer, ranked by the earliest matching text field in the feedback definition's order, then newest first. The automatic listing read refreshes the whole inbox.

Each submission shows the current feedback definition's fields in one ordered pass. A text answer renders as one escaped row, a message answer as a scrollable read-only textarea, a select answer as its configured English option label, the configured placeholder when unset, or the stored value as text when the current options do not hold it, and an attachment answer as its configured label beside one button per stored image, labelled with that image's submitted filename, in the field's own position. An image field with no stored image renders no row. An answer or attachment whose field the feedback definition does not name is left out. The identity, submission time, current publication outcome label, **Open GitHub issue** link, fixed failure description and **Delete** sit outside the answer order. The submitted time and its date value keep a wider gap.

The outcome label is **Private**, **GitHub publication pending**, **Issue created**, **Issue created with incomplete attachments**, **Publication failed before issue creation** or **Publication outcome unconfirmed**. The link appears when the stored record carries a created issue link. A fixed failure description appears when the record carries one.

Each attachment button reads `POST /api/feedback/attachment` with both the submission and attachment identities, and renders the returned base64 content as one bounded image whose accessible name carries the submitted filename. The read runs only on that explicit control and not on a listing poll. The control shows the filename and swaps to **Reading…** while that read runs. Pressing the control of a rendered image drops that image and returns the control to its place, and rendering it again reads it once more. Only PNG and JPEG images are stored, so every attachment carries a control.

Every control occupies one fixed row at the top in the feedback definition's order, and a rendered control is highlighted rather than moving. Images unfold below that row, each with its filename beneath it and a little padding after the caption, so a rendered image is always identified and toggling one never reorders the controls. A row holding images centers its label against that top control row.

One **Download attachments (n)** control per submission, in the entry header beside **Delete**, reads every stored image of that submission and saves them together as one `feedback-<identity>.zip` archive, each image under its submitted filename and a repeated name made distinct. Those reads also run only on that explicit control.

The listing enters with one short staggered rise per submission when it loads. Deleting opens a confirmation, which enters and leaves with one short animation, that names the exact feedback identity and submission time and states that it removes the local feedback and stored images without deleting a GitHub issue or GitHub-hosted images. Cancelling posts nothing. Confirming posts only that feedback identity, and a success reloads the listing while a failure retains the row and shows the command's failure.

## Tests

| Test file | Covers |
|---|---|
| `admin-web/src/shared/StagePanel.test.ts` | The status a stage action returns without another read, and the disabled action row without a Working dataset |
| `admin-web/src/features/datasets/Datasets.test.ts` | The reduced Settings dataset panel and the Working dataset and backup deletion confirmations |
| `admin-web/src/features/datasets/DatasetCopy.test.ts` | The reported promotion steps before completion and its terminal outcomes |
| `admin-web/src/features/settings/Backups.test.ts` | The empty note and the failure of a held first read |
| `admin-web/src/features/settings/Configuration.test.ts` | A partial file save that stops at the first refused key |
| `admin-web/src/features/settings/Rebuild.test.ts` | Both rebuild confirmations and the administration report |
| `admin-web/src/features/logs/Logs.test.ts` | The on-demand worker log read |
| `admin-web/src/features/feedback/Feedback.test.ts` | The feedback deletion confirmation under cancel, confirm and failure |
| `tests/admin_web/test_routes.py` | Route admission and the automatic-read command-log rule, including the administration rebuild sequence |
| `tests/admin_web/test_command_log_read.py` | The command-log read's order and its file handling |

`StagePanel.test.ts` proves that a stage action's returned status shows without another status request, and that an ingestion panel without a Working dataset disables all four actions, reads one status and posts none. `Logs.test.ts` proves that the worker log reads nothing on mount, on a poll interval or on a selection change, reads once for the explicit control, and performs exactly one local read and no worker read on a worker-to-local transition.

`Datasets.test.ts` covers the reduced Settings dataset panel and the backup cleanup panel, each posting only the confirmed listed target and posting nothing when it is cancelled. The panel renders the **SELECTED** and **WORKING** role cards and inventory cards with the retained dump and artifact facts, and a confirmed command failure closes the dialog, leaves the row in place and shows the owning guidance line. `DatasetCopy.test.ts` holds one promotion stream open and proves that the owner's reported steps render before the terminal result, that the successful result clears the step list and reloads the inventory and dashboard without a separate receipt block, and that a failed terminal result shows its own guidance line and reloads the inventory.

`Feedback.test.ts` covers the feedback panel's deletion confirmation: the dialog names only the chosen feedback identity and time, cancelling posts nothing, confirming posts only that identity and reloads the listing, and a confirmed command failure retains the row and shows the failure without reloading.

`Backups.test.ts` holds the first read and proves that it states neither an empty inventory nor a failure before it completes, then the empty note after a successful empty report or its own failure alone.

`Configuration.test.ts` proves a partial file save over typed synthetic values, which stops at the first refused key, reports the saved and unsaved counts without rendering a value, retries the refused key and the keys after it, and clears the saved summary when a draft changes.

`Rebuild.test.ts` proves both confirmations: a cancelled one posts nothing, a confirmed one posts only its own route, and the administration action alone reports the completed build to the shell.

`tests/admin_web/test_routes.py` maps every feature route to one admitted request, one argv and one transient outcome, for success and for a checked failure, with and without the console's automatic-read header. The four summary routes carry the resolved role, a failed request carries its owning guidance line, a marked successful read route omits its command-log entry, while a failed read and every action or manual-only route append theirs, and the retained entry holds none of the request-supplied values.

The administration rebuild route proves its build-then-queue sequence, its one build-failure entry with no restart call, its intact build response beside a queued restart failure, and the restart that runs only after the final body send completes.

`tests/admin_web/test_command_log_read.py` covers the `logs commands` machine command, which prints the newest configured entries oldest first from a file that holds more, creates no file for an absent log and rewrites none for a present one.
