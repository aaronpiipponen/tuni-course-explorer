/** App and docs composition with the provider and persistent store mounted across navigation. */
import { useLayoutEffect } from "react";
import { TopBar } from "./TopBar";
import { PhoneTabBar } from "./PhoneTabBar";
import { TabCarousel } from "./TabCarousel";
import { AppFooter } from "./AppFooter";
import { DocsShell } from "../features/docs/DocsShell";
import { DOCS_REPOSITORY_URL } from "../features/docs/registry";
import { usePage } from "./usePage";
import { useCurrentProfileId } from "../state/useCurrentProfile";
import { NoticeProvider } from "../shared/NoticeProvider";
import { useWording } from "../shared/useWording";

/** Render the application shell or the documentation surface. */
export function App() {
  const { page, entranceKey, navigate } = usePage();
  const currentProfileId = useCurrentProfileId();
  const { language } = useWording();
  // The English wiki and the app shell each own their document language.
  useLayoutEffect(() => {
    document.documentElement.lang = page === "docs" ? "en" : language;
  }, [page, language]);
  if (page === "docs") return <DocsShell returnToApp={() => navigate("app")} />;
  return (
    <NoticeProvider key={currentProfileId}>
      <div key={entranceKey} className="app-shell">
        <TopBar openDocs={() => navigate("docs")} />
        <TabCarousel key={currentProfileId} />
        <PhoneTabBar openDocs={() => navigate("docs")} />
        <AppFooter repositoryUrl={DOCS_REPOSITORY_URL} />
      </div>
    </NoticeProvider>
  );
}
