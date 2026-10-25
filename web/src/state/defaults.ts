/** Single constructors for an initial profile and first-visit browser envelope. */
import { initialCompareState } from "../features/compare/state";
import { initialDiscoverState } from "../features/discover/state";
import { initialPrerequisitesState } from "../features/prerequisites/state";
import { initialSearchState } from "../features/search/state";
import { initialStructureState } from "../features/structure/state";
import type { BrowserState, ProfileState } from "./types";

/** Build the initial state for one profile. */
export function initialProfileState(): ProfileState {
  return {
    language: "en",
    selectedCourseIds: [],
    completedCourseIds: [],
    search: initialSearchState(),
    compare: initialCompareState(),
    prerequisites: initialPrerequisitesState(),
    discover: initialDiscoverState(),
    structure: initialStructureState(),
    pendingSisuImport: null,
  };
}

/** Build the first browser envelope with one default profile. */
export function initialBrowserState(): BrowserState {
  return {
    schemaVersion: 3,
    currentProfileId: "default",
    profiles: { default: { name: "My plan", state: initialProfileState() } },
  };
}
