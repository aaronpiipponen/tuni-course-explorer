/** Comparison-result rendering distinguishes missing analysis from zero and holds meter positions. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";
import type { CourseComparisonReport } from "../../api/types";
import { ReadCacheContext } from "../../app/readCacheContext";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { StoreContext } from "../../state/context";
import { createBrowserStore } from "../../state/store";
import { ComparisonResults } from "./ComparisonResults";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("comparison result presentation", () => {
  beforeEach(() => localStorage.clear());

  it("renders unavailable comparison values distinctly from zero", () => {
    const course = {
      group_id: "course",
      name_fi: null,
      name_en: "Course",
      code: "COURSE",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid",
    };
    const report: CourseComparisonReport = {
      dataset_identity: "dataset-one",
      course_a: course,
      course_b: { ...course, group_id: "other", code: "OTHER" },
      meters: {
        overall_relatedness: 0,
        content_similarity: null,
        learning_outcome_similarity: 20,
        overlap: { a_in_b: 40, b_in_a: null },
      },
      verdict: null,
      uses_derived_text: false,
    };
    const store = createBrowserStore(localStorage);
    const html = renderToStaticMarkup(
      createElement(
        StoreContext.Provider,
        { value: store },
        createElement(ComparisonResults, { report, loading: false }),
      ),
    );
    expect(html).toContain("0 %");
    expect(html).toContain("not available");
    expect(html).toContain("not available</strong>");
  });

  it("holds meter positions while a replacement comparison loads", async () => {
    const course = {
      group_id: "course",
      name_fi: null,
      name_en: "Course",
      code: "COURSE",
      credits_min: "5",
      credits_max: null,
      is_active: true,
      official_url: "https://example.invalid",
    };
    const report = (values: readonly number[]): CourseComparisonReport => ({
      dataset_identity: "dataset-one",
      course_a: course,
      course_b: { ...course, group_id: "other", code: "OTHER" },
      meters: {
        overall_relatedness: values[0],
        content_similarity: values[1],
        learning_outcome_similarity: values[2],
        overlap: { a_in_b: values[3], b_in_a: values[4] },
      },
      verdict: null,
      uses_derived_text: false,
    });
    const store = createBrowserStore(localStorage);
    const identity = "synthetic-dataset";
    const cache = new ReadCache(identity, READ_CACHE_CAPACITY);
    const renderResults = (
      current: CourseComparisonReport | null,
      loading: boolean,
    ) =>
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
            createElement(ComparisonResults, { report: current, loading }),
          ),
        ),
      );
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
    const host = document.createElement("div");
    document.body.append(host);
    const root: Root = createRoot(host);
    const widths = () =>
      [...host.querySelectorAll<HTMLElement>(".comparison-track i")].map(
        (bar) => bar.style.width,
      );
    try {
      await act(async () =>
        root.render(renderResults(report([40, 50, 60, 70, 80]), false)),
      );
      expect(widths()).toEqual(["40%", "50%", "60%", "70%", "80%"]);

      await act(async () => root.render(renderResults(null, true)));
      expect(widths()).toEqual(["40%", "50%", "60%", "70%", "80%"]);
      expect(
        [...host.querySelectorAll(".comparison-meter b")].map(
          (value) => value.textContent,
        ),
      ).toEqual(["–", "–", "–", "–", "–"]);

      await act(async () =>
        root.render(renderResults(report([10, 20, 30, 40, 50]), false)),
      );
      expect(widths()).toEqual(["10%", "20%", "30%", "40%", "50%"]);
    } finally {
      await act(async () => root.unmount());
      host.remove();
      window.matchMedia = originalMatchMedia;
    }
  });
});
