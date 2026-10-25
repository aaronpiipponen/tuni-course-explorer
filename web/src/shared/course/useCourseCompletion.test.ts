/** Shared completion interaction: one confirmed atomic write, and dismissing asks nothing. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { CourseSummary } from "../../api/types";
import { StoreContext } from "../../state/context";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  type BrowserStore,
} from "../../state/store";
import { useCourseCompletion } from "./useCourseCompletion";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const course: CourseSummary = {
  group_id: "course-completion-fixture",
  code: "TEST.001",
  name_en: "Fixture course",
  name_fi: "Testikurssi",
  credits_min: "5",
  credits_max: null,
  is_active: true,
  official_url: "https://example.invalid/course",
};

function Harness() {
  const completion = useCourseCompletion(course, () => {});
  return createElement(
    "div",
    null,
    createElement(
      "button",
      { type: "button", id: "toggle", onClick: completion.toggle },
      "toggle",
    ),
    completion.dialog,
  );
}

describe("course completion", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(Harness),
        ),
      ),
    );
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function pressToggle(): void {
    act(() =>
      container
        .querySelector<HTMLButtonElement>("#toggle")!
        .dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );
  }

  function dialog(): HTMLElement | null {
    return document.querySelector<HTMLElement>(".dialog-panel");
  }

  function press(selector: string): void {
    act(() =>
      document
        .querySelector<HTMLButtonElement>(selector)!
        .dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );
  }

  it("confirming adds an unselected course to the selection and completes it once", () => {
    const saved = localStorage.getItem(BROWSER_STORAGE_KEY);

    pressToggle();
    expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(saved);
    expect(dialog()?.textContent).toContain("Mark completed?");
    expect(dialog()?.textContent).toContain("TEST.001 Fixture course");

    press(".dialog-confirm");
    expect(dialog()).toBeNull();
    const state =
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    expect(
      state.selectedCourseIds.filter(
        (id) => id === "course-completion-fixture",
      ),
    ).toHaveLength(1);
    expect(
      state.completedCourseIds.filter(
        (id) => id === "course-completion-fixture",
      ),
    ).toHaveLength(1);
    expect(state.structure).toEqual(
      JSON.parse(saved!).profiles.default.state.structure,
    );
  });

  it("cancel, escape and outside dismissal leave saved state untouched", async () => {
    const saved = localStorage.getItem(BROWSER_STORAGE_KEY);

    for (const dismiss of [
      () => press(".dialog-cancel"),
      () =>
        act(() =>
          document.dispatchEvent(
            new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
          ),
        ),
      async () => {
        await act(async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          const scrim = document.querySelector<HTMLElement>(".dialog-scrim")!;
          scrim.dispatchEvent(
            new MouseEvent("pointerdown", { bubbles: true, button: 0 }),
          );
          // The dialog defers its outside-pointerdown dismissal until the click that follows.
          scrim.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        });
      },
    ]) {
      pressToggle();
      expect(dialog()).not.toBeNull();
      await dismiss();
      expect(dialog()).toBeNull();
      expect(localStorage.getItem(BROWSER_STORAGE_KEY)).toBe(saved);
    }
  });
});
