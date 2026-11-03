/**
 * Promotion-progress proofs for the Settings dataset panel.
 *
 * One invocation mounts the real panel over one held promotion stream and the shell's shared
 * inventory read through the shared proof harness: the inventory answers first, the confirmation
 * posts one admitted promotion, and the test then releases the owner's actual step records in
 * separate chunks before the terminal result. It proves that progress is observable before
 * completion, that only reported steps are marked, and that a failed terminal result renders its
 * owning guidance line and re-reads the inventory. The returned receipt is not a panel block of its
 * own.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetListReport, ServerStatusReport } from "../../api/types";
import type { PanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { buttonsNamed, DatasetsHarness, settle } from "./datasetsTestHarness";

const SELECTED_ID = "a".repeat(32);
const SELECTED_DATABASE = "course_admin_selected";
const PROMOTED_ID = "d".repeat(32);
const FAILURE_LINE = "ValueError";
const FAILURE_GUIDANCE = "synthetic promotion guidance";

const LISTING: DatasetListReport = {
  schema_version: 1,
  datasets: [
    {
      dataset_id: SELECTED_ID,
      kind: "returned",
      database_name: SELECTED_DATABASE,
      predecessor_id: "0".repeat(32),
      receipt_schema_revision: "20261028_0022",
      dump_path: "data/admin/dumps/selected.dump",
      selected: true,
      working: false,
      database_presence: "present",
      artifacts_present: true,
    },
  ],
  mode: "enrolled",
  database_probe: "available",
  bootstrap_database: null,
  stage_busy: {
    ingestion: false,
    embedding: false,
    translation: false,
    inference: false,
  },
};

const RECEIPT = {
  schema_version: 1,
  dataset_id: PROMOTED_ID,
  database_name: "course_admin_promoted",
  kind: "copied",
  verification: {
    schema_version: 1,
    alembic_revision: "20261028_0022",
    table_row_counts: { course: 2, module: 1 },
  },
};

const session = { csrfToken: "csrf-token", pollSeconds: 3600 };

/** One held newline-delimited body the test releases by hand. */
interface HeldStream {
  body: ReadableStream<Uint8Array>;
  push: (record: string) => void;
  close: () => void;
}

function heldStream(): HeldStream {
  let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start: (created) => {
      controller = created;
    },
  });
  const encoder = new TextEncoder();
  return {
    body,
    push: (record: string) => controller?.enqueue(encoder.encode(record)),
    close: () => controller?.close(),
  };
}

const calls: string[] = [];

/** Install one boundary: the inventory answers at once, and the promotion returns the held body. */
function install(stream: HeldStream): void {
  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    calls.push(`${method} ${path}`);
    if (method === "GET" && path === "/api/datasets") {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          exit_code: 0,
          report: LISTING,
          failure_line: null,
        }),
      };
    }
    if (method === "POST" && path === "/api/datasets/copy-to-selected") {
      return { ok: true, status: 200, body: stream.body };
    }
    throw new Error(`unexpected request ${method} ${path}`);
  }) as unknown as typeof fetch);
}

describe.each(["success", "failure"] as const)(
  "promotion confirmed as %s",
  (outcome) => {
    let container: HTMLDivElement;
    let root: Root;
    let stream: HeldStream;
    let reloads: number;

    beforeEach(() => {
      calls.length = 0;
      reloads = 0;
      stream = heldStream();
      container = document.createElement("div");
      document.body.appendChild(container);
      root = createRoot(container);
      install(stream);
    });

    afterEach(() => {
      act(() => root.unmount());
      container.remove();
      vi.unstubAllGlobals();
    });

    it("shows owner steps until a confirmed promotion finishes", async () => {
      const dashboard: PanelRead<ServerStatusReport> = {
        report: null,
        failure: null,
        lastSuccess: null,
        loading: true,
        reload: () => {
          reloads += 1;
        },
      };
      await act(async () => {
        root.render(createElement(DatasetsHarness, { session, dashboard }));
      });
      await settle(8);
      expect(container.textContent).toContain(SELECTED_ID);

      // The confirmation names the exact listed source and its database.
      await act(async () => {
        buttonsNamed(wording.datasets.copyToSelected)[0].click();
      });
      await settle(8);
      expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
        wording.datasets.copyToSelectedMessage
          .replace("{dataset_id}", SELECTED_ID)
          .replace("{database_name}", SELECTED_DATABASE),
      );
      await act(async () => {
        buttonsNamed(wording.inference.confirm)[0].click();
      });
      await settle(8);
      expect(calls).toContain("POST /api/datasets/copy-to-selected");

      // The owner's steps arrive in separate chunks, and progress is observable before completion.
      await act(async () => {
        stream.push('{"step":"copy"}\n');
      });
      await settle(8);
      await act(async () => {
        stream.push('{"step":"build"}\n');
      });
      await settle(8);
      const steps = [...container.querySelectorAll(".steplist li")].map(
        (element) => element.textContent,
      );
      expect(steps).toEqual([
        wording.datasets.promotionSteps.copy,
        wording.datasets.promotionSteps.build,
        wording.datasets.promotionSteps.switch,
        wording.datasets.promotionSteps.restart,
        wording.datasets.promotionSteps.prove,
      ]);
      const list = container.querySelector(".steplist");
      const current = list?.querySelector('[aria-current="step"]');
      expect(current?.textContent).toContain(
        wording.datasets.promotionSteps.build,
      );
      expect(current?.querySelector(".steppulse")).not.toBeNull();
      expect(container.textContent).not.toContain(PROMOTED_ID);

      // The terminal record alone completes the action.
      await act(async () => {
        stream.push(
          `${JSON.stringify(
            outcome === "success"
              ? {
                  result: {
                    exit_code: 0,
                    report: RECEIPT,
                    failure_line: null,
                  },
                }
              : {
                  result: {
                    exit_code: 1,
                    report: null,
                    failure_line: FAILURE_LINE,
                    guidance_line: FAILURE_GUIDANCE,
                  },
                },
          )}\n`,
        );
        stream.close();
      });
      await settle(8);

      // The step list belongs to the pending promotion, so the outcome replaces it, and the
      // terminal receipt is not a separate panel block.
      expect(container.querySelector(".steplist")).toBeNull();
      // Both outcomes re-read the inventory and the shared dashboard.
      expect(calls.filter((call) => call === "GET /api/datasets")).toHaveLength(
        2,
      );
      expect(reloads).toBe(1);
      if (outcome === "success") {
        expect([...container.querySelectorAll("p.failure")]).toHaveLength(0);
        expect(container.textContent).not.toContain(PROMOTED_ID);
        expect(container.textContent).not.toContain("course_admin_promoted");
        return;
      }
      expect(container.textContent).toContain(FAILURE_GUIDANCE);
      expect(container.textContent).not.toContain(FAILURE_LINE);
      expect(container.textContent).not.toContain(PROMOTED_ID);
    });
  },
);
