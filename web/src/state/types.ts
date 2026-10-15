/** Profile-owned browser state shapes. Canonical course identities are the only course keys. */
import type { CompareState } from "../features/compare/state";
import type { DiscoverState } from "../features/discover/state";
import type { PrerequisitesState } from "../features/prerequisites/state";
import type { SearchState } from "../features/search/state";
import type { StructureState } from "../features/structure/state";

export type CourseId = string;
export type TabId =
  "search" | "compare" | "prerequisites" | "discover" | "structure";
export type DisplayLanguage = "fi" | "en";
export type ProfileState = {
  language: DisplayLanguage;
  activeTab: TabId;
  selectedCourseIds: CourseId[];
  completedCourseIds: CourseId[];
  search: SearchState;
  compare: CompareState;
  prerequisites: PrerequisitesState;
  discover: DiscoverState;
  structure: StructureState;
};
export type Profile = { name: string; state: ProfileState };
export type BrowserState = {
  schemaVersion: 1;
  currentProfileId: string;
  profiles: Record<string, Profile>;
};
