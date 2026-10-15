/** Cancellable official substring request shared by course narrowing surfaces. */
import { useCallback } from "react";
import { lookupCourses } from "../../api/course-lookup";
import type { CourseLookupReport } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { LOOKUP_DEBOUNCE_MS, useLookup } from "../useLookup";

export function useCourseLookup(
  open: boolean,
  query: string,
  activeOnly: boolean,
): {
  report: CourseLookupReport | null;
  loading: boolean;
  error: Error | null;
} {
  const { value: language } = useProfileSelector((state) => state.language);
  const key = JSON.stringify([open, query, activeOnly, language]);
  const enabled = open && query.trim() !== "";
  const run = useCallback(
    (signal: AbortSignal) =>
      lookupCourses(
        { query, display_language: language, include_inactive: !activeOnly },
        signal,
      ),
    [query, language, activeOnly],
  );
  return useLookup<CourseLookupReport>(key, enabled, run, LOOKUP_DEBOUNCE_MS);
}
