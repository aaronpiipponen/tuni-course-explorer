/** The feedback form keeps an explicit publication choice through answer changes. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FeedbackFormReport } from "../../api/feedback";
import { StoreContext } from "../../state/context";
import { createBrowserStore, type BrowserStore } from "../../state/store";
import { FeedbackPage } from "./FeedbackPage";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const REPORT: FeedbackFormReport = {
  definition: {
    selectPlaceholder: { en: "Not selected", fi: "Ei valittu" },
    fields: [
      {
        id: "type",
        kind: "select",
        label: { en: "Type", fi: "Tyyppi" },
        required: true,
        options: [
          {
            value: "bug",
            label: { en: "Bug", fi: "Virheilmoitus" },
            publicIssueByDefault: true,
          },
          {
            value: "other",
            label: { en: "Other", fi: "Muu" },
            publicIssueByDefault: false,
          },
        ],
      },
      {
        id: "title",
        kind: "text",
        label: { en: "Title", fi: "Otsikko" },
        required: true,
        maxLength: 150,
      },
      {
        id: "message",
        kind: "textarea",
        label: { en: "Message", fi: "Viesti" },
        required: true,
        maxLength: 10000,
      },
      {
        id: "screenshots",
        kind: "attachment",
        label: { en: "Screenshots", fi: "Kuvakaappaukset" },
        required: false,
        acceptedMimeTypes: ["image/png", "image/jpeg"],
        maxFiles: 3,
        maxBytesPerFile: 5242880,
      },
    ],
    githubIssue: {
      typeField: "type",
      titleField: "title",
      bodyFields: ["message"],
      attachmentField: "screenshots",
    },
  },
  repository: "owner/repository",
  visibility: "public",
  max_request_bytes: 1000000,
};

function respond(body: unknown): {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
} {
  return { ok: true, status: 200, json: async () => body };
}

function triggerFor(container: HTMLElement, id: string): HTMLButtonElement {
  const element = container.querySelector<HTMLButtonElement>(`#${id}`);
  if (element === null) throw new Error(`no select named ${id}`);
  return element;
}

/** Open the styled select with the keyboard and choose one option by its label. */
async function choose(
  trigger: HTMLButtonElement,
  label: string,
): Promise<void> {
  await act(async () => {
    trigger.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
  });
  await settle();
  const item = [
    ...document.querySelectorAll<HTMLElement>('[role="menuitemradio"]'),
  ].find((element) => element.textContent === label);
  if (item === undefined) throw new Error(`no option named ${label}`);
  await act(async () => {
    item.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await settle();
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 4; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

describe("feedback publication choice", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe(): void {}
        unobserve(): void {}
        disconnect(): void {}
      },
    );
    vi.stubGlobal("matchMedia", ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia);
    vi.stubGlobal("fetch", (async (input: unknown) => {
      if (String(input) !== "/api/feedback/definition") {
        throw new Error(`unexpected request ${String(input)}`);
      }
      return respond(REPORT);
    }) as unknown as typeof fetch);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("preserves a manual publication choice when selections change", async () => {
    await act(async () => {
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(FeedbackPage, { returnToApp: () => {} }),
        ),
      );
    });
    await settle();

    const toggle = container.querySelector<HTMLInputElement>(
      'input[type="checkbox"]',
    );
    const type = triggerFor(container, "feedback-field-type");
    expect(toggle?.checked).toBe(true);

    // The derived default follows the selected false option before any manual change.
    await choose(type, "Other");
    expect(toggle?.checked).toBe(false);

    // An explicit opt-in holds across a selection whose own default is true or false.
    await act(async () => toggle?.click());
    await settle();
    expect(toggle?.checked).toBe(true);
    await choose(type, "Bug");
    expect(toggle?.checked).toBe(true);
    await choose(type, "Other");
    expect(toggle?.checked).toBe(true);
  });
});
