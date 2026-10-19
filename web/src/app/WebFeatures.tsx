/** Bootstrap provider of the site's served feature switches for the mounted app shell. */
import { useEffect, useState, type ReactNode } from "react";
import { readWebFeatures } from "../api/features";
import type { WebFeatures as WebFeaturesReport } from "../api/types";
import { ErrorNotice } from "../shared/ErrorNotice";
import { useWording } from "../shared/useWording";
import { WebFeaturesContext } from "./webFeaturesContext";

type Loaded =
  | { status: "pending" }
  | { status: "failed"; error: Error }
  | { status: "ready"; features: WebFeaturesReport };

export function WebFeatures({ children }: { children: ReactNode }) {
  const { language, t } = useWording();
  const [loaded, setLoaded] = useState<Loaded>({ status: "pending" });
  useEffect(() => {
    const controller = new AbortController();
    readWebFeatures(controller.signal).then(
      (features) => {
        if (!controller.signal.aborted)
          setLoaded({ status: "ready", features });
      },
      (caught: unknown) => {
        if (!controller.signal.aborted)
          setLoaded({
            status: "failed",
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
      },
    );
    return () => controller.abort();
  }, []);
  if (loaded.status === "pending")
    return (
      <p className="features-loading" role="status">
        {t("Loading site features")}
      </p>
    );
  if (loaded.status === "failed")
    return <ErrorNotice error={loaded.error} language={language} />;
  return (
    <WebFeaturesContext.Provider value={loaded.features}>
      {children}
    </WebFeaturesContext.Provider>
  );
}
