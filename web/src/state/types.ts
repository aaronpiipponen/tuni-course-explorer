/** Profile-owned browser state shapes use canonical course identities as course keys. */
import type { CompareState } from "../features/compare/state";
import type { DiscoverState } from "../features/discover/state";
import type { PrerequisitesState } from "../features/prerequisites/state";
import type { SearchState } from "../features/search/state";
import type { StructureState } from "../features/structure/state";
import type { SisuCaptureFile, SisuPlan } from "../features/structure/sisu";

/** Canonical course group identity. */
export type CourseId = string;
/** Served application tab identity. */
export type TabId =
  "search" | "compare" | "prerequisites" | "discover" | "structure";
/** Supported display language. */
export type DisplayLanguage = "fi" | "en";
/** Persistent state owned by one browser profile. */
export type ProfileState = {
  language: DisplayLanguage;
  selectedCourseIds: CourseId[];
  completedCourseIds: CourseId[];
  search: SearchState;
  compare: CompareState;
  prerequisites: PrerequisitesState;
  discover: DiscoverState;
  structure: StructureState;
  /** A captured Sisu hierarchy awaiting Structure's first hydrated placement. */
  pendingSisuImport: SisuPlan | null;
};
/** Named browser profile and its persistent state. */
export type Profile = { name: string; state: ProfileState };
/** Persistent browser envelope containing all profiles. */
export type BrowserState = {
  schemaVersion: 3;
  currentProfileId: string;
  profiles: Record<string, Profile>;
};
/** One exported single-profile file. */
export type BrowserProfileFile = {
  type: "tuni-course-explorer/profile/3";
  profile: Profile;
};
/** One exported whole-state file containing the stored envelope text. */
export type BrowserStateFile = {
  type: "tuni-course-explorer/state/3";
  data: string;
};
/** One file the profile menu can export. */
export type BrowserFile = BrowserProfileFile | BrowserStateFile;
/** One parsed and validated import before it is applied. */
export type BrowserImport =
  | BrowserProfileFile
  | { type: "tuni-course-explorer/state/3"; state: BrowserState }
  | SisuCaptureFile;
