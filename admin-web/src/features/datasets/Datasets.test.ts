/**
 * Deletion-contract proofs for the Settings dataset panel and the backup cleanup panel.
 *
 * Each invocation mounts one real panel and its confirmation dialog over one fetch boundary that
 * answers that panel's own inventory and deletion routes. The dataset panel renders the shell's
 * shared inventory read through the shared proof harness. The proofs cover that only the confirmed
 * listed target is posted, that a Working target carries its explicit confirmation flag, that
 * cancelling posts nothing, that the selected dataset offers no deletion at all and that the panel
 * shows the owning guidance line of a failed command.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ServerStatusReport } from "../../api/types";
import type { PanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { buttonsNamed, DatasetsHarness, settle } from "./datasetsTestHarness";
import { Backups } from "../settings/Backups";

const SELECTED_ID = "a".repeat(32);
const WORKING_ID = "c".repeat(32);
const SELECTED_DATABASE = "course_admin_selected";
const WORKING_DATABASE = "course_admin_working";
const BACKUP_NAME = "before-inference.dump";
const FAILURE_LINE = "ValueError";
const FAILURE_GUIDANCE = "synthetic cleanup guidance";

const DATASET_LISTING = {
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
    {
      dataset_id: WORKING_ID,
      kind: "copied",
      database_name: WORKING_DATABASE,
      predecessor_id: SELECTED_ID,
      receipt_schema_revision: "20261028_0022",
      dump_path: "data/admin/dumps/working.dump",
      selected: false,
      working: true,
      database_presence: "present",
      artifacts_present: false,
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

type Surface = "datasets" | "backups";

const session = { csrfToken: "csrf-token", pollSeconds: 3600 };

/** One dashboard read that has not answered yet, so only the inventory is observed here. */
const dashboard: PanelRead<ServerStatusReport> = {
  report: null,
  failure: null,
  lastSuccess: null,
  loading: true,
  reload: () => {},
};

/** The routes, inventory, confirmation and posted body of one surface. */
interface SurfaceSpec {
  listPath: string;
  deletePath: string;
  listing: unknown;
  acknowledged: unknown;
  message: string;
  body: Record<string, unknown>;
  absent: string[];
  deleteLabel: string;
  failureGuidance: string;
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
      deleteLabel: wording.inference.delete,
      failureGuidance:
        "pick a regular file from the backup listing printed by this entry and check its access permissions",
      element: createElement(Backups, { session, onRefusal: () => {} }),
    };
  }
  return {
    listPath: "/api/datasets",
    deletePath: "/api/datasets/delete",
    listing: DATASET_LISTING,
    acknowledged: {
      schema_version: 1,
      dataset_id: WORKING_ID,
      database_name: WORKING_DATABASE,
    },
    message: wording.datasets.deleteWorkingMessage
      .replace("{dataset_id}", WORKING_ID)
      .replace("{database_name}", WORKING_DATABASE),
    body: { dataset_id: WORKING_ID, confirm_working: true },
    absent: [SELECTED_ID, SELECTED_DATABASE],
    deleteLabel: wording.datasets.delete,
    failureGuidance: FAILURE_GUIDANCE,
    element: createElement(DatasetsHarness, {
      session,
      dashboard,
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

function failedEnvelope(guidance: string): StubResponse {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      exit_code: 1,
      report: null,
      failure_line: FAILURE_LINE,
      guidance_line: guidance,
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
        ? failedEnvelope(spec.failureGuidance)
        : envelope(spec.acknowledged);
    }
    throw new Error(`unexpected request ${method} ${path}`);
  }) as unknown as typeof fetch);
}

function dialogText(): string | null {
  return document.querySelector('[role="dialog"]')?.textContent ?? null;
}

describe.each(["datasets", "backups"] as const)("%s deletion", (surface) => {
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
        await settle(6);

        if (surface === "datasets") {
          // Both roles are listed, and only the Working dataset offers deletion.
          expect(container.textContent).toContain(SELECTED_ID);
          expect(container.textContent).toContain(WORKING_ID);
          expect(container.textContent).toContain(wording.datasets.selectedTag);
          expect(container.textContent).toContain(wording.datasets.workingTag);
          const roleCard = (tag: string): Element => {
            const span = [...container.querySelectorAll("span")].find(
              (element) =>
                element.textContent === tag &&
                element.closest("article") === null,
            );
            const section = span?.closest("section");
            if (section === null || section === undefined) {
              throw new Error(`no role card tagged ${tag}`);
            }
            return section;
          };
          const rowHolding = (id: string): Element => {
            const row = [...container.querySelectorAll("code")]
              .filter((element) => element.textContent === id)
              .map((element) => element.closest("article"))
              .find((element) => element !== null);
            if (row === null || row === undefined) {
              throw new Error(`no retained row holding ${id}`);
            }
            return row;
          };
          const namedIn = (row: Element) =>
            [...row.querySelectorAll("button")].filter(
              (button) => button.textContent?.trim() === spec.deleteLabel,
            );
          expect(namedIn(rowHolding(SELECTED_ID))).toHaveLength(0);
          expect(namedIn(rowHolding(WORKING_ID))).toHaveLength(1);
          const selectedRole = roleCard(wording.datasets.selectedTag);
          expect(selectedRole.textContent).toContain(SELECTED_DATABASE);
          expect(selectedRole.textContent).toContain(
            wording.datasets.recordedHead,
          );
          expect(selectedRole.textContent).toContain(
            "data/admin/dumps/selected.dump",
          );
          expect(selectedRole.textContent).toContain(
            wording.datasets.artifactsPresent,
          );
          const workingRole = roleCard(wording.datasets.workingTag);
          expect(workingRole.textContent).toContain(
            wording.datasets.predecessor,
          );
          expect(workingRole.textContent).toContain(SELECTED_ID);
          expect(workingRole.textContent).toContain(
            "data/admin/dumps/working.dump",
          );
          expect(workingRole.textContent).toContain(
            wording.datasets.artifactsAbsent,
          );
          const retained = rowHolding(SELECTED_ID);
          expect(retained.textContent).toContain(
            "data/admin/dumps/selected.dump",
          );
          expect(retained.textContent).not.toContain(
            wording.datasets.predecessor,
          );
          expect(retained.textContent).not.toContain(
            wording.datasets.recordedHead,
          );
        }
        const deletions = buttonsNamed(spec.deleteLabel);
        expect(deletions).toHaveLength(1);

        await act(async () => {
          deletions[0].click();
        });
        await settle(6);

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
          await settle(6);
          expect(
            calls.filter((call) => call.path === spec.deletePath),
          ).toHaveLength(0);
          expect(dialogText()).toBeNull();
          return;
        }

        await act(async () => {
          confirm[0].click();
        });
        await settle(6);

        const posted = calls.filter((call) => call.method === "POST");
        expect(posted).toHaveLength(1);
        expect(posted[0].path).toBe(spec.deletePath);
        expect(JSON.parse(posted[0].body ?? "{}")).toEqual(spec.body);
        if (choice === "failure") {
          // The dialog closes first, and the retained row's panel shows the owning guidance line.
          expect(dialogText()).toBeNull();
          expect(container.textContent).toContain(spec.failureGuidance);
          expect(container.textContent).not.toContain(FAILURE_LINE);
          expect(container.textContent).toContain(
            surface === "datasets" ? WORKING_ID : BACKUP_NAME,
          );
          // A failed dataset action re-reads the inventory to discover the actual state, while
          // the backup panel keeps its failed row without another read.
          expect(
            calls.filter(
              (call) => call.method === "GET" && call.path === spec.listPath,
            ),
          ).toHaveLength(surface === "datasets" ? 2 : 1);
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
});
