/** Rendered proof that a whole-state import waits for its replacement confirmation. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProfileTransfer } from "./ProfileTransfer";
import { uiText } from "../../shared/wording";
import { StoreContext } from "../../state/context";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  type BrowserStore,
} from "../../state/store";
import { waitFor } from "../../test/waitFor";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const originalMedia = globalThis.matchMedia;

describe("whole-state import confirmation", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;
  let input!: HTMLInputElement;
  let originalFilesDescriptor: PropertyDescriptor | undefined;
  const selectedFiles: File[] = [];
  let payload: string;
  let imported: ReturnType<BrowserStore["getSnapshot"]>;
  let initialEnvelope: string;
  let reload!: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    // jsdom has no media queries. The panel presents its desktop import area.
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
    const realWindow = window;
    reload = vi.fn();
    vi.stubGlobal(
      "window",
      new Proxy(realWindow, {
        get(target, key) {
          if (key === "location") return { reload };
          return Reflect.get(target, key, target);
        },
      }),
    );
    container = document.createElement("div");
    document.body.appendChild(container);

    // A separate storage builds a distinct whole-state file through the real export owner.
    const source = createBrowserStore(sessionStorage);
    source.updateCurrent((state) => ({
      ...state,
      language: "fi",
      selectedCourseIds: ["course-imported"],
      completedCourseIds: ["course-imported"],
      search: { ...state.search, query: "imported query" },
    }));
    payload = JSON.stringify(source.exportState());
    imported = source.getSnapshot();

    store = createBrowserStore(localStorage);
    store.saveAsProfile("Second");
    const envelope = localStorage.getItem(BROWSER_STORAGE_KEY);
    if (envelope === null) throw new Error("The saved envelope is missing");
    initialEnvelope = envelope;
    root = createRoot(container);
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(ProfileTransfer, { store }),
        ),
      ),
    );
    const found =
      container.querySelector<HTMLInputElement>('input[type="file"]');
    if (!found) throw new Error("The file input is missing");
    input = found;
    originalFilesDescriptor = Object.getOwnPropertyDescriptor(input, "files");
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    if (originalFilesDescriptor === undefined)
      Reflect.deleteProperty(input, "files");
    else Object.defineProperty(input, "files", originalFilesDescriptor);
    for (const file of selectedFiles) Reflect.deleteProperty(file, "text");
    selectedFiles.length = 0;
    globalThis.matchMedia = originalMedia;
    vi.unstubAllGlobals();
  });

  async function chooseFile(): Promise<void> {
    const file = new File([payload], "saved-data.json", {
      type: "application/json",
    });
    Object.defineProperty(file, "text", {
      configurable: true,
      value: async () => payload,
    });
    selectedFiles.push(file);
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [file],
    });
    await act(async () => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await waitFor(() =>
      expect(document.body.querySelector('[role="dialog"]')).toBeTruthy(),
    );
  }

  function dialogButton(name: string): HTMLButtonElement {
    const found = [
      ...document.body.querySelectorAll<HTMLButtonElement>(
        '[role="dialog"] button',
      ),
    ].find((button) => button.textContent?.trim() === name);
    if (!found) throw new Error(`The dialog button ${name} is missing`);
    return found;
  }

  it("replaces every profile only after the whole-state import confirmation", async () => {
    await chooseFile();
    expect(reload).not.toHaveBeenCalled();
    expect(document.body.querySelector('[role="dialog"]')).toBeTruthy();
    expect(store.getSnapshot().profiles.default).toBeTruthy();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(initialEnvelope);

    act(() => dialogButton(uiText("en", "Cancel")).click());
    await waitFor(() =>
      expect(document.body.querySelector('[role="dialog"]')).toBeNull(),
    );
    expect(reload).not.toHaveBeenCalled();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(initialEnvelope);
    expect(Object.keys(store.getSnapshot().profiles)).toHaveLength(2);

    await chooseFile();
    expect(reload).not.toHaveBeenCalled();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(initialEnvelope);
    act(() => dialogButton(uiText("en", "Replace")).click());
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));

    const restored = createBrowserStore(localStorage).getSnapshot();
    expect(restored).toEqual(imported);
    expect(Object.keys(restored.profiles)).toEqual(
      Object.keys(imported.profiles),
    );
    expect(restored.currentProfileId).toBe(imported.currentProfileId);
  });
});
