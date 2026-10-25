/** Dataset-bound cached comparison report keyed by the canonical pair in caller order. */
import { useEffect, useState } from "react";
import { readCachedReport } from "../../app/cachedRead";
import { useReadCache } from "../../app/useReadCache";
import { compareCourses } from "../../api/comparison";
import type { CourseComparisonReport } from "../../api/types";

/** Read the cached comparison report for two occupied slots. */
export function useComparison(slots: readonly [string | null, string | null]): {
  report: CourseComparisonReport | null;
  loading: boolean;
  error: Error | null;
} {
  const cache = useReadCache();
  const [a, b] = slots;
  const enabled = Boolean(a && b);
  const key = JSON.stringify(["comparison", a, b]);
  const [result, setResult] = useState<{
    key: string;
    report: CourseComparisonReport | null;
    loading: boolean;
    error: Error | null;
  }>({ key, report: null, loading: false, error: null });
  useEffect(() => {
    if (!a || !b) {
      setResult({ key, report: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setResult({ key, report: null, loading: true, error: null });
    readCachedReport(
      cache,
      key,
      (signal) => compareCourses({ course_a: a, course_b: b }, signal),
      controller.signal,
    ).then(
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
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
      },
    );
    return () => controller.abort();
  }, [a, b, cache, key]);
  if (!enabled) return { report: null, loading: false, error: null };
  if (result.key !== key) return { report: null, loading: true, error: null };
  return result;
}
