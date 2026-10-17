/** Shell wording: the language control re-renders words and leaves study state alone. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { StoreContext } from "../state/context";
import { BrowserStore, createBrowserStore } from "../state/store";
import { uiText } from "../shared/wording";
import { TopBar } from "./TopBar";
import { AppFooter } from "./AppFooter";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const FOOTER =
  "This is an independent project that is not affiliated with Tampere University.";

describe("shell language", () => {
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

  it("switches shell wording with the profile language without changing study state", () => {
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: ["canonical-a"],
      completedCourseIds: ["canonical-a"],
      search: { ...state.search, query: "kept query" },
    }));
    const seeded = structuredClone(store.getSnapshot().profiles.default.state);
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(TopBar, { openDocs: () => {} }),
          createElement(AppFooter, {
            repositoryUrl: "https://github.com/owner/repo",
          }),
        ),
      ),
    );
    const footer = container.querySelector(".app-footer-notice");
    const tab = container.querySelector(".nav-tab");
    const control =
      container.querySelector<HTMLButtonElement>(".language-switch");
    expect(footer?.textContent).toBe(uiText("en", FOOTER));
    expect(tab?.textContent).toBe(uiText("en", "Search"));
    expect(control?.getAttribute("aria-label")).toBe(
      uiText("en", "App language: {language}", { language: "EN" }),
    );

    act(() =>
      control?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );

    expect(store.getSnapshot().profiles.default.state.language).toBe("fi");
    expect(footer?.textContent).toBe(uiText("fi", FOOTER));
    expect(tab?.textContent).toBe(uiText("fi", "Search"));
    expect(control?.getAttribute("aria-label")).toBe(
      uiText("fi", "App language: {language}", { language: "FI" }),
    );
    const switched = store.getSnapshot().profiles.default.state;
    // Only the language field moves. The profile name and every study slice are untouched.
    expect({ ...switched, language: seeded.language }).toEqual(seeded);
    expect(store.getSnapshot().profiles.default.name).toBe("My plan");

    act(() =>
      control?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );
    expect(store.getSnapshot().profiles.default.state.language).toBe("en");
    expect(footer?.textContent).toBe(uiText("en", FOOTER));
    expect(store.getSnapshot().profiles.default.state).toEqual(seeded);
  });
});
