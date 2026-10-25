/** Rendered proof that the lexical fallback notice follows the served semantic switch. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type {
  CourseSummary,
  UnifiedCourseSearchResult,
  UnifiedSearchReport,
} from "../../api/types";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { StoreContext } from "../../state/context";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import { SearchResults } from "./SearchResults";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const identity = "synthetic-dataset";

const course: CourseSummary = {
  group_id: "course-lexical",
  name_fi: null,
  name_en: "Lexical course",
  code: "LEX-101",
  credits_min: "5",
  credits_max: null,
  is_active: true,
  official_url: "https://example.invalid/lex",
};

const result: UnifiedCourseSearchResult = {
  course,
  match_sources: ["substring"],
  fuzzy_score: null,
  semantic_score: null,
};

const report: UnifiedSearchReport = {
  dataset_identity: identity,
  display_language: "en",
  semantic_min_score: 0.5,
  fuzzy_min_score: 0.7,
  include_inactive: true,
  semantic_available: false,
  tier_priority: ["exact_code", "substring", "fuzzy_name", "semantic"],
  results: [result],
};

describe("Search semantic fallback notice", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function render(embeddingsEnabled: boolean): void {
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
                dataset_identity: identity,
              },
            },
            createElement(SearchResults, {
              report,
              loading: false,
              scrollElement: null,
            }),
          ),
        ),
      ),
    );
  }

  it("shows the semantic fallback notice only on a site that serves semantic matching", () => {
    render(true);
    const notice = container.querySelector<HTMLElement>('[role="status"]');
    const framing = container.querySelector<HTMLElement>(".head");
    expect(notice).toBeTruthy();
    expect(framing).toBeTruthy();
    // The fallback is the first child of the result section.
    expect(container.querySelector(".search-results")?.firstElementChild).toBe(
      notice,
    );
    expect(framing?.querySelector("b")?.textContent).toBe("1");

    render(false);
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(container.querySelector(".head b")?.textContent).toBe("1");
  });
});
