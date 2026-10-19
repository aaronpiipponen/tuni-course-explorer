/**
 * Demand-read proofs for the two log panels.
 *
 * Each invocation mounts one real log panel over one fetch boundary, advances the poll interval with
 * fake timers, and selects the panel's worker source. It proves that a worker log is read only by its
 * explicit control: no request reaches the worker on mount, on a timer or on a selection change, one
 * request follows the control, and no timer read follows it.
 */
import { createElement } from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LogSessionEntry, LogSource, StageName } from "../../api/types";
import { wording } from "../../shared/wording";
import { RuntimeLogs } from "./RuntimeLogs";
import { SessionLogs } from "./SessionLogs";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const SESSION_ID = "a".repeat(32);
const REMOTE_STAGE: StageName = "inference";
const POLL_SECONDS = 10;
const READ_PATH = "/api/logs/read";
const EMBEDDING_PATH = "/api/logs/embedding";
const LOG_TEXT = "synthetic worker log line\n";

const SESSIONS: LogSessionEntry[] = [
  {
    stage: REMOTE_STAGE,
    session_id: SESSION_ID,
    created_at: "2026-10-18T09:30:00Z",
  },
];

const session = { csrfToken: "csrf-token", pollSeconds: POLL_SECONDS };

/** One panel invocation with the worker source its own control reads. */
interface Case {
  name: string;
  panel: "session" | "runtime";
  source: LogSource;
}

const CASES: Case[] = [
  { name: "the session panel", panel: "session", source: "worker-runner" },
  { name: "the runtime panel", panel: "runtime", source: "worker-runtime" },
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

interface RecordedCall {
  path: string;
  body: Record<string, unknown>;
}

const calls: RecordedCall[] = [];

function install(): void {
  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const body =
      init?.body === undefined
        ? {}
        : (JSON.parse(String(init.body)) as Record<string, unknown>);
    calls.push({ path, body });
    if (path === READ_PATH) {
      return envelope({
        schema_version: 1,
        stage: body.stage,
        session_id: body.session_id,
        source: body.source,
        available: true,
        text: LOG_TEXT,
      });
    }
    if (path === EMBEDDING_PATH) {
      return envelope({
        schema_version: 1,
        stage: "embedding",
        session_id: null,
        source: "embedding-runtime",
        available: true,
        text: LOG_TEXT,
      });
    }
    throw new Error(`unexpected request ${path}`);
  }) as unknown as typeof fetch);
}

/** Return every bounded session-log read of one fixed source. */
function readsOf(source: string): RecordedCall[] {
  return calls.filter(
    (call) => call.path === READ_PATH && call.body.source === source,
  );
}

function clickNamed(container: HTMLElement, name: string): void {
  const found = [...container.querySelectorAll("button")].filter(
    (element) => element.textContent?.trim() === name,
  );
  if (found.length !== 1) {
    throw new Error(`${found.length} buttons named ${name}`);
  }
  found[0].click();
}

function choose(container: HTMLElement, label: string, value: string): void {
  const trigger = container.querySelector<HTMLButtonElement>(
    `button[aria-label="${label}"]`,
  );
  if (trigger === null) {
    throw new Error(`no picker labelled ${label}`);
  }
  trigger.click();
  const option = container.querySelector<HTMLButtonElement>(
    `button[data-value="${value}"]`,
  );
  if (option === null) {
    throw new Error(`no option ${value} in picker ${label}`);
  }
  option.click();
}

/** Flush the pending request chain and its state updates without advancing the poll interval. */
async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 6; turn += 1) {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    }
  });
}

/** Advance one or more poll intervals. */
async function advance(seconds: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(seconds * 1000);
  });
  await settle();
}

describe.each(CASES)("worker log reads of $name", (kase) => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    calls.length = 0;
    vi.useFakeTimers();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    install();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reads a worker log only after its explicit control", async () => {
    const props = {
      session,
      onRefusal: () => {},
      sessions: SESSIONS,
      sessionsFailure: null,
      sessionsLoading: false,
    };
    await act(async () => {
      root.render(
        kase.panel === "session"
          ? createElement(SessionLogs, props)
          : createElement(RuntimeLogs, props),
      );
    });
    await settle();

    // The panel's own local source reads automatically, and nothing reaches the worker.
    expect(readsOf(kase.source)).toHaveLength(0);
    expect(
      kase.panel === "session"
        ? readsOf("server-stdout")
        : calls.filter((call) => call.path === EMBEDDING_PATH),
    ).toHaveLength(1);

    // A poll interval reads the local source alone.
    await advance(POLL_SECONDS * 2);
    expect(readsOf(kase.source)).toHaveLength(0);

    // Selecting the worker source reads nothing from the worker.
    await act(async () => {
      choose(
        container,
        kase.panel === "session"
          ? wording.logs.sourcePicker
          : wording.logs.runtimePicker,
        kase.panel === "session"
          ? kase.source
          : `${REMOTE_STAGE}/${SESSION_ID}`,
      );
    });
    await settle();
    await advance(POLL_SECONDS * 2);
    expect(readsOf(kase.source)).toHaveLength(0);

    // One explicit Read reads the worker once and renders what it returned.
    await act(async () => {
      clickNamed(container, wording.logs.read);
    });
    await settle();
    expect(readsOf(kase.source)).toHaveLength(1);
    expect(container.textContent).toContain(LOG_TEXT.trim());

    // No timer read follows the explicit one.
    await advance(POLL_SECONDS * 4);
    expect(readsOf(kase.source)).toHaveLength(1);

    // The worker-to-local transition has one read owner: exactly one local read, no worker read.
    const localBefore =
      kase.panel === "session"
        ? readsOf("server-stdout").length
        : calls.filter((call) => call.path === EMBEDDING_PATH).length;
    await act(async () => {
      choose(
        container,
        kase.panel === "session"
          ? wording.logs.sourcePicker
          : wording.logs.runtimePicker,
        kase.panel === "session" ? "server-stdout" : "embedding",
      );
    });
    await settle();
    const localAfter =
      kase.panel === "session"
        ? readsOf("server-stdout").length
        : calls.filter((call) => call.path === EMBEDDING_PATH).length;
    expect(localAfter).toBe(localBefore + 1);
    expect(readsOf(kase.source)).toHaveLength(1);
  });
});
