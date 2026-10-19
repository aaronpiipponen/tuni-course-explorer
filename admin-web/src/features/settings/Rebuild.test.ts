/**
 * Confirmation proofs for the rebuild panel.
 *
 * Each invocation mounts the real component over a fetch boundary that answers both maintenance
 * routes and records them. It proves that a cancelled confirmation runs nothing and that a confirmed
 * one invokes only its own action, and that the administration action alone reports the completed
 * build to the shell.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AdminRebuildReport, RebuildReport } from "../../api/types";
import { wording } from "../../shared/wording";
import { Rebuild } from "./Rebuild";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const APP_PATH = "/api/settings/rebuild";
const ADMIN_PATH = "/api/settings/rebuild-admin";

const APP_REPORT: RebuildReport = {
  schema_version: 1,
  steps: ["frontend", "containers", "web", "bind"],
  host: "127.0.0.1",
  port: 18026,
};
const ADMIN_REPORT: AdminRebuildReport = {
  schema_version: 1,
  steps: ["frontend"],
};

/** One action the panel offers, with its own label, confirmation and route. */
interface Case {
  name: string;
  label: string;
  confirmation: string;
  path: string;
}

const CASES: Case[] = [
  {
    name: "app rebuild",
    label: wording.settings.rebuildApp,
    confirmation: wording.settings.rebuildConfirm,
    path: APP_PATH,
  },
  {
    name: "admin rebuild",
    label: wording.settings.rebuildAdmin,
    confirmation: wording.settings.rebuildAdminConfirm,
    path: ADMIN_PATH,
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

const calls: string[] = [];

function install(): void {
  vi.stubGlobal("fetch", (async (input: unknown) => {
    const path = String(input);
    calls.push(path);
    if (path === APP_PATH) {
      return respond(200, {
        exit_code: 0,
        report: APP_REPORT,
        failure_line: null,
      });
    }
    if (path === ADMIN_PATH) {
      return respond(200, {
        exit_code: 0,
        report: ADMIN_REPORT,
        failure_line: null,
      });
    }
    throw new Error(`unexpected request ${path}`);
  }) as unknown as typeof fetch);
}

/** Return the one button the panel or the open dialog renders with that text. */
function buttonNamed(name: string): HTMLButtonElement {
  const found = [...document.body.querySelectorAll("button")].filter(
    (element) => element.textContent?.trim() === name,
  );
  if (found.length !== 1) {
    throw new Error(`${found.length} buttons named ${name}`);
  }
  return found[0];
}

/** Return the text of the open confirmation dialog, which renders in a body-level portal. */
function dialogText(): string {
  return document.body.querySelector(".dialog")?.textContent ?? "";
}

/** Report whether the open confirmation dialog offers a button with that text. */
function dialogOffers(name: string): boolean {
  return [...document.body.querySelectorAll("button")].some(
    (element) => element.textContent?.trim() === name,
  );
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 6; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

describe.each(CASES)("rebuild confirmation for the $name", (kase) => {
  let container: HTMLDivElement;
  let root: Root;
  let adminRebuilds: number;

  beforeEach(() => {
    calls.length = 0;
    adminRebuilds = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    install();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("runs only the confirmed rebuild action", async () => {
    await act(async () => {
      root.render(
        createElement(Rebuild, {
          session: { csrfToken: "csrf-token", pollSeconds: 3600 },
          onRefusal: () => {},
          onAdminRebuild: () => {
            adminRebuilds += 1;
          },
        }),
      );
    });
    await settle();

    // Both separate actions are offered, and no action has run.
    expect(container.textContent).toContain(wording.settings.rebuildApp);
    expect(container.textContent).toContain(wording.settings.rebuildAdmin);
    expect(calls).toEqual([]);

    // The action's own confirmation is shown, and cancelling it runs nothing.
    await act(async () => {
      buttonNamed(kase.label).click();
    });
    await settle();
    expect(dialogText()).toContain(kase.confirmation);
    await act(async () => {
      buttonNamed(wording.inference.cancel).click();
    });
    await settle();
    expect(calls).toEqual([]);
    expect(dialogOffers(wording.inference.confirm)).toBe(false);

    // Confirming runs that action alone, over its own route.
    await act(async () => {
      buttonNamed(kase.label).click();
    });
    await settle();
    await act(async () => {
      buttonNamed(wording.inference.confirm).click();
    });
    await settle();
    expect(calls).toEqual([kase.path]);
    if (kase.path === ADMIN_PATH) {
      // The administration action alone hands the completed build to the shell.
      expect(adminRebuilds).toBe(1);
      return;
    }
    expect(adminRebuilds).toBe(0);
    expect(container.textContent).toContain(
      `${APP_REPORT.host}:${APP_REPORT.port}`,
    );
  });
});
