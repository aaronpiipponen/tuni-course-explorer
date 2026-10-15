/** Browser-store persistence for canonical selected and completed ownership. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore } from "./store";
import { addCoursesToFreeChoice, toggleCompleted } from "./course-actions";
import { BROWSER_STORAGE_KEY } from "./store";

describe("course actions", () => {
  beforeEach(() => localStorage.clear());

  it("persists canonical completion as a subset of current-profile selections", () => {
    const store = createBrowserStore(localStorage);
    toggleCompleted(store, "canonical-course-id");
    let current =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(current.selectedCourseIds).toEqual(["canonical-course-id"]);
    expect(current.completedCourseIds).toEqual(["canonical-course-id"]);
    expect(
      createBrowserStore(localStorage).getSnapshot().currentProfileId,
    ).toBe("default");

    toggleCompleted(createBrowserStore(localStorage), "canonical-course-id");
    current = JSON.parse(localStorage.getItem(BROWSER_STORAGE_KEY)!).profiles
      .default.state;
    expect(current.selectedCourseIds).toEqual(["canonical-course-id"]);
    expect(current.completedCourseIds).toEqual([]);
  });

  it("adds missing module courses to Unplaced studies once and preserves completion", () => {
    const store = createBrowserStore(localStorage);
    toggleCompleted(store, "already-completed");
    addCoursesToFreeChoice(store, [
      "already-completed",
      "module-course",
      "module-course",
    ]);
    addCoursesToFreeChoice(store, ["already-completed", "module-course"]);
    const state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).toEqual([
      "already-completed",
      "module-course",
    ]);
    expect(state.completedCourseIds).toEqual(["already-completed"]);
  });
});
