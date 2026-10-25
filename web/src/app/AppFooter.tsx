/** Independent-project notice and repository link pinned to the bottom of the application shell. */
import { useWording } from "../shared/useWording";

/** Render the application notice and repository link. */
export function AppFooter({ repositoryUrl }: { repositoryUrl: string }) {
  const { t } = useWording();
  return (
    <footer className="app-footer">
      <span className="app-footer-notice">
        {t(
          "This is an independent project that is not affiliated with Tampere University.",
        )}
      </span>{" "}
      <a href={repositoryUrl} target="_blank" rel="noopener noreferrer">
        {t("Source code on GitHub.")}
      </a>
    </footer>
  );
}
