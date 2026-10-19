/** Ordered shell tab identities, their wording-resource label keys and the visible-tab policy. */
import type { UiTextKey } from "../shared/wording";
import type { TabId } from "../state/types";

export const TABS: readonly { id: TabId; labelKey: UiTextKey }[] = [
  { id: "search", labelKey: "Search" },
  { id: "compare", labelKey: "Compare" },
  { id: "prerequisites", labelKey: "Prerequisites" },
  { id: "discover", labelKey: "Discover" },
  { id: "structure", labelKey: "Structure of studies" },
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
