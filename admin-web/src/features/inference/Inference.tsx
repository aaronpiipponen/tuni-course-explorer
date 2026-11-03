/**
 * The Inference tab: the separate inference run, its retained-server reports and its explicit
 * operator actions.
 *
 * The tab owns one automatic summary read for the four retained-server panels, while the run and
 * the target decisions each own their own read and actions. The summary reads only while the site
 * reports its selection enabled, so a disabled site and a site whose dataset state is unavailable
 * state that reason without a refused read, while the run, the target decisions and their ordinary
 * commands keep their own behavior. The summary read resolves Working first and names the role it
 * read. Nothing here starts a stage on another stage's behalf, and no panel chains several commands.
 * The dataset roles, copies and cleanup sit in the Settings dataset panel.
 */
import { readInferenceSummary } from "../../api/inference";
import { FailureNotice } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { WorkingDatasetNotice } from "../../shared/WorkingDatasetNotice";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { Failures } from "./Failures";
import { GenerationIdentities } from "./GenerationIdentities";
import { InferenceCoverage } from "./InferenceCoverage";
import { InferenceRun } from "./InferenceRun";
import { PublicationDiagnostics } from "./PublicationDiagnostics";
import type { SummaryView } from "./summaryView";
import { TargetDecisions } from "./TargetDecisions";

const summaryRead = (signal: AbortSignal, automatic: boolean) =>
  readInferenceSummary(signal, automatic);

/** Render the Inference tab. */
export function Inference({
  session,
  onRefusal,
  selectionEnabled,
  selectionFailure,
  workingPresent,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  selectionEnabled: boolean | "unavailable" | null;
  selectionFailure: string | null;
  workingPresent: boolean | null;
}) {
  const summary = usePanelRead(summaryRead, {
    pollSeconds: session.pollSeconds,
    enabled: selectionEnabled === true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const refreshSummary = summary.reload;
  const scope = summary.report;
  const view: SummaryView = {
    scope,
    summary: scope?.report ?? null,
    lastSuccess: summary.lastSuccess,
    loading: summary.loading,
    selectionEnabled,
    selectionFailure,
  };
  return (
    <div>
      <WorkingDatasetNotice absent={workingPresent === false} />
      <FailureNotice
        text={selectionEnabled === true ? summary.failure : selectionFailure}
      />
      <div className="grid">
        <InferenceRun
          session={session}
          onRefusal={onRefusal}
          workingPresent={workingPresent}
        />
        <PublicationDiagnostics view={view} />
        <InferenceCoverage view={view} />
        <GenerationIdentities view={view} />
        <TargetDecisions
          session={session}
          onRefusal={onRefusal}
          onDecisionRecorded={refreshSummary}
        />
        <Failures view={view} />
      </div>
    </div>
  );
}
