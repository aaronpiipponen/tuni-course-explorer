/** Search tab composition over profile-owned controls and transient real reports. */
import { useCallback, useState } from "react";
import { setSearchActiveOnly, setSearchQuery } from "./actions";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWebFeatures } from "../../app/useWebFeatures";
import { useAction } from "../../shared/useAction";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { HelpLink, HelpTip, type HelpSection } from "../../shared/HelpTip";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { PHONE_CONTENT_QUERY } from "../../shared/viewport";
import { useWording } from "../../shared/useWording";
import { showPhoneTabs } from "../../shared/phoneTabs";
import { searchMethodLabel } from "../../shared/wording";
import { SearchBar } from "./SearchBar";
import { SearchCount } from "./SearchCount";
import { SearchResults } from "./SearchResults";
import { useSearchSession } from "./SearchSession";

/** Render the Search tab over the profile's query, activity scope and transient report. */
export function SearchPane() {
  const { store, value: query } = useProfileSelector(
    (state) => state.search.query,
  );
  const { value: activeOnly } = useProfileSelector(
    (state) => state.search.activeOnly,
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const { embeddings_enabled } = useWebFeatures();
  const search = useSearchSession();
  const [tabPane, setTabPane] = useState<HTMLElement | null>(null);
  const [resultsScroller, setResultsScroller] = useState<HTMLElement | null>(
    null,
  );
  const paneRef = useCallback(
    (element: HTMLElement | null) =>
      setTabPane(element?.closest<HTMLElement>(".tab-pane") ?? null),
    [],
  );
  const resultsRef = useCallback(
    (element: HTMLDivElement | null) => setResultsScroller(element),
    [],
  );
  const phone = useMediaQuery(PHONE_CONTENT_QUERY);
  const scrollElement = phone ? resultsScroller : tabPane;
  const idle = !search.report && !search.loading && !search.error && !error;
  const activity = (
    <ActivitySwitch
      activeOnly={activeOnly}
      onChange={(activeOnly) =>
        runAction(() => setSearchActiveOnly(store, activeOnly))
      }
    />
  );
  const searchModes = [
    {
      term: searchMethodLabel("exact_code", language),
      tag: true,
      text: t(
        "Finds courses whose full code is a word in the query. Separate several codes with spaces or commas to find them together.",
      ),
    },
    {
      term: searchMethodLabel("substring", language),
      tag: true,
      text: t(
        "Finds the text inside a course name or code, ignoring case. A code fragment such as COMP.CS finds codes containing that fragment.",
      ),
    },
    {
      term: searchMethodLabel("fuzzy_name", language),
      tag: true,
      text: t(
        "Finds course names close to the query. A small typo or a different word order can still match.",
      ),
    },
    ...(embeddings_enabled
      ? [
          {
            term: (
              <HelpLink href="/docs#search/semantic">
                {searchMethodLabel("semantic", language)}
              </HelpLink>
            ),
            tag: true,
            text: t(
              "Matches the meaning of your query against course names, content and learning outcomes. A course can match without using the same words. Prerequisite text does not drive this match.",
            ),
          },
        ]
      : []),
  ];
  const help: readonly HelpSection[] = [
    {
      heading: t("options"),
      items: [
        {
          term: (
            <HelpLink href="/docs#guide-search/active-only">
              {t("Active only")}
            </HelpLink>
          ),
          text: t(
            "Shows only courses that are currently active. Turn it off to include inactive courses.",
          ),
        },
      ],
    },
    {
      heading: (
        <HelpLink href="/docs#guide-search/the-match-methods">
          {t("search methods")}
        </HelpLink>
      ),
      items: searchModes,
    },
    {
      heading: t("results"),
      items: [
        {
          term: (
            <HelpLink href="/docs#guide-search/reading-the-results">
              {t("Search results")}
            </HelpLink>
          ),
          text: t(
            "A course appears once with every method that matched it. Results are grouped by their first matching method. Run the search with Enter or the magnifier. Editing the text alone does not run it.",
          ),
        },
      ],
    },
  ];
  return (
    <div
      className={`pane-content search-pane${phone && idle ? " search-idle" : ""}`}
      role="tabpanel"
      aria-label={t("Search")}
      ref={paneRef}
    >
      <div className="search-row">
        <SearchBar
          query={query}
          loading={search.loading}
          phone={phone}
          activity={phone ? undefined : activity}
          onQueryChange={(query) =>
            runAction(() => setSearchQuery(store, query))
          }
          onSubmit={() => {
            showPhoneTabs();
            search.submit();
          }}
        />
        <div className="search-secondary">
          {phone && activity}
          <HelpTip sections={help} />
          {phone && search.report && (
            <span className="search-count">
              <SearchCount count={search.report.results.length} />
            </span>
          )}
        </div>
      </div>
      <div className="search-results-scroll" ref={resultsRef}>
        {error && <ErrorNotice error={error} language={language} />}
        {search.error && (
          <ErrorNotice error={search.error} language={language} />
        )}
        <SearchResults
          report={search.report}
          loading={search.loading}
          scrollElement={scrollElement}
          activeOnly={activeOnly}
        />
      </div>
    </div>
  );
}
