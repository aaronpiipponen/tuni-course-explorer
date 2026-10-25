/**
 * Save-contract proofs for the configuration panel.
 *
 * Each invocation mounts the real component over one fetch boundary that answers the file listing,
 * the opened file's read and the sequential key saves. It proves that a refused key stops the
 * sequence, that the panel reports the saved and unsaved counts without rendering a value, and that
 * a retry posts only the keys that are unsaved.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { wording } from "../../shared/wording";
import { Configuration } from "./Configuration";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const FILE = "config/web.toml";
const SECRET = "synthetic-stored-secret";
const REPLACEMENT = "synthetic-replacement-secret";

const FILES_PATH = "/api/settings/config/files";
const READ_PATH = "/api/settings/config/read";
const SET_PATH = "/api/settings/config/set";

/** One typed draft the panel edits, with the JSON literal its key accepts. */
interface Draft {
  key: string;
  typed: string;
  literal: string;
}

/** One synthetic file's typed values, the drafts the panel edits and the key it first refuses. */
interface Case {
  name: string;
  values: Record<string, unknown>;
  drafts: Draft[];
  refused: number;
}

const CASES: Case[] = [
  {
    name: "primitive values",
    values: {
      WEB_PORT: 8037,
      WEB_INFERENCE_ENABLED: true,
      POSTGRES_PASSWORD: SECRET,
    },
    drafts: [
      { key: "WEB_PORT", typed: "18026", literal: "18026" },
      { key: "WEB_INFERENCE_ENABLED", typed: "false", literal: "false" },
      {
        key: "POSTGRES_PASSWORD",
        typed: REPLACEMENT,
        literal: JSON.stringify(REPLACEMENT),
      },
    ],
    refused: 1,
  },
  {
    name: "array and string values",
    values: { POSTGRES_HOSTS: ["127.0.0.1"], POSTGRES_PASSWORD: SECRET },
    drafts: [
      {
        key: "POSTGRES_HOSTS",
        typed: '["db", "127.0.0.1"]',
        literal: '["db","127.0.0.1"]',
      },
      {
        key: "POSTGRES_PASSWORD",
        typed: REPLACEMENT,
        literal: JSON.stringify(REPLACEMENT),
      },
    ],
    refused: 0,
  },
];

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function respond(status: number, body?: unknown): StubResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function envelope(report: unknown): StubResponse {
  return respond(200, { exit_code: 0, report, failure_line: null });
}

function refusedCommand(): StubResponse {
  return respond(200, { exit_code: 1, report: null, failure_line: null });
}

interface RecordedCall {
  path: string;
  body: Record<string, unknown>;
}

const calls: RecordedCall[] = [];
const state: { refuseKey: string | null } = { refuseKey: null };

function install(kase: Case): void {
  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const body =
      init?.body === undefined
        ? {}
        : (JSON.parse(String(init.body)) as Record<string, unknown>);
    calls.push({ path, body });
    if (path === FILES_PATH) {
      return envelope({ schema_version: 1, files: [FILE] });
    }
    if (path === READ_PATH) {
      return envelope({
        schema_version: 1,
        file: FILE,
        values: kase.values,
      });
    }
    if (path === SET_PATH) {
      return body.key === state.refuseKey
        ? refusedCommand()
        : envelope({ schema_version: 1, file: FILE, key: body.key });
    }
    throw new Error(`unexpected request ${path}`);
  }) as unknown as typeof fetch);
}

function buttonsNamed(
  container: HTMLElement,
  name: string,
): HTMLButtonElement[] {
  return [...container.querySelectorAll("button")].filter(
    (element) => element.textContent?.trim() === name,
  );
}

function clickNamed(container: HTMLElement, name: string): void {
  const found = buttonsNamed(container, name);
  if (found.length !== 1) {
    throw new Error(`${found.length} buttons named ${name}`);
  }
  found[0].click();
}

function labelledInput(container: HTMLElement, name: string): HTMLInputElement {
  const found = container.querySelector<HTMLInputElement>(
    `input[aria-label="${name}"]`,
  );
  if (found === null) {
    throw new Error(`no input labelled ${name}`);
  }
  return found;
}

function type(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

/** Return the text of every notice the panel rendered. */
function noticeText(container: HTMLElement): string {
  return [...container.querySelectorAll("p.note, p.failure")]
    .map((element) => element.textContent ?? "")
    .join("\n");
}

/** Return the posted key and value of every configuration save, in request order. */
function posts(): { key: string; value: string }[] {
  return calls
    .filter((call) => call.path === SET_PATH)
    .map((call) => ({
      key: String(call.body.key),
      value: String(call.body.value),
    }));
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 6; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

const session = { csrfToken: "csrf-token", pollSeconds: 3600 };

describe.each(CASES)("configuration save with $name", (kase) => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    calls.length = 0;
    state.refuseKey = null;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    install(kase);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("reports a partial file save and retries only unsaved keys", async () => {
    await act(async () => {
      root.render(
        createElement(Configuration, {
          session,
          onRefusal: () => {},
          webUpdate: null,
          onWebSaved: () => {},
        }),
      );
    });
    await settle();

    // No file is open on arrival, and the selected file is read only after its selection.
    expect(container.textContent).toContain(wording.settings.selectFile);
    expect(calls.filter((call) => call.path === READ_PATH)).toHaveLength(0);
    await act(async () => {
      clickNamed(container, FILE);
    });
    await settle();
    expect(calls.filter((call) => call.path === READ_PATH)).toHaveLength(1);

    for (const draft of kase.drafts) {
      await act(async () => {
        type(labelledInput(container, draft.key), draft.typed);
      });
    }
    await settle();

    // The first refused key stops the sequence after the keys before it were saved.
    state.refuseKey = kase.drafts[kase.refused].key;
    await act(async () => {
      clickNamed(container, wording.settings.saveFile.replace("{file}", FILE));
    });
    await settle();

    const first = kase.drafts.slice(0, kase.refused + 1);
    const afterFirst = posts();
    expect(afterFirst.map((post) => post.key)).toEqual(
      first.map((draft) => draft.key),
    );
    expect(afterFirst.map((post) => post.value)).toEqual(
      first.map((draft) => draft.literal),
    );
    expect(noticeText(container)).toContain(
      wording.settings.partialSave
        .replace("{saved}", String(kase.refused))
        .replace("{total}", String(kase.drafts.length)),
    );
    expect(noticeText(container)).toContain(wording.writeFailed);
    // No notice renders a stored or an edited value.
    expect(noticeText(container)).not.toContain(SECRET);
    expect(noticeText(container)).not.toContain(REPLACEMENT);

    // A retry saves the refused key and the keys after it, and never a key that is already saved.
    state.refuseKey = null;
    await act(async () => {
      clickNamed(container, wording.settings.saveFile.replace("{file}", FILE));
    });
    await settle();

    const retried = posts().slice(afterFirst.length);
    expect(retried.map((post) => post.key)).toEqual(
      kase.drafts.slice(kase.refused).map((draft) => draft.key),
    );
    expect(retried.map((post) => post.value)).toEqual(
      kase.drafts.slice(kase.refused).map((draft) => draft.literal),
    );
    expect(retried.map((post) => post.key)).not.toContain(
      kase.drafts[kase.refused - 1]?.key,
    );
    expect(noticeText(container)).toContain(wording.settings.savedAll);

    // Editing the draft again clears the summary that described the saved values.
    await act(async () => {
      type(
        labelledInput(container, kase.drafts[kase.refused].key),
        "changed-again",
      );
    });
    await settle();
    expect(noticeText(container)).not.toContain(wording.settings.savedAll);
  });
});
