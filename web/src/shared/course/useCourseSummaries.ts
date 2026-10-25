/**
 * Transient request hook for the supplied course IDs, holding loaded courses while others load.
 */
import { useEffect, useState } from "react";
import type { CourseSummary } from "../../api/types";
import { useReadCache } from "../../app/useReadCache";
import { readCachedCourseSummaries } from "./reads";

/** Return the official summaries of the supplied course identities. */
export function useCourseSummaries(identifiers: readonly string[]): {
  courses: readonly CourseSummary[];
  loading: boolean;
  error: Error | null;
} {
  const cache = useReadCache();
  const key = JSON.stringify(["course-summaries", identifiers]);
  const requested = new Set(identifiers);
  const [result, setResult] = useState<{
    key: string;
    courses: readonly CourseSummary[];
    loading: boolean;
    error: Error | null;
  }>({
    key,
    courses: [],
    loading: identifiers.length > 0,
    error: null,
  });
  useEffect(() => {
    if (!identifiers.length) {
      setResult({ key, courses: [], loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setResult((current) => ({
      key,
      courses: current.courses.filter((course) =>
        identifiers.includes(course.group_id),
      ),
      loading: true,
      error: null,
    }));
    readCachedCourseSummaries(cache, identifiers, controller.signal).then(
      (report) => {
        if (!controller.signal.aborted)
          setResult({
            key,
            courses: report.results,
            loading: false,
            error: null,
          });
      },
      (caught: unknown) => {
        if (!controller.signal.aborted) {
          setResult({
            key,
            courses: [],
            loading: false,
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
        }
      },
    );
    return () => controller.abort();
  }, [cache, key]);
  if (result.key !== key)
    return {
      courses: result.courses.filter((course) =>
        requested.has(course.group_id),
      ),
      loading: identifiers.length > 0,
      error: null,
    };
  return {
    courses: result.courses,
    loading: result.loading,
    error: result.error,
  };
}
