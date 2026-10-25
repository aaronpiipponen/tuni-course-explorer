/**
 * Rendered proof that a confirmed target decision writes the resolved identity and calls
 * `onDecisionRecorded`.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { InferenceTargetDisposition } from "../../api/types";
import { wording } from "../../shared/wording";
import { TargetDecisions } from "./TargetDecisions";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const TARGET = "synthetic-target-group";
const session = { csrfToken: "synthetic-csrf", pollSeconds: 3600 };

const resolved: InferenceTargetDisposition = {
  dataset_id: "synthetic-dataset",
  target_group_id: TARGET,
  course_code: "SYN-101",
  course_name: "Synthetic target",
  disposition: null,
};

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

describe("target decision confirmation", () => {
  let container: HTMLDivElement;
  let root: Root;
  let responseDisposition: InferenceTargetDisposition["disposition"] = null;
  const decisions: { target_id: string; disposition: string }[] = [];

  beforeEach(() => {
    decisions.length = 0;
    responseDisposition = null;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
      const path = String(input);
      const body = JSON.parse(String(init?.body ?? "{}")) as {
        target_id?: string;
        disposition?: string;
      };
      if (path === "/api/inference/target/read") return envelope(resolved);
      if (path === "/api/inference/target/decision") {
        decisions.push({
          target_id: String(body.target_id),
          disposition: String(body.disposition),
        });
        return envelope({ ...resolved, disposition: responseDisposition });
      }
      throw new Error(`Unexpected request ${path}`);
    }) as unknown as typeof fetch);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  async function settle(): Promise<void> {
    await act(async () => {
      for (let turn = 0; turn < 6; turn += 1)
        await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }

  function buttonsNamed(name: string): HTMLButtonElement[] {
    return [
      ...document.body.querySelectorAll<HTMLButtonElement>("button"),
    ].filter((button) => button.textContent?.trim() === name);
  }

  function type(input: HTMLInputElement, value: string): void {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  it.each([
    { token: "done", tag: wording.inference.done },
    { token: "failed", tag: wording.inference.failed },
    { token: "nothing", tag: wording.inference.nothing },
  ] as const)(
    "records a $token decision for the resolved target and refreshes the shared summary",
    async ({ token, tag }) => {
      responseDisposition = token === "nothing" ? null : token;
      const onDecisionRecorded = vi.fn();
      act(() =>
        root.render(
          createElement(TargetDecisions, {
            session,
            onRefusal: () => {},
            onDecisionRecorded,
          }),
        ),
      );
      await settle();

      const record = () => buttonsNamed(wording.inference.recordDecision)[0];
      const input = container.querySelector<HTMLInputElement>(
        `input[aria-label="${wording.inference.targetInput}"]`,
      );
      if (!input) throw new Error("The target input is missing");
      expect(record().disabled).toBe(true);

      type(input, TARGET);
      act(() => buttonsNamed(wording.inference.search)[0].click());
      await settle();
      expect(record().disabled).toBe(false);

      // The decisions follow the exact identity the read resolved.
      type(input, `${TARGET}-edited`);
      await settle();
      expect(record().disabled).toBe(true);

      type(input, TARGET);
      await settle();
      act(() => buttonsNamed(tag)[0].click());

      if (token === "nothing") {
        act(() => record().click());
        await settle();
        expect(document.body.querySelector('[role="dialog"]')).toBeNull();
      } else {
        act(() => record().click());
        await settle();
        expect(document.body.querySelector('[role="dialog"]')).toBeTruthy();
        act(() => buttonsNamed(wording.inference.cancel)[0].click());
        await settle();
        expect(decisions).toHaveLength(0);

        act(() => record().click());
        await settle();
        act(() => buttonsNamed(wording.inference.confirm)[0].click());
        await settle();
      }

      expect(decisions).toHaveLength(1);
      expect(decisions[0].target_id).toBe(TARGET);
      expect(decisions[0].disposition).toBe(token);
      expect(container.querySelector(".tag")?.textContent).toBe(tag);
      expect(onDecisionRecorded).toHaveBeenCalledTimes(1);
    },
  );
});
