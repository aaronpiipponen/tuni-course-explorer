/** Cancellable graph request retaining a successful same-root graph while marks update. */
import { useEffect, useState } from "react";
import { readPrerequisites } from "../../api/prerequisites";
import type { PrerequisiteGraphReport } from "../../api/types";
import type { usePrerequisiteInputs } from "./usePrerequisiteInputs";

export function usePrerequisiteReport(
  inputs: ReturnType<typeof usePrerequisiteInputs>,
): {
  report: PrerequisiteGraphReport | null;
  loading: boolean;
  error: Error | null;
} {
  const { request, key, active } = inputs;
  const root = request?.target_code ?? null;
  const [result, setResult] = useState<{
    root: string | null;
    key: string;
    report: PrerequisiteGraphReport | null;
    loading: boolean;
    error: Error | null;
  }>({
    root,
    key,
    report: null,
    loading: Boolean(root) && active,
    error: null,
  });
  useEffect(() => {
    if (!request || !active) {
      setResult({ root: null, key, report: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setResult((current) => ({
      root,
      key,
      // A same-root input refresh retains the last successful graph. A different root never shows it.
      report: current.root === root ? current.report : null,
      loading: true,
      error: null,
    }));
    readPrerequisites(request, controller.signal).then(
      (report) => {
        if (!controller.signal.aborted)
          setResult({ root, key, report, loading: false, error: null });
      },
      (caught: unknown) => {
        if (!controller.signal.aborted)
          setResult({
            root,
            key,
            report: null,
            loading: false,
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
      },
    );
    return () => controller.abort();
  }, [key, active]);
  if (!request || !active) return { report: null, loading: false, error: null };
  if (result.key !== key || result.root !== root)
    return {
      report: result.root === root ? result.report : null,
      loading: true,
      error: null,
    };
  return {
    report: result.report,
    loading: result.loading,
    error: result.error,
  };
}
