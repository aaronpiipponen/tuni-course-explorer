/** Persistent application chrome: brand, cyclic-tab entry points, docs and profile language. */
import { TABS } from "./tabs";
import { useProfileSelector } from "../state/useProfileSelector";
import { ProfileButton } from "../features/profiles/ProfileButton";
import { LanguageSwitch } from "../shared/LanguageSwitch";
import { setActiveTab } from "./actions";
import { useAction } from "../shared/useAction";
import { ErrorNotice } from "../shared/ErrorNotice";
import { useWording } from "../shared/useWording";

export function TopBar({ openDocs }: { openDocs: () => void }) {
  const { store, value: activeTab } = useProfileSelector(
    (state) => state.activeTab,
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-text">tuni</span>
        <span>/</span>
        <span className="brand-text">course-explorer</span>
      </div>
      <nav aria-label={t("Main navigation")}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "nav-tab active" : "nav-tab"}
            onClick={() => runAction(() => setActiveTab(store, tab.id))}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </nav>
      <div className="topbar-actions">
        <a
          className="docs-link"
          href="/docs"
          onClick={(event) => {
            event.preventDefault();
            openDocs();
          }}
        >
          {t("Docs")}
        </a>
        <ProfileButton />
        <LanguageSwitch />
      </div>
      {error && <ErrorNotice error={error} language={language} />}
    </header>
  );
}
