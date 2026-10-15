/** Independent-project notice pinned to the bottom of the application shell. */
import { useWording } from "../shared/useWording";

export function AppFooter() {
  const { t } = useWording();
  return (
    <footer className="app-footer">
      {t(
        "This is an independent project that is not affiliated with Tampere University.",
      )}
    </footer>
  );
}
