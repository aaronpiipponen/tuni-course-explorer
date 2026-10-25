/** Rendered proof that a full comparison asks which slot changes and cancel writes nothing. */
import { act, createElement, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { CourseSummary } from "../../api/types";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import { ReadCacheContext } from "../../app/readCacheContext";
import { StoreContext } from "../../state/context";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  type BrowserStore,
} from "../../state/store";
import { ComparisonReplaceDialog } from "./ComparisonReplaceDialog";
import { waitFor } from "../../test/waitFor";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const identity = "synthetic-dataset";

function summary(id: string): CourseSummary {
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

const summaries = {
  "course-a": summary("course-a"),
  "course-b": summary("course-b"),
  "course-c": summary("course-c"),
} as const;

function Host({ initiallyOpen }: { initiallyOpen: boolean }) {
  const [open, setOpen] = useState(initiallyOpen);
  return createElement(ComparisonReplaceDialog, {
    course: summaries["course-c"],
    open,
    onClose: () => setOpen(false),
    returnFocus: () => {},
  });
}

describe("comparison replacement question", () => {
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
      compare: { ...state.compare, slots: ["course-a", "course-b"] },
    }));
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("asks which comparison slot to replace and writes only the chosen one", async () => {
    const cache = new ReadCache(identity, READ_CACHE_CAPACITY);
    for (const id of ["course-a", "course-b"] as const) {
      cache.put(identity, JSON.stringify(["course-summaries", [id]]), {
        dataset_identity: identity,
        results: [summaries[id]],
      });
    }
    const renderDialog = () =>
      createElement(
        StoreContext.Provider,
        { value: store },
        createElement(
          ReadCacheContext.Provider,
          { value: cache },
          createElement(Host, { initiallyOpen: true }),
        ),
      );
    await act(async () => root.render(renderDialog()));
    await waitFor(() =>
      expect(document.body.querySelectorAll(".dialog-option")).toHaveLength(2),
    );

    const options = [...document.body.querySelectorAll(".dialog-option")];
    expect(options[0].textContent).toContain(summaries["course-a"].code);
    expect(options[1].textContent).toContain(summaries["course-b"].code);

    act(() => (options[0] as HTMLButtonElement).click());
    await waitFor(() =>
      expect(store.getSnapshot().profiles.default.state.compare.slots).toEqual([
        "course-c",
        "course-b",
      ]),
    );
    expect(
      createBrowserStore(localStorage).getSnapshot().profiles.default.state
        .compare.slots,
    ).toEqual(["course-c", "course-b"]);
    const saved = localStorage.getItem(BROWSER_STORAGE_KEY);

    // A second dialog mount asks again, and its cancel leaves the saved envelope untouched.
    const reopened = createElement(
      StoreContext.Provider,
      { value: store },
      createElement(
        ReadCacheContext.Provider,
        { value: cache },
        createElement(Host, { initiallyOpen: true, key: "reopened" }),
      ),
    );
    await act(async () => root.render(reopened));
    await waitFor(() =>
      expect(document.body.querySelector('[role="dialog"]')).toBeTruthy(),
    );
    const cancel = [
      ...document.body.querySelectorAll<HTMLButtonElement>("button"),
    ].find((button) => button.classList.contains("dialog-cancel"));
    if (!cancel) throw new Error("The dialog cancel control is missing");
    act(() => cancel.click());
    await waitFor(() =>
      expect(document.body.querySelector('[role="dialog"]')).toBeNull(),
    );

    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(saved);
    expect(store.getSnapshot().profiles.default.state.compare.slots).toEqual([
      "course-c",
      "course-b",
    ]);
  });
});
