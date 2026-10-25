# Administration console panels

Each administration console panel reads one fixed route through a typed client and presents the report that route returned.

The panels sit under the console's five tabs, and [Administration console code](/docs/frontend/admin-console.md) describes the separate build, the shared clients, the session flow and the read loops that drive them.

## Panel routes

Every panel reads through one typed client, and each client names one route and one request body.

| Panel group | Read | Kind |
|---|---|---|
| Dashboard | `GET /api/dashboard` | One automatic read in the signed-in shell |
| Preparation stages | `GET /api/preparation/status/{stage}` | One automatic read per stage |
| Preparation reports | `GET /api/preparation/report/{kind}` | One automatic read per report |
| Inference run | `GET /api/inference/status` | Automatic |
| Inference summary panels | `GET /api/inference/summary` | One automatic read shared by four panels, gated by the dashboard |
| Target decisions | `POST /api/inference/target/read` | Explicit |
| Dataset cleanup | `GET /api/inference/datasets` | Automatic, gated by the dashboard |
| Command log | `GET /api/logs/commands` | Automatic |
| Session and runtime logs | `GET /api/logs/sessions`, `POST /api/logs/read`, `POST /api/logs/embedding` | Inventory automatic, worker logs on demand |
| Usage | `POST /api/logs/usage` | Automatic for the applied window |
| Configuration | `GET /api/settings/config/files`, `POST /api/settings/config/read` | List automatic, open file automatic |
| Feature switches | `POST /api/settings/config/read` | Automatic read, explicit writes through `POST /api/settings/config/set` |
| Backups | `GET /api/settings/backups` | Automatic |
| Rebuild | `POST /api/settings/rebuild`, `POST /api/settings/rebuild-admin` | Explicit |
| Settings dataset | Shared dashboard read, `GET /api/inference/datasets` | Listing gated by the dashboard |
| Worker provisioning | `POST /api/settings/worker/setup`, `POST /api/settings/worker/preflight` | Explicit |

## Dashboard

The signed-in shell's one read feeds the tab's five panels. Serving state renders `serving` and `hubs`, with the restart hint only for a hub whose `newer_than_web_start` is true. The website panel shows `configured_workers` as configured processes and the checkout branch and revision as the checkout identity. The host, database and embedding runtime show their own measured and configured members. The host's CPU usage renders as the aggregate busy share of all CPUs over one short sample, between 0% and 100%. Every nullable fact renders as unknown.

## Data preparation

Each of the three stage panels reads its own status with an automatic marker. The panel takes its top-level lifecycle, session, revision, active time, rate and ETA as authoritative, and the host row names the stage's execution host, worker for translation and server for ingestion and embedding.

Ingestion shows its response and verified counts, its verification total when the owner supplies one, and its normalized flag. Embedding shows its desired and completed counts and its remaining count as pending plus failed. Translation shows its mirrored worker desired, completed and remaining counts, and its reboot flag reads unknown while the stage reports no worker status.

A successful lifecycle action installs the status it returned through the hook's `apply`, so the panel shows the returned state without another status read. Start, Pause and Resume run at once, and Stop asks for confirmation naming the stage.

The three reports have their own automatic reads. The catalogue report is the six `CatalogueSummary` counts. The teaching-text report shows one row per field and language with its official, derived, stale and missing counts, one all-representative-fields row that sums each column, and the representative, no-representative, name-only and unembeddable course counts. The embedding report shows one row per coverage entry, whose first column names the field, the uppercase language and the reported origin, plus the report's own total pending, completed and failed counters.

The hub write posts one empty `POST /api/preparation/hubs`, reports the returned file paths and chunk counts, and states that a running web server reads the hubs at start.

## Inference

The run panel reads its own status with an automatic marker. It shows the cycle from `worker.coverage.cycle_id` when present and unknown otherwise, the current stage, the session, the active time, the supplied top-level rate and ETA, the reboot flag, the preparation step when present, and one line per `worker.stages` entry with its done, total and remaining counts. Start, Pause and Resume run at once, and Stop asks for confirmation naming the run.

One `GET /api/inference/summary` read feeds publication diagnostics, coverage, generation identities and failures, and the coverage panel carries the retained-server note. The read runs only while the dashboard reports the selection enabled. A `null` selection state shows the automatic reading state in each panel's header marker and no body note. A `false` state renders the disabled note without a report body or an automatic marker.

Diagnostics shows the publication state counts, the candidate counts, the warning count and the three configured policy fields, with the non-local route count under Route other read from either of its two field names. Coverage shows the coverage counts and the summary's own `operator_done_targets`, with the retained-server note and the coverage cycle and stage. Generation rows are the coverage `generation_counts` entries alone, with the model, prompt, schema, pipeline, route and target count of each, and each route occupies one line. Each failure row shows its canonical `target_group_id`, stage, attempt count, error type, reason, exhausted flag and creation time from the retained record.

The target decisions input starts empty, and a report appears only after a successful `POST /api/inference/target/read`. The panel shows the dataset id, the canonical group id, the official code, the English name and the current decision, where a null decision reads as NOTHING. The decisions are available only for the identity the read resolved. DONE and FAILED confirm first with the panel's own confirmation text, NOTHING records immediately, and a recorded decision installs the returned report and refreshes the shared summary.

One `GET /api/inference/datasets` read lists the chain in selected-first order and runs only while the dashboard reports the selection enabled. The listing shows the dataset id, the named database and the dump path. Every non-selected row offers deletion, the selected row shows the selected marker in place of that control, and the confirmation names the exact dataset id and database name. Cancelling posts nothing, and confirming closes the dialog and posts only that listed dataset id. A successful deletion refreshes the listing, and a failed one leaves the row in place and shows the command's failure in the panel. A `false` selection state renders the disabled note in place of the listing, its rows and any open confirmation.

## Logs

The command log reads automatically and renders newest first from a display copy of the report's own oldest-first order. Each row shows the entry's time, fixed command label, exit code, duration, outcome token and the one safe failure line that belongs to it. A login, failed-login or lock event is one of those entries.

The session and runtime panels share one `GET /api/logs/sessions` inventory, so the console discovers the stage sessions once. The session panel initially selects the first listed stage and session and `server-stdout`. It offers `server-stdout` and `server-stderr` for every stage, and `keepalive` and `worker-runner` for the translation and inference stages through the shared picker. The selected server stream and the keepalive file read automatically, and the worker's `runner.log` is read only by the panel's Read control. Selecting another session or source clears the displayed log. The line-count control starts at 200 and shows its `lines` unit.

The runtime panel offers the embedding service's own container log and each listed translation or inference session through the shared picker. The embedding log reads automatically, and a listed session's `runtime.log` is read over the transport only by the panel's Read control.

The usage panel reads one `POST /api/logs/usage` for the applied window, which it initially sets to 24 hours, and its hour control shows its `hours` unit. It shows the window bounds, the total requests, the mean duration and one row per returned route. A window with no recorded request reports zero requests, an unknown mean and no route row, and the panel counts course-exploration requests alone.

## Settings

The configuration panel reads `GET /api/settings/config/files`, and one `POST /api/settings/config/read` of the file the operator selects. It opens no file on arrival and one file at a time. Every key renders as a visible text control, a string key edits its own contents and the other keys edit JSON text, and the open file reads automatically while its drafts match the reported values and no save runs.

Save parses every changed draft before the first request, then saves the changed keys one at a time in the report's own order through `POST /api/settings/config/set`. The first refused key stops the sequence and reports the saved and unsaved counts, and the panel holds the unsaved drafts. A retry saves the refused key and the keys after it. An edit of a draft clears the save summary. Selecting another file fades the detail body in over 180 ms, and the keys stagger into place as their read reports them.

The feature switches panel reads `config/web.toml` and reports `WEB_INFERENCE_ENABLED` and `WEB_EMBEDDINGS_ENABLED`, and each switch writes its own key through `POST /api/settings/config/set`. A switch shows the written position only after the command acknowledged it, and a refused write leaves the value the file holds. A value the file does not report as a boolean renders as an unknown note in its row. A saved switch reports that a rebuild or restart applies it to serving. A saved switch updates the editor's own value of the same key, and an editor save of that file reloads the switches.

The backups panel reads `GET /api/settings/backups` for the actual file names, modification times and sizes. Every listed row offers deletion, the confirmation names the exact listed name, cancelling posts nothing, and confirming closes the dialog and posts that one name through `POST /api/settings/backups/delete`. A successful deletion reloads the listing, and a failed one leaves the row in place and shows the command's failure in the panel. The empty note renders only after a successful report lists no backup file.

The rebuild panel shows the four fixed steps of the site rebuild in their own order, with **Rebuild app** first on the panel's left and **Rebuild admin panel** beside it as a second action with its own confirmation, which states that the action signs all operators out. Pending covers the operation as a whole, and one pending operation disables both actions. The site action posts `POST /api/settings/rebuild` and renders the returned steps and its verified bind. The administration action posts `POST /api/settings/rebuild-admin` and reports a completed build to the shell.

The dataset panel reads the shell's shared dashboard report for the pointer, the selection state, the recorded head and the live database facts, and one `GET /api/inference/datasets` read for the selected entry, which runs only while that report says the selection is enabled. While the state is `null`, the panel's header marker shows the automatic reading state and no body note. A `false` state renders the disabled note in place of the selected-chain rows, and a dashboard failure renders its own failure.

The database and head facts, the two confirmed actions and their own receipts, verifications and failures render throughout. The recorded receipt revision and the live database head render as separate observations. `POST /api/settings/datasets/setup` and `POST /api/settings/datasets/migrate` are two separately confirmed actions, each renders the receipt or the verification its own command returned, and each reloads the listing and the shared report on success.

The worker provisioning panel starts with an empty origin branch input and a code-only choice that is off. The choice uses the same switch the feature switches use, and a setup needs a branch before its confirmation. `POST /api/settings/worker/setup` carries exactly that branch and that boolean, and `POST /api/settings/worker/preflight` is the read-only preflight of the panel's own Preflight control. A setup report and a preflight report render separately, each from the report its own command returned, and a request reaches the worker only through an explicit action.

The administration rebuild completes differently from the site rebuild, because the backend that answered it restarts next. The panel reports a successful administration build to `App` through the callback the shell passes down to the Settings tab. `App` then clears the session, the failure and every protected tab tree and shows `SignIn` with no session and the restart notice, so no session request reaches the process that is restarting. The next credential submission on that screen reads `GET /auth/session` once for a fresh anonymous session and posts the login over that session's CSRF token. A failed administration build renders the command's own safe failure in the panel and leaves the protected session, its reports and its drafts in place.

## Tests

| Test file | Covers |
|---|---|
| `admin-web/src/shared/StagePanel.test.ts` | The status a stage action returns, shown without another read |
| `admin-web/src/features/inference/DatasetCleanup.test.ts` | The dataset and backup deletion confirmations |
| `admin-web/src/features/settings/Backups.test.ts` | The empty note and the failure of a held first read |
| `admin-web/src/features/settings/Configuration.test.ts` | A partial file save that stops at the first refused key |
| `admin-web/src/features/settings/Rebuild.test.ts` | Both rebuild confirmations and the administration report |
| `admin-web/src/features/logs/Logs.test.ts` | The on-demand worker log read |
| `tests/admin_web/test_routes.py` | Route admission and the automatic-read command-log rule, including the administration rebuild sequence |
| `tests/admin_web/test_command_log_read.py` | The command-log read's order and its file handling |

`StagePanel.test.ts` proves that a stage action's returned status shows without another status request. `Logs.test.ts` proves that the worker log reads nothing on mount, on a poll interval or on a selection change, reads once for the explicit control, and performs exactly one local read and no worker read on a worker-to-local transition.

`DatasetCleanup.test.ts` covers the deletion confirmation of the dataset cleanup panel and the backup cleanup panel, each posting only the confirmed listed target and posting nothing when it is cancelled. A confirmed command failure closes the dialog, leaves the row in place, shows the failure and reloads no listing.

`Backups.test.ts` holds the first read and proves that it states neither an empty inventory nor a failure before it completes, then the empty note after a successful empty report or its own failure alone.

`Configuration.test.ts` proves a partial file save over typed synthetic values, which stops at the first refused key, reports the saved and unsaved counts without rendering a value, retries the refused key and the keys after it, and clears the saved summary when a draft changes.

`Rebuild.test.ts` proves both confirmations: a cancelled one posts nothing, a confirmed one posts only its own route, and the administration action alone reports the completed build to the shell.

`tests/admin_web/test_routes.py` maps every feature route to one admitted request, one argv and one transient outcome, for success and for a checked failure, with and without the console's automatic-read header. A marked successful read route omits its command-log entry, while a failed read and every action or manual-only route append theirs, and the retained entry holds none of the request-supplied values.

The administration rebuild route proves its build-then-queue sequence, its one build-failure entry with no restart call, its intact build response beside a queued restart failure, and the restart that runs only after the final body send completes.

`tests/admin_web/test_command_log_read.py` covers the `logs commands` machine command, which prints the newest configured entries oldest first from a file that holds more, creates no file for an absent log and rewrites none for a present one.
