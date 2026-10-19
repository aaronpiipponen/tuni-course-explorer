/**
 * The Inference tab: the separate inference run, its retained-server reports and its explicit
 * operator actions.
 *
 * The tab owns one automatic summary read for the four retained-server panels, the run, the target
 * decisions and the dataset cleanup each own their own read. The summary and the dataset listing
 * read only while the site reports its selection enabled, so a disabled site states that reason
 * without a refused read, while the run, the target decisions and their ordinary commands keep
 * their own behavior. Nothing here starts a stage on another stage's behalf, and no panel chains
 * several commands.
 */
import { useCallback } from "react";
import { readInferenceSummary } from "../../api/inference";
import type { InferenceAdministrativeSummary } from "../../api/types";
import { FailureNotice } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { DatasetCleanup } from "./DatasetCleanup";
import { Failures } from "./Failures";
import { GenerationIdentities } from "./GenerationIdentities";
import { InferenceCoverage } from "./InferenceCoverage";
import { InferenceRun } from "./InferenceRun";
import { PublicationDiagnostics } from "./PublicationDiagnostics";
import { TargetDecisions } from "./TargetDecisions";

/** The shared state of the one retained-server summary read. */
export interface SummaryView {
  summary: InferenceAdministrativeSummary | null;
  lastSuccess: number | null;
  loading: boolean;
  selectionEnabled: boolean | null;
  selectionFailure: string | null;
}

const summaryRead = (signal: AbortSignal, automatic: boolean) =>
  readInferenceSummary(signal, automatic);

/** Render the Inference tab. */
export function Inference({
  session,
  onRefusal,
  selectionEnabled,
  selectionFailure,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  selectionEnabled: boolean | null;
  selectionFailure: string | null;
}) {
  const summary = usePanelRead(summaryRead, {
    pollSeconds: session.pollSeconds,
    enabled: selectionEnabled === true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const refreshSummary = useCallback(() => summary.reload(), [summary]);
  const view: SummaryView = {
    summary: summary.report,
    lastSuccess: summary.lastSuccess,
    loading: summary.loading,
    selectionEnabled,
    selectionFailure,
  };
  return (
    <div>
      <FailureNotice
        text={selectionEnabled === true ? summary.failure : selectionFailure}
      />
      <div className="grid">
        <InferenceRun session={session} onRefusal={onRefusal} />
        <PublicationDiagnostics view={view} />
        <InferenceCoverage view={view} />
        <GenerationIdentities view={view} />
        <TargetDecisions
          session={session}
          onRefusal={onRefusal}
          onDecisionRecorded={refreshSummary}
        />
        <DatasetCleanup
          session={session}
          onRefusal={onRefusal}
          selectionEnabled={selectionEnabled}
          selectionFailure={selectionFailure}
        />
        <Failures view={view} />
      </div>
    </div>
  );
}
