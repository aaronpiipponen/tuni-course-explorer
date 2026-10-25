/** Browser-state proof that a presented Discover list tab writes no unchanged choice. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CourseSummary, DiscoveryRequest } from "../../api/types";
import { ReadCacheContext } from "../../app/readCacheContext";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { StoreContext } from "../../state/context";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  type BrowserStore,
} from "../../state/store";
import { uiText } from "../../shared/wording";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { NoticeProvider } from "../../shared/NoticeProvider";
import { addToComparison } from "../compare/actions";
import { DiscoverPane } from "./DiscoverPane";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("Discover list preservation", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;
  let originalMatchMedia: typeof window.matchMedia;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      language: "en",
      selectedCourseIds: [],
      completedCourseIds: [],
      discover: { ...state.discover, list: "recommended" },
    }));
    originalMatchMedia = window.matchMedia;
    // The pane hosts the list tabs inline at a desktop width, and the phone options sheet holds no tabs.
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  function render(
    embeddingsEnabled: boolean,
    cache = new ReadCache("synthetic-dataset", READ_CACHE_CAPACITY),
  ): void {
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(
            WebFeaturesContext.Provider,
            {
              value: {
                embeddings_enabled: embeddingsEnabled,
                inference_enabled: true,
                dataset_identity: "synthetic-dataset",
              },
            },
            createElement(
              ReadCacheContext.Provider,
              { value: cache },
              createElement(NoticeProvider, null, createElement(DiscoverPane)),
            ),
          ),
        ),
      ),
    );
  }

  function tabs(): HTMLButtonElement[] {
    return [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  }

  it("preserves the saved list when its effective tab is already selected", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const saved = localStorage.getItem(BROWSER_STORAGE_KEY);

    render(false);
    // The stored Recommended list is not presented while embeddings are off.
    expect(tabs().map((tab) => tab.textContent)).toEqual([
      uiText("en", "Next courses"),
    ]);
    expect(tabs()[0].getAttribute("aria-selected")).toBe("true");

    act(() =>
      tabs()[0].dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );

    expect(store.getSnapshot().profiles.default.state.discover.list).toBe(
      "recommended",
    );
    expect(
      createBrowserStore(localStorage).getSnapshot().profiles.default.state
        .discover.list,
    ).toBe("recommended");
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(saved);

    render(true);
    // The saved choice is presented again without another write.
    expect(tabs().map((tab) => tab.textContent)).toEqual([
      uiText("en", "Next courses"),
      uiText("en", "Recommended"),
    ]);
    expect(
      tabs()
        .find((tab) => tab.textContent === uiText("en", "Recommended"))
        ?.getAttribute("aria-selected"),
    ).toBe("true");
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(saved);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("preserves recommended result rows after another tab adds a comparison course", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    act(() =>
      store.updateCurrent((state) => ({
        ...state,
        selectedCourseIds: ["course-basis"],
        completedCourseIds: [],
        discover: { ...state.discover, list: "recommended", basis: "selected" },
      })),
    );
    const identity = "synthetic-dataset";
    const basisCourse: CourseSummary = {
      group_id: "course-basis",
      name_fi: null,
      name_en: "Basis course",
      code: "BASIS",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid/basis",
    };
    const recommended: CourseSummary = {
      group_id: "course-rec",
      name_fi: null,
      name_en: "Recommended course",
      code: "REC",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid/rec",
    };
    const request: DiscoveryRequest = {
      selected_courses: ["course-basis"],
      completed_courses: [],
      basis: "selected",
      mode: "all",
      display_language: "en",
      include_inferred: true,
      active_only: true,
    };
    const cache = new ReadCache(identity, READ_CACHE_CAPACITY);
    cache.put(identity, JSON.stringify(["recommended", request]), {
      dataset_identity: identity,
      similarity_results: [
        {
          course: recommended,
          relatedness: 37,
          score: 1,
          overlap_with_basis: null,
          uses_derived_text: false,
        },
      ],
    });
    cache.put(
      identity,
      JSON.stringify(["course-summaries", ["course-basis"]]),
      {
        dataset_identity: identity,
        results: [basisCourse],
      },
    );

    render(true, cache);
    await act(async () => {});
    await act(async () => {});
    const row = container.querySelector('[data-course-id="course-rec"]');
    expect(row).toBeTruthy();

    const other = createBrowserStore(localStorage);
    act(() => {
      addToComparison(other, "course-rec");
    });
    act(() => {
      store.refreshFromStorage();
    });

    expect(container.querySelector('[data-course-id="course-rec"]')).toBe(row);
    expect(container.querySelector(".discover-loading")).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
