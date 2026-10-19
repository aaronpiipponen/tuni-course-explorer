/**
 * Visibility-lifecycle proofs for one panel's automatic read loop.
 *
 * Each invocation mounts a small harness over the real hook and a fetch boundary that answers the
 * hook's one fixed route, drives the page's own visibility and a fake clock, and proves that a
 * hidden page issues no read, cancels one in flight without showing a failure, shows the report it
 * already had, and reads once on the return before it resumes its ordinary loop.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePanelRead } from "./usePanelRead";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const POLL_SECONDS = 60;
const READ_FAILED = "The read failed.";

/** One report the boundary returns, so a retained report is distinguishable from a fresh one. */
interface ReadReport {
  marker: number;
}

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

interface RecordedRequest {
  signal: AbortSignal | null;
  settle: (outcome: "success" | "failure") => void;
}

const requests: RecordedRequest[] = [];
/** The attribution the hook passed to each read, in request order. */
const attributions: boolean[] = [];
let nextMarker = 1;
let deferred = false;

function install(): void {
  vi.stubGlobal("fetch", ((_input: unknown, init?: RequestInit) => {
    const marker = nextMarker;
    nextMarker += 1;
    let settle!: (outcome: "success" | "failure") => void;
    const answer = new Promise<StubResponse>((resolve, reject) => {
      settle = (outcome: string): void => {
        if (outcome === "success") {
          resolve({
            ok: true,
            status: 200,
            json: async () => ({
              exit_code: 0,
              report: { marker },
              failure_line: null,
            }),
          });
          return;
        }
        reject(new Error("synthetic read failure"));
      };
    });
    requests.push({ signal: init?.signal ?? null, settle });
    if (!deferred) {
      settle("success");
    }
    return answer;
  }) as unknown as typeof fetch);
}

/** The one read the harness performs, with the hook's own attribution recorded. */
async function readDashboard(
  signal: AbortSignal,
  automatic: boolean,
): Promise<ReadReport> {
  attributions.push(automatic);
  const response = await fetch("/api/dashboard", { signal });
  const payload = (await response.json()) as { report: ReadReport };
  return payload.report;
}

/** The one options object every harness render passes, so no read loop restarts on a render. */
const OPTIONS = {
  pollSeconds: POLL_SECONDS,
  enabled: true,
  onRefusal: () => {},
  failureTextValue: READ_FAILED,
};

/** One harness that renders the hook's own state for the assertions. */
function Harness() {
  const panel = usePanelRead<ReadReport>(readDashboard, OPTIONS);
  const report = panel.report;
  return createElement(
    "div",
    null,
    createElement(
      "span",
      { className: "report" },
      report === null ? "none" : report.marker,
    ),
    createElement(
      "span",
      { className: "marker" },
      panel.lastSuccess === null ? "never" : "read",
    ),
    createElement("span", { className: "failure" }, panel.failure ?? "none"),
  );
}

let container: HTMLDivElement;
let root: Root;

/** Set the page's own visibility and announce the change. */
function setVisible(visible: boolean): void {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => !visible,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

function text(name: string): string {
  return container.querySelector(`.${name}`)?.textContent ?? "";
}

/** Flush the pending request chain and its state updates. */
async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 8; turn += 1) {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    }
  });
}

/** Advance one or more poll intervals of fake time. */
async function advance(seconds: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(seconds * 1000);
  });
  await settle();
}

describe("one panel's automatic read loop", () => {
  beforeEach(() => {
    requests.length = 0;
    attributions.length = 0;
    nextMarker = 1;
    deferred = false;
    vi.useFakeTimers();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    install();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    delete (document as { hidden?: boolean }).hidden;
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("pauses automatic reads while hidden and refreshes on return", async () => {
    setVisible(false);
    await act(async () => {
      root.render(createElement(Harness));
    });
    await settle();
    // A page that opens hidden issues no read and reports no completed one.
    expect(requests).toHaveLength(0);
    expect(text("marker")).toBe("never");

    // The return reads once immediately, attributed to the loop, and shows its report.
    await act(async () => {
      setVisible(true);
    });
    await settle();
    expect(requests).toHaveLength(1);
    expect(attributions).toEqual([true]);
    expect(text("report")).toBe("1");
    expect(text("failure")).toBe("none");

    // One poll interval issues the next read, which stays in flight while it is deferred.
    deferred = true;
    await advance(POLL_SECONDS);
    expect(requests).toHaveLength(2);
    const inFlight = requests[1];
    expect(inFlight.signal?.aborted).toBe(false);

    // Hiding cancels the read in flight without a failure and keeps the report and its marker.
    await act(async () => {
      setVisible(false);
    });
    await settle();
    expect(inFlight.signal?.aborted).toBe(true);
    inFlight.settle("failure");
    await settle();
    expect(text("failure")).toBe("none");
    expect(text("report")).toBe("1");
    expect(text("marker")).toBe("read");

    // No interval of a hidden page issues another read.
    await advance(POLL_SECONDS * 3);
    expect(requests).toHaveLength(2);

    // The next return reads once and resumes the ordinary loop.
    deferred = false;
    await act(async () => {
      setVisible(true);
    });
    await settle();
    expect(requests).toHaveLength(3);
    expect(attributions).toEqual([true, true, true]);
    expect(text("report")).toBe("3");
    await advance(POLL_SECONDS);
    expect(requests).toHaveLength(4);
    expect(attributions).toEqual([true, true, true, true]);
    expect(text("report")).toBe("4");
  });
});
