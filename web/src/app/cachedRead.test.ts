/** Shared successful-read reuse across pane remounts. */
import { act, createElement, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { readCachedReport } from "./cachedRead";
import { READ_CACHE_CAPACITY, ReadCache } from "./readCache";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("cached report read", () => {
  it("reuses a successful feature read across pane remounts", async () => {
    const cache = new ReadCache("dataset-one", READ_CACHE_CAPACITY);
    const report = { dataset_identity: "dataset-one", payload: "saved" };
    const read = vi.fn(() => Promise.resolve(report));
    const seen: (typeof report | null)[] = [];
    const Harness = () => {
      useEffect(() => {
        const controller = new AbortController();
        void readCachedReport(
          cache,
          JSON.stringify(["discover", "next"]),
          read,
          controller.signal,
        ).then((value) => seen.push(value));
        return () => controller.abort();
      }, []);
      return null;
    };
    const host = document.createElement("div");
    document.body.append(host);
    let root = createRoot(host);
    await act(async () => {
      root.render(createElement(Harness));
    });
    await act(async () => {});
    expect(seen).toEqual([report]);

    await act(async () => root.unmount());
    root = createRoot(host);
    await act(async () => {
      root.render(createElement(Harness));
    });
    await act(async () => {});
    expect(read).toHaveBeenCalledTimes(1);
    expect(seen).toEqual([report, report]);
    expect(seen[1]).toBe(report);
    await act(async () => root.unmount());
    host.remove();
  });
});
