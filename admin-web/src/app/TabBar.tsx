/**
 * The console's tab bar.
 *
 * Every tab selects its own panel, and the current tab is marked for assistive technology.
 */
import { wording } from "../shared/wording";

/** The five tabs the console implements. */
export type TabId =
  "dashboard" | "preparation" | "inference" | "logs" | "settings";

const TABS: { id: TabId; label: string }[] = [
  { id: "dashboard", label: wording.tabs.dashboard },
  { id: "preparation", label: wording.tabs.preparation },
  { id: "inference", label: wording.tabs.inference },
  { id: "logs", label: wording.tabs.logs },
  { id: "settings", label: wording.tabs.settings },
];

/** Report whether one stored value names a tab the console implements. */
export function isTabId(value: string | null): value is TabId {
  return TABS.some((tab) => tab.id === value);
}

/** Render the tab bar for the current tab. */
export function TabBar({
  current,
  onSelect,
}: {
  current: TabId;
  onSelect: (tab: TabId) => void;
}) {
  return (
    <nav className="tabs" aria-label={wording.admin}>
      {TABS.map((tab) => (
        <button
          key={tab.id}
          className={`tab${tab.id === current ? " on" : ""}`}
          type="button"
          aria-current={tab.id === current ? "page" : undefined}
          onClick={() => onSelect(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
