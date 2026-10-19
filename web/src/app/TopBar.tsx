/** Persistent application chrome: brand, cyclic-tab entry points, docs and profile language. */
import { visibleTabs, effectiveTab } from "./tabs";
import { ProfileButton } from "../features/profiles/ProfileButton";
import { LanguageSwitch } from "../shared/LanguageSwitch";
import { setActiveTab, useActiveTab } from "./sessionTab";
import { useAction } from "../shared/useAction";
import { ErrorNotice } from "../shared/ErrorNotice";
import { useWording } from "../shared/useWording";
import { useWebFeatures } from "./useWebFeatures";

export function TopBar({ openDocs }: { openDocs: () => void }) {
  const storedTab = useActiveTab();
  const { embeddings_enabled } = useWebFeatures();
  const activeTab = effectiveTab(storedTab, embeddings_enabled);
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
        {visibleTabs(embeddings_enabled).map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "nav-tab active" : "nav-tab"}
            onClick={() => runAction(() => setActiveTab(tab.id))}
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
