/** Profile-language module/programme narrowing request. */
import { useCallback } from "react";
import { lookupModules } from "../../api/module-lookup";
import type { ModuleLookupReport } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { LOOKUP_DEBOUNCE_MS, useLookup } from "../../shared/useLookup";

export function useModuleLookup(open: boolean, query: string) {
  const { value: language } = useProfileSelector((state) => state.language);
  const key = JSON.stringify([open, query, language]);
  const run = useCallback(
    (signal: AbortSignal) =>
      lookupModules({ query, display_language: language }, signal),
    [query, language],
  );
  return useLookup<ModuleLookupReport>(
    key,
    open && query.trim() !== "",
    run,
    LOOKUP_DEBOUNCE_MS,
  );
}
