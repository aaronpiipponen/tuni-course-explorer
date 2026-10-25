/** Prerequisites' course selection, display options and report-owned node marks. */
import type { CourseId } from "../../state/types";

/** The prerequisite root, display options and report-issued node marks. */
export type PrerequisitesState = {
  rootCourseId: CourseId | null;
  courseQuery: string;
  includeRecommended: boolean;
  includeInferred: boolean;
  activeOnly: boolean;
  basis: "completed" | "selected";
  excludedCourseIds: CourseId[];
  completedNodeKeys: string[];
  excludedNodeKeys: string[];
};
/** Build the initial prerequisite state. */
export const initialPrerequisitesState = (): PrerequisitesState => ({
  rootCourseId: null,
  courseQuery: "",
  includeRecommended: false,
  includeInferred: false,
  activeOnly: true,
  basis: "completed",
  excludedCourseIds: [],
  completedNodeKeys: [],
  excludedNodeKeys: [],
});
