/** One identity-gated catalogue read shared by the local course and module lookups. */
import { useEffect, useState } from "react";
import type { CatalogueReport } from "../../api/types";
import { useReadCache } from "../../app/useReadCache";
import { readCachedCatalogue } from "./catalogue";

type CatalogueState = {
  identity: string;
  report: CatalogueReport | null;
  loading: boolean;
  error: Error | null;
};

/**
 * Return the one shared catalogue for an open lookup with a nonempty query.
 *
 * The read runs once per identity, a cancelled read is discarded, and a response of another
 * identity stays loading until the effect reads again under it.
 */
export function useCatalogueRead(
  open: boolean,
  query: string,
): {
  catalogue: CatalogueReport | null;
  loading: boolean;
  error: Error | null;
} {
  const cache = useReadCache();
  const identity = cache.getDatasetIdentity();
  const enabled = open && query.trim() !== "";
  const [state, setState] = useState<CatalogueState>({
    identity,
    report: null,
    loading: false,
    error: null,
  });
  useEffect(() => {
    if (!enabled) {
      setState({ identity, report: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ identity, report: null, loading: true, error: null });
    readCachedCatalogue(cache).then(
      (report) => {
        if (!cancelled)
          setState({
            identity: report.dataset_identity,
            report,
            loading: false,
            error: null,
          });
      },
      (caught: unknown) => {
        if (!cancelled)
          setState({
            identity,
            report: null,
            loading: false,
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [cache, enabled, identity]);
  if (!enabled) return { catalogue: null, loading: false, error: null };
  if (state.identity !== identity)
    return { catalogue: null, loading: true, error: null };
  if (state.error || state.loading || !state.report)
    return { catalogue: null, loading: state.loading, error: state.error };
  return { catalogue: state.report, loading: false, error: null };
}
