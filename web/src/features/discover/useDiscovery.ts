/** One keyed, cancellable request to the selected discovery endpoint. */
import { useEffect, useState } from "react";
import { readNextCourses, readRecommendations } from "../../api/discovery";
import type {
  DiscoveryRequest,
  NextCoursesReport,
  SimilarityRecommendation,
} from "../../api/types";
import type { DiscoverState } from "./state";

export function useDiscovery(
  list: DiscoverState["list"],
  request: DiscoveryRequest,
): {
  next: NextCoursesReport | null;
  similarity: readonly SimilarityRecommendation[];
  loading: boolean;
  error: Error | null;
} {
  const key = JSON.stringify([list, request]);
  const hasBasis =
    (request.basis === "selected"
      ? request.selected_courses
      : request.completed_courses
    ).length > 0;
  const [result, setResult] = useState<{
    key: string;
    next: NextCoursesReport | null;
    similarity: readonly SimilarityRecommendation[];
    loading: boolean;
    error: Error | null;
  }>({ key, next: null, similarity: [], loading: false, error: null });

  useEffect(() => {
    if (!hasBasis) {
      setResult({
        key,
        next: null,
        similarity: [],
        loading: false,
        error: null,
      });
      return;
    }
    const controller = new AbortController();
    setResult({ key, next: null, similarity: [], loading: true, error: null });
    const pending =
      list === "next"
        ? readNextCourses(request, controller.signal).then((next) => ({
            next,
            similarity: [],
          }))
        : readRecommendations(request, controller.signal).then((report) => ({
            next: null,
            similarity: report.similarity_results,
          }));
    pending.then(
      ({ next, similarity }) => {
        if (!controller.signal.aborted)
          setResult({ key, next, similarity, loading: false, error: null });
      },
      (caught: unknown) => {
        if (!controller.signal.aborted)
          setResult({
            key,
            next: null,
            similarity: [],
            loading: false,
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
      },
    );
    return () => controller.abort();
  }, [hasBasis, key, list, request]);

  if (!hasBasis)
    return { next: null, similarity: [], loading: false, error: null };
  if (result.key !== key)
    return { next: null, similarity: [], loading: true, error: null };
  return result;
}
