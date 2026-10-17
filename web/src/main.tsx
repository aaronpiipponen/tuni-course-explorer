/**
 * Browser bootstrap: one store, one lifetime storage handler and a recovery screen for
 * saved data that cannot be read.
 */
import { createRoot } from "react-dom/client";
import { StoreContext } from "./state/context";
import {
  BROWSER_STORAGE_KEY,
  createBrowserStore,
  exportSavedBrowserData,
  resetBrowserStore,
  type BrowserStore,
} from "./state/store";
import { App } from "./app/App";
import { StorageRecovery } from "./features/profiles/StorageRecovery";
import { downloadBrowserFile } from "./features/profiles/files";
import "./styles/theme.css";
import "./app/shell.css";
import "./shared/course/course.css";
import "./shared/course/course-lookup.css";
import "./shared/button.css";
import "./shared/toggle-chip.css";
import "./shared/dialog.css";
import "./shared/help.css";
import "./features/compare/compare.css";
import "./shared/activity-switch.css";
import "./shared/disclosure.css";
import "./shared/picker-overlay.css";
import "./shared/course/tile.css";
import "./shared/course/list-row.css";
import "./features/search/search.css";
import "./features/docs/docs.css";
import "./features/prerequisites/prerequisites.css";
import "./features/prerequisites/graph/graph.css";
import "./features/prerequisites/route/route.css";
import "./features/structure/structure.css";
import "./features/discover/discover.css";
import "./features/profiles/profiles.css";

const root = createRoot(document.getElementById("root")!);
// The live store, or null while the recovery screen is shown.
let activeStore: BrowserStore | null = null;

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught));
}

function renderStore(store: BrowserStore): void {
  root.render(
    <StoreContext.Provider value={store}>
      <App />
    </StoreContext.Provider>,
  );
}

function showRecovery(error: Error): void {
  activeStore = null;
  root.render(
    <StorageRecovery
      error={error}
      onExport={() =>
        downloadBrowserFile(exportSavedBrowserData(window.localStorage))
      }
      onReset={() => {
        activeStore = resetBrowserStore(window.localStorage);
        renderStore(activeStore);
      }}
    />,
  );
}

function mountStore(): void {
  try {
    const store = createBrowserStore(window.localStorage);
    activeStore = store;
    renderStore(store);
  } catch (caught) {
    showRecovery(asError(caught));
  }
}

window.addEventListener("storage", (event) => {
  if (event.storageArea !== window.localStorage) return;
  if (event.key !== BROWSER_STORAGE_KEY && event.key !== null) return;
  if (!activeStore) {
    // Another tab's valid write is a chance to leave the recovery screen.
    mountStore();
    return;
  }
  try {
    activeStore.refreshFromStorage();
  } catch (caught) {
    showRecovery(asError(caught));
  }
});

mountStore();
