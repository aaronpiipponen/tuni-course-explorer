/** Profile-owned browser state shapes. Canonical course identities are the only course keys. */
import type { CompareState } from "../features/compare/state";
import type { DiscoverState } from "../features/discover/state";
import type { PrerequisitesState } from "../features/prerequisites/state";
import type { SearchState } from "../features/search/state";
import type { StructureState } from "../features/structure/state";
import type { SisuCaptureFile, SisuPlan } from "../features/structure/sisu";

export type CourseId = string;
export type TabId =
  "search" | "compare" | "prerequisites" | "discover" | "structure";
export type DisplayLanguage = "fi" | "en";
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
export type Profile = { name: string; state: ProfileState };
export type BrowserState = {
  schemaVersion: 2;
  currentProfileId: string;
  profiles: Record<string, Profile>;
};
/** One exported single-profile file. */
export type BrowserProfileFile = {
  type: "tuni-course-explorer/profile/2";
  profile: Profile;
};
/** One exported whole-state file containing the stored envelope text. */
export type BrowserStateFile = {
  type: "tuni-course-explorer/state/2";
  data: string;
};
/** One file the profile menu can export. */
export type BrowserFile = BrowserProfileFile | BrowserStateFile;
/** One parsed and validated import before it is applied. */
export type BrowserImport =
  | BrowserProfileFile
  | { type: "tuni-course-explorer/state/2"; state: BrowserState }
  | SisuCaptureFile;
