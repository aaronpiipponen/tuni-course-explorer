/**
 * Inventory-state proofs for the Backups panel.
 *
 * Each invocation mounts the real panel over one fetch response that stays pending until released.
 * It proves that no empty claim appears before a successful read, that a successful empty report
 * states the empty inventory, and that a failed first read states its failure alone.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { wording } from "../../shared/wording";
import { Backups } from "./Backups";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const LIST_PATH = "/api/settings/backups";
const SESSION = { csrfToken: "csrf-token", pollSeconds: 3600 };
const onRefusal = (): void => {};

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function envelope(report: unknown): StubResponse {
  return {
    ok: true,
    status: 200,
    json: async () => ({ exit_code: 0, report, failure_line: null }),
  };
}

function refused(): StubResponse {
  return {
    ok: false,
    status: 500,
    json: async () => ({}),
  };
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 6; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

describe.each(["empty", "failure"] as const)("%s first read", (outcome) => {
  let container: HTMLDivElement;
  let root: Root;
  let release: () => void;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal("fetch", (async (input: unknown) => {
      if (String(input) !== LIST_PATH) {
        throw new Error(`unexpected request ${String(input)}`);
      }
      await held;
      return outcome === "empty"
        ? envelope({ schema_version: 1, backups: [] })
        : refused();
    }) as unknown as typeof fetch);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("shows an empty inventory only after a successful read", async () => {
    await act(async () => {
      root.render(createElement(Backups, { session: SESSION, onRefusal }));
    });
    await settle();

    // The held first read states neither an empty inventory nor a failure.
    expect(container.textContent).not.toContain(wording.settings.noBackups);
    expect(container.textContent).not.toContain(wording.readFailed);

    await act(async () => {
      release();
      await settle();
    });

    if (outcome === "empty") {
      expect(container.textContent).toContain(wording.settings.noBackups);
      expect(container.textContent).not.toContain(wording.readFailed);
    } else {
      expect(container.textContent).toContain(wording.readFailed);
      expect(container.textContent).not.toContain(wording.settings.noBackups);
    }
  });
});
