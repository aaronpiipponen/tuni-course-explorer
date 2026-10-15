/** Backend-ordered search result framing and memoized contiguous tier presentation. */
import { memo, useMemo, useRef } from "react";
import type {
  SearchMethod,
  UnifiedCourseSearchResult,
  UnifiedSearchReport,
} from "../../api/types";
import { useWording } from "../../shared/useWording";
import { searchMethodLabel } from "../../shared/wording";
import { SearchTierList, type SearchTierListHandle } from "./SearchTierList";

type Tier = { method: SearchMethod; results: UnifiedCourseSearchResult[] };

function SearchResultsView({
  report,
  loading,
  scrollElement,
}: {
  report: UnifiedSearchReport | null;
  loading: boolean;
  scrollElement: HTMLElement | null;
}) {
  const { language, t } = useWording();
  const handles = useRef(new Map<number, SearchTierListHandle>());
  const activeReport = useRef<UnifiedSearchReport | null>(null);
  const animation = useRef(0);
  if (report && report !== activeReport.current) {
    if (activeReport.current) animation.current += 1;
    activeReport.current = report;
  }
  const groups = useMemo(() => {
    if (!report) return [];
    const tiers: Tier[] = [];
    for (const result of report.results) {
      const method = result.match_sources[0];
      const previous = tiers.at(-1);
      if (previous?.method === method) previous.results.push(result);
      else tiers.push({ method, results: [result] });
    }
    return tiers;
  }, [report]);

  if (loading)
    return (
      <section
        className="search-results results"
        aria-label={t("Search results")}
        aria-busy="true"
      >
        <div className="list search-list" aria-hidden="true">
          {Array.from({ length: 5 }, (_, index) => (
            <div className="search-skeleton dskel" key={index} />
          ))}
        </div>
      </section>
    );
  if (!report) return null;
  return (
    <section
      className="search-results results"
      aria-label={t("Search results")}
      aria-busy={loading}
    >
      <div className="head">
        <div className="eyebrow">
          // <b>{report.results.length}</b> {t("courses")}
        </div>
      </div>
      {report.results.length === 0 ? (
        <div className="empty2 search-empty" key={animation.current}>
          {t("No courses match this search.")}
        </div>
      ) : (
        groups.map((group, index) => (
          <section
            className="search-tier-group"
            key={`${group.method}-${index}-${animation.current}`}
          >
            <div className="tier eyebrow">
              // {searchMethodLabel(group.method, language)}
            </div>
            <SearchTierList
              ref={(handle) => {
                if (handle) handles.current.set(index, handle);
                else handles.current.delete(index);
              }}
              method={group.method}
              results={group.results}
              scrollElement={scrollElement}
              onBoundaryFocus={(direction) => {
                const adjacent = handles.current.get(index + direction);
                if (!adjacent) return false;
                adjacent.focusCourse(
                  direction > 0 ? 0 : adjacent.count - 1,
                  direction < 0,
                );
                return true;
              }}
            />
          </section>
        ))
      )}
    </section>
  );
}

export const SearchResults = memo(SearchResultsView);
