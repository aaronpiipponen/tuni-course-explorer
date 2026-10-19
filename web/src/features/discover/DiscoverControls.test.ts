/** Browser-state proof that a presented Discover list tab writes no unchanged choice. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StoreContext } from "../../state/context";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  type BrowserStore,
} from "../../state/store";
import { uiText } from "../../shared/wording";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { DiscoverPane } from "./DiscoverPane";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("Discover list preservation", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

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
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
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
              },
            },
            createElement(DiscoverPane),
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
});
