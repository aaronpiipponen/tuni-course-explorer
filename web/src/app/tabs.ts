/** Ordered shell tab identities and their wording-resource label keys. */
import type { UiTextKey } from "../shared/wording";
import type { TabId } from "../state/types";

export const TABS: readonly { id: TabId; labelKey: UiTextKey }[] = [
  { id: "search", labelKey: "Search" },
  { id: "compare", labelKey: "Compare" },
  { id: "prerequisites", labelKey: "Prerequisites" },
  { id: "discover", labelKey: "Discover" },
  { id: "structure", labelKey: "Structure of studies" },
];
