/** Search tab composition over profile-owned controls and transient real reports. */
import { useCallback, useState } from "react";
import { setSearchActiveOnly, setSearchQuery } from "./actions";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWebFeatures } from "../../app/useWebFeatures";
import { useAction } from "../../shared/useAction";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { HelpTip, type HelpSection } from "../../shared/HelpTip";
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
      text: t("The text matches a course code, for example COMP.CS.100."),
    },
    {
      term: searchMethodLabel("substring", language),
      tag: true,
      text: t(
        "The text appears inside a course name or code, ignoring case, for example the code fragment COMP.CS.",
      ),
    },
    {
      term: searchMethodLabel("fuzzy_name", language),
      tag: true,
      text: t(
        "A course name that is close to the text, so a small typo still matches it.",
      ),
    },
    ...(embeddings_enabled
      ? [
          {
            term: searchMethodLabel("semantic", language),
            tag: true,
            text: t(
              "Courses whose content is about the topic you describe, even when they share no words with it.",
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
          term: t("Active only"),
          text: t(
            "Shows only courses that are currently active. Turn it off to include inactive courses.",
          ),
        },
      ],
    },
    {
      heading: t("search methods"),
      items: searchModes,
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
          <HelpTip
            sections={help}
            guide={{
              href: "/docs#guide-search",
              label: t("Searching for courses"),
            }}
          />
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
        />
      </div>
    </div>
  );
}
