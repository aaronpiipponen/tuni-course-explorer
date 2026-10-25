/** Rendered proof that Search reads the submitted query and re-reads its activity scope. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CourseSummary,
  SearchRequest,
  UnifiedSearchReport,
} from "../../api/types";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { ReadCacheContext } from "../../app/readCacheContext";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { NoticeProvider } from "../../shared/NoticeProvider";
import { uiText } from "../../shared/wording";
import { StoreContext } from "../../state/context";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import { SearchPane } from "./SearchPane";
import { SearchSessionProvider } from "./SearchSession";
import { waitFor } from "../../test/waitFor";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const identity = "synthetic-dataset";
const query = "synthetic topic";

function course(id: string): CourseSummary {
  return {
    group_id: id,
    name_fi: null,
    name_en: `Course ${id}`,
    code: id.toUpperCase(),
    credits_min: "5",
    credits_max: null,
    is_active: true,
    official_url: `https://example.invalid/${id}`,
  };
}

function report(
  request: SearchRequest,
  identifiers: string[],
): UnifiedSearchReport {
  return {
    dataset_identity: identity,
    display_language: request.display_language,
    semantic_min_score: 0.5,
    fuzzy_min_score: 0.7,
    include_inactive: request.include_inactive,
    semantic_available: true,
    tier_priority: ["exact_code", "substring", "fuzzy_name", "semantic"],
    results: identifiers.map((id) => ({
      course: course(id),
      match_sources: ["substring"],
      fuzzy_score: null,
      semantic_score: null,
    })),
  };
}

describe("Search submitted re-read", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;
  const requests: SearchRequest[] = [];
  const originalMedia = globalThis.matchMedia;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    requests.length = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    // jsdom has no media queries. The desktop width keeps the field and activity chip inline.
    globalThis.matchMedia = ((media: string) => ({
      matches: false,
      media,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    globalThis.matchMedia = originalMedia;
    vi.unstubAllGlobals();
  });

  function typeQuery(value: string): void {
    const field = container.querySelector<HTMLTextAreaElement>("textarea");
    if (!field) throw new Error("The search field is missing");
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function submit(): void {
    const form = container.querySelector("form.search-bar");
    if (!form) throw new Error("The search form is missing");
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  }

  it("re-reads the submitted search under the changed activity scope", async () => {
    const fetchFixture = async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      if (String(input) !== "/api/search")
        throw new Error(`Unexpected request ${String(input)}`);
      const request = JSON.parse(String(init?.body)) as SearchRequest;
      requests.push(request);
      const payload = report(
        request,
        request.include_inactive
          ? ["course-one", "course-two"]
          : ["course-one"],
      );
      return {
        ok: true,
        status: 200,
        json: async () => payload,
      } as unknown as Response;
    };
    vi.stubGlobal("fetch", fetchFixture);
    const cache = new ReadCache(identity, READ_CACHE_CAPACITY);

    act(() =>
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
              createElement(NoticeProvider, {
                children: createElement(SearchSessionProvider, {
                  children: createElement(SearchPane),
                }),
              }),
            ),
          ),
        ),
      ),
    );

    act(() => typeQuery(query));
    expect(requests).toHaveLength(0);
    expect(container.querySelector(".head")).toBeNull();

    act(() => submit());
    await waitFor(() =>
      expect(container.querySelector(".head b")?.textContent).toBe("1"),
    );
    expect(requests).toHaveLength(1);
    expect(requests[0].query).toBe(query);
    expect(requests[0].include_inactive).toBe(false);

    // Editing the field is not a submission, so it sends no read.
    act(() => typeQuery(`${query} edited`));
    expect(requests).toHaveLength(1);

    const activity = [
      ...container.querySelectorAll<HTMLButtonElement>("button"),
    ].find(
      (button) => button.textContent?.trim() === uiText("en", "Active only"),
    );
    if (!activity) throw new Error("The activity control is missing");
    act(() => activity.click());
    await waitFor(() =>
      expect(container.querySelector(".head b")?.textContent).toBe("2"),
    );

    expect(requests).toHaveLength(2);
    expect(requests[1].query).toBe(query);
    expect(requests[1].include_inactive).toBe(true);
    expect(container.querySelector(".head b")?.textContent).toBe("2");
  });
});
