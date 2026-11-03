/**
 * Action-outcome and availability proofs for the preparation stage panels and the inference run
 * panel.
 *
 * Each action invocation mounts one real panel over one fetch boundary, answers the initial status
 * once, then answers the panel's Start action with a distinguishable running status. It proves that
 * the returned status is presented without another status read. The availability proof mounts the
 * ingestion panel without a Working dataset and observes the disabled action row.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LifecycleStatus } from "../api/types";
import type { PreparationStage } from "../api/preparation";
import { InferenceRun } from "../features/inference/InferenceRun";
import { StagePanel } from "./StagePanel";
import { wording } from "./wording";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const SESSION = { csrfToken: "csrf-token", pollSeconds: 3600 };
const SESSION_ID = "a".repeat(32);
const onRefusal = (): void => {};

interface Case {
  name: string;
  stage: PreparationStage | null;
  statusPath: string;
  actionPath: string;
}

const CASES: Case[] = [
  {
    name: "ingestion",
    stage: "ingestion",
    statusPath: "/api/preparation/status/ingestion",
    actionPath: "/api/preparation/action",
  },
  {
    name: "embedding",
    stage: "embedding",
    statusPath: "/api/preparation/status/embedding",
    actionPath: "/api/preparation/action",
  },
  {
    name: "translation",
    stage: "translation",
    statusPath: "/api/preparation/status/translation",
    actionPath: "/api/preparation/action",
  },
  {
    name: "inference",
    stage: null,
    statusPath: "/api/inference/status",
    actionPath: "/api/inference/action",
  },
];

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

function status(
  stage: LifecycleStatus["stage"],
  lifecycle: string,
  activeSeconds: number,
): LifecycleStatus {
  return {
    stage,
    lifecycle,
    session_id: lifecycle === "running" ? SESSION_ID : null,
    revision: null,
    progress: null,
    active_seconds: activeSeconds,
    error_type: null,
    items_per_second: null,
    eta_seconds: null,
  };
}

interface RecordedCall {
  method: string;
  path: string;
  body: Record<string, unknown>;
}

const calls: RecordedCall[] = [];

function install(kase: Case): void {
  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    calls.push({
      method,
      path,
      body:
        init?.body === undefined
          ? {}
          : (JSON.parse(String(init.body)) as Record<string, unknown>),
    });
    if (method === "GET" && path === kase.statusPath) {
      return envelope(status(kase.stage ?? "inference", "idle", 0));
    }
    if (method === "POST" && path === kase.actionPath) {
      return envelope(status(kase.stage ?? "inference", "running", 42));
    }
    throw new Error(`unexpected request ${method} ${path}`);
  }) as unknown as typeof fetch);
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 6; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

function buttonNamed(name: string): HTMLButtonElement {
  const found = [...document.body.querySelectorAll("button")].find(
    (element) => element.textContent?.trim() === name,
  );
  if (found === undefined) {
    throw new Error(`no button named ${name}`);
  }
  return found;
}

describe.each(CASES)("$name action status", (kase) => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    calls.length = 0;
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

  it("presents the lifecycle action result without another status read", async () => {
    await act(async () => {
      root.render(
        kase.stage === null
          ? createElement(InferenceRun, {
              session: SESSION,
              onRefusal,
              workingPresent: true,
            })
          : createElement(StagePanel, {
              stage: kase.stage,
              session: SESSION,
              onRefusal,
              workingPresent: true,
            }),
      );
    });
    await settle();

    expect(container.textContent).toContain("idle");

    await act(async () => {
      buttonNamed(wording.action.start).click();
    });
    await settle();

    expect(container.textContent).toContain("running");
    expect(calls.filter((call) => call.method === "GET")).toEqual([
      { method: "GET", path: kase.statusPath, body: {} },
    ]);
    const actions = calls.filter((call) => call.method === "POST");
    expect(actions).toHaveLength(1);
    expect(actions[0].path).toBe(kase.actionPath);
    expect(actions[0].body).toEqual(
      kase.stage === null
        ? { action: "start" }
        : { stage: kase.stage, action: "start" },
    );
  });
});

describe("stage action availability", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    calls.length = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    install(CASES[0]);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("disables the four stage actions without a Working dataset", async () => {
    await act(async () => {
      root.render(
        createElement(StagePanel, {
          stage: "ingestion",
          session: SESSION,
          onRefusal,
          workingPresent: false,
        }),
      );
    });
    await settle();

    const actions = ["start", "pause", "resume", "stop"] as const;
    expect(
      actions.map((action) => buttonNamed(wording.action[action]).disabled),
    ).toEqual([true, true, true, true]);
    expect(calls.filter((call) => call.method === "GET")).toEqual([
      { method: "GET", path: "/api/preparation/status/ingestion", body: {} },
    ]);
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(0);
  });
});
