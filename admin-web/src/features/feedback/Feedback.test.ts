/**
 * Deletion-contract proof for the feedback inbox.
 *
 * One real panel mounts over one fetch boundary that answers its listing and deletion routes. The
 * proof drives the named confirmation of one row and asserts that cancelling posts nothing, that
 * confirming posts only that identity, and that a failed command retains the row.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FeedbackListReport } from "../../api/types";
import { moment } from "../../shared/format";
import { wording } from "../../shared/wording";
import { Feedback } from "./Feedback";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const FIRST_ID = "11111111-1111-4111-8111-111111111111";
const SECOND_ID = "22222222-2222-4222-8222-222222222222";
const FIRST_TIME = "2026-10-20T09:30:00Z";
const SECOND_TIME = "2026-10-19T08:15:00Z";
const FAILURE_LINE = "ValueError";
const FAILURE_GUIDANCE =
  "check the configured feedback definition, the feedback database connection and the stored submission identity, then retry";
const LIST_PATH = "/api/feedback/list";
const DELETE_PATH = "/api/feedback/delete";

const LISTING: FeedbackListReport = {
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
  submissions: [
    {
      id: FIRST_ID,
      created_at: FIRST_TIME,
      answers: { type: "bug", title: "First", message: "First message" },
      public_issue: true,
      publication_state: "pending",
      issue_url: null,
      publication_failure: null,
      attachments: [],
    },
    {
      id: SECOND_ID,
      created_at: SECOND_TIME,
      answers: { type: "other", title: "Second", message: "Second message" },
      public_issue: false,
      publication_state: "private",
      issue_url: null,
      publication_failure: null,
      attachments: [],
    },
  ],
};

const REMAINING: FeedbackListReport = {
  ...LISTING,
  submissions: LISTING.submissions.filter(
    (submission) => submission.id !== FIRST_ID,
  ),
};

const session = { csrfToken: "csrf-token", pollSeconds: 3600 };

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
      guidance_line: FAILURE_GUIDANCE,
    }),
  };
}

interface RecordedCall {
  method: string;
  path: string;
  body: string | null;
}

const calls: RecordedCall[] = [];

function install(outcome: "cancel" | "confirm" | "failure"): void {
  let listings = 0;
  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    calls.push({
      method,
      path,
      body: (init?.body as string | undefined) ?? null,
    });
    if (method === "POST" && path === LIST_PATH) {
      listings += 1;
      return envelope(listings > 1 ? REMAINING : LISTING);
    }
    if (method === "POST" && path === DELETE_PATH) {
      return outcome === "failure"
        ? failedEnvelope()
        : envelope({ feedback_id: FIRST_ID });
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

function dialogText(): string {
  return document.body.querySelector('[role="dialog"]')?.textContent ?? "";
}

function type(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

/** Return the listed submission identities in the order the panel draws them. */
function entryIds(container: HTMLElement): string[] {
  return [
    ...container.querySelectorAll<HTMLElement>("article.feedback-entry"),
  ].map(
    (entry) =>
      [FIRST_ID, SECOND_ID].find((id) => entry.textContent?.includes(id)) ?? "",
  );
}

function buttonNamed(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find(
    (element) => element.textContent?.trim() === name,
  );
  if (found === undefined) throw new Error(`no button named ${name}`);
  return found;
}

describe.each(["cancel", "confirm", "failure"] as const)(
  "feedback deletion confirmed as %s",
  (choice) => {
    let container: HTMLDivElement;
    let root: Root;

    beforeEach(() => {
      calls.length = 0;
      container = document.createElement("div");
      document.body.appendChild(container);
      root = createRoot(container);
      install(choice);
    });

    afterEach(() => {
      act(() => root.unmount());
      container.remove();
      vi.unstubAllGlobals();
    });

    it("deletes only the feedback confirmed by identity", async () => {
      await act(async () => {
        root.render(createElement(Feedback, { session, onRefusal: () => {} }));
      });
      await settle();

      // A text search ranks by the earliest matching text field, then by recency.
      const search =
        container.querySelector<HTMLInputElement>(".feedback-search");
      if (search === null) throw new Error("no feedback search input");
      type(search, "e");
      await act(async () => {
        buttonNamed(container, wording.feedback.apply).click();
      });
      await settle();
      expect(entryIds(container)).toEqual([SECOND_ID, FIRST_ID]);

      // A type filter narrows that ranked list to the matching identity.
      await act(async () => {
        const picker = container.querySelector<HTMLButtonElement>(
          'button.pick-button[aria-label="Type"]',
        );
        if (picker === null) throw new Error("no type filter");
        picker.click();
      });
      await settle();
      await act(async () => {
        const option =
          document.querySelector<HTMLButtonElement>('[data-value="bug"]');
        if (option === null) throw new Error("no bug option");
        option.click();
      });
      await act(async () => {
        buttonNamed(container, wording.feedback.apply).click();
      });
      await settle();
      expect(entryIds(container)).toEqual([FIRST_ID]);

      await act(async () => {
        buttonNamed(container, wording.feedback.clearFilters).click();
      });
      await settle();
      expect(entryIds(container)).toEqual([SECOND_ID, FIRST_ID]);

      const entries = [
        ...container.querySelectorAll<HTMLElement>("article.feedback-entry"),
      ];
      expect(entries).toHaveLength(2);
      const target = entries.find((entry) =>
        entry.textContent?.includes(FIRST_ID),
      );
      expect(target).toBeDefined();

      await act(async () => {
        target?.querySelector<HTMLButtonElement>(".feedback-delete")?.click();
      });
      await settle();

      // The confirmation names exactly the row's identity and submission time.
      expect(dialogText()).toContain(
        wording.feedback.deleteMessage
          .replace("{id}", FIRST_ID)
          .replace("{time}", moment(FIRST_TIME)),
      );
      expect(dialogText()).not.toContain(SECOND_ID);

      if (choice === "cancel") {
        await act(async () => {
          buttonNamed(document.body, wording.inference.cancel).click();
        });
        await settle();
        expect(calls.filter((call) => call.path === DELETE_PATH)).toHaveLength(
          0,
        );
        expect(dialogText()).toBe("");
        expect(container.textContent).toContain(FIRST_ID);
        return;
      }

      await act(async () => {
        buttonNamed(document.body, wording.inference.confirm).click();
      });
      await settle();

      const deletions = calls.filter((call) => call.path === DELETE_PATH);
      expect(deletions).toHaveLength(1);
      expect(deletions[0].method).toBe("POST");
      expect(JSON.parse(deletions[0].body ?? "{}")).toEqual({
        feedback_id: FIRST_ID,
      });

      if (choice === "failure") {
        // The row stays, the dialog is closed and the panel shows the owning guidance line.
        expect(dialogText()).toBe("");
        expect(container.textContent).toContain(FIRST_ID);
        expect(container.textContent).toContain(FAILURE_GUIDANCE);
        expect(container.textContent).not.toContain(FAILURE_LINE);
        expect(calls.filter((call) => call.path === LIST_PATH)).toHaveLength(1);
        return;
      }

      // A successful deletion reloads the listing without that row.
      expect(calls.filter((call) => call.path === LIST_PATH)).toHaveLength(2);
      expect(container.textContent).not.toContain(FIRST_ID);
      expect(container.textContent).toContain(SECOND_ID);
    });
  },
);
