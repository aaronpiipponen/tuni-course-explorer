/**
 * Deletion-contract proofs for the dataset cleanup and backup cleanup panels.
 *
 * Each invocation mounts one real panel and its confirmation dialog over one fetch boundary that
 * answers that panel's own listing and deletion routes. It proves that only the confirmed listed
 * target is posted and that cancelling posts nothing.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Backups } from "../settings/Backups";
import { wording } from "../../shared/wording";
import { DatasetCleanup } from "./DatasetCleanup";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const SELECTED_ID = "a".repeat(32);
const OTHER_ID = "c".repeat(32);
const SELECTED_DATABASE = "course_admin_selected";
const OTHER_DATABASE = "course_admin_other";
const BACKUP_NAME = "before-inference.dump";
const FAILURE_LINE = "ValueError";

const DATASET_LISTING = {
  schema_version: 1,
  datasets: [
    {
      dataset_id: SELECTED_ID,
      kind: "returned",
      database_name: SELECTED_DATABASE,
      dump_path: "data/admin/dumps/selected.dump",
      selected: true,
    },
    {
      dataset_id: OTHER_ID,
      kind: "returned",
      database_name: OTHER_DATABASE,
      dump_path: "data/admin/dumps/other.dump",
      selected: false,
    },
  ],
};

const BACKUP_LISTING = {
  schema_version: 1,
  backups: [
    {
      name: BACKUP_NAME,
      size_bytes: 4096,
      modified_at: "2026-10-18T09:30:00Z",
    },
  ],
};

type Surface = "dataset-cleanup" | "backups";

const session = { csrfToken: "csrf-token", pollSeconds: 3600 };

/** The routes, listing, confirmation and posted body of one cleanup surface. */
interface SurfaceSpec {
  listPath: string;
  deletePath: string;
  listing: unknown;
  acknowledged: unknown;
  message: string;
  body: Record<string, string>;
  absent: string[];
  element: ReturnType<typeof createElement>;
}

function contract(surface: Surface): SurfaceSpec {
  if (surface === "backups") {
    return {
      listPath: "/api/settings/backups",
      deletePath: "/api/settings/backups/delete",
      listing: BACKUP_LISTING,
      acknowledged: { schema_version: 1, name: BACKUP_NAME },
      message: wording.settings.backupMessage.replace("{name}", BACKUP_NAME),
      body: { name: BACKUP_NAME },
      absent: [],
      element: createElement(Backups, { session, onRefusal: () => {} }),
    };
  }
  return {
    listPath: "/api/inference/datasets",
    deletePath: "/api/inference/datasets/delete",
    listing: DATASET_LISTING,
    acknowledged: {
      schema_version: 1,
      dataset_id: OTHER_ID,
      database_name: OTHER_DATABASE,
    },
    message: wording.inference.deleteMessage
      .replace("{dataset_id}", OTHER_ID)
      .replace("{database_name}", OTHER_DATABASE),
    body: { dataset_id: OTHER_ID },
    absent: [SELECTED_ID, SELECTED_DATABASE],
    element: createElement(DatasetCleanup, {
      session,
      onRefusal: () => {},
      selectionEnabled: true,
      selectionFailure: null,
    }),
  };
}

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

function failedEnvelope(): StubResponse {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      exit_code: 1,
      report: null,
      failure_line: FAILURE_LINE,
    }),
  };
}

interface RecordedCall {
  method: string;
  path: string;
  body: string | null;
}

const calls: RecordedCall[] = [];

function install(
  spec: SurfaceSpec,
  outcome: "cancel" | "confirm" | "failure",
): void {
  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    calls.push({
      method,
      path,
      body: (init?.body as string | undefined) ?? null,
    });
    if (method === "GET" && path === spec.listPath) {
      return envelope(spec.listing);
    }
    if (method === "POST" && path === spec.deletePath) {
      return outcome === "failure"
        ? failedEnvelope()
        : envelope(spec.acknowledged);
    }
    throw new Error(`unexpected request ${method} ${path}`);
  }) as unknown as typeof fetch);
}

function buttonsNamed(name: string): HTMLButtonElement[] {
  return [...document.body.querySelectorAll("button")].filter(
    (element) => element.textContent?.trim() === name,
  );
}

function dialogText(): string | null {
  return document.querySelector('[role="dialog"]')?.textContent ?? null;
}

async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 6; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

describe.each(["dataset-cleanup", "backups"] as const)(
  "%s deletion",
  (surface) => {
    describe.each(["cancel", "confirm", "failure"] as const)(
      "confirmed as %s",
      (choice) => {
        let container: HTMLDivElement;
        let root: Root;
        let spec: SurfaceSpec;

        beforeEach(() => {
          calls.length = 0;
          spec = contract(surface);
          container = document.createElement("div");
          document.body.appendChild(container);
          root = createRoot(container);
          install(spec, choice);
        });

        afterEach(() => {
          act(() => root.unmount());
          container.remove();
          vi.unstubAllGlobals();
        });

        it("deletes only the listed target confirmed by name", async () => {
          await act(async () => {
            root.render(spec.element);
          });
          await settle();

          if (surface === "dataset-cleanup") {
            // The selected dataset offers no deletion, and the non-selected one offers exactly one.
            expect(container.textContent).toContain(SELECTED_ID);
            expect(container.textContent).toContain(OTHER_ID);
            // The selected row shows its marker in the cell that holds the delete control.
            const selectedRow = [
              ...container.querySelectorAll("tbody tr"),
            ].find((row) => row.textContent?.includes(SELECTED_ID));
            expect(
              selectedRow?.querySelector("td:last-child")?.textContent,
            ).toBe(wording.inference.selectedTag);
          }
          const deletions = buttonsNamed(wording.inference.delete);
          expect(deletions).toHaveLength(1);

          await act(async () => {
            deletions[0].click();
          });
          await settle();

          // The confirmation names exactly the listed target of that row.
          expect(dialogText()).toContain(spec.message);
          for (const value of spec.absent) {
            expect(dialogText()).not.toContain(value);
          }

          const confirm = buttonsNamed(wording.inference.confirm);
          expect(confirm).toHaveLength(1);
          if (choice === "cancel") {
            await act(async () => {
              buttonsNamed(wording.inference.cancel)[0].click();
            });
            await settle();
            expect(
              calls.filter((call) => call.path === spec.deletePath),
            ).toHaveLength(0);
            expect(dialogText()).toBeNull();
            return;
          }

          await act(async () => {
            confirm[0].click();
          });
          await settle();

          const posted = calls.filter((call) => call.method === "POST");
          expect(posted).toHaveLength(1);
          expect(posted[0].path).toBe(spec.deletePath);
          expect(JSON.parse(posted[0].body ?? "{}")).toEqual(spec.body);
          if (choice === "failure") {
            // The dialog closes first, and the retained row's panel shows the command failure.
            expect(dialogText()).toBeNull();
            expect(container.textContent).toContain(FAILURE_LINE);
            expect(container.textContent).toContain(
              surface === "dataset-cleanup" ? OTHER_ID : BACKUP_NAME,
            );
            expect(
              calls.filter(
                (call) => call.method === "GET" && call.path === spec.listPath,
              ),
            ).toHaveLength(1);
            return;
          }
          // A successful deletion refreshes that panel's own listing.
          expect(
            calls.filter(
              (call) => call.method === "GET" && call.path === spec.listPath,
            ),
          ).toHaveLength(2);
        });
      },
    );
  },
);
