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
import { useWebFeatures } from "../../app/useWebFeatures";

export function DiscoverPane() {
  const { store, value: options } = useProfileSelector(
    (state) => state.discover,
  );
  const { t } = useWording();
  const { embeddings_enabled, inference_enabled } = useWebFeatures();
  const selected = useProfileSelector((state) => state.selectedCourseIds).value;
  const completed = useProfileSelector(
    (state) => state.completedCourseIds,
  ).value;
  const language = useProfileSelector((state) => state.language).value;
  // A site without embedding features serves the next-course list, so Recommended never runs.
  const effective = useMemo(
    () =>
      embeddings_enabled ? options : { ...options, list: "next" as const },
    [options, embeddings_enabled],
  );
  const request = useMemo<DiscoveryRequest>(
    () => ({
      selected_courses: selected,
      completed_courses: completed,
      basis: effective.basis,
      // Recommended always excludes next courses found with the strict All mode.
      mode: effective.list === "recommended" ? "all" : effective.mode,
      display_language: language,
      include_inferred: inference_enabled,
      active_only: effective.activeOnly,
    }),
    [selected, completed, effective, language, inference_enabled],
  );
  const chosenBasis = effective.basis === "selected" ? selected : completed;
  const hasBasis = chosenBasis.length > 0;
  const { next, similarity, loading, error } = useDiscovery(
    effective.list,
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
          options={effective}
          onChange={(patch) => setDiscoverOptions(store, patch)}
        />
        <DiscoverBasis
          basis={effective.basis}
          courseIds={chosenBasis}
          expanded={effective.basisExpanded}
          onExpandedChange={(basisExpanded) =>
            setDiscoverOptions(store, { basisExpanded })
          }
        />
        <DiscoverResults
          next={next}
          similarity={similarity}
          list={effective.list}
          loading={loading}
          error={error}
          hasBasis={hasBasis}
        />
      </div>
    </main>
  );
}
