/** Explicit transient unified-search requests send only submitted input. */
import { useEffect, useState } from "react";
import { readCachedReport } from "../../app/cachedRead";
import { useReadCache } from "../../app/useReadCache";
import type { SearchRequest, UnifiedSearchReport } from "../../api/types";
import { searchCourses } from "../../api/search";
import { useProfileSelector } from "../../state/useProfileSelector";

/** Return the submitted search, its report, its state and its submit action. */
export function useSearch(): {
  report: UnifiedSearchReport | null;
  loading: boolean;
  error: Error | null;
  submit: () => void;
} {
  const { value: language } = useProfileSelector((state) => state.language);
  const { value: activeOnly } = useProfileSelector(
    (state) => state.search.activeOnly,
  );
  const { value: query } = useProfileSelector((state) => state.search.query);
  const cache = useReadCache();
  const [submitted, setSubmitted] = useState<{
    request: SearchRequest;
    serial: number;
  } | null>(null);
  const [result, setResult] = useState<{
    request: SearchRequest | null;
    report: UnifiedSearchReport | null;
    loading: boolean;
    error: Error | null;
  }>({ request: null, report: null, loading: false, error: null });

  const currentRequest = submitted
    ? {
        ...submitted.request,
        display_language: language,
        include_inactive: !activeOnly,
      }
    : null;

  useEffect(() => {
    if (!currentRequest) return;
    const controller = new AbortController();
    const request = currentRequest;
    setResult((previous) => ({
      ...previous,
      request,
      loading: true,
      error: null,
    }));
    readCachedReport(
      cache,
      JSON.stringify(["search", request]),
      (signal) => searchCourses(request, signal),
      controller.signal,
    ).then(
      (report) => {
        if (!controller.signal.aborted)
          setResult({ request, report, loading: false, error: null });
      },
      (caught: unknown) => {
        if (!controller.signal.aborted)
          setResult({
            request,
            report: null,
            loading: false,
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
      },
    );
    return () => controller.abort();
  }, [
    cache,
    currentRequest?.query,
    currentRequest?.display_language,
    currentRequest?.include_inactive,
    submitted?.serial,
  ]);

  return {
    report: result.report,
    loading:
      Boolean(currentRequest) &&
      (result.request?.query !== currentRequest?.query ||
        result.request?.display_language !== currentRequest?.display_language ||
        result.request?.include_inactive !== currentRequest?.include_inactive ||
        result.loading),
    error: result.error,
    submit: () => {
      const submittedQuery = query;
      if (submittedQuery.trim()) {
        setSubmitted((previous) => ({
          serial: (previous?.serial ?? 0) + 1,
          request: {
            query: submittedQuery,
            display_language: language,
            include_inactive: !activeOnly,
          },
        }));
      }
    },
  };
}
