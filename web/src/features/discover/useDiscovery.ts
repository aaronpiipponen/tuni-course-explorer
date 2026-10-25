/** One keyed, cancellable request to the selected discovery endpoint. */
import { useEffect, useState } from "react";
import { readCachedReport } from "../../app/cachedRead";
import { useReadCache } from "../../app/useReadCache";
import { readNextCourses, readRecommendations } from "../../api/discovery";
import type {
  DiscoveryRequest,
  NextCoursesReport,
  SimilarityRecommendation,
} from "../../api/types";
import type { DiscoverState } from "./state";

/** Read and cache the selected discovery report. */
export function useDiscovery(
  list: DiscoverState["list"],
  request: DiscoveryRequest,
  hasBasis: boolean,
): {
  next: NextCoursesReport | null;
  similarity: readonly SimilarityRecommendation[];
  loading: boolean;
  error: Error | null;
} {
  const cache = useReadCache();
  const key = JSON.stringify([list, request]);
  const [result, setResult] = useState<{
    key: string;
    next: NextCoursesReport | null;
    similarity: readonly SimilarityRecommendation[];
    loading: boolean;
    error: Error | null;
  }>({ key, next: null, similarity: [], loading: false, error: null });

  useEffect(() => {
    const [currentList, currentRequest] = JSON.parse(key) as [
      DiscoverState["list"],
      DiscoveryRequest,
    ];
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
      currentList === "next"
        ? readCachedReport(
            cache,
            key,
            (signal) => readNextCourses(currentRequest, signal),
            controller.signal,
          ).then((next) => ({
            next,
            similarity: [],
          }))
        : readCachedReport(
            cache,
            key,
            (signal) => readRecommendations(currentRequest, signal),
            controller.signal,
          ).then((report) => ({
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
  }, [cache, hasBasis, key]);

  if (!hasBasis)
    return { next: null, similarity: [], loading: false, error: null };
  if (result.key !== key)
    return { next: null, similarity: [], loading: true, error: null };
  return result;
}
