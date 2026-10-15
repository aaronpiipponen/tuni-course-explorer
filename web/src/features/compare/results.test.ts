/** Comparison-result rendering distinguishes missing analysis from zero. */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";
import type { CourseComparisonReport } from "../../api/types";
import { StoreContext } from "../../state/context";
import { createBrowserStore } from "../../state/store";
import { ComparisonResults } from "./ComparisonResults";

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
});
