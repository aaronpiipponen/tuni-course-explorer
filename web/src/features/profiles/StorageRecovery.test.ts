/** Rendered proof that unreadable saved data is exported raw and reset only after confirmation. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { StorageRecovery } from "./StorageRecovery";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  exportSavedBrowserData,
  resetBrowserStore,
} from "../../state/store";
import type { BrowserStateFile } from "../../state/types";
import { waitFor } from "../../test/waitFor";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("saved-data reset confirmation", () => {
  let container: HTMLDivElement;
  let root: Root;
  const invalid = '{"schemaVersion": 3, "profiles":';

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem(BROWSER_STORAGE_KEY, invalid);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function button(name: string): HTMLButtonElement {
    const found = [
      ...document.body.querySelectorAll<HTMLButtonElement>("button"),
    ].find((element) => element.textContent?.trim() === name);
    if (!found) throw new Error(`The button ${name} is missing`);
    return found;
  }

  it("resets unreadable saved data only after its confirmation", async () => {
    const captured: { file: BrowserStateFile | null } = { file: null };
    act(() =>
      root.render(
        createElement(StorageRecovery, {
          error: new Error("Saved browser state is invalid"),
          onExport: () => {
            captured.file = exportSavedBrowserData(localStorage);
          },
          onReset: () => {
            resetBrowserStore(localStorage);
          },
        }),
      ),
    );

    act(() => button("Export saved data").click());
    await waitFor(() => expect(captured.file).not.toBeNull());
    expect(captured.file?.data).toBe(invalid);
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(invalid);

    act(() => button("Reset saved data").click());
    await waitFor(() =>
      expect(document.body.querySelector('[role="dialog"]')).toBeTruthy(),
    );
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(invalid);

    act(() => button("Cancel").click());
    await waitFor(() =>
      expect(document.body.querySelector('[role="dialog"]')).toBeNull(),
    );
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(invalid);

    act(() => button("Reset saved data").click());
    await waitFor(() =>
      expect(document.body.querySelector('[role="dialog"]')).toBeTruthy(),
    );
    act(() => button("Reset").click());
    await waitFor(() =>
      expect(localStorage.getItem(BROWSER_STORAGE_KEY)).not.toBe(invalid),
    );

    const restored = createBrowserStore(localStorage).getSnapshot();
    expect(Object.keys(restored.profiles)).toEqual(["default"]);
    expect(restored.currentProfileId).toBe("default");
    expect(restored.profiles.default.name).toBe("My plan");
  });
});
