# Browser state

The browser state is one local-storage envelope of profiles, held by a single store that re-reads it before every change and writes before it publishes.

## The envelope and its types

`web/src/state/types.ts` defines the shapes:

- `CourseId` is a canonical course identity as a string, and it is the only course key the envelope uses.
- `TabId` is `search`, `compare`, `prerequisites`, `discover`, or `structure`.
- `DisplayLanguage` is `fi` or `en`.
- `ProfileState` holds `language`, `selectedCourseIds`, `completedCourseIds`, `pendingSisuImport`, and one slice per feature: `search`, `compare`, `prerequisites`, `discover`, and `structure`.
- `Profile` is `{ name, state }`.
- `BrowserState` is `{ schemaVersion: 3, currentProfileId, profiles }`.
- `BrowserProfileFile` is `{ type: "tuni-course-explorer/profile/3", profile }`, `BrowserStateFile` is `{ type: "tuni-course-explorer/state/3", data }`, and `BrowserFile` joins the two. `BrowserImport` joins an imported profile file, a state import whose `state` is the validated envelope, and a `SisuCaptureFile`.
- The console script downloads a raw capture of `{ type: "tuni-course-explorer/sisu/1", markup, modules, courses }`: the plan tree markup, each shown module version identity resolved to the Kori group ids of that module, and each shown course code resolved to its Kori search hits.
- `parseSisuCapture` in `web/src/features/structure/sisu.ts` reads that raw capture and returns `SisuCaptureFile`, `{ type: "tuni-course-explorer/sisu/1", programmes }`, the parsed hierarchy that carries no plan markup. Each captured module keeps the exact version id its status cell names as the required nullable `versionId`, and `pendingSisuImport` holds only that parsed `SisuPlan` hierarchy.

`web/src/state/defaults.ts` holds the two constructors. `initialProfileState()` returns English, empty course sets, and the initial slice of each feature. `initialBrowserState()` returns `schemaVersion: 3`, the current profile `default`, and one profile named `My plan`.

Each feature owns its slice type and its constructor in `web/src/features/<feature>/state.ts`. `StructureState` in `web/src/features/structure/state.ts` adds `programmeGroupIds`, `moduleVersions` and `placedCourseIds` to `choices`, `coursePlacements`, and `modulePlacements`, and `UNPLACED_KEY` names the place that holds courses with no programme. `moduleVersions` keeps at most one exact official version id per canonical module group. An operation forgets the version entries of the groups that the starting tree renders and the resulting tree does not render. A selection for a group the starting tree does not render keeps its entry. `StructureEdits` holds choices and placements alone.

## One store and one write path

`BrowserStore` in `web/src/state/store.ts` holds the storage object, the snapshot, and a listener set. `createBrowserStore(storage)` reads the envelope and returns the store, and `BROWSER_STORAGE_KEY` (`tuni-course-explorer`) is the single key it reads and writes. An absent key at that point resolves to `resetBrowserStore(storage)`, which writes the first-visit envelope through the same reset writer the recovery screen uses.

- `getSnapshot` and `subscribe` feed `useSyncExternalStore`. `useCurrentProfile`, `useCurrentProfileId`, and `useProfileSelector` in `web/src/state/` are the React bindings, and `StoreContext` in `web/src/state/context.ts` carries the one store instance.
- The private `#commit(update)` reads and validates the stored envelope once. The callback receives the held snapshot when the serialized stored envelope equals it, and the validated value when the two differ. A local change to one slice therefore reuses the references of every other slice, and another tab's write reaches the callback. It writes the envelope the callback returned. A mutation applies its change and its target, duplicate-name, and last-profile checks to that value.
- A callback that returns its argument writes nothing. When the chosen value differs from the snapshot, that no-op case adopts it and notifies once.
- The private `#write(next)` writes the envelope to storage, assigns the snapshot, and then notifies the listeners. A write that throws therefore reaches neither the snapshot nor a listener.
- `refreshFromStorage()` reads and validates the stored envelope, adopts it when its content differs from the snapshot, and returns the adopted snapshot. An equal value keeps the snapshot reference, and a removed envelope adopts the absent-key initial state through `initialBrowserState()` without a write.
- `updateCurrent(update)` calls the update with the current profile state and returns without a change when the update returns the same reference. Otherwise it builds the next envelope and commits it.
- `switchProfile`, `saveAsProfile`, `deleteProfile`, and `renameProfile` commit through the same method and keep their synchronous signatures.

`web/src/main.tsx` keeps one module-local active store and registers one `storage` handler for the lifetime of the page. The handler acts on the envelope key and on a cleared storage area only. With a live store it calls `refreshFromStorage`, and while the recovery screen is mounted it mounts the ordinary store again, so another tab's valid write restores the page.

The same module mounts the site's feature bootstrap above the shell: it asks the server for the two switches and the serving dataset identity once per visit and holds the answer in a React context, outside every stored value. The bootstrap also mounts one `ReadCache` above the tab panes, bounded and scoped to that identity. It holds the successful reports of every cached read, the graph reports and the route results included, survives tab and profile changes, and is never written to local storage or session storage.

Study structures also persist in a derived IndexedDB store keyed by the identity, the canonical root and the exact selection key that produced them, and that store holds no profile value.

Every feature action reaches the store through `updateCurrent`: `web/src/app/actions.ts` for the language and the prerequisite root, `web/src/state/course-actions.ts` for the shared course sets, and `web/src/features/<feature>/actions.ts` for the slice a feature owns.

The open tab is separate: `web/src/app/sessionTab.ts` owns it in the browser tab's session storage under the key `tuni-course-explorer-active-tab`, `useActiveTab` binds it with `useSyncExternalStore`, and `setActiveTab(tab)` writes it before it notifies. `openPrerequisites(store, courseId)` writes the profile's prerequisite root first and then moves the browser tab, so another browser tab stays where it is.

## Reading and validation

`web/src/state/validation.ts` is the one validation boundary for the stored envelope and for imported files, and it returns the current shape only. `validateBrowserState(value)` requires a non-array object, a literal `schemaVersion: 3`, a nonempty string `currentProfileId`, a non-array `profiles` record with nonempty string identities, at least one profile, an own entry for the current profile, a nonblank trimmed name on every profile, and names that no two profiles share.

An unsupported schema version raises `Unsupported saved browser state schema`, and a missing current profile raises `Saved browser state has no current profile`. The profiles record is built through `Object.fromEntries`, so a stored key is data and never a prototype assignment.

`validateProfileState(value)` fills an absent field from its constructor and checks every supplied one. `language` is `fi` or `en`. The selected and completed identities are arrays of nonempty strings, each without repeats, with the completed set inside the selected set. Each of the five slices is projected onto its current fields:

| Slice | Checked fields |
|---|---|
| `search` | A string `query` and a boolean `activeOnly` |
| `compare` | Exactly two nullable nonempty-string `slots` without a repeated course, a string `pickerQuery` and a boolean `pickerActiveOnly` |
| `prerequisites` | A nullable `rootCourseId`, a string `courseQuery`, the booleans `includeRecommended`, `includeInferred` and `activeOnly`, a `basis` of `completed` or `selected`, and the string arrays `excludedCourseIds`, `completedNodeKeys` and `excludedNodeKeys`. The two mark arrays keep each nonempty string that matches the node-mark key grammar and drop the others |
| `discover` | A `list` of `next` or `recommended`, a `mode` of `all` or `at_least_one`, a boolean `activeOnly`, a boolean `basisExpanded` and a `basis` of `completed` or `selected` |
| `structure` | Unique string `programmeGroupIds`, `moduleVersions` as a required record of nonempty-string identities, `choices` as a record of string arrays, `coursePlacements` and `modulePlacements` as records of nullable string targets, and unique string `placedCourseIds` |

The two site feature switches and the serving dataset identity are not part of this envelope. No field of `ProfileState` and no key of the stored object carries them, they are never written or read back, and a site serves its features without a stored switch. A saved **Compare**, **Recommended** list or `includeInferred` value therefore stays stored while a site hides the control that changes it.

`pendingSisuImport` is `null` or one validated capture hierarchy. `validateProfileState` sends a supplied value through `validateSisuPlan` in `web/src/features/structure/sisu.ts`, which checks the same recursion, throws `Invalid Sisu plan file`, and rejects two non-null top-level programme identities that agree. An absent field and a stored `null` both read as `null`, which is the value a profile holds once the structure places its pending capture.

A supplied profile state that holds a pending capture together with saved choices, places or placed identities passes validation, because all three are profile data. The Structure of studies tab places no such capture, performs no structure write, and shows the shared hold notice, so a profile file or whole-state file keeps the combination as it arrived. A pending capture whose profile holds none of those edits is placed on the first structure read.

A supplied structure object without `programmeGroupIds` or `moduleVersions` is rejected, because the list and the exact selections are the structure's own identity. A supplied field that fails its check rejects the whole value, with one exception: a mark array throws on a non-string or empty entry, drops each nonempty string outside the node-mark key grammar, and keeps a valid key whose box is not drawn.

An absent slice falls back to its constructor, and an unknown field is dropped. The identity checks are string checks alone: an identity is never resolved against the server or required to be in the catalogue. The structure checks cover types and do not read a rule tree, so a saved placement is retained when a tree traversal does not visit the node it names.

`validateProfile(value)` is the one profile check. It requires a string `name` that is neither blank nor padded with whitespace, then validates `state` through `validateProfileState`. A name with surrounding whitespace is rejected rather than trimmed, so validation never renames a stored or imported profile. `validateBrowserState` calls it for every profile of the envelope.

`readBrowserState` reads `BROWSER_STORAGE_KEY` and hands the parsed value to `validateBrowserState`. An absent key returns `initialBrowserState()` without a write. A stored value that is not valid JSON raises the fixed `Saved browser state is invalid` error, and every other read or validation failure propagates, so invalid stored bytes stay in place.

`parseBrowserImport(text)` in `web/src/state/store.ts` is the file-input boundary. It requires an object with an exact string `type`, sends the `profile` of a `tuni-course-explorer/profile/3` file through `validateProfile`, parses the `data` string of a `tuni-course-explorer/state/3` file through `validateBrowserState`, and sends a `tuni-course-explorer/sisu/1` file through `parseSisuCapture`, which is the one validation and parse boundary of a downloaded capture.

A state file carries the exact stored envelope text, which keeps healthy export and broken-data recovery in one format, and a profile file carries one name and one state without a source profile identity.

Malformed JSON, a missing or non-string `type`, an absent `data` string, and unparsable nested JSON raise `Invalid import file`. Another string `type` raises `Unsupported file type`, and an invalid payload raises the message of the validator that rejected it. A refused file changes neither the stored value nor the file.

Every validation failure throws an `Error` whose message `errorPresentation` in `web/src/shared/errorPresentation.ts` maps to a wording key. `KNOWN_MESSAGES` holds the app-authored messages, an `ApiError` with status 422 reads as `Invalid request`, any other status reads as `Request failed ({status})`, and an unknown message reads as `Operation failed` with the raw text as detail.

`web/src/main.tsx` creates the one store inside a `try` and mounts it. A read failure mounts `StorageRecovery` instead, and the stored bytes stay in place. `useAction` in `web/src/shared/useAction.ts` wraps a UI action: it clears the error when the action succeeds and exposes the thrown error otherwise, and its optional `clearAfterMs` clears the message after that long. `ProfileButton` passes `PROFILE_NOTICE_MS` for both of its actions.

## Saved-data recovery

`web/src/features/profiles/StorageRecovery.tsx` renders the startup failure as `ErrorNotice` in English, and its own controls state their text in English as well. No valid profile language exists on this screen, so no profile language is available to read.

- **Export saved data** calls `exportSavedBrowserData(window.localStorage)`, which reads `BROWSER_STORAGE_KEY` once and wraps the string unchanged in a state file. The stored text is never parsed, validated or displayed, so unreadable data leaves the browser exactly as it is. A missing key raises `There is no saved data to export`.
- **Reset saved data** opens a dialog titled **Reset saved data** that states that every profile of this browser is deleted and the browser starts with a profile named My plan. Cancel, Escape, and a click outside the dialog write nothing. The confirmation calls `resetBrowserStore(window.localStorage)`, which writes `initialBrowserState()` and returns a live store, and the bootstrap mounts it without a page reload. A failure leaves the recovery screen and its data in place and shows the failure on the screen itself.

The download helper is `downloadBrowserFile(file)` in `web/src/features/profiles/files.ts`. It derives the name from the typed file: a profile file downloads as `course-explorer-profile-<profile name>.json`, where every character a path segment cannot hold and every character from U+0000 to U+001F becomes `_`, and a state file downloads as `course-explorer-saved-data.json`. It serializes the wrapper with `JSON.stringify(file, null, 2)`, builds a JSON `Blob`, clicks a temporary anchor over an object URL, and releases both. A profile name never becomes a path.

## Profile, file and state operations

- `switchProfile(id)` requires a profile that the envelope holds and returns without a write when the identity is already current.
- `saveAsProfile(name)` trims the name, rejects an empty name and a name that another profile holds, builds an identity from `crypto.getRandomValues`, copies the current state with `structuredClone`, and makes the copy current.
- `deleteProfile(id)` requires a profile that the envelope holds and refuses to delete the only profile. Deleting the current profile selects the first profile in insertion order.
- `renameProfile(id, name)` trims the name, rejects an empty name and a name that another profile holds, returns without a write when the name equals the stored one, and changes the name only.
- `exportProfile(id)` refreshes the envelope, requires that profile, and returns a `BrowserProfileFile` holding an independent copy. Exporting a profile does not make it current.
- `exportState()` delegates to `exportSavedBrowserData`, so a whole-state file holds the stored bytes.
- `importProfile(profile)` takes the profile of a parsed import file, builds a fresh identity, and makes it current. An empty name and a name that another profile holds are refused without a write, and the name and copy rule is shared with Save as. `ProfileTransfer` calls this method once, after the confirmation that names the imported profile. A profile that holds a waiting capture beside saved choices or places is imported unchanged and is not placed automatically.
- `restoreState(state)` writes the envelope of a parsed whole-state file and replaces the saved data as a whole. It neither merges nor keeps a backup, and `ProfileTransfer` asks for its confirmation before it calls this method and reloads the page. An envelope whose profile holds a waiting capture beside saved choices or places is written unchanged and is not placed automatically.
- `resetSavedData()` writes `initialBrowserState()` through the same writer. The first-visit bootstrap and the confirmed recovery reset are its two callers.

`ProfilePanel` in `web/src/features/profiles/ProfilePanel.tsx` owns the list, the copy form, the transfer controls, the rename dialog, and the delete dialog, and it hides the delete control while the profile list holds one profile.

`ProfileTransfer` in the same folder owns the drop area and file picker, the parse dispatch, the bottom row with its help drawer and script copy, the export disclosure, and one confirmation per kind: a profile import, a state replacement, or a Sisu import with a **Profile name** field that stays unavailable while its trimmed value is empty. Its `importOnly` prop renders the import heading, the drop area, and a bottom row with the script copy and a help drawer that explains the import and the Sisu plan, without the export disclosure, for the empty **Structure of studies** tab. The parse dispatch and the three confirmations are the same in both presentations.

All three kinds wait in one pending import until that confirmation, which reads the store at confirmation time. A profile import and a Sisu import create the profile through `importProfile`, and the Sisu import prepares it with `prepareSisuProfile` in `web/src/features/structure/sisu.ts`. A cancelled, dismissed or failed confirmation writes nothing.

`ProfileTransfer` copies the script through one path that works on a plain HTTP origin: the click selects `SISU_SNIPPET` in a temporary textarea and calls `document.execCommand("copy")`, then removes the element, restores the focus and the earlier selection, and reports `Sisu import script copied` or `Could not copy Sisu import script`. A successful copy clears any earlier notice timer, restarts the green copy notice lifetime, and drops the timer on unmount. `ProfileButton` owns the profiles menu, the store calls, and the store it passes to the panel.

`ProfileNotice` in `web/src/features/profiles/ProfileNotice.tsx` is the one presentation wrapper for the profile menu's transient notices: it animates the height and opacity of the content it holds, keeps that content through the exit, and draws it at once under reduced motion. It exports `PROFILE_NOTICE_MS`, 5000 milliseconds, which `ProfileButton` passes to both of its `useAction` calls and `ProfileTransfer` uses to clear the copy notice. `ProfilePanel` wraps its save and rename error branches in it, and `ProfileTransfer` wraps the copy success, whose green box reuses the alert box with the course-status tone.

## Selected and completed courses

- `toggleCompleted(store, courseId)` in `web/src/state/course-actions.ts` adds the identity to `completedCourseIds` and to `selectedCourseIds` when it is not completed, and removes it from `completedCourseIds` alone when it is. A completed course is therefore always selected.
- `useCourseCompletion` in `web/src/shared/course/useCourseCompletion.tsx` is the shared interaction of the course menu's **Mark completed** and the graph's **Complete** button. A selected course calls `toggleCompleted` at once. An unselected course opens a `ConfirmDialog` from `web/src/shared/ConfirmDialog.tsx` and calls `toggleCompleted` once on confirmation, so the selection and the completion are written in one update. Cancelling writes nothing. Unplaced studies render the selected identities that no structure node holds, so the confirmed addition needs no placement record.
- `addCoursesToFreeChoice(store, courseIds)` appends the identities that are not already selected, de-duplicated through a `Set`, and leaves the completion set alone. It returns the number the latest stored envelope gained, read inside the update callback, so a repeated request returns zero and a failed write throws without a count.
- `useNotice` in `web/src/shared/useNotice.ts` reads the app-level notice API from `NoticeContext`. `NoticeProvider` in `web/src/shared/NoticeProvider.tsx` renders one `role="status"` notice at the bottom of the window for 2200 milliseconds, resolves its text in the live language and runs one optional action inside `useAction`, so a navigation failure reaches `ErrorNotice`. `App` mounts it around the app shell with the current profile as its key, above the carousel panes. Replacing a notice restarts its lifetime, a profile switch or a move to the docs unmounts it, and no notice is stored.
- `removeFromSelection(store, courseId)` in `web/src/features/structure/actions.ts` drops the identity from both sets.
- `applyStructure` in the same file is the only writer of `selectedCourseIds`, `completedCourseIds`, and the structure slice together, and it is described in [Structure model](/docs/frontend/structure-model.md).

## Per-feature slices and wording

| Slice | Fields |
|---|---|
| `search` | `query`, `activeOnly` |
| `compare` | `slots` (two nullable canonical identities), `pickerQuery`, `pickerActiveOnly` |
| `prerequisites` | `rootCourseId`, `courseQuery`, `includeRecommended`, `includeInferred`, `activeOnly`, `basis`, `excludedCourseIds`, `completedNodeKeys`, `excludedNodeKeys` |
| `discover` | `list`, `mode`, `activeOnly`, `basis`, `basisExpanded` |
| `structure` | `programmeGroupIds`, `moduleVersions`, `choices`, `coursePlacements`, `modulePlacements`, `placedCourseIds` |

`UI_TEXT` in `web/src/shared/wording.ts` holds one `{ en, fi }` entry per app-authored string, keyed by the English literal, and `UiTextKey` is the key union. `uiText(language, key, values)` selects the entry, substitutes the named `{placeholder}` values, and throws on an unknown key or on a placeholder that has no supplied value. A context suffix such as `Completed (basis)` or `Completed (course)` splits one English word into the Finnish form the context needs. `searchMethodLabel` maps a `SearchMethod` token to its key, `reasonText` maps a backend reason token to its key and shows an unknown token in raw form, and `diagnosticText` appends the detail under the localized `Original technical detail` label. `useWording()` reads the language from the current profile and returns `t`, so every component renders in the language of the open profile.

## Async reads, cancellation and request identity

`web/src/app/cachedRead.ts` is the one publication rule for a dataset-bound successful read:

- `readCachedReport(cache, key, read, signal)` returns a held successful value without a request. Otherwise it captures the cache identity, reads once, calls `acceptDatasetRead` and stores the report under its own identity.
- `acceptDatasetRead(cache, startingIdentity, responseIdentity, signal)` stops a cancelled read, rejects a response of the previous dataset when the cache already observed another one, and records the response identity. An older outstanding read therefore never rolls the cache backwards.
- `ReadCache.observeDatasetIdentity(identity)` performs the identity-change clear, and `put` delegates to it. The cache keeps one bounded map of successful values and no error or cancelled response.

`web/src/shared/course/reads.ts` wraps the course-summary read in that rule under `JSON.stringify(["course-summaries", identifiers])`, preserving caller order and repeats. Empty input returns an empty identity-tagged report without a request. `web/src/shared/course/catalogue.ts` reads the minimal official catalogue under `JSON.stringify(["catalogue"])` and coalesces simultaneous consumers through one module-local `WeakMap` keyed by the cache, holding only a pending fetch that settles and is removed.

`web/src/shared/course/useCatalogueRead.ts` owns the common identity-gated lifecycle of that read, and `useCourseLookup` and `useModuleLookup` narrow the returned catalogue locally. A module lookup returns one row per canonical group, carrying the group's full eligible candidate list and the displayed candidate's code and names, so it never raises for an ambiguous group and never chooses a version. The group matching rule is stated in [Search](/docs/backend/search-and-discovery/search.md#the-minimal-official-catalogue). A course lookup has no error path of its own.

Both lookup hooks memoize their narrowing result over the catalogue, the query and the language, and the course lookup also memoizes over the course activity scope. The module lookup memoizes its group rows without an ambiguity branch. The drawer search memoizes its category filter over the module results and the chosen category.

The lookup list in `web/src/shared/LookupVirtualList.tsx` owns only transient measurements and transient row focus. It keeps one index-to-key reader and one scroll-owner reader across a scroll render, and each caller passes a module-scope key function. It returns focus to the surface's query field, through the ref the surface supplies, when a focused row disappears and the list held that focus, and it never takes focus from a control outside the list. A surface without a query ref, such as the version picker, passes no ref. No measurement or focus enters the stored envelope, the memory cache or the derived structure store.

The hooks and their keys:

| Owner | Key |
|---|---|
| `useSearch` in `web/src/features/search/useSearch.ts` | `JSON.stringify(["search", request])` with every submitted request field, checked inside the submitted-read effect |
| `useComparison` in `web/src/features/compare/useComparison.ts` | `JSON.stringify(["comparison", a, b])` in caller A/B order |
| `useDiscovery` in `web/src/features/discover/useDiscovery.ts` | `JSON.stringify([list, request])`, decoded inside the effect, which depends on that key, the cache and the basis flag rather than on the caller's request or list references, and asks for nothing without a basis |
| `useCourseSummaries` in `web/src/shared/course/useCourseSummaries.ts` | `readCachedCourseSummaries`, holding the requested courses that already arrived while others load |
| `usePrerequisiteReport` in `web/src/features/prerequisites/usePrerequisiteReport.ts` | The graph's structural key through `readCachedReport`, with `ready` only for the settled response of the active root and its exact key |

`ComparePane` and `ComparisonReplaceDialog` call `useCourseSummaries` twice, with a singleton identifier list for an occupied slot and an empty list for an empty slot or a closed dialog. A change to one slot reads only the course that takes it, and the other slot's summary comes from the cache under its own key.

Every one of those hooks aborts its pending read on an input change or unmount and drops a settled result whose signal is aborted. A hit sends no request.

`useMinimumRoute` in `web/src/features/prerequisites/route/useMinimumRoute.ts` keeps its own route key, which covers the dataset identity, the structural graph key, the complete live input key and the allocation limit, and it starts one disposable worker only on an explicit click. A successful outcome joins the same `ReadCache` before the hook publishes it, and every input, readiness, report, dataset, pane or unmount change aborts the worker and drops the visible result.

The structure reads share one owner. `web/src/features/structure/structureReads.ts` returns every requested root from the memory cache, then from the persistent store, then from one batch request for what remains. The memory key is `["study-structure", rootGroupId, moduleVersionKey(moduleVersions)]`, and the request carries the same map. It caches only per-root reports, persists only the roots a response returned, and settles an unavailable or version-selection-required root for that operation alone. `moduleVersionKey` in `web/src/features/structure/moduleVersions.ts` is the canonical JSON of the map's entries sorted by group, and it is an identity helper, not a resolver. A network response of another dataset identity cannot mix roots of the previous identity into the result.

`web/src/features/structure/structureStorage.ts` owns the IndexedDB database `tuni-course-explorer-structures`, version 2, with the object store `reports` keyed by `[datasetIdentity, rootGroupId, selectionKey]`. Its upgrade deletes an existing version-1 `reports` store and creates the one store, so only derived reports are discarded and localStorage is untouched. Every operation prunes the entries of other identities in the same transaction, settles on transaction completion, rejects an open, blocked or transaction failure, and closes the connection. It stores no mark, completion, profile setting, timestamp or query.

`usePlacedContent(courseIds, moduleIds, moduleVersions, allowUnrepresented = false)` in `web/src/features/structure/usePlacedContent.ts` is the one Structure hydration owner, including the programme reports. It reads missing courses through `readCachedCourseSummaries` once and all missing modules through `readCachedStudyStructures` once under the same map. A missing requested course becomes `unavailableCourseIds` only with `allowUnrepresented`, the structure response's unavailable identities become `unavailableModuleIds`, and its selection-required identities become the separate `versionSelectionRequiredIds`. Both settled module lists are excluded from missing-root detection and cleared when the selection key changes. A failed summary request is never converted into an omission.

Its hydrated state carries the serving identity and the selection key, and a render whose state belongs to another identity or key shows an empty view and reads the missing inputs once under the discovered identity. `extend({ datasetIdentity, courses?, reports?, moduleVersions? })` requires the extension's identity to equal the cache identity before it merges. Reports require their prospective map, and a different selection key starts from the same-dataset course summaries alone without another key's reports or settled module lists. The merged prospective context is returned to the operation but installed as live hydration only for the live selection key. When a summary read and a structure read return different identities, the hook fails with one dataset-changed error and updates nothing.

`useProgrammeActions` and the `addModule` operation of `useStructureEditor` read through `readProspectiveStructure` in `web/src/features/structure/structureReads.ts`, which is the one prospective-read owner for both. Each caller builds its prospective map from the refreshed stored map plus its picked exact id, and the owner reads every current programme root, every placed module root and the candidate under that map. It reuses supplied content only when both its dataset and selection identities match and every requested root is present, and otherwise reads the whole requested set once. `useProgrammeActions(content, extend, confirmMoves, contentDatasetIdentity, contentSelectionKey)` and the matching options of `useStructureEditor` name the identity of the content they were rendered from, so a supplied report answers an operation only while both identities are current.

Each operation aborts the previous one, captures `store.getSnapshot().currentProfileId`, the programme list and the base selection key before the read, and refreshes the saved envelope after it. A report that arrives after a profile switch, programme-list change or selection change is discarded. A module operation reports a changed programme list, a changed version selection and a changed serving dataset as three distinct messages, while `useProgrammeActions.refreshed` returns without a write on a changed profile, programme list or selection.

A module operation holds its abort controller, its pending identity and its visible error across the move confirmation as well: it refreshes the saved envelope before the question and after the answer, refuses a profile, programme list or selection that moved on, and derives its write from the current profile state inside the store callback. A pick that conflicts with an existing version of the same group raises `Another version of this module is already selected` and writes nothing.

`App` renders `<TabCarousel key={currentProfileId} />`, so a profile switch remounts the carousel and its search session and unmounts every pane hook that owns a request. `SearchSessionProvider` in `web/src/features/search/SearchSession.tsx` sits above the panes, so the submitted search and its report survive a move between tabs and are dropped with the remount.

## Where a change belongs and what covers it

- A field that must survive a reload belongs in `ProfileState` in `web/src/state/types.ts`, its initial value in `initialProfileState()` in `web/src/state/defaults.ts`, its slice type and constructor in `web/src/features/<feature>/state.ts`, and a check in `validateProfileState` in `web/src/state/validation.ts`.
- A change to a shared course set belongs in `web/src/state/course-actions.ts`. A feature-owned change belongs in that feature's `actions.ts`, reaches the store through `updateCurrent`, and returns the same state reference when nothing changes.
- An exported file kind belongs in the `BrowserFile` union in `web/src/state/types.ts`, an imported kind belongs in `BrowserImport`, and each imported kind takes one case in `parseBrowserImport`.
- An app-authored string belongs in `UI_TEXT`. A message that the error boundary should read in the profile language belongs in both `UI_TEXT` and `KNOWN_MESSAGES`.

| Test file | Covers |
|---|---|
| `web/src/state/profiles.test.ts` | Profile isolation across a reload, the projected prerequisites slice, `Save as` with an independent copy and a refused duplicate name, deleting the current profile selecting the first of those left, rename changing the name only, the stored value left as it is after a refused operation, a stale tab applying its change to the stored envelope, an exported profile imported as an independent current profile with its duplicate name refused, and a full-state restore from an exported envelope |
| `web/src/state/course-actions.test.ts` | Completion persisted as a subset of the selection, and an added course persisted once with its completion and the count its latest stored envelope gained |
| `web/src/app/language.test.ts` | The language control switching every shell word and leaving the profile name and the study slices untouched |
| `web/src/shared/ErrorNotice.test.ts` | One localized summary with the diagnostic text under the localized label |
| `web/src/features/compare/actions.test.ts` | Slot uniqueness, the write-free duplicate and full-slot refusals, and a slot removal that leaves the study slices at their references and the saved study values as they are |
| `web/src/features/compare/ComparePane.test.ts` | One slot's replacement summary read while the other slot's card stays the same node |
| `web/src/features/compare/results.test.ts` | An unavailable meter rendered apart from a zero value, and the meter positions held during a slot change until its report settles |
| `web/src/features/discover/actions.test.ts` | The Discover options persisted without a change to the shared course sets or the exclusion |
| `web/src/features/discover/DiscoverControls.test.ts` | The saved list left as it is when its effective tab is selected, and recommended result rows that stay the same node after another tab adds a comparison course |
| `web/src/features/structure/model.test.ts` | Choice resolution, single placement, and the projection of the rule kinds |
| `web/src/features/structure/edits.test.ts` | The scoped reset and the resolved-destination placement of an added module |
| `web/src/features/structure/actions.test.ts` | The selection migration, the completion that outlives a deselection, the Unplaced studies reset with the version entries of the groups it removes, a shared course moving into the later holder and staying out of an untouched holder, the scoped programme replace and reset with their surviving and departing version selections, and deleting a programme with the selections of its root and nested module |
| `web/src/features/structure/sisu.test.ts` | A downloaded capture parsed into a reloadable profile with its pending hierarchy and no fetch, the placement of captured choices in their programme scopes with one atomic pending clear, the named omissions of a partial catalogue with the representable courses kept loose, and a restored profile that keeps its saved edits and waiting capture without an automatic write |
| `web/src/features/structure/useStructureEditor.test.ts` | A structure edit another tab saves while a module confirmation waits, which the confirmed move keeps, the containing module named for a chosen course, and the containing module named in a pulled-course confirmation |
| `web/src/app/readCache.test.ts` | Dataset-scoped reads, the clear on another dataset identity, and the least-recently-used eviction at capacity with a refreshed recency on a hit |
| `web/src/app/cachedRead.test.ts` | A successful feature read reused across a pane remount with one read boundary |
| `web/src/shared/course/narrowing.test.ts` | The displayed official course substring contract with FI/EN fallback, hidden names, NFKC, casefolding, no cap and the activity/name/code/ID order, and the module group rows with programme order, the displayed candidate's fields, the full candidate list and the sibling match |
| `web/src/features/prerequisites/route/useMinimumRoute.test.ts` | The explicit worker calculation behind a ready report, the cache hit on a repeat click, the cleared and un-restored visible route, and the discard of obsolete work on an input, readiness, report, dataset, pane or unmount change |
