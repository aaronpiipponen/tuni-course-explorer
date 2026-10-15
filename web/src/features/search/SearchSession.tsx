/** Holds the submitted search and its report while other tabs are shown. */
import { createContext, useContext, type ReactNode } from "react";
import { useSearch } from "./useSearch";

const SearchSessionContext = createContext<ReturnType<typeof useSearch> | null>(
  null,
);

export function SearchSessionProvider({ children }: { children: ReactNode }) {
  const search = useSearch();
  return (
    <SearchSessionContext.Provider value={search}>
      {children}
    </SearchSessionContext.Provider>
  );
}

export function useSearchSession() {
  const search = useContext(SearchSessionContext);
  if (!search) throw new Error("Search session provider is missing");
  return search;
}
