/** Shared shell actions over the session tab and the current profile's language and graph root. */
import type { BrowserStore } from "../state/store";
import type { CourseId, DisplayLanguage } from "../state/types";
import { setActiveTab } from "./sessionTab";

/** Set the current profile's display language. */
export function setLanguage(
  store: BrowserStore,
  language: DisplayLanguage,
): void {
  store.updateCurrent((state) => ({ ...state, language }));
}

/** Select a prerequisite root and open its tab. */
export function openPrerequisites(
  store: BrowserStore,
  courseId: CourseId,
): void {
  store.updateCurrent((state) => ({
    ...state,
    prerequisites: { ...state.prerequisites, rootCourseId: courseId },
  }));
  setActiveTab("prerequisites");
}
