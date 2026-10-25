/**
 * Cancellable graph read over the app-level read cache.
 *
 * A cached structural input publishes its held response without a request. A resolved new input
 * reads once on a miss, and leaving the pane aborts the pending read without dropping successful
 * values. A same-root read keeps the last successful graph while it runs. `ready` is true only for
 * the settled response of the active root and its exact graph key.
 */
import { useEffect, useRef, useState } from "react";
import { readCachedReport } from "../../app/cachedRead";
import { readPrerequisites } from "../../api/prerequisites";
import type { PrerequisiteGraphReport } from "../../api/types";
import { useReadCache } from "../../app/useReadCache";
import type { usePrerequisiteInputs } from "./usePrerequisiteInputs";

/** Return the cached, cancellable graph read of one input snapshot. */
export function usePrerequisiteReport(
  inputs: ReturnType<typeof usePrerequisiteInputs>,
): {
  report: PrerequisiteGraphReport | null;
  loading: boolean;
  error: Error | null;
  ready: boolean;
} {
  const {
    graphRequest,
    graphKey,
    graphInputError,
    graphInputsPending,
    active,
  } = inputs;
  const cache = useReadCache();
  const request = useRef(graphRequest);
  request.current = graphRequest;
  // The live snapshot names the root while an activity classification is still pending.
  const root = inputs.request?.target_code ?? null;
  const [result, setResult] = useState<{
    root: string | null;
    key: string | null;
    report: PrerequisiteGraphReport | null;
    loading: boolean;
    error: Error | null;
  }>({ root: null, key: null, report: null, loading: false, error: null });
  useEffect(() => {
    if (!graphKey || !active) {
      setResult({ root, key: null, report: null, loading: false, error: null });
      return;
    }
    const cached = cache.get<PrerequisiteGraphReport>(graphKey);
    if (cached !== undefined) {
      setResult({
        root,
        key: graphKey,
        report: cached,
        loading: false,
        error: null,
      });
      return;
    }
    const pendingRequest = request.current;
    if (!pendingRequest) {
      setResult({ root, key: null, report: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setResult((current) => ({
      root,
      key: graphKey,
      // A same-root input refresh retains the last successful graph. A different root never shows it.
      report: current.root === root ? current.report : null,
      loading: true,
      error: null,
    }));
    readCachedReport(
      cache,
      graphKey,
      (signal) => readPrerequisites(pendingRequest, signal),
      controller.signal,
    ).then(
      (report) => {
        if (controller.signal.aborted) return;
        setResult({
          root,
          key: graphKey,
          report,
          loading: false,
          error: null,
        });
      },
      (caught: unknown) => {
        if (controller.signal.aborted) return;
        setResult({
          root,
          key: graphKey,
          report: null,
          loading: false,
          error: caught instanceof Error ? caught : new Error(String(caught)),
        });
      },
    );
    return () => controller.abort();
  }, [cache, graphKey, active, root]);
  if (!active || !root)
    return {
      report: null,
      loading: false,
      error: graphInputError,
      ready: false,
    };
  if (graphInputError)
    return {
      report: null,
      loading: false,
      error: graphInputError,
      ready: false,
    };
  if (graphInputsPending) {
    // The retained structural input keeps the held drawing until the classification settles.
    return {
      report: result.root === root ? result.report : null,
      loading: true,
      error: null,
      ready: false,
    };
  }
  if (!graphKey) {
    // A root with no resolved structural key shows the ordinary waiting state.
    return { report: null, loading: true, error: null, ready: false };
  }
  if (result.key !== graphKey || result.root !== root)
    return {
      report: result.root === root ? result.report : null,
      loading: true,
      error: null,
      ready: false,
    };
  return {
    report: result.report,
    loading: result.loading,
    error: result.error,
    ready: !result.loading && result.error === null && result.report !== null,
  };
}
