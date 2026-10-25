/** Rendered proof that a refused switch write leaves the value the web file reports. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConfigurationFileReport } from "../../api/types";
import { WEB_CONFIGURATION_FILE } from "../../api/settings";
import { wording } from "../../shared/wording";
import { FeatureSwitches } from "./FeatureSwitches";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const session = { csrfToken: "synthetic-csrf", pollSeconds: 3600 };

const report: ConfigurationFileReport = {
  schema_version: 1,
  file: WEB_CONFIGURATION_FILE,
  values: {
    WEB_INFERENCE_ENABLED: false,
    WEB_EMBEDDINGS_ENABLED: true,
  },
};

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function envelope(reportValue: unknown): StubResponse {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      exit_code: 0,
      report: reportValue,
      failure_line: null,
    }),
  };
}

function refusedCommand(): StubResponse {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      exit_code: 1,
      report: null,
      failure_line: "ValueError",
    }),
  };
}

describe("refused feature-switch write", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal("fetch", (async (input: unknown) => {
      const path = String(input);
      if (path === "/api/settings/config/read") {
        return envelope(report);
      }
      if (path === "/api/settings/config/set") return refusedCommand();
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

  it("keeps the reported switch value when the write is refused", async () => {
    const onSaved = vi.fn();
    act(() =>
      root.render(
        createElement(FeatureSwitches, {
          session,
          onRefusal: () => {},
          revision: 0,
          onSaved,
        }),
      ),
    );
    await settle();

    const selector = `button[role="switch"][aria-label="${wording.settings.inferenceFeatures}"]`;
    const current = container.querySelector<HTMLButtonElement>(selector);
    if (!current) throw new Error("The inference switch is missing");
    expect(current.getAttribute("aria-checked")).toBe("false");

    act(() => current.click());
    await settle();

    const failure = container.querySelector<HTMLElement>(
      '.failure[role="alert"]',
    );
    expect(failure?.textContent?.trim()).toBeTruthy();
    const settled = container.querySelector<HTMLButtonElement>(selector);
    expect(settled?.getAttribute("aria-checked")).toBe("false");
    expect(settled?.disabled).toBe(false);
    expect(onSaved).not.toHaveBeenCalled();
  });
});
