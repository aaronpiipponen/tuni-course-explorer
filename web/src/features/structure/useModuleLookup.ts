/** Local programme/module narrowing over the one shared cached catalogue. */
import { useMemo } from "react";
import type {
  LocalModuleLookupReport,
  ModuleLookupGroup,
} from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useCatalogueRead } from "../../shared/course/useCatalogueRead";
import { narrowModules } from "../../shared/course/narrowing";

/** Return one row per matching module group, with every eligible candidate of that group. */
export function useModuleLookup(
  open: boolean,
  query: string,
): {
  report: LocalModuleLookupReport | null;
  loading: boolean;
  error: Error | null;
} {
  const { value: language } = useProfileSelector((state) => state.language);
  const { catalogue, loading, error } = useCatalogueRead(open, query);
  const results = useMemo<readonly ModuleLookupGroup[] | null>(
    () =>
      catalogue === null
        ? null
        : narrowModules(catalogue.modules, query, language),
    [catalogue, language, query],
  );
  if (error || loading || !catalogue || results === null)
    return { report: null, loading, error };
  return { report: { results }, loading: false, error: null };
}
