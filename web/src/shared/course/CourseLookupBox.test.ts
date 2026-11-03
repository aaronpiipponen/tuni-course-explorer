/** Rendered proof that the shared course picker places its activity control by width. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { ReadCacheContext } from "../../app/readCacheContext";
import { StoreContext } from "../../state/context";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import { uiText } from "../wording";
import { CourseLookupBox } from "./CourseLookupBox";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const originalMedia = globalThis.matchMedia;

describe("course picker activity placement", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;
  let phone = false;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
    globalThis.matchMedia = ((media: string) => ({
      matches: phone,
      media,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    globalThis.matchMedia = originalMedia;
    vi.unstubAllGlobals();
  });

  function render(onActiveOnly: (activeOnly: boolean) => void): void {
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(
            ReadCacheContext.Provider,
            { value: new ReadCache("synthetic-dataset", READ_CACHE_CAPACITY) },
            createElement(CourseLookupBox, {
              open: false,
              query: "",
              onQuery: () => {},
              activeOnly: false,
              onActiveOnly,
              pick: () => ({
                onPick: () => {},
                text: "+ add",
                ariaLabel: "add",
              }),
            }),
          ),
        ),
      ),
    );
  }

  it("keeps one activity control inside the bar on desktop and below it on a phone", () => {
    const changed: boolean[] = [];
    render((activeOnly) => changed.push(activeOnly));

    const desktopChip = container.querySelector(
      ".course-lookup-controls .toggle-chip",
    );
    expect(desktopChip?.textContent).toBe(uiText("en", "Active only"));
    expect(container.querySelector(".course-lookup-filters")).toBeNull();
    act(() =>
      desktopChip?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );
    expect(changed).toEqual([true]);

    act(() => root.unmount());
    phone = true;
    root = createRoot(container);
    render((activeOnly) => changed.push(activeOnly));

    expect(
      container.querySelector(".course-lookup-controls .toggle-chip"),
    ).toBeNull();
    const phoneChip = container.querySelector(
      ".course-lookup-filters .toggle-chip",
    );
    expect(phoneChip?.textContent).toBe(uiText("en", "Active only"));
    act(() =>
      phoneChip?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );
    expect(changed).toEqual([true, true]);
  });
});
