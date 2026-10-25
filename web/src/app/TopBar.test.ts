/** Rendered proof that the header follows the served tab set and resolves a stored Compare tab. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setActiveTab } from "./sessionTab";
import { TABS } from "./tabs";
import { TopBar } from "./TopBar";
import { WebFeaturesContext } from "./webFeaturesContext";
import { StoreContext } from "../state/context";
import { createBrowserStore, type BrowserStore } from "../state/store";
import { uiText } from "../shared/wording";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const originalMedia = globalThis.matchMedia;
const originalObserver = globalThis.ResizeObserver;

function restore(target: object, name: string, value: unknown) {
  if (value === undefined) Reflect.deleteProperty(target, name);
  else Reflect.set(target, name, value);
}

describe("served header tabs", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

  beforeEach(() => {
    // jsdom has no layout observer or media queries, and the header measures its own height.
    globalThis.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
    localStorage.clear();
    sessionStorage.clear();
    setActiveTab("compare");
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    sessionStorage.clear();
    setActiveTab("search");
    restore(globalThis, "matchMedia", originalMedia);
    restore(globalThis, "ResizeObserver", originalObserver);
  });

  it("offers the served tabs and resolves a stored Compare tab to Search", () => {
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(
            WebFeaturesContext.Provider,
            {
              value: {
                embeddings_enabled: false,
                inference_enabled: true,
                dataset_identity: "synthetic-dataset",
              },
            },
            createElement(TopBar, { openDocs: () => {} }),
          ),
        ),
      ),
    );
    const navigation = container.querySelector<HTMLElement>(
      'nav[aria-label="' + uiText("en", "Main navigation") + '"]',
    );
    expect(navigation).toBeTruthy();
    const tabs = [
      ...(navigation?.querySelectorAll<HTMLButtonElement>(".nav-tab") ?? []),
    ];
    const served = TABS.filter((tab) => tab.id !== "compare");
    expect(tabs.map((tab) => tab.textContent)).toEqual(
      served.map((tab) => uiText("en", tab.labelKey)),
    );
    expect(tabs.map((tab) => tab.textContent)).not.toContain(
      uiText("en", "Compare"),
    );
    expect(tabs.filter((tab) => tab.classList.contains("active"))).toHaveLength(
      1,
    );
    expect(tabs[0].classList.contains("active")).toBe(true);
  });
});
