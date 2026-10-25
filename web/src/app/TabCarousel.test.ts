/** Carousel touch swipes select one tab per blank-pane gesture through the served ring. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReadCacheProvider } from "./ReadCacheProvider";
import { WebFeaturesContext } from "./webFeaturesContext";
import { NoticeProvider } from "../shared/NoticeProvider";
import { StoreContext } from "../state/context";
import { createBrowserStore, type BrowserStore } from "../state/store";
import { TabCarousel } from "./TabCarousel";
import { setActiveTab } from "./sessionTab";

// The graph's bundled ELK worker cannot start under jsdom, and an empty root lays out no graph.
vi.mock("../features/prerequisites/graph/elk", () => ({
  layoutWithElk: async () => ({ children: [] }),
}));

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const ACTIVE_TAB_KEY = "tuni-course-explorer-active-tab";
const IDENTITY = "synthetic-dataset";

type PointerInit = {
  pointerId: number;
  pointerType: string;
  isPrimary: boolean;
  clientX: number;
  clientY: number;
};

class TestPointerEvent extends Event {
  readonly pointerId: number;
  readonly pointerType: string;
  readonly isPrimary: boolean;
  readonly clientX: number;
  readonly clientY: number;

  constructor(type: string, init: PointerInit) {
    super(type, { bubbles: true, cancelable: true });
    this.pointerId = init.pointerId;
    this.pointerType = init.pointerType;
    this.isPrimary = init.isPrimary;
    this.clientX = init.clientX;
    this.clientY = init.clientY;
  }
}

// jsdom has no media queries, layout observer or pointer capture. The substitute reports the phone
// width and reduced motion, so the release settles its pane without a transition.
const mediaQuery = (query: string) =>
  ({
    matches: true,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList;

const originalMedia = globalThis.matchMedia;
const originalObserver = globalThis.ResizeObserver;
const originalSetCapture = Element.prototype.setPointerCapture;
const originalReleaseCapture = Element.prototype.releasePointerCapture;
const originalHasCapture = Element.prototype.hasPointerCapture;

function restore(target: object, name: string, value: unknown) {
  if (value === undefined) Reflect.deleteProperty(target, name);
  else Reflect.set(target, name, value);
}

describe("carousel touch swipes", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    globalThis.matchMedia = mediaQuery as typeof window.matchMedia;
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
    Element.prototype.setPointerCapture = () => {};
    Element.prototype.releasePointerCapture = () => {};
    Element.prototype.hasPointerCapture = () => false;
    setActiveTab("search");
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    localStorage.clear();
    sessionStorage.clear();
    restore(globalThis, "matchMedia", originalMedia);
    restore(globalThis, "ResizeObserver", originalObserver);
    restore(Element.prototype, "setPointerCapture", originalSetCapture);
    restore(Element.prototype, "releasePointerCapture", originalReleaseCapture);
    restore(Element.prototype, "hasPointerCapture", originalHasCapture);
  });

  it("swipes through the served tab ring in both directions", async () => {
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(ReadCacheProvider, {
            datasetIdentity: IDENTITY,
            children: createElement(
              WebFeaturesContext.Provider,
              {
                value: {
                  embeddings_enabled: false,
                  inference_enabled: false,
                  dataset_identity: IDENTITY,
                },
              },
              createElement(NoticeProvider, null, createElement(TabCarousel)),
            ),
          }),
        ),
      ),
    );
    const carouselWindow =
      container.querySelector<HTMLDivElement>(".carousel-window");
    if (!carouselWindow) throw new Error("The carousel window is missing");
    const settle = async () => {
      for (let attempt = 0; attempt < 20; attempt += 1) {
        if (!container.querySelector(".tab-pane.exiting")) break;
        await act(async () => {
          await new Promise((resolve) => setTimeout(resolve, 20));
        });
      }
      return container.querySelector<HTMLElement>(".tab-pane:not(.exiting)")
        ?.dataset.tab;
    };
    const swipe = (fromX: number, toX: number) => {
      const paneContent = container.querySelector<HTMLElement>(
        ".tab-pane:not(.exiting) .pane-content",
      );
      if (!paneContent) throw new Error("The active pane content is missing");
      const at = (clientX: number) => ({
        pointerId: 7,
        pointerType: "touch",
        isPrimary: true,
        clientX,
        clientY: 300,
      });
      act(() => {
        paneContent.dispatchEvent(
          new TestPointerEvent("pointerdown", at(fromX)),
        );
        paneContent.dispatchEvent(
          new TestPointerEvent("pointermove", at((fromX + toX) / 2)),
        );
        // The carousel takes capture from the touched descendant, whose capture loss bubbles.
        paneContent.dispatchEvent(
          new TestPointerEvent("lostpointercapture", at((fromX + toX) / 2)),
        );
        carouselWindow.dispatchEvent(
          new TestPointerEvent("pointermove", at(toX)),
        );
        carouselWindow.dispatchEvent(
          new TestPointerEvent("pointerup", at(toX)),
        );
      });
    };

    expect(await settle()).toBe("search");
    // A rightward swipe wraps backwards to the last served tab.
    swipe(100, 200);
    expect(await settle()).toBe("structure");
    expect(sessionStorage.getItem(ACTIVE_TAB_KEY)).toBe("structure");
    // A leftward swipe returns to Search, so the ring accepts both directions.
    swipe(300, 200);
    expect(await settle()).toBe("search");
    expect(sessionStorage.getItem(ACTIVE_TAB_KEY)).toBe("search");
    // The next leftward swipe reaches Prerequisites, because the site serves no Compare.
    swipe(300, 200);
    expect(await settle()).toBe("prerequisites");
    expect(sessionStorage.getItem(ACTIVE_TAB_KEY)).toBe("prerequisites");
  });
});
