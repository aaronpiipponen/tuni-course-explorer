/** Transient cancellable comparison request keyed only by the canonical pair. */
import { useCallback } from "react";
import { compareCourses } from "../../api/comparison";
import type { CourseComparisonReport } from "../../api/types";
import { useLookup } from "../../shared/useLookup";

export function useComparison(slots: readonly [string | null, string | null]): {
  report: CourseComparisonReport | null;
  loading: boolean;
  error: Error | null;
} {
  const [a, b] = slots;
  const run = useCallback(
    (signal: AbortSignal) =>
      compareCourses({ course_a: a!, course_b: b! }, signal),
    [a, b],
  );
  return useLookup<CourseComparisonReport>(
    JSON.stringify([a, b]),
    Boolean(a && b),
    run,
  );
}
