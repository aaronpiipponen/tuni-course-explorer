/** The shared course menu removes one placed course from the holder that renders it. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { CourseSummary } from "../../api/types";
import { WebFeaturesContext } from "../../app/webFeaturesContext";
import { StoreContext } from "../../state/context";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import { NoticeProvider } from "../NoticeProvider";
import { NoticeStack } from "../NoticeStack";
import { uiText } from "../wording";
import { CourseMenu } from "./CourseMenu";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const COURSE: CourseSummary = {
  group_id: "course-1",
  code: "TEST.101",
  name_fi: "Testikurssi",
  name_en: "Test course",
  credits_min: "5",
  credits_max: null,
  is_active: true,
  official_url: "https://example.invalid/course-1",
};

const FEATURES = {
  embeddings_enabled: false,
  inference_enabled: false,
  dataset_identity: "test-dataset",
};

/** Let the menu mount and its deferred write settle. */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
}

const originalMedia = globalThis.matchMedia;

function restore(target: object, name: string, value: unknown) {
  if (value === undefined) Reflect.deleteProperty(target, name);
  else Reflect.set(target, name, value);
}

describe("course menu remove from holder", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

  beforeEach(() => {
    // jsdom has no media queries, and the notice stack reads the motion and phone preferences.
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
    localStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    store.updateCurrent((state) => ({
      ...state,
      selectedCourseIds: [COURSE.group_id],
      structure: {
        ...state.structure,
        placedCourseIds: [COURSE.group_id],
        coursePlacements: { [COURSE.group_id]: "module-1" },
        courseHolders: {
          [COURSE.group_id]: {
            group_id: "module-1",
            name_fi: "Testimoduuli",
            name_en: "Test module",
          },
        },
      },
    }));
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    restore(globalThis, "matchMedia", originalMedia);
  });

  it("names the holder outside Structure and moves the course to Unplaced", async () => {
    await act(async () => {
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(
            WebFeaturesContext.Provider,
            { value: FEATURES },
            createElement(
              NoticeProvider,
              null,
              createElement(CourseMenu, {
                course: COURSE,
                open: true,
                onOpenChange: () => {},
                children: createElement(
                  "button",
                  { type: "button" },
                  "Open menu",
                ),
              }),
              createElement(NoticeStack, { tab: "search" }),
            ),
          ),
        ),
      );
    });
    await settle();

    // The card sits on a surface without Structure's flag, which must still offer the holder.
    const remove = [
      ...document.querySelectorAll<HTMLElement>('[role="menuitem"]'),
    ].find(
      (item) =>
        item.textContent ===
        uiText("en", "Remove from {name}", { name: "Test module" }),
    );
    expect(remove).toBeDefined();

    await act(async () => {
      remove!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await settle();

    const state =
      store.getSnapshot().profiles[store.getSnapshot().currentProfileId].state;
    expect(state.selectedCourseIds).toContain(COURSE.group_id);
    expect(state.structure.placedCourseIds).not.toContain(COURSE.group_id);
    expect(state.structure.coursePlacements[COURSE.group_id]).toBeNull();
    expect(state.structure.courseHolders?.[COURSE.group_id]).toBeUndefined();
    expect(container.querySelector(".toast")?.textContent).toContain(
      COURSE.code,
    );
  });
});
