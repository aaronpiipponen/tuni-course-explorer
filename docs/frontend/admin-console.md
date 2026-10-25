# Administration console code

The administration console code is a separate React application, and its typed clients run fixed administration commands over one signed-in session.

The [Administration console](/docs/operations/admin-console/README.md) how-to states the tabs and their actions, and [Console access and records](/docs/operations/admin-console/access-and-records.md) states the backend's admission, sessions and records.

## The separate build

The console is a React and TypeScript application in `admin-web/`, with its own manifest, its own lock file, its own TypeScript and Vite configuration and its own build into `admin-web/dist`. It depends on `react`, `react-dom` and `@radix-ui/react-dialog` alone, and its build emits every referenced asset under `dist/assets`. The course-exploration application is a separate React application in `web/` with its own manifest and its own build, and no module is shared between the two.

`admin-web/index.html` declares a 980 px layout viewport. A phone lays the CSS out at that width and scales the result to the screen, so the console uses its narrow desktop layout and its responsive rules at that width.

`src/course_explorer_admin_web/frontend.py` serves that build. `register_frontend` answers `GET` and `HEAD /` with the build's `index.html` and no-store caching, and mounts `/assets` over the build's assets directory with the default refusal of symlinked entries. No other document, catch-all route, filesystem browser or source map is registered, so an absent build fails when it is requested.

The poll interval, the App address and the repository address come from the site. `ADMIN_WEB_POLL_SECONDS`, `ADMIN_WEB_APP_URL` and `ADMIN_WEB_REPOSITORY_URL` of `config/admin_web.toml` are validated by `AdminWebSettings` in `src/course_explorer/config.py`, and `src/course_explorer_admin_web/routes/auth.py` reports them as `SessionReport.poll_seconds`, `SessionReport.app_url` and `SessionReport.repository_url`, so the console reads them once with its own session. The frontend `SessionReport` projection in `admin-web/src/api/types.ts` carries `authenticated`, `csrf_token`, `poll_seconds`, `app_url` and `repository_url`, the fields the console consumes. The elapsed time a read marker shows is the browser's own measurement from its last successful read.

## Module ownership

| Module | Owns |
|---|---|
| `admin-web/src/main.tsx` | The browser bootstrap that mounts `App` over the page root |
| `admin-web/src/app/App.tsx` | The in-memory session, its bootstrap, the one refusal each authenticated session consumes, the sign-out transition and the sign-in screen a completed administration rebuild leaves |
| `admin-web/src/app/SignedInConsole.tsx` | The signed-in header, the tab selection, the five mounted tab trees and one shared server-status read whose selection state gates the dataset-dependent reads |
| `admin-web/src/app/SignIn.tsx` | One credential attempt over the CSRF token of the session the shell supplies, or of the one session the screen reads when the shell supplies none |
| `admin-web/src/app/TabBar.tsx` | The five tabs of the console |
| `admin-web/src/api/http.ts` | The same-origin transport, `ApiError`, `CommandFailure`, the admission classifier `handleAdmissionFailure` and the command-envelope decoding |
| `admin-web/src/api/types.ts` | The consumed DTO fields of every panel |
| `admin-web/src/api/auth.ts`, `dashboard.ts`, `preparation.ts`, `inference.ts`, `logs.ts`, `settings.ts` | The typed clients, one function per fixed command |
| `admin-web/src/shared/usePanelRead.ts` | One enabled panel's automatic read loop, its page-visibility lifecycle, its explicit reload and the action-result apply that installs a returned report |
| `admin-web/src/shared/useDemandRead.ts` | One panel's explicit read, which runs only when the operator asks for it |
| `admin-web/src/shared/AutoMarker.tsx` | The elapsed read marker of one panel, automatic or on demand |
| `admin-web/src/shared/AnimatedPanelBody.tsx` | One panel body whose viewport height follows its measured content with the console's transition |
| `admin-web/src/shared/Panel.tsx` | The panel box, its measured body, its row list, its table with its optional scroll class and its failure notice |
| `admin-web/src/shared/StagePanel.tsx` | One preparation stage panel and the shared lifecycle action row |
| `admin-web/src/shared/ConfirmDialog.tsx` | The one confirmation dialog over `@radix-ui/react-dialog`, whose content is centered inside the fixed overlay |
| `admin-web/src/shared/Picker.tsx` | The one styled choice list behind a trigger, its placement beside the trigger, and its close on a select, an outside press or Escape |
| `admin-web/src/shared/Switch.tsx` | The one boolean switch shared by the feature switches and the other boolean choices |
| `admin-web/src/shared/icons.tsx` | The immutable SVG marks of the interface controls, including the GitHub mark |
| `admin-web/src/shared/format.ts` | The measured and nullable fact presentation, with the relative-age text taken from `wording.ts` |
| `admin-web/src/shared/wording.ts` | Every English interface string the console renders |
| `admin-web/src/styles/admin.css` | The palette, the shell, the panels and their transitions, the tables, the log scroll boxes, the configuration rows and the responsive stacking |

The feature modules are grouped by tab:

- `admin-web/src/features/dashboard/Dashboard.tsx` renders the Dashboard.
- `admin-web/src/features/preparation/DataPreparation.tsx` and `PreparationReport.tsx` render the Data preparation tab.
- `admin-web/src/features/inference/` holds `Inference.tsx`, `InferenceRun.tsx`, `PublicationDiagnostics.tsx`, `InferenceCoverage.tsx`, `GenerationIdentities.tsx`, `Failures.tsx`, `TargetDecisions.tsx` and `DatasetCleanup.tsx`.
- `admin-web/src/features/logs/` holds `Logs.tsx`, `CommandLog.tsx`, `SessionLogs.tsx`, `RuntimeLogs.tsx` and `Usage.tsx`.
- `admin-web/src/features/settings/` holds `Settings.tsx`, `Configuration.tsx`, `FeatureSwitches.tsx`, `Backups.tsx`, `Rebuild.tsx`, `Dataset.tsx` and `WorkerProvisioning.tsx`.

No module of the console imports `web/src/`, and a user-visible string written outside `shared/wording.ts` is a defect.

`SessionLogs.tsx` also owns the bounded-read presentation, the positive whole-line control and the whole-count reading that `RuntimeLogs.tsx` renders, because the two panels read the same bounded log shape of the same route.

## The typed clients

`runCommand` sends one `GET` or one `POST` with the session credentials, no stored response and the session's `X-CSRF-Token` on a `POST`, and the browser supplies the `Origin` header itself. A response with a status outside the successful range throws `ApiError` with that status, and an admission refusal is one such response. A network rejection reaches the caller as the browser's own error, which the interface renders as its generic failure. A `204` decodes to no body, and a `200` envelope whose `exit_code` is nonzero or whose `report` is null throws `CommandFailure` with the command's own safe failure line. No request is retried, and no request or response body is logged. The password never appears in a URL, in storage or in a log.

An automatic read adds one fixed `X-Admin-Automatic-Read: 1` header. The flag is request metadata that reaches only the read routes, so it changes no argument list, no admission decision and no CSRF requirement, and a successful automatic read leaves no entry in the sole command log. `runCommand` and the console transport take the flag as an optional boolean that defaults to false, and each automatic-capable read client takes it as a trailing optional boolean that defaults to false. An action, a manual client and a target lookup send no such header.

Each feature client names one route and one body. Every request that carries a parameter in its body uses the route's exact snake_case field names. `rebuildAdminPanel` is the one action that returns a report whose next effect, the backend's own restart, is outside the response.

- The preparation tab: `readStageStatus`, `runStageAction`, `readPreparationReport` and `writeHubs`.
- The inference tab: `readInferenceStatus`, `runInferenceAction`, `readInferenceSummary`, `readTarget`, `recordDecision`, `readDatasets` and `deleteDataset`.
- The logs tab: `readCommandLog`, `readLogSessions`, `readSessionLog`, `readEmbeddingLog` and `readUsage`.
- The settings tab: `readConfigurationFiles`, `readConfigurationFile`, `setConfigurationValue`, `readBackups`, `deleteBackup`, `rebuildSite`, `rebuildAdminPanel`, `setupDataset`, `migrateDataset`, `setupWorker` and `preflightWorker`.

## Session, polling and error flow

`App` loads `GET /auth/session` once. An anonymous report shows `SignIn`, and a successful login replaces the session metadata, which mounts `SignedInConsole` and every tab tree at once. The selected tab alone is visible and the other four are `hidden`, so an inactive tree is retained in browser memory, absent from keyboard and accessibility navigation, and reads nothing again when it is opened. The open tab lives in this browser tab's session storage, so a reload restores it and another browser tab has its own.

The signed-in header carries the TUNI Course Explorer brand, the **Admin** label, the five tabs, the GitHub link, the Docs link, the App address and the sign-out control, and no account name. GitHub opens the configured repository address in another browser tab, Docs opens the site's `/docs#home` page, and both App and Docs use the primary button style.

Sign-out posts `POST /auth/logout` and returns to the anonymous bootstrap. The protected trees exist only in the authenticated branch, so signing out, a refusal or a lost session unmounts the whole subtree with its reports, drafts and selections and aborts its reads. A completed administration rebuild clears the same subtree without a bootstrap, because the backend that holds the session and answered the build restarts next, so that screen reads no session until its next credential submission.

`SignedInConsole` owns one `GET /api/dashboard` read for the whole signed-in session. `Dashboard` renders that result from the `panel` prop, `Settings` forwards the same result to `Dataset`, and the report's `serving.selection_enabled` decides three automatic consumers: the inference summary, the dataset cleanup listing and the Settings dataset listing.

The selection state has three forms:

- `null` means no dashboard read has succeeded. A dependent panel's own header marker shows the automatic reading state while it waits, or the panel shows the dashboard failure that stopped the read.
- `false` means the selected dataset is not enabled on the site. No summary, listing or delete row renders, no automatic marker appears for those reads, and no request is issued.
- `true` enables their ordinary loop, report and failure display.

A failed refresh after a success holds the last report and gates from that report. A failed read is never reported as a disabled site.

`usePanelRead` reads immediately when its panel is enabled and the page is visible, then schedules its next read only after the current one completes plus the session's poll interval. The interval is `ADMIN_WEB_POLL_SECONDS`, and every enabled automatic read of the signed-in page follows it.

The page's own visibility governs the loop: a hidden page performs no read, cancels a scheduled one and aborts one in flight without showing a failure, and the return to visibility reads once immediately and resumes the ordinary loop. A report and its marker outlive a hidden interval, an inactive-tab switch, a loading read and an ordinary failure.

A failed read renders the command's own safe failure and shows the report and marker of the last successful read instead of clearing them. It schedules the next read after the same interval while the panel is enabled and visible, so a success clears the failure. A `401` or the lock's `403` stops the loop and follows the shell's session policy.

The loop passes its own read attribution to its callback: the mount, timer and visibility-return reads are automatic, and the returned `reload` performs one explicit read. A reload that arrives while the panel cannot read is retained and consumed once when it can, with its explicit attribution, in place of the visibility read, so a file selection or a changed log window issues one request rather than two. The hook also returns `apply`, which installs a report an action already returned, clears the read failure and stamps the read marker without issuing a read or changing the loop schedule.

`useDemandRead` issues no read on mount, on a timer or on a selection change, and its signature and call sites are independent of the automatic loop. An explicit reload reads once, a changed identity clears the result and aborts the read in flight, and unmounting aborts it. The runtime and worker log panels and the worker preflight use it, so no request reaches the worker until the operator asks for one. A demanded panel's marker names the operator's own read rather than an automatic one, and its in-memory result is shown again when a tab switch reveals its panel.

`AutoMarker` renders the elapsed whole seconds, minutes, hours or days since the last successful read from its own one-second tick, without issuing a command.

`handleAdmissionFailure` in `admin-web/src/api/http.ts` is the one classifier of a refused request. An `ApiError` with status `401` or `403` calls the shell's refusal callback once and reports true, so one returned value says whether the caller must stop its own handling. A caller that sets its own failure state before it notifies the shell is unmounted by that handling, and every other error is the panel's own failure. The read loop of `usePanelRead`, a demanded read, the dataset deletion, the backup deletion, the target read and decision, a stage action, an inference action, the hub write, a configuration save, a rebuild, a dataset setup or migration, a worker setup and the sign-out report their refusals through it.

The shell treats a `401` and a bare `403` as admission conditions. The lock's empty `403` at the shell's own bootstrap, at the login attempt or at any protected request clears the session and the mounted trees and renders an empty root, without naming any reason, file or recovery step, and it issues no further request. A protected `401` clears the protected state and returns to sign-in through one bootstrap: the shell consumes one refusal per authenticated session, so the concurrent refusals of the initial read wave share that one re-bootstrap, and a granted session opens the next one.

A login `401` states a wrong credential rather than an expired session, so the sign-in screen shows its own invalid-credential message, clears the password field and issues no bootstrap and no second attempt. A login `403` is the terminal admission refusal, and a missing live login session and a site or CSRF refusal answer it as well. A network failure renders one generic failure, and a command failure renders the command's own safe failure line in the panel it belongs to.

## Motion and log boxes

A revealed tab pane runs a 180 ms ease-out entrance from opacity zero and a 4 px downward offset to full opacity and no transform. The rule matches only a pane that is not `hidden`, so the browser restarts it on every reveal without a remount, an outgoing pane or a timer, while `hidden` is the authority for layout, focus and accessibility. The reduced-motion preference applies each final tab state at once.

A panel body measures its own content border box and holds that pixel height in an outer viewport that clips the interpolation. A measurement after the first transitions the viewport height over 180 ms ease-out, so a report, a table or an opened editor grows and shrinks with its content. A hidden tab's zero measurement is ignored, the first nonzero measurement establishes the height without an entry animation, and reduced motion applies every final height at once. The grid aligns its items at their start, so a row cannot stretch a panel whose content shrinks.

The command log table and the session and runtime log text share one scroll presentation: a maximum height of 24 rem, a scrolling vertical axis with a stable gutter and a visible scrollbar, and horizontal scrolling with pre wrapping inside the same box. Panel headings, log controls and every other table keep their natural height.

The session, source and runtime pickers share one styled menu. Its arrow sits clear of the right edge, and the menu fades and slides open and closed over 160 ms. The menu uses the same scrollbar width, track and thumb as the log boxes, and its hidden state is out of the tab order and the accessibility tree. Reduced motion applies both final states at once.

The Settings tab places Configuration first across the full width, then Dataset and Backups, then Rebuild and Worker provisioning, then Feature switches. The Inference tab places Generation identities before Target decisions.

## Panel reads and routes

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

### Dashboard

The signed-in shell's one read feeds all five panels. Serving state renders `serving` and `hubs`, with the restart hint only for a hub whose `newer_than_web_start` is true. The website panel shows `configured_workers` as configured processes and the checkout branch and revision as the checkout identity. The host, database and embedding runtime show their own measured and configured members. The host's CPU usage renders as one percentage sampled over a short interval, so it lies between 0% and 100% rather than counting waiting work. Every nullable fact renders as unknown.

### Preparation

Each of the three stage panels reads its own status with an automatic marker. The panel takes its top-level lifecycle, session, revision, active time, rate and ETA as authoritative, and the host row names the stage's execution host, worker for translation and server for ingestion and embedding.

Ingestion shows its response and verified counts, its verification total when the owner supplies one, and its normalized flag. Embedding shows its desired and completed counts and its remaining count as pending plus failed. Translation shows its mirrored worker desired, completed and remaining counts, and its reboot flag reads unknown while the stage reports no worker status.

A successful lifecycle action installs the status it returned through the hook's `apply`, so the panel shows the returned state without another status read. Start, Pause and Resume run at once, and Stop asks for confirmation naming the stage.

The three reports have their own automatic reads. The catalogue report is the six `CatalogueSummary` counts. The teaching-text report shows one row per field and language with its official, derived, stale and missing counts, one all-representative-fields row that sums each column, and the representative, no-representative, name-only and unembeddable course counts. The embedding report shows one row per coverage entry, whose first column names the field, the uppercase language and the reported origin, plus the report's own total pending, completed and failed counters.

The hub write posts one empty `POST /api/preparation/hubs`, reports the returned file paths and chunk counts, and states that a running web server reads the hubs at start.

### Inference

The run panel reads its own status with an automatic marker. It shows the cycle from `worker.coverage.cycle_id` when present and unknown otherwise, the current stage, the session, the active time, the supplied top-level rate and ETA, the reboot flag, the preparation step when present, and one line per `worker.stages` entry with its done, total and remaining counts. Start, Pause and Resume run at once, and Stop asks for confirmation naming the run.

One `GET /api/inference/summary` read feeds publication diagnostics, coverage, generation identities and failures, and the coverage panel carries the retained-server label. The read runs only while the dashboard reports the selection enabled. A `null` selection state shows the automatic reading state in each panel's header marker and no body note. A `false` state renders the disabled note without a report body or an automatic marker.

Diagnostics shows the publication state counts, the candidate counts, the warning count and the three configured policy fields, with the non-local route count under Route other from either of its two live spellings. Coverage shows the coverage counts and the summary's own `operator_done_targets`, and states the retained cycle. Generation rows are the coverage `generation_counts` entries alone, with the model, prompt, schema, pipeline, route and target count of each, and each route occupies one line. Each failure row shows its canonical `target_group_id`, stage, attempt count, error type, reason, exhausted flag and creation time from the retained record.

The target decisions input starts empty, and no report appears before a successful `POST /api/inference/target/read`. The panel shows the dataset id, the canonical group id, the official code, the English name and the current decision, where a null decision reads as NOTHING. The decisions are available only for the identity the read resolved. DONE and FAILED confirm first with the panel's own confirmation text, NOTHING records immediately, and a recorded decision replaces its report and refreshes the shared summary.

One `GET /api/inference/datasets` read lists the chain in selected-first order and runs only while the dashboard reports the selection enabled. The listing shows the dataset id, the named database and the dump path. Every non-selected row offers deletion, the selected row shows the selected marker in place of that control, and the confirmation names the exact dataset id and database name. Cancelling posts nothing, and confirming closes the dialog and posts only that listed dataset id. A successful deletion refreshes the listing, and a failed one leaves the row in place and shows the command's failure in the panel. A `false` selection state renders the disabled note in place of the listing and its rows, so a stale row and an open confirmation are not shown.

### Logs

The command log reads automatically and renders newest first from a display copy of the report's own oldest-first order. Each row shows the entry's time, fixed command label, exit code, duration, outcome token and the one safe failure line that belongs to it. A login, failed-login or lock event is one of those entries rather than a separate history.

The session and runtime panels share one `GET /api/logs/sessions` inventory, so the console discovers the stage sessions once. The session panel initially selects the first listed stage and session and `server-stdout`. It offers `server-stdout` and `server-stderr` for every stage, and `keepalive` and `worker-runner` for the translation and inference stages through the shared picker. The selected server stream and the keepalive file read automatically, and the worker's `runner.log` is read only by the panel's Read control. Selecting another session or source clears the previous log. The line-count control starts at 200 and shows its `lines` unit.

The runtime panel offers the embedding service's own container log and each listed translation or inference session through the shared picker. The embedding log reads automatically, and a listed session's `runtime.log` is read over the transport only by the panel's Read control.

The usage panel reads one `POST /api/logs/usage` for the applied window, which it initially sets to 24 hours, and its hour control shows its `hours` unit. It shows the window bounds, the total requests, the mean duration and one row per returned route. A window with no recorded request reports zero requests, an unknown mean and no route row, and the panel counts course-exploration requests alone.

### Settings

The configuration panel reads `GET /api/settings/config/files`, and one `POST /api/settings/config/read` of the file the operator selects. It opens no file on arrival and one file at a time. Every key renders as a visible text control, a string key edits its own contents and the other keys edit JSON text, and the open file reads automatically while its drafts match the reported values.

Save parses every changed draft before the first request, then saves the changed keys one at a time in the report's own order through `POST /api/settings/config/set`. The first refused key stops the sequence and reports the saved and unsaved counts, and the panel holds the unsaved drafts. A retry saves the refused key and the keys after it. An edit of a draft clears the save summary. Selecting another file fades the detail body in over 180 ms, and the keys stagger into place as their read reports them.

The feature switches panel reads `config/web.toml` and reports `WEB_INFERENCE_ENABLED` and `WEB_EMBEDDINGS_ENABLED`, and each switch writes its own key through `POST /api/settings/config/set`. A switch shows the written position only after the command acknowledged it, and a refused write leaves the value the file holds. A value the file does not report as a boolean renders as an unknown note in its row rather than as an unchecked switch. A saved switch reports that a rebuild or restart applies it to serving. A saved switch updates the editor's own value of the same key, and an editor save of that file reloads the switches.

The backups panel reads `GET /api/settings/backups` for the actual file names, modification times and sizes. Every listed row offers deletion, the confirmation names the exact listed name, cancelling posts nothing, and confirming closes the dialog and posts that one name through `POST /api/settings/backups/delete`. A successful deletion reloads the listing, and a failed one leaves the row in place and shows the command's failure in the panel. The empty note renders only after a successful report lists no backup file.

The rebuild panel shows the four fixed steps of the site rebuild in their own order, with **Rebuild app** first on the panel's left and **Rebuild admin panel** beside it as a second action with its own confirmation, which states that the action signs all operators out. Pending covers the operation as a whole rather than invented step progress, and one pending operation disables both actions. The site action posts `POST /api/settings/rebuild` and renders the returned steps and its verified bind. The administration action posts `POST /api/settings/rebuild-admin` and reports a completed build to the shell.

The dataset panel reads the shell's shared dashboard report for the pointer, the selection state, the recorded head and the live database facts, and one `GET /api/inference/datasets` read for the selected entry, which runs only while that report says the selection is enabled. While the state is `null`, the panel's header marker shows the automatic reading state and no body note. A `false` state renders the disabled note in place of the selected-chain rows, and a dashboard failure renders its own failure.

The database and head facts, the two confirmed actions and their own receipts, verifications and failures render throughout. The recorded receipt revision and the live database head render as separate observations. `POST /api/settings/datasets/setup` and `POST /api/settings/datasets/migrate` are two separately confirmed actions, each renders the receipt or the verification its own command returned, and each reloads the listing and the shared report on success.

The worker provisioning panel starts with an empty origin branch input and a code-only choice that is off. The choice uses the same switch the feature switches use, and a setup needs a branch before its confirmation. `POST /api/settings/worker/setup` carries exactly that branch and that boolean, and `POST /api/settings/worker/preflight` is the read-only preflight of the panel's own Preflight control. A setup report and a preflight report render separately, each from the report its own command returned, and a request reaches the worker only through an explicit action.

The administration rebuild completes differently from the site rebuild, because the backend that answered it restarts next. The panel reports a successful administration build to `App` through the callback the shell passes down to the Settings tab. `App` then clears the session, the failure and every protected tab tree and shows `SignIn` with no session and the restart notice, so no session request reaches the process that is restarting. The next credential submission on that screen reads `GET /auth/session` once for a fresh anonymous session and posts the login over that session's CSRF token. A failed administration build renders the command's own safe failure in the panel and leaves the protected session, its reports and its drafts in place.

## Tests

| Test file | Covers |
|---|---|
| `admin-web/src/app/App.test.ts` | The shell's session boundary, its shared reads, the selection gate and both rebuilds |
| `admin-web/src/shared/usePanelRead.test.ts` | The automatic read loop over page visibility |
| `admin-web/src/shared/StagePanel.test.ts` | The status a stage action returns, shown without another read |
| `admin-web/src/features/inference/DatasetCleanup.test.ts` | The dataset and backup deletion confirmations |
| `admin-web/src/features/settings/Backups.test.ts` | The empty note and the failure of a held first read |
| `admin-web/src/features/settings/Configuration.test.ts` | A partial file save that stops at the first refused key |
| `admin-web/src/features/settings/Rebuild.test.ts` | Both rebuild confirmations and the administration report |
| `admin-web/src/features/logs/Logs.test.ts` | The on-demand worker log read |
| `tests/admin_web/test_routes.py` | Route admission and the automatic-read command-log rule, including the administration rebuild sequence |
| `tests/admin_web/test_command_log_read.py` | The command-log read's order and its file handling |

`App.test.ts` exercises the shell through the real application, over these cases:

- The lock's `403` at the initial bootstrap and at the login attempt, a successful login and a login refused by a wrong credential, the successful sign-out, one opening of each of the five tabs, and one refusal of every protected read of the signed-in page, which shares one re-bootstrap.
- The retained tab session: one tagged initial read per enabled consumer, the one shared server-status read, the two dataset-listing consumers, and tab switches that reveal a retained report and marker without another request.
- Selection gating: the first dashboard response is held, and the inference summary and both dataset listings read nothing before it and once each after an enabled report, while a disabled or failed first report issues neither read.
- Both administration rebuilds: a successful build clears every protected tree without a bootstrap and reads a fresh session before the next login submission, while a failed build leaves the session in place and shows the command's own safe failure.

`usePanelRead.test.ts` covers one enabled panel's automatic loop over the page's own visibility: no read while the page opens hidden, one tagged read on the return, an in-flight read cancelled on the next hide without a failure, the report and its marker retained, and one further read on each following return and poll interval.

`StagePanel.test.ts` proves that a stage action's returned status shows without another status request. `Logs.test.ts` proves that the worker log reads nothing on mount, on a poll interval or on a selection change, reads once for the explicit control, and performs exactly one local read and no worker read on a worker-to-local transition.

`DatasetCleanup.test.ts` covers the deletion confirmation of the dataset cleanup panel and the backup cleanup panel, each posting only the confirmed listed target and posting nothing when it is cancelled. A confirmed command failure closes the dialog, leaves the row in place, shows the failure and reloads no listing.

`Backups.test.ts` holds the first read and proves that it states neither an empty inventory nor a failure before it completes, then the empty note after a successful empty report or its own failure alone.

`Configuration.test.ts` proves a partial file save over typed synthetic values, which stops at the first refused key, reports the saved and unsaved counts without rendering a value, retries the refused key and the keys after it, and clears the saved summary when a draft changes.

`Rebuild.test.ts` proves both confirmations: a cancelled one posts nothing, a confirmed one posts only its own route, and the administration action alone reports the completed build to the shell.

`tests/admin_web/test_routes.py` maps every feature route to one admitted request, one argv and one transient outcome, for success and for a checked failure, with and without the console's automatic-read header. A marked successful read route omits its command-log entry, while a failed read and every action or manual-only route append theirs, and the retained entry holds none of the request-supplied values.

The administration rebuild route proves its build-then-queue sequence, its one build-failure entry with no restart call, its intact build response beside a queued restart failure, and the restart that runs only after the final body send completes.

`tests/admin_web/test_command_log_read.py` covers the `logs commands` machine command, which prints the newest configured entries oldest first from a file that holds more, creates no file for an absent log and rewrites none for a present one.

`admin-web/src/testSetup.ts` installs one no-op `ResizeObserver` substitute for every console test file, because jsdom performs no layout and emits no measurement. Real measurement belongs to the bounded browser check.

The frontend gate installs the locked dependencies with `npm --prefix admin-web ci --no-audit --no-fund` and then runs `npm --prefix admin-web run typecheck`, `npm --prefix admin-web run test`, `npm --prefix admin-web run format:check` and `npm --prefix admin-web run build`.
