/** App, docs and feedback composition under the provider and persistent store. */
import { lazy, Suspense, useLayoutEffect } from "react";
import { TopBar } from "./TopBar";
import { PhoneTabBar } from "./PhoneTabBar";
import { TabCarousel } from "./TabCarousel";
import { AppFooter } from "./AppFooter";
import { FeedbackPage } from "../features/feedback/FeedbackPage";
import { DOCS_REPOSITORY_URL } from "../features/docs/repository";
import { usePage } from "./usePage";
import { useCurrentProfileId } from "../state/useCurrentProfile";
import { NoticeProvider } from "../shared/NoticeProvider";
import { useWording } from "../shared/useWording";

const DocsShell = lazy(() =>
  import("../features/docs/DocsShell").then((module) => ({
    default: module.DocsShell,
  })),
);

/** Render the application shell, the documentation surface or the standalone feedback page. */
export function App() {
  const { page, entranceKey, navigate } = usePage();
  const currentProfileId = useCurrentProfileId();
  const { language } = useWording();
  // The English wiki keeps its own document language. Both app paths follow the profile language.
  useLayoutEffect(() => {
    document.documentElement.lang = page === "docs" ? "en" : language;
  }, [page, language]);
  if (page === "docs")
    return (
      <Suspense fallback={null}>
        <DocsShell returnToApp={() => navigate("app")} />
      </Suspense>
    );
  if (page === "feedback")
    return <FeedbackPage returnToApp={() => navigate("app")} />;
  return (
    <NoticeProvider key={currentProfileId}>
      <div key={entranceKey} className="app-shell">
        <TopBar
          openDocs={() => navigate("docs")}
          openFeedback={() => navigate("feedback")}
        />
        <TabCarousel key={currentProfileId} />
        <PhoneTabBar
          openDocs={() => navigate("docs")}
          openFeedback={() => navigate("feedback")}
        />
        <AppFooter repositoryUrl={DOCS_REPOSITORY_URL} />
      </div>
    </NoticeProvider>
  );
}
