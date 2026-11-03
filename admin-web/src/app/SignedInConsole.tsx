/**
 * The signed-in console: the header, the six mounted tab trees and their two shared reads.
 *
 * The shell owns one server-status read and one dataset inventory read for the whole signed-in
 * session. The dashboard renders the server status, the Settings dataset panel renders the
 * inventory, and the inventory's Working presence controls the four stage action rows. The reported
 * selection state gates the inference summary alone. An unknown state waits for a successful read,
 * a disabled state states the site's own reason without a failure, and a failed refresh keeps the
 * last report and gates from it. The header carries branding, tab navigation, GitHub, Docs, App and
 * sign-out controls. The open tab is stored in this browser tab's session storage, so a reload
 * restores it, while every inactive tab tree is mounted and hidden.
 */
import { useState } from "react";
import { readDashboard } from "../api/dashboard";
import { readDatasets } from "../api/datasets";
import type {
  DatasetListReport,
  ServerStatusReport,
  SessionReport,
} from "../api/types";
import { Dashboard } from "../features/dashboard/Dashboard";
import { Feedback } from "../features/feedback/Feedback";
import { Inference } from "../features/inference/Inference";
import { Logs } from "../features/logs/Logs";
import { DataPreparation } from "../features/preparation/DataPreparation";
import { Settings } from "../features/settings/Settings";
import { FailureNotice } from "../shared/Panel";
import { GITHUB_MARK } from "../shared/icons";
import type { SessionAccess } from "../shared/StagePanel";
import { usePanelRead } from "../shared/usePanelRead";
import { wording } from "../shared/wording";
import { BrandMark } from "./BrandMark";
import { isTabId, TabBar, type TabId } from "./TabBar";

const dashboardRead = (signal: AbortSignal, automatic: boolean) =>
  readDashboard(signal, automatic);

const datasetsRead = (signal: AbortSignal, automatic: boolean) =>
  readDatasets(signal, automatic);

/** The session-storage key of the open tab. */
const TAB_STORAGE_KEY = "course-explorer-admin-tab";

/** Return the tab stored for this browser tab, or the Dashboard when none is stored. */
function storedTab(): TabId {
  const stored = window.sessionStorage.getItem(TAB_STORAGE_KEY);
  return isTabId(stored) ? stored : "dashboard";
}

/** Render the authenticated console for one granted session. */
export function SignedInConsole({
  session,
  onRefusal,
  onSignOut,
  onAdminRebuild,
  failure,
}: {
  session: SessionReport;
  onRefusal: (status: number) => void;
  onSignOut: () => Promise<void>;
  onAdminRebuild: () => void;
  failure: string | null;
}) {
  const [tab, setTab] = useState<TabId>(storedTab);
  const access: SessionAccess = {
    csrfToken: session.csrf_token,
    pollSeconds: session.poll_seconds,
  };
  const selectTab = (next: TabId): void => {
    setTab(next);
    window.sessionStorage.setItem(TAB_STORAGE_KEY, next);
  };
  const docsUrl = new URL("/docs#home", session.app_url).href;
  const dashboard = usePanelRead<ServerStatusReport>(dashboardRead, {
    pollSeconds: session.poll_seconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const datasets = usePanelRead<DatasetListReport>(datasetsRead, {
    pollSeconds: session.poll_seconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const selectionEnabled =
    dashboard.report === null
      ? null
      : (dashboard.report.serving.selection_enabled ?? "unavailable");
  const workingPresent =
    datasets.report === null || datasets.report.mode === "unavailable"
      ? null
      : datasets.report.datasets.some((entry) => entry.working);
  return (
    <div>
      <header>
        <div className="logo">
          <BrandMark />
        </div>
        <span className="docl">{wording.admin}</span>
        <TabBar current={tab} onSelect={selectTab} />
        <div className="right">
          <a
            className="btn github"
            href={session.repository_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {GITHUB_MARK}
            {wording.github}
          </a>
          <a className="btn p" href={docsUrl}>
            {wording.docs}
          </a>
          <a className="btn p" href={session.app_url}>
            {wording.app}
          </a>
          <button
            className="btn"
            type="button"
            onClick={() => void onSignOut()}
          >
            {wording.signOut}
          </button>
        </div>
      </header>
      <div className="wrap">
        <FailureNotice text={failure} />
        <div className="tab-pane" hidden={tab !== "dashboard"}>
          <Dashboard panel={dashboard} />
        </div>
        <div className="tab-pane" hidden={tab !== "preparation"}>
          <DataPreparation
            session={access}
            onRefusal={onRefusal}
            workingPresent={workingPresent}
          />
        </div>
        <div className="tab-pane" hidden={tab !== "inference"}>
          <Inference
            session={access}
            onRefusal={onRefusal}
            selectionEnabled={selectionEnabled}
            selectionFailure={dashboard.failure}
            workingPresent={workingPresent}
          />
        </div>
        <div className="tab-pane" hidden={tab !== "logs"}>
          <Logs session={access} onRefusal={onRefusal} />
        </div>
        <div className="tab-pane" hidden={tab !== "settings"}>
          <Settings
            session={access}
            onRefusal={onRefusal}
            onAdminRebuild={onAdminRebuild}
            dashboard={dashboard}
            datasets={datasets}
          />
        </div>
        <div className="tab-pane" hidden={tab !== "feedback"}>
          <Feedback session={access} onRefusal={onRefusal} />
        </div>
      </div>
    </div>
  );
}
