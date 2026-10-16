# Browser state

The browser state is one local-storage envelope of profiles, held by a single store that writes before it publishes.

## The envelope and its types

`web/src/state/types.ts` defines the shapes:

- `CourseId` is a canonical course identity as a string, and it is the only course key the envelope uses.
- `TabId` is `search`, `compare`, `prerequisites`, `discover`, or `structure`.
- `DisplayLanguage` is `fi` or `en`.
- `ProfileState` holds `language`, `activeTab`, `selectedCourseIds`, `completedCourseIds`, and one slice per feature: `search`, `compare`, `prerequisites`, `discover`, and `structure`.
- `Profile` is `{ name, state }`.
- `BrowserState` is `{ schemaVersion: 1, currentProfileId, profiles }`.

`web/src/state/defaults.ts` holds the two constructors. `initialProfileState()` returns English, the `search` tab, empty course sets, and the initial slice of each feature. `initialBrowserState()` returns `schemaVersion: 1`, the current profile `default`, and one profile named `My plan`.

Each feature owns its slice type and its constructor in `web/src/features/<feature>/state.ts`. `StructureState` in `web/src/features/structure/state.ts` adds `rootGroupId` and `placedCourseIds` to `choices`, `coursePlacements`, and `modulePlacements`, and `UNPLACED_KEY` names the place that holds courses with no module.

## One store and one write path

`BrowserStore` in `web/src/state/store.ts` holds the storage object, the snapshot, and a listener set. `createBrowserStore(storage)` reads the envelope and returns the store, and `BROWSER_STORAGE_KEY` (`tuni-course-explorer`) is the single key it reads and writes.

- `getSnapshot` and `subscribe` feed `useSyncExternalStore`. `useCurrentProfile`, `useCurrentProfileId`, and `useProfileSelector` in `web/src/state/` are the React bindings, and `StoreContext` in `web/src/state/context.ts` carries the one store instance.
- `updateCurrent(update)` calls the update with the current profile state and returns without a write when the update returns the same reference. Otherwise it builds the next envelope and commits it.
- `#commit` writes the envelope to storage first and only then assigns the snapshot and notifies the listeners. A write that throws therefore reaches neither the snapshot nor a listener.
- `switchProfile`, `saveAsProfile`, `deleteProfile`, and `renameProfile` commit through the same method.

Every feature action reaches the store through `updateCurrent`: `web/src/app/actions.ts` for the tab, the language, and the prerequisite root, `web/src/state/course-actions.ts` for the shared course sets, and `web/src/features/<feature>/actions.ts` for the slice a feature owns. `setActiveTab` and `openPrerequisites` in `web/src/app/actions.ts` write the shared state, so a course opened from a card sets the tab and the prerequisite root in one update.

## Reading, validating and reporting failures

`readBrowserState` runs once at startup. With no stored value it writes `initialBrowserState()` and uses it. Otherwise it parses the value and requires a non-array object, `schemaVersion === 1`, a string `currentProfileId`, a non-array `profiles` object, a string `name` and a state object on every profile, and a current profile that exists in `profiles`.

`mergeProfileState` starts from `initialProfileState()`, overlays the saved fields, and for each of the five slices requires a non-array object and merges it over that slice's initial value. The prerequisites slice goes through `mergePrerequisitesState`, which projects the saved value onto the fields of `initialPrerequisitesState()`, so a stored write of that slice holds those fields only.

Every validation failure throws an `Error` whose message `errorPresentation` in `web/src/shared/errorPresentation.ts` maps to a wording key. `KNOWN_MESSAGES` holds the app-authored messages, an `ApiError` with status 422 reads as `Invalid request`, any other status reads as `Request failed ({status})`, and an unknown message reads as `Operation failed` with the raw text as detail.

`web/src/main.tsx` creates the one store inside a `try`. A read failure renders `ErrorNotice` with no language, which shows the English and the Finnish summary with one diagnostic detail, and the stored bytes are not reset. `useAction` in `web/src/shared/useAction.ts` wraps a UI action: it clears the error when the action succeeds and exposes the thrown error otherwise, and its optional `clearAfterMs` clears the message after that long. `ProfileButton` uses five seconds for the profile menu.

## Profile operations

- `switchProfile(id)` requires a profile that the envelope holds and returns without a write when the identity is already current.
- `saveAsProfile(name)` trims the name, rejects an empty name and a name that another profile holds, builds an identity from `crypto.getRandomValues`, copies the current state with `structuredClone`, and makes the copy current.
- `deleteProfile(id)` requires a profile that the envelope holds and refuses to delete the only profile. Deleting the current profile selects the first profile in insertion order.
- `renameProfile(id, name)` trims the name, rejects an empty name and a name that another profile holds, returns without a write when the name equals the stored one, and changes the name only.

`ProfilePanel` in `web/src/features/profiles/ProfilePanel.tsx` owns the list, the copy form, the rename dialog, and the delete dialog, and it hides the delete control while the profile list holds one profile. `ProfileButton` owns the profiles menu and the store calls.

## Selected and completed courses

- `toggleCompleted(store, courseId)` in `web/src/state/course-actions.ts` adds the identity to `completedCourseIds` and to `selectedCourseIds` when it is not completed, and removes it from `completedCourseIds` alone when it is. A completed course is therefore always selected.
- `addCoursesToFreeChoice(store, courseIds)` appends the identities that are not already selected, de-duplicated through a `Set`, and leaves the completion set alone.
- `removeFromSelection(store, courseId)` in `web/src/features/structure/actions.ts` drops the identity from both sets.
- `applyStructure` in the same file is the only writer of `selectedCourseIds`, `completedCourseIds`, and the structure slice together, and it is described in [Structure model](/docs/frontend/structure-model.md).

## Per-feature slices and wording

| Slice | Fields |
|---|---|
| `search` | `query`, `activeOnly` |
| `compare` | `slots` (two nullable canonical identities), `pickerQuery`, `pickerActiveOnly` |
| `prerequisites` | `rootCourseId`, `courseQuery`, `includeRecommended`, `includeInferred`, `activeOnly`, `basis`, `excludedCourseIds`, `completedNodeKeys`, `excludedNodeKeys` |
| `discover` | `list`, `mode`, `activeOnly`, `basis`, `basisExpanded` |
| `structure` | `rootGroupId`, `choices`, `coursePlacements`, `modulePlacements`, `placedCourseIds` |

`UI_TEXT` in `web/src/shared/wording.ts` holds one `{ en, fi }` entry per app-authored string, keyed by the English literal, and `UiTextKey` is the key union. `uiText(language, key, values)` selects the entry, substitutes the named `{placeholder}` values, and throws on an unknown key or on a placeholder that has no supplied value. A context suffix such as `Completed (basis)` or `Completed (course)` splits one English word into the Finnish form the context needs. `searchMethodLabel` maps a `SearchMethod` token to its key, `reasonText` maps a backend reason token to its key and shows an unknown token in raw form, and `diagnosticText` appends the detail under the localized `Original technical detail` label. `useWording()` reads the language from the current profile and returns `t`, so every component renders in the language of the open profile.

## Async reads, cancellation and request identity

`useLookup(key, enabled, run, delayMs)` in `web/src/shared/useLookup.ts` is the shared read lifecycle:

- It aborts the pending request when the key, the enabled flag, the `run` identity, or the delay changes, and on unmount.
- It sets `loading` and drops a settled result whose signal is aborted, so a report for other inputs is never published.
- While the result key differs from the requested key it reads `loading: true` with a null report.
- `LOOKUP_DEBOUNCE_MS` is 200, and a delay of zero asks at once.

The owners of each key:

| Owner | Key |
|---|---|
| `useSearch` in `web/src/features/search/useSearch.ts` | The submitted request with the live language and activity scope, plus a submit serial |
| `useComparison` in `web/src/features/compare/useComparison.ts` | `JSON.stringify([a, b])` of the two slots |
| `useDiscovery` in `web/src/features/discover/useDiscovery.ts` | The chosen list plus the serialized request, and it asks for nothing without a basis |
| `useCourseSummaries` in `web/src/shared/course/useCourseSummaries.ts` | The identity list, and the loaded courses that the requested identities name are held while the others load |
| `useStructureReport` in `web/src/features/structure/useStructureReport.ts` | The root identity, and it asks for nothing without a root |

Three structure reads bypass `useLookup`. `useChooseRoot` and the `addModule` operation of `useStructureEditor` call `readStudyStructure` directly, abort the previous operation of their own, capture `store.getSnapshot().currentProfileId` before the request, and compare it with the current profile before they write, so a report that arrives after a profile switch is discarded. `usePlacedContent` in `web/src/features/structure/usePlacedContent.ts` runs its own effect keyed on the serialized course and module identity lists, starts one `AbortController` for the identities it is missing, and aborts it on cleanup, so a change to either list and an unmount cancel the pending read.

`App` renders `<TabCarousel key={currentProfileId} />`, so a profile switch remounts the carousel and its search session and unmounts every pane hook that owns a request. `SearchSessionProvider` in `web/src/features/search/SearchSession.tsx` sits above the panes, so the submitted search and its report survive a move between tabs and are dropped with the remount.

## Where a change belongs and what covers it

- A field that must survive a reload belongs in `ProfileState` in `web/src/state/types.ts`, its initial value in `initialProfileState()` in `web/src/state/defaults.ts`, its slice type and constructor in `web/src/features/<feature>/state.ts`, and a merge case in `mergeProfileState`.
- A change to a shared course set belongs in `web/src/state/course-actions.ts`. A feature-owned change belongs in that feature's `actions.ts`, reaches the store through `updateCurrent`, and returns the same state reference when nothing changes.
- An app-authored string belongs in `UI_TEXT`. A message that the error boundary should read in the profile language belongs in both `UI_TEXT` and `KNOWN_MESSAGES`.

| Test file | Covers |
|---|---|
| `web/src/state/profiles.test.ts` | Profile isolation across a reload, the projected prerequisites slice, `Save as` with an independent copy and a refused duplicate name, deleting the current profile selecting the first of those left, rename changing the name only, and the stored value left as it is after a refused operation |
| `web/src/state/course-actions.test.ts` | Completion persisted as a subset of the selection, and an added course persisted once with its completion |
| `web/src/app/language.test.ts` | The language control switching every shell word and leaving the profile name and the study slices untouched |
| `web/src/shared/ErrorNotice.test.ts` | One localized summary with the diagnostic text under the localized label |
| `web/src/features/compare/actions.test.ts` | Slot uniqueness, the replace-required outcome, and a slot removal that leaves the study state alone |
| `web/src/features/compare/results.test.ts` | An unavailable meter rendered apart from a zero value |
| `web/src/features/discover/actions.test.ts` | The Discover options persisted without a change to the shared course sets or the exclusion |
| `web/src/features/structure/model.test.ts` | Choice resolution, single placement, and the projection of the rule kinds |
| `web/src/features/structure/edits.test.ts` | The scoped reset and the resolved-destination placement of an added module |
| `web/src/features/structure/actions.test.ts` | The selection migration, the completion that outlives a deselection, and the Unplaced studies reset |
