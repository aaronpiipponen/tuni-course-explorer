/** Bootstrap proof that a failed feature read renders the failure alert in place of the shell. */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WebFeatures as WebFeaturesReport } from "../api/types";
import { useReadCache } from "./useReadCache";
import { useWebFeatures } from "./useWebFeatures";
import { WebFeatures } from "./WebFeatures";
import { StoreContext } from "../state/context";
import { createBrowserStore, type BrowserStore } from "../state/store";
import { waitFor } from "../test/waitFor";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const identity = "synthetic-dataset";
const features: WebFeaturesReport = {
  embeddings_enabled: true,
  inference_enabled: false,
  dataset_identity: identity,
};

function FeatureProbe() {
  const served = useWebFeatures();
  const cache = useReadCache();
  return createElement(
    "p",
    { "data-testid": "feature-child" },
    `${served.dataset_identity} ${cache.getDatasetIdentity()}`,
  );
}

interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function response(payload: unknown): StubResponse {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  };
}

describe("feature bootstrap", () => {
  let container: HTMLDivElement;
  let root: Root;
  let store: BrowserStore;
  let mode: "pending" | "failed" | "ready";
  let release: (() => void) | null;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    mode = "pending";
    release = null;
    container = document.createElement("div");
    document.body.appendChild(container);
    store = createBrowserStore(localStorage);
    root = createRoot(container);
    vi.stubGlobal("fetch", (async (input: unknown) => {
      if (String(input) !== "/api/features")
        throw new Error(`Unexpected request ${String(input)}`);
      if (mode === "pending")
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      if (mode === "failed")
        return { ok: false, status: 500, json: async () => ({}) };
      return response(features);
    }) as unknown as typeof fetch);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  function render(): void {
    act(() =>
      root.render(
        createElement(
          StoreContext.Provider,
          { value: store },
          createElement(WebFeatures, {
            children: createElement(FeatureProbe),
          }),
        ),
      ),
    );
  }

  it("renders the failure alert in place of the served shell", async () => {
    render();
    expect(container.querySelector('[data-testid="feature-child"]')).toBeNull();

    mode = "failed";
    release?.();
    await waitFor(() =>
      expect(
        container.querySelector('[role="alert"]')?.textContent,
      ).toBeTruthy(),
    );

    expect(container.querySelector('[data-testid="feature-child"]')).toBeNull();
    expect(container.textContent).not.toContain(identity);

    act(() => root.unmount());
    mode = "ready";
    root = createRoot(container);
    render();
    await waitFor(() =>
      expect(
        container.querySelector<HTMLElement>('[data-testid="feature-child"]')
          ?.textContent,
      ).toBe(`${identity} ${identity}`),
    );
  });
});
