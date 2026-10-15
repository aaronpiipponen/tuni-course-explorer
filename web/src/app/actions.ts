/** Shared shell navigation actions mutate only the current profile. */
import type { BrowserStore } from "../state/store";
import type { CourseId, DisplayLanguage, TabId } from "../state/types";

export function setActiveTab(store: BrowserStore, tab: TabId): void {
  store.updateCurrent((state) => ({ ...state, activeTab: tab }));
}

export function setLanguage(
  store: BrowserStore,
  language: DisplayLanguage,
): void {
  store.updateCurrent((state) => ({ ...state, language }));
}

export function openPrerequisites(
  store: BrowserStore,
  courseId: CourseId,
): void {
  store.updateCurrent((state) => ({
    ...state,
    activeTab: "prerequisites",
    prerequisites: { ...state.prerequisites, rootCourseId: courseId },
  }));
}
