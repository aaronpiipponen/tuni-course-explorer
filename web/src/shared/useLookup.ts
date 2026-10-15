/** One cancellable, key-scoped request lifecycle with opt-in narrowing debounce. */
import { useEffect, useState } from "react";

export const LOOKUP_DEBOUNCE_MS = 200;

export function useLookup<T>(
  key: string,
  enabled: boolean,
  run: (signal: AbortSignal) => Promise<T>,
  delayMs = 0,
): { report: T | null; loading: boolean; error: Error | null } {
  const [result, setResult] = useState<{
    key: string;
    report: T | null;
    loading: boolean;
    error: Error | null;
  }>({ key, report: null, loading: false, error: null });
  useEffect(() => {
    if (!enabled) {
      setResult({ key, report: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setResult({ key, report: null, loading: true, error: null });
    const start = () => {
      run(controller.signal).then(
        (report) => {
          if (!controller.signal.aborted)
            setResult({ key, report, loading: false, error: null });
        },
        (caught: unknown) => {
          if (!controller.signal.aborted)
            setResult({
              key,
              report: null,
              loading: false,
              error:
                caught instanceof Error ? caught : new Error(String(caught)),
            });
        },
      );
    };
    const timer = delayMs > 0 ? window.setTimeout(start, delayMs) : null;
    if (timer === null) start();
    return () => {
      if (timer !== null) window.clearTimeout(timer);
      controller.abort();
    };
  }, [key, enabled, run, delayMs]);
  if (!enabled) return { report: null, loading: false, error: null };
  if (result.key !== key) return { report: null, loading: true, error: null };
  return {
    report: result.report,
    loading: result.loading,
    error: result.error,
  };
}
