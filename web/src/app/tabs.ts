/** Ordered shell tab identities, their wording-resource label keys and the visible-tab policy. */
import type { UiTextKey } from "../shared/wording";
import type { TabId } from "../state/types";

/** The five tabs in canonical navigation order. */
export const TABS: readonly {
  id: TabId;
  labelKey: UiTextKey;
  phoneLabelKey: UiTextKey;
}[] = [
  { id: "search", labelKey: "Search", phoneLabelKey: "Search" },
  { id: "compare", labelKey: "Compare", phoneLabelKey: "Compare" },
  {
    id: "prerequisites",
    labelKey: "Prerequisites",
    phoneLabelKey: "Prereqs",
  },
  { id: "discover", labelKey: "Discover", phoneLabelKey: "Discover (phone)" },
  {
    id: "structure",
    labelKey: "Structure of studies",
    phoneLabelKey: "Structure",
  },
];

const WITHOUT_COMPARE = TABS.filter((tab) => tab.id !== "compare");

/** Return the tabs a site serves, in canonical order, without Compare where embeddings are off. */
export function visibleTabs(embeddingsEnabled: boolean): typeof TABS {
  return embeddingsEnabled ? TABS : WITHOUT_COMPARE;
}

/** Return the served tab for one stored identity, resolving a hidden Compare to Search. */
export function effectiveTab(tab: TabId, embeddingsEnabled: boolean): TabId {
  return !embeddingsEnabled && tab === "compare" ? "search" : tab;
}
