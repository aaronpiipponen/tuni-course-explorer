/** Real-pane proof that one comparison slot hydrates without reading the other. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReadCacheContext } from "../../app/readCacheContext";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { NoticeProvider } from "../../shared/NoticeProvider";
import { StoreContext } from "../../state/context";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import type {
  CourseComparisonReport,
  CourseSummary,
  CourseSummariesReport,
} from "../../api/types";
import { ComparePane } from "./ComparePane";
import { replaceComparisonSlot } from "./actions";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("Compare slot hydration", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;
  const identity = "synthetic-dataset";
  const summaries: Record<string, CourseSummary> = {
    "course-a": {
      group_id: "course-a",
      name_fi: null,
      name_en: "Course A",
      code: "COURSE-A",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid/a",
    },
    "course-b": {
      group_id: "course-b",
      name_fi: null,
      name_en: "Course B",
      code: "COURSE-B",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid/b",
    },
    "course-c": {
      group_id: "course-c",
      name_fi: null,
      name_en: "Course C",
      code: "COURSE-C",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid/c",
    },
  };

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      language: "en",
      compare: { ...state.compare, slots: ["course-a", "course-b"] },
    }));
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  function comparisonReport(
    courseA: CourseSummary,
    courseB: CourseSummary,
  ): CourseComparisonReport {
    return {
      dataset_identity: identity,
      course_a: courseA,
      course_b: courseB,
      meters: {
        overall_relatedness: 40,
        content_similarity: 50,
        learning_outcome_similarity: 60,
        overlap: { a_in_b: 70, b_in_a: 80 },
      },
      verdict: "partly_overlapping",
      uses_derived_text: false,
    };
  }

  function response(payload: unknown): Response {
    return {
      ok: true,
      status: 200,
      json: async () => payload,
    } as unknown as Response;
  }

  it("retains the unchanged slot summary when the other slot changes", async () => {
    const summaryRequests: string[][] = [];
    const fetchFixture = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const body = init?.body ? JSON.parse(String(init.body)) : null;
        if (path === "/api/course-summaries") {
          const identifiers = body.identifiers as string[];
          summaryRequests.push(identifiers);
          const report: CourseSummariesReport = {
            results: identifiers.map((id) => summaries[id]),
            dataset_identity: identity,
          };
          return response(report);
        }
        if (path === "/api/comparison") {
          return response(
            comparisonReport(
              summaries[body.course_a as string],
              summaries[body.course_b as string],
            ),
          );
        }
        throw new Error(`Unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchFixture);
    const cache = new ReadCache(identity, READ_CACHE_CAPACITY);
    for (const id of ["course-a", "course-b"]) {
      cache.put(identity, JSON.stringify(["course-summaries", [id]]), {
        dataset_identity: identity,
        results: [summaries[id]],
      });
    }
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    const render = async () => {
      await act(async () =>
        root.render(
          createElement(
            StoreContext.Provider,
            { value: store },
            createElement(
              ReadCacheContext.Provider,
              { value: cache },
              createElement(
                WebFeaturesContext.Provider,
                {
                  value: {
                    embeddings_enabled: true,
                    inference_enabled: true,
                    dataset_identity: identity,
                  },
                },
                createElement(NoticeProvider, null, createElement(ComparePane)),
              ),
            ),
          ),
        ),
      );
      await act(async () => {});
    };
    try {
      await render();
      const unchanged = container.querySelector('[data-slot="1"] .course-card');
      expect(unchanged).toBeTruthy();
      expect(summaryRequests).toEqual([]);

      await act(async () => {
        replaceComparisonSlot(store, "course-c", 0);
      });
      await act(async () => {});
      await act(async () => {});

      expect(summaryRequests).toEqual([["course-c"]]);
      expect(container.querySelector('[data-slot="1"] .course-card')).toBe(
        unchanged,
      );
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });
});
