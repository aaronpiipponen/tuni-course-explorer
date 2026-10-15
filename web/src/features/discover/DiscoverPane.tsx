/** Discover composition over the selected/completed browser sets and reports. */
import { useMemo } from "react";
import type { DiscoveryRequest } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { setDiscoverOptions } from "./actions";
import { DiscoverBasis } from "./DiscoverBasis";
import { DiscoverControls } from "./DiscoverControls";
import { DiscoverResults } from "./DiscoverResults";
import { useDiscovery } from "./useDiscovery";
import { useWording } from "../../shared/useWording";

export function DiscoverPane() {
  const { store, value: options } = useProfileSelector(
    (state) => state.discover,
  );
  const { t } = useWording();
  const selected = useProfileSelector((state) => state.selectedCourseIds).value;
  const completed = useProfileSelector(
    (state) => state.completedCourseIds,
  ).value;
  const language = useProfileSelector((state) => state.language).value;
  const request = useMemo<DiscoveryRequest>(
    () => ({
      selected_courses: selected,
      completed_courses: completed,
      basis: options.basis,
      // Recommended always excludes next courses found with the strict All mode.
      mode: options.list === "recommended" ? "all" : options.mode,
      display_language: language,
      include_inferred: true,
      active_only: options.activeOnly,
    }),
    [
      selected,
      completed,
      options.basis,
      options.list,
      options.mode,
      options.activeOnly,
      language,
    ],
  );
  const chosenBasis = options.basis === "selected" ? selected : completed;
  const hasBasis = chosenBasis.length > 0;
  const { next, similarity, loading, error } = useDiscovery(
    options.list,
    request,
  );

  return (
    <main
      className="pane-content discover-pane"
      role="tabpanel"
      aria-label={t("Discover")}
    >
      <div className="discover-main">
        <DiscoverControls
          options={options}
          onChange={(patch) => setDiscoverOptions(store, patch)}
        />
        <DiscoverBasis
          basis={options.basis}
          courseIds={chosenBasis}
          expanded={options.basisExpanded}
          onExpandedChange={(basisExpanded) =>
            setDiscoverOptions(store, { basisExpanded })
          }
        />
        <DiscoverResults
          next={next}
          similarity={similarity}
          list={options.list}
          loading={loading}
          error={error}
          hasBasis={hasBasis}
        />
      </div>
    </main>
  );
}
