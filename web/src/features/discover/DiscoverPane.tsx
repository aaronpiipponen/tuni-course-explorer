/** Discover composition over the selected/completed browser sets and reports. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DiscoveryRequest } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { setDiscoverOptions } from "./actions";
import { DiscoverBasis } from "./DiscoverBasis";
import { DiscoverControls, DiscoverListTabs } from "./DiscoverControls";
import { DiscoverResults } from "./DiscoverResults";
import { useDiscovery } from "./useDiscovery";
import { useWording } from "../../shared/useWording";
import { useWebFeatures } from "../../app/useWebFeatures";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { PHONE_CONTENT_QUERY } from "../../shared/viewport";
import { PhoneSheet } from "../../shared/PhoneSheet";
import { SLIDERS_ICON } from "../../shared/icons";

/** Render discovery controls, basis and report results. */
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
    hasBasis,
  );
  const phone = useMediaQuery(PHONE_CONTENT_QUERY);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const optionsTrigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!phone) setOptionsOpen(false);
  }, [phone]);
  const closeOptions = useCallback(() => {
    setOptionsOpen(false);
    optionsTrigger.current?.focus();
  }, []);
  const controls = (
    <DiscoverControls
      options={effective}
      showTabs={!phone}
      onChange={(patch) => setDiscoverOptions(store, patch)}
    />
  );

  return (
    <main
      className="pane-content discover-pane"
      role="tabpanel"
      aria-label={t("Discover")}
    >
      <div className="discover-main">
        {phone && (
          <div className="discover-phone-head">
            <DiscoverListTabs
              options={effective}
              onChange={(patch) => setDiscoverOptions(store, patch)}
            />
            <button
              ref={optionsTrigger}
              className="phone-options-trigger discover-settings-trigger"
              type="button"
              aria-label={t("Discover options")}
              aria-expanded={optionsOpen}
              onClick={() => setOptionsOpen(true)}
            >
              {SLIDERS_ICON}
            </button>
          </div>
        )}
        {!phone && controls}
        <div className="discover-phone-body">
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
      </div>
      <PhoneSheet
        open={phone && optionsOpen}
        title={t("Discover options")}
        onClose={closeOptions}
      >
        {controls}
      </PhoneSheet>
    </main>
  );
}
