/** Browser bootstrap: create exactly one storage store and show startup failures without resetting. */
import { createRoot } from "react-dom/client";
import { StoreContext } from "./state/context";
import { createBrowserStore } from "./state/store";
import { App } from "./app/App";
import { ErrorNotice } from "./shared/ErrorNotice";
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
try {
  const store = createBrowserStore(window.localStorage);
  root.render(
    <StoreContext.Provider value={store}>
      <App />
    </StoreContext.Provider>,
  );
} catch (caught) {
  root.render(
    <ErrorNotice
      error={caught instanceof Error ? caught : new Error(String(caught))}
    />,
  );
}
