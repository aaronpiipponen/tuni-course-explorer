/** Local official course narrowing over the one shared cached catalogue. */
import { useMemo } from "react";
import type { LocalCourseLookupReport } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useCatalogueRead } from "./useCatalogueRead";
import { narrowCourses } from "./narrowing";

/** Return the official courses that match one open lookup query. */
export function useCourseLookup(
  open: boolean,
  query: string,
  activeOnly: boolean,
): {
  report: LocalCourseLookupReport | null;
  loading: boolean;
  error: Error | null;
} {
  const { value: language } = useProfileSelector((state) => state.language);
  const { catalogue, loading, error } = useCatalogueRead(open, query);
  const report = useMemo<LocalCourseLookupReport | null>(
    () =>
      catalogue === null
        ? null
        : {
            results: narrowCourses(
              catalogue.courses,
              query,
              language,
              activeOnly,
            ),
          },
    [activeOnly, catalogue, language, query],
  );
  if (error || loading || !catalogue) return { report: null, loading, error };
  return { report, loading: false, error: null };
}
