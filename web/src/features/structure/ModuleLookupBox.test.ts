/**
 * Rendered proof that a module lookup hands over only an explicitly chosen version.
 *
 * jsdom lays out nothing, so this file supplies the lookup window's viewport and row geometry and
 * one no-op `ResizeObserver`. The test mounts the real window and its installed virtualizer.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogueModule, CatalogueReport } from "../../api/types";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { ReadCacheContext } from "../../app/readCacheContext";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { StoreContext } from "../../state/context";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import { uiText } from "../../shared/wording";
import { ModuleLookupBox } from "./ModuleLookupBox";
import { waitFor } from "../../test/waitFor";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const identity = "synthetic-dataset";
const ROW_HEIGHT = 44;
const VIEWPORT_HEIGHT = 400;

type Candidate = Omit<CatalogueModule, "group_id">;

function candidate(id: string, code: string, name: string): Candidate {
  return {
    sisu_module_id: id,
    module_type: "Module",
    code,
    name_fi: null,
    name_en: name,
    validity_start: "2025-08-01",
    validity_end: null,
    curriculum_periods: [{ id: "2025-2026", academic_year_start: 2025 }],
  };
}

const single = candidate("single-v1", "SYN-SINGLE", "Synthetic single");
const multipleA = candidate(
  "multiple-v1",
  "SYN-MULTI-A",
  "Synthetic multiple A",
);
const multipleB = candidate(
  "multiple-v2",
  "SYN-MULTI-B",
  "Synthetic multiple B",
);

const catalogue: CatalogueReport = {
  dataset_identity: identity,
  courses: [],
  modules: [
    { group_id: "module-single", candidates: [single] },
    {
      group_id: "module-multiple",
      candidates: [multipleA, multipleB],
    },
  ],
};

const originalObserver = globalThis.ResizeObserver;
const originalOffsetHeight = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "offsetHeight",
);

function restore(target: object, name: string, value: unknown) {
  if (value === undefined) Reflect.deleteProperty(target, name);
  else Reflect.set(target, name, value);
}

function installGeometry(): void {
  const boxHeight = (element: HTMLElement) =>
    element.classList.contains("lookup-virtual-row")
      ? ROW_HEIGHT
      : element.classList.contains("lookup-virtual-list")
        ? VIEWPORT_HEIGHT
        : 0;
  // The virtualizer reads `clientHeight` for its viewport and rows, and the row measurement
  // reads `offsetHeight`, so both report the same synthetic geometry.
  for (const name of ["offsetHeight", "clientHeight"] as const)
    Object.defineProperty(HTMLElement.prototype, name, {
      configurable: true,
      get(this: HTMLElement) {
        return boxHeight(this);
      },
    });
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

describe("module version hand-off", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;
  let input: HTMLInputElement;
  const onPick = vi.fn<(module: CatalogueModule) => void>();

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    onPick.mockClear();
    installGeometry();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        throw new Error(`Unexpected request ${String(input)}`);
      }),
    );
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    restore(globalThis, "ResizeObserver", originalObserver);
    if (originalOffsetHeight === undefined)
      Reflect.deleteProperty(HTMLElement.prototype, "offsetHeight");
    else
      Object.defineProperty(
        HTMLElement.prototype,
        "offsetHeight",
        originalOffsetHeight,
      );
    vi.unstubAllGlobals();
  });

  function typeQuery(value: string): void {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function groupRow(groupId: string): HTMLButtonElement {
    const row = container.querySelector<HTMLElement>(
      `.lookup-virtual-row[data-key="${groupId}"]`,
    );
    const button = row?.querySelector("button");
    if (!button) throw new Error(`The lookup row ${groupId} is missing`);
    return button;
  }

  function versionRow(code: string): HTMLButtonElement {
    const buttons = [
      ...container.querySelectorAll<HTMLButtonElement>(".module-version-row"),
    ];
    const found = buttons.find((button) =>
      button.querySelector(".code")?.textContent?.includes(code),
    );
    if (!found) throw new Error(`The version row ${code} is missing`);
    return found;
  }

  it("writes only an explicitly selected module version", async () => {
    const cache = new ReadCache(identity, READ_CACHE_CAPACITY);
    cache.put(identity, JSON.stringify(["catalogue"]), catalogue);
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
              createElement(ModuleLookupBox, {
                open: true,
                pendingId: null,
                onPick,
              }),
            ),
          ),
        ),
      ),
    );
    await waitFor(() => expect(container.querySelector("input")).toBeTruthy());
    input = container.querySelector<HTMLInputElement>("input")!;
    act(() => typeQuery("synthetic"));
    await waitFor(() => expect(groupRow("module-single")).toBeTruthy());
    expect(groupRow("module-multiple")).toBeTruthy();

    // One eligible version is handed over from the row itself.
    act(() => groupRow("module-single").click());
    await waitFor(() => expect(onPick).toHaveBeenCalledTimes(1));
    expect(onPick).toHaveBeenLastCalledWith({
      group_id: "module-single",
      ...single,
    });

    // An ambiguous group opens the exact version picker and writes nothing.
    onPick.mockClear();
    act(() => groupRow("module-multiple").click());
    await waitFor(() =>
      expect(container.querySelector(".module-version-picker")).toBeTruthy(),
    );
    expect(onPick).not.toHaveBeenCalled();
    expect(container.querySelectorAll(".module-version-row")).toHaveLength(2);
    const chosen = versionRow("SYN-MULTI-B");
    act(() => chosen.click());
    await waitFor(() => expect(onPick).toHaveBeenCalledTimes(1));
    expect(onPick).toHaveBeenLastCalledWith({
      group_id: "module-multiple",
      ...multipleB,
    });

    // Repeating the ambiguous activation and cancelling hands over nothing and leaves the filter text in place.
    onPick.mockClear();
    act(() => groupRow("module-multiple").click());
    await waitFor(() =>
      expect(container.querySelectorAll(".module-version-row")).toHaveLength(2),
    );
    const cancel = [
      ...container.querySelectorAll<HTMLButtonElement>(
        ".module-version-cancel button",
      ),
    ].find((button) => button.textContent?.trim() === uiText("en", "Cancel"));
    if (!cancel) throw new Error("The hand-off cancel control is missing");
    act(() => cancel.click());
    await waitFor(() =>
      expect(container.querySelector(".module-version-picker")).toBeNull(),
    );
    expect(onPick).not.toHaveBeenCalled();
    expect(input.value).toBe("synthetic");
    await waitFor(() => expect(document.activeElement).toBe(input));
  });
});
