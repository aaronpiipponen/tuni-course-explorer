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

## The panels page

Each tab's panels, the route every panel reads, the rows and actions each one presents, and the tests that cover them are described in [Administration console panels](/docs/frontend/admin-console-panels.md). The modules in the ownership table own those panels.

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

## Tests

| Test file | Covers |
|---|---|
| `admin-web/src/app/App.test.ts` | The shell's session boundary, its shared reads, the selection gate and both rebuilds |
| `admin-web/src/shared/usePanelRead.test.ts` | The automatic read loop over page visibility |

`App.test.ts` exercises the shell through the real application, over these cases:

- The lock's `403` at the initial bootstrap and at the login attempt, a successful login and a login refused by a wrong credential, the successful sign-out, one opening of each of the five tabs, and one refusal of every protected read of the signed-in page, which shares one re-bootstrap.
- The retained tab session: one tagged initial read per enabled consumer, the one shared server-status read, the two dataset-listing consumers, and tab switches that reveal a retained report and marker without another request.
- Selection gating: the first dashboard response is held, and the inference summary and both dataset listings read nothing before it and once each after an enabled report, while a disabled or failed first report issues neither read.
- Both administration rebuilds: a successful build clears every protected tree without a bootstrap and reads a fresh session before the next login submission, while a failed build leaves the session in place and shows the command's own safe failure.

`usePanelRead.test.ts` covers one enabled panel's automatic loop over the page's own visibility: no read while the page opens hidden, one tagged read on the return, an in-flight read cancelled on the next hide without a failure, the report and its marker retained, and one further read on each following return and poll interval.

`admin-web/src/testSetup.ts` installs one no-op `ResizeObserver` substitute for every console test file, because jsdom performs no layout and emits no measurement. Real measurement belongs to the bounded browser check.

The frontend gate installs the locked dependencies with `npm --prefix admin-web ci --no-audit --no-fund` and then runs `npm --prefix admin-web run typecheck`, `npm --prefix admin-web run test`, `npm --prefix admin-web run format:check` and `npm --prefix admin-web run build`.
