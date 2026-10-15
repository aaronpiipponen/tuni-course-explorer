/** Search tab composition over profile-owned controls and transient real reports. */
import { useCallback, useState } from "react";
import { setSearchActiveOnly, setSearchQuery } from "./actions";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useAction } from "../../shared/useAction";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { HelpTip, type HelpSection } from "../../shared/HelpTip";
import { useWording } from "../../shared/useWording";
import { searchMethodLabel } from "../../shared/wording";
import { SearchBar } from "./SearchBar";
import { SearchResults } from "./SearchResults";
import { useSearchSession } from "./SearchSession";

export function SearchPane() {
  const { store, value: query } = useProfileSelector(
    (state) => state.search.query,
  );
  const { value: activeOnly } = useProfileSelector(
    (state) => state.search.activeOnly,
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const search = useSearchSession();
  const [scrollElement, setScrollElement] = useState<HTMLElement | null>(null);
  const paneRef = useCallback(
    (element: HTMLElement | null) =>
      setScrollElement(element?.closest<HTMLElement>(".tab-pane") ?? null),
    [],
  );
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
      heading: t("search modes"),
      items: [
        {
          term: searchMethodLabel("exact_code", language),
          tag: true,
          text: t("The text matches a course code, for example COMP.CS.100."),
        },
        {
          term: searchMethodLabel("substring", language),
          tag: true,
          text: t(
            "The text appears inside a course name or code, ignoring upper and lower case. A code fragment such as: COMP.CS",
          ),
        },
        {
          term: searchMethodLabel("fuzzy_name", language),
          tag: true,
          text: t(
            "A course name that is close to the text, so a small typo still finds it.",
          ),
        },
        {
          term: searchMethodLabel("semantic", language),
          tag: true,
          text: t(
            "Courses whose content is about the topic you describe, even when they share no words with it.",
          ),
        },
      ],
    },
  ];
  return (
    <div
      className="pane-content search-pane"
      role="tabpanel"
      aria-label={t("Search")}
      ref={paneRef}
    >
      <div className="search-row">
        <SearchBar
          query={query}
          activeOnly={activeOnly}
          loading={search.loading}
          onQueryChange={(query) =>
            runAction(() => setSearchQuery(store, query))
          }
          onActiveOnlyChange={(activeOnly) =>
            runAction(() => setSearchActiveOnly(store, activeOnly))
          }
          onSubmit={search.submit}
        />
        <HelpTip sections={help} />
      </div>
      {error && <ErrorNotice error={error} language={language} />}
      {search.error && <ErrorNotice error={search.error} language={language} />}
      <SearchResults
        report={search.report}
        loading={search.loading}
        scrollElement={scrollElement}
      />
    </div>
  );
}
