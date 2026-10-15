/** Persistence for the Discover-owned option slice. */
import { beforeEach, describe, expect, it } from "vitest";
import { createBrowserStore } from "../../state/store";
import { setDiscoverOptions } from "./actions";

describe("Discover actions", () => {
  beforeEach(() => localStorage.clear());

  it("Discover options persist without changing shared course or graph state", () => {
    const store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["selected"],
      completedCourseIds: ["selected"],
      prerequisites: {
        ...state.prerequisites,
        excludedCourseIds: ["excluded"],
      },
    }));
    setDiscoverOptions(store, {
      list: "recommended",
      mode: "at_least_one",
      activeOnly: false,
      basis: "selected",
      basisExpanded: true,
    });

    const state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(state.discover).toEqual({
      list: "recommended",
      mode: "at_least_one",
      activeOnly: false,
      basis: "selected",
      basisExpanded: true,
    });
    expect(state.selectedCourseIds).toEqual(["selected"]);
    expect(state.completedCourseIds).toEqual(["selected"]);
    expect(state.prerequisites.excludedCourseIds).toEqual(["excluded"]);
  });
});
