/** Persistence for graph-only marks, which leave shared course state alone. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore } from "../../state/store";
import { toggleNodeCompleted, toggleNodeExcluded } from "./actions";

describe("prerequisite graph actions", () => {
  beforeEach(() => localStorage.clear());
  it("graph-only node marks never change course state and completing or excluding a node clears the opposite mark", () => {
    const store = createBrowserStore(localStorage);
    toggleNodeCompleted(store, "module:one");
    toggleNodeExcluded(store, "module:one");
    toggleNodeCompleted(store, "module:one");
    const state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.selectedCourseIds).toEqual([]);
    expect(state.completedCourseIds).toEqual([]);
    expect(state.prerequisites.completedNodeKeys).toEqual(["module:one"]);
    expect(state.prerequisites.excludedNodeKeys).toEqual([]);
  });
});
